/* ============================================================================
 * Машина Кузьміна (Kuzmin Machine) — Гетерогенний симбіоз з GPU (ADR B6)
 * Файл: heterogeneous_subscribers.cu
 * Issue: #256 (EXP-GPU-03: предикатна диспетчеризація гетерогенних підписників
 *        у варпі GPU, спеціалізація варпів, профіль MAXN та ізоляція CPU/TSG)
 * Цільова платформа: Seeed Studio reServer Industrial J501 (Jetson AGX Orin 64GB)
 * Архітектура GPU: NVIDIA Ampere (GA10B, SM 8.7)
 *
 * Ключові архітектурні інваріанти:
 *   1. Per-SM partitioned 128-Б слоти входу ingress[blockIdx.x] + ізольовані
 *      128-Б лінії підтвердження isolated_ack[blockIdx.x] + предикатний запис
 *      outputs[global_id] лише для активних підписників.
 *   2. Чотири змістовно різні stateful-оператори у регістрах SM:
 *      - OP_0_PID_Q8:      дискретний ПІД 2-го порядку (Q8) з anti-windup [-32768, 32767];
 *      - OP_1_BIQUAD_Q12:  каскадний БІХ-фільтр 2-го порядку (DF2T Biquad у Q12, z1/z2);
 *      - OP_2_HYST_WINDOW: двопороговий тригер Шмітта з мертвою зоною та dwell_count;
 *      - OP_3_EWMA_SLEW:   експоненційне згладжування EWMA (Q8) зі slew-rate limiter
 *                          max_delta та детектором стрибка похідної.
 *   3. Три режими розміщення операторів по нитках (--layout):
 *      - homo_pid:     усі 1024 нитки виконують OP_0_PID_Q8;
 *      - mixed_warp:   усередині кожного варпа op_type = lane_id & 3 (4 гілки у варпі);
 *      - grouped_warp: warp-level operator specialization op_type = warp_global & 3.
 *   4. Подвійна апаратна метрологія (clock64 + sysfs cur_freq та %globaltimer)
 *      разом із декомпозицією Host RT = T_host_pub + T_wait_ack і прапорцем --rt-pin
 *      (закріплення нитки публікації на CPU 11 + спроба SCHED_FIFO пріоритету 80).
 *   5. Незалежна побітова перевірка станів s0..s3, out_val, trigger_count та outputs[]
 *      проти еталонної CPU-моделі (mismatch_count == 0).
 * ============================================================================ */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include <cuda_runtime.h>
#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <sched.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define KM_WARP_SIZE          32u
#define KM_MAX_WARPS_PER_BLK  16u
#define KM_MAX_SUBSCRIBERS    1024u
#define KM_MAX_BLOCKS         16u
#define KM_SLOT_MASK_WORDS    16u
#define KM_MASK_WORDS         (KM_MAX_SUBSCRIBERS / 32u)
#define KM_TELEMETRY_CAP      10000u
#define KM_BOOTSTRAP_ITERS    1000u
#define KM_BOOTSTRAP_SEED     0x5EED25601234ULL
#define KM_NUM_OP_TYPES       4u

#define KM_PID_INT_MIN       (-32768)
#define KM_PID_INT_MAX        32767

typedef enum {
    OP_0_PID_Q8      = 0u,
    OP_1_BIQUAD_Q12  = 1u,
    OP_2_HYST_WINDOW = 2u,
    OP_3_EWMA_SLEW   = 3u
} km_op_type_t;

typedef enum {
    KM_LAYOUT_HOMO_PID     = 0u,
    KM_LAYOUT_MIXED_WARP   = 1u,
    KM_LAYOUT_GROUPED_WARP = 2u
} km_layout_mode_t;

typedef enum {
    KM_INGRESS_PARTITIONED  = 0u,
    KM_INGRESS_SHARED_1LINE = 1u
} km_ingress_mode_t;

/* --- Вхідна когерентна скринька подій: рівно одна 128-байтна лінія L2 на слот SM --- */
typedef struct __align__(128) {
    uint32_t seq_id;                         /* [0..3]    Лічильник події (release/acquire) */
    uint32_t stop_flag;                      /* [4..7]    1 = штатне завершення кернела */
    int32_t  concept_val;                    /* [8..11]   Стан концепту після коміту */
    uint32_t active_words;                   /* [12..15]  Кількість слів маски у слоті */
    uint32_t event_mask[KM_SLOT_MASK_WORDS]; /* [16..79]  512-бітний вектор підписок слота */
    uint32_t reserved[12];                   /* [80..127] Вирівнювання рівно до 128 Б */
} km_event_ingress_t;

static_assert(sizeof(km_event_ingress_t) == 128, "km_event_ingress_t must fit in one 128B L2 cache line");

/* --- Окрема 128-байтна кеш-лінія для підтвердження одного блока SM --- */
typedef struct __align__(128) {
    uint32_t ack;
    uint32_t pad[31];
} km_ack_line_t;

static_assert(sizeof(km_ack_line_t) == 128, "km_ack_line_t must fit in one 128B L2 cache line");

/* --- Вихідний буфер підписників: окремі 128-байтні лінії кешу L2 --- */
typedef struct __align__(128) {
    uint32_t      packed_ack[KM_MAX_BLOCKS];   /* [0..63]     Суміжний масив ack */
    uint32_t      pad_packed[16];              /* [64..127]   Ізоляція від isolated_ack */
    km_ack_line_t isolated_ack[KM_MAX_BLOCKS]; /* [128..2175] Окрема 128-Б лінія на кожен блок */
    int32_t       outputs[KM_MAX_SUBSCRIBERS]; /* [2176..]    Виходи підписників (предикатний запис) */
} km_event_egress_t;

static_assert(offsetof(km_event_egress_t, isolated_ack) == 128, "isolated_ack must start on a separate 128B cache line");
static_assert(offsetof(km_event_egress_t, outputs) == 128 + KM_MAX_BLOCKS * 128, "outputs must start on a separate 128B cache line");

/* --- Дескриптор параметрів і стану гетерогенного підписника --- */
typedef struct {
    uint32_t op_type;       /* 0..3: тип оператора підписника */
    uint32_t inst_id;       /* 0..255: індекс екземпляра у межах класу оператора */
    int32_t  p0;            /* Параметр 0 (target / b0_q12 / center / alpha_q8) */
    int32_t  p1;            /* Параметр 1 (kp_q8  / b1_q12 / deadband / max_delta) */
    int32_t  p2;            /* Параметр 2 (ki_q8  / b2_q12 / th_hi / jump_thresh) */
    int32_t  p3;            /* Параметр 3 (kd_q8  / a1_q12 / th_lo / jump_gain) */
    int32_t  p4;            /* Параметр 4 (sat_hi / a2_q12 / min_dwell / 0) */
    int32_t  s0;            /* Внутрішній стан 0 у регістрі SM */
    int32_t  s1;            /* Внутрішній стан 1 у регістрі SM */
    int32_t  s2;            /* Внутрішній стан 2 у регістрі SM */
    int32_t  s3;            /* Внутрішній стан 3 у регістрі SM */
    int32_t  out_val;       /* Останній обчислений вихід підписника */
    uint32_t trigger_count; /* Кількість опрацьованих активних подій */
} km_hetero_state_t;

/* --- Буфер телеметрії у device-local пам'яті GPU (cudaMalloc) --- */
typedef struct {
    uint64_t t_math_cycles[KM_MAX_BLOCKS][KM_TELEMETRY_CAP];
    uint64_t t_e2e_cycles[KM_MAX_BLOCKS][KM_TELEMETRY_CAP];
    uint64_t t_math_gt_ns[KM_MAX_BLOCKS][KM_TELEMETRY_CAP];
    uint64_t t_e2e_gt_ns[KM_MAX_BLOCKS][KM_TELEMETRY_CAP];
    uint32_t recorded_samples[KM_MAX_BLOCKS];
} km_telemetry_t;

__device__ __forceinline__ uint64_t km_read_globaltimer(void) {
    uint64_t ret = 0;
#if __CUDA_ARCH__ >= 700
    asm volatile("mov.u64 %0, %%globaltimer;" : "=l"(ret));
#endif
    return ret;
}

__device__ __forceinline__ uint32_t km_ld_acquire_sys_u32(const uint32_t *ptr) {
    uint32_t val = 0;
#if __CUDA_ARCH__ >= 700
    asm volatile("ld.global.acquire.sys.u32 %0, [%1];" : "=r"(val) : "l"(ptr) : "memory");
#else
    val = atomicAdd((unsigned int *)ptr, 0u);
#endif
    return val;
}

__device__ __forceinline__ void km_st_release_sys_u32(uint32_t *ptr, uint32_t val) {
#if __CUDA_ARCH__ >= 700
    asm volatile("st.global.release.sys.u32 [%0], %1;" :: "l"(ptr), "r"(val) : "memory");
#else
    *(volatile uint32_t *)ptr = val;
#endif
}

/* --- Виконання одного кроку гетерогенного оператора у регістрах SM --- */
__device__ __forceinline__ void km_exec_hetero_operator(
    uint32_t  reg_op,
    uint32_t  reg_inst,
    int32_t   c_val,
    bool      is_active,
    int32_t   reg_p0,
    int32_t   reg_p1,
    int32_t   reg_p2,
    int32_t   reg_p3,
    int32_t   reg_p4,
    int32_t  *reg_s0,
    int32_t  *reg_s1,
    int32_t  *reg_s2,
    int32_t  *reg_s3,
    int32_t  *reg_out,
    uint32_t *reg_triggers
) {
    int32_t in_val = c_val + (int32_t)((reg_inst & 31u) * 4u) - 60;

    switch (reg_op) {
        case OP_0_PID_Q8: {
            /* Дискретний ПІД-регулятор 2-го порядку (Q8) з anti-windup [-32768, 32767] */
            int32_t err      = in_val - reg_p0;
            int32_t raw_int  = *reg_s0 + err;
            bool    clamped  = (raw_int > reg_p4) || (raw_int < KM_PID_INT_MIN);
            int32_t cand_int = (raw_int > reg_p4) ? reg_p4
                             : ((raw_int < KM_PID_INT_MIN) ? KM_PID_INT_MIN : raw_int);
            int32_t diff_err = err - *reg_s1;
            int32_t p_term   = (err * reg_p1) >> 8;
            int32_t i_term   = (cand_int * reg_p2) >> 8;
            int32_t d_term   = (diff_err * reg_p3) >> 8;
            int32_t cand_out = p_term + i_term + d_term;
            int32_t cand_sat = *reg_s2 + (clamped ? 1 : 0);

            *reg_s0 = is_active ? cand_int : *reg_s0;
            *reg_s1 = is_active ? err      : *reg_s1;
            *reg_s2 = is_active ? cand_sat : *reg_s2;
            *reg_out = is_active ? cand_out : *reg_out;
            break;
        }
        case OP_1_BIQUAD_Q12: {
            /* Direct Form II Transposed Biquad у фіксованій комі Q12 зі станами z1, z2 */
            int32_t acc     = reg_p0 * in_val + *reg_s0 + 2048;
            int32_t y_val   = acc >> 12;
            int32_t cand_z1 = reg_p1 * in_val - reg_p3 * y_val + *reg_s1;
            int32_t cand_z2 = reg_p2 * in_val - reg_p4 * y_val;
            int32_t abs_y   = (y_val < 0) ? -y_val : y_val;
            int32_t cand_pk = (abs_y > *reg_s2) ? abs_y : *reg_s2;

            *reg_s0 = is_active ? cand_z1 : *reg_s0;
            *reg_s1 = is_active ? cand_z2 : *reg_s1;
            *reg_s2 = is_active ? cand_pk : *reg_s2;
            *reg_out = is_active ? y_val  : *reg_out;
            break;
        }
        case OP_2_HYST_WINDOW: {
            /* Двопороговий тригер Шмітта з мертвою зоною та лічильником dwell_count */
            int32_t d    = in_val - reg_p0;
            int32_t x_db = (d > reg_p1) ? (d - reg_p1)
                         : ((d < -reg_p1) ? (d + reg_p1) : 0);

            int32_t prev_st = *reg_s0;
            int32_t cand_st = prev_st;
            if (prev_st == 1) {
                if (x_db < reg_p3) {
                    cand_st = (x_db <= -reg_p2) ? -1 : 0;
                }
            } else if (prev_st == -1) {
                if (x_db > -reg_p3) {
                    cand_st = (x_db >= reg_p2) ? 1 : 0;
                }
            } else {
                if (x_db >= reg_p2) {
                    cand_st = 1;
                } else if (x_db <= -reg_p2) {
                    cand_st = -1;
                }
            }

            int32_t cand_dwell = 0;
            if (cand_st != 0) {
                cand_dwell = (cand_st == prev_st) ? (*reg_s1 + 1) : 1;
            }
            int32_t cand_trans = *reg_s2 + ((cand_st != prev_st) ? 1 : 0);
            int32_t qual_term  = (cand_dwell >= reg_p4) ? (cand_st * 1000) : 0;
            int32_t clamp_dw   = (cand_dwell < 64) ? cand_dwell : 64;
            int32_t cand_out   = qual_term + (cand_st * 100) + clamp_dw;

            *reg_s0 = is_active ? cand_st    : *reg_s0;
            *reg_s1 = is_active ? cand_dwell : *reg_s1;
            *reg_s2 = is_active ? cand_trans : *reg_s2;
            *reg_out = is_active ? cand_out  : *reg_out;
            break;
        }
        default: { /* OP_3_EWMA_SLEW */
            /* EWMA у Q8 + slew-rate limiter max_delta + детектор стрибка похідної */
            int32_t target_q8    = in_val << 8;
            int32_t cand_ewma_q8 = *reg_s0 + ((reg_p0 * (target_q8 - *reg_s0)) >> 8);
            int32_t ewma_val     = cand_ewma_q8 >> 8;
            int32_t raw_delta    = ewma_val - *reg_s1;
            int32_t step_delta   = (raw_delta > reg_p1) ? reg_p1
                                 : ((raw_delta < -reg_p1) ? -reg_p1 : raw_delta);
            int32_t cand_slew    = *reg_s1 + step_delta;

            int32_t deriv      = in_val - *reg_s2;
            int32_t abs_deriv  = (deriv < 0) ? -deriv : deriv;
            bool    is_jump    = (abs_deriv > reg_p2);
            int32_t cand_jumps = *reg_s3 + (is_jump ? 1 : 0);
            int32_t jump_term  = is_jump ? ((deriv > 0) ? reg_p3 : -reg_p3) : 0;
            int32_t cand_out   = cand_slew + jump_term;

            *reg_s0 = is_active ? cand_ewma_q8 : *reg_s0;
            *reg_s1 = is_active ? cand_slew    : *reg_s1;
            *reg_s2 = is_active ? in_val       : *reg_s2;
            *reg_s3 = is_active ? cand_jumps   : *reg_s3;
            *reg_out = is_active ? cand_out    : *reg_out;
            break;
        }
    }

    *reg_triggers = is_active ? (*reg_triggers + 1u) : *reg_triggers;
}

/* ============================================================================
 * ПЕРСИСТЕНТНИЙ ГЕТЕРОГЕННИЙ КЕРНЕЛ GPU (1..16 блоків, 32..512 ниток у блоці)
 * ============================================================================ */
__global__ void __launch_bounds__(512, 1) km_heterogeneous_subscribers_kernel(
    const km_event_ingress_t * __restrict__ ingress,
    km_event_egress_t        * __restrict__ egress,
    km_telemetry_t           * __restrict__ telemetry,
    const km_hetero_state_t  * __restrict__ init_states,
    km_hetero_state_t        * __restrict__ final_states,
    uint32_t                                sleep_ns,
    uint32_t                                ack_isolated,
    uint32_t                                ingress_mode
) {
    const uint32_t tid         = threadIdx.x;
    const uint32_t lane_id     = tid & 31u;
    const uint32_t warp_id     = tid >> 5u;
    const uint32_t warps_in_blk = blockDim.x >> 5u;
    const uint32_t global_id   = blockIdx.x * blockDim.x + tid;
    const uint32_t mask_word   = global_id >> 5u;
    const bool     single_warp = (blockDim.x == KM_WARP_SIZE);
    const km_event_ingress_t *my_in = (ingress_mode == KM_INGRESS_PARTITIONED) ? &ingress[blockIdx.x] : &ingress[0];

    __shared__ uint32_t s_cur_seq;
    __shared__ uint32_t s_stop;
    __shared__ int32_t  s_cval;
    __shared__ uint32_t s_masks[KM_MAX_WARPS_PER_BLK];
    __shared__ uint64_t s_warp_math_cyc[KM_MAX_WARPS_PER_BLK];
    __shared__ uint64_t s_warp_math_gt[KM_MAX_WARPS_PER_BLK];

    /* 1. Завантаження дескриптора та внутрішнього стану підписника у регістри SM */
    km_hetero_state_t st = init_states[global_id];
    uint32_t reg_op       = st.op_type;
    uint32_t reg_inst     = st.inst_id;
    int32_t  reg_p0       = st.p0;
    int32_t  reg_p1       = st.p1;
    int32_t  reg_p2       = st.p2;
    int32_t  reg_p3       = st.p3;
    int32_t  reg_p4       = st.p4;
    int32_t  reg_s0       = st.s0;
    int32_t  reg_s1       = st.s1;
    int32_t  reg_s2       = st.s2;
    int32_t  reg_s3       = st.s3;
    int32_t  reg_out      = st.out_val;
    uint32_t reg_triggers = st.trigger_count;

    if (single_warp) {
        __syncwarp();
    } else {
        __syncthreads();
    }

    uint32_t last_seq = 0u;

    while (true) {
        uint32_t cur_seq = 0u;
        uint32_t stop    = 0u;

        if (single_warp) {
            if (lane_id == 0u) {
                cur_seq = km_ld_acquire_sys_u32(&my_in->seq_id);
                stop    = *(const volatile uint32_t *)&my_in->stop_flag;
            }
            cur_seq = __shfl_sync(0xFFFFFFFFu, cur_seq, 0);
            stop    = __shfl_sync(0xFFFFFFFFu, stop, 0);

            if (stop != 0u) {
                break;
            }

            if (cur_seq != last_seq) {
                uint64_t t_e2e_c0 = clock64();
                uint64_t t_e2e_g0 = km_read_globaltimer();

                int32_t  c_val = 0;
                uint32_t mask  = 0u;
                if (lane_id == 0u) {
                    c_val = *(const volatile int32_t *)&my_in->concept_val;
                    if (ingress_mode == KM_INGRESS_PARTITIONED) {
                        mask = *(const volatile uint32_t *)&my_in->event_mask[0];
                    } else {
                        mask = *(const volatile uint32_t *)&ingress[0].event_mask[mask_word & 15u];
                    }
                }
                c_val = __shfl_sync(0xFFFFFFFFu, c_val, 0);
                mask  = __shfl_sync(0xFFFFFFFFu, mask, 0);

                bool is_active = ((mask & (1u << lane_id)) != 0u);

                uint64_t t_math_c0 = clock64();
                uint64_t t_math_g0 = km_read_globaltimer();

                km_exec_hetero_operator(
                    reg_op, reg_inst, c_val, is_active,
                    reg_p0, reg_p1, reg_p2, reg_p3, reg_p4,
                    &reg_s0, &reg_s1, &reg_s2, &reg_s3, &reg_out, &reg_triggers
                );

                uint64_t t_math_c1 = clock64();
                uint64_t t_math_g1 = km_read_globaltimer();

                if (is_active) {
                    egress->outputs[global_id] = reg_out;
                }
                __syncwarp();

                uint64_t t_e2e_c1 = clock64();
                uint64_t t_e2e_g1 = km_read_globaltimer();

                if (lane_id == 0u) {
                    uint32_t *ack_ptr = (ack_isolated != 0u)
                        ? &egress->isolated_ack[blockIdx.x].ack
                        : &egress->packed_ack[blockIdx.x];
                    km_st_release_sys_u32(ack_ptr, cur_seq);
                    if (cur_seq <= KM_TELEMETRY_CAP) {
                        uint32_t idx = cur_seq - 1u;
                        telemetry->t_math_cycles[blockIdx.x][idx] = t_math_c1 - t_math_c0;
                        telemetry->t_e2e_cycles[blockIdx.x][idx]  = t_e2e_c1  - t_e2e_c0;
                        telemetry->t_math_gt_ns[blockIdx.x][idx]  = t_math_g1 - t_math_g0;
                        telemetry->t_e2e_gt_ns[blockIdx.x][idx]   = t_e2e_g1  - t_e2e_g0;
                        telemetry->recorded_samples[blockIdx.x]   = cur_seq;
                    }
                }
                last_seq = cur_seq;
            } else if (sleep_ns > 0u) {
#if __CUDA_ARCH__ >= 700
                __nanosleep(sleep_ns);
#endif
            }
        } else {
            /* Багатоварповий шлях (64..512 ниток на SM): лише tid == 0 опитує власну лінію L2 */
            if (tid == 0u) {
                s_cur_seq = km_ld_acquire_sys_u32(&my_in->seq_id);
                s_stop    = *(const volatile uint32_t *)&my_in->stop_flag;
            }
            __syncthreads();

            cur_seq = s_cur_seq;
            stop    = s_stop;

            if (stop != 0u) {
                break;
            }

            if (cur_seq != last_seq) {
                uint64_t t_e2e_c0 = clock64();
                uint64_t t_e2e_g0 = km_read_globaltimer();

                if (tid == 0u) {
                    s_cval = *(const volatile int32_t *)&my_in->concept_val;
                }
                if (tid < warps_in_blk) {
                    if (ingress_mode == KM_INGRESS_PARTITIONED) {
                        s_masks[tid] = *(const volatile uint32_t *)&my_in->event_mask[tid];
                    } else {
                        uint32_t gw = (blockIdx.x * warps_in_blk) + tid;
                        s_masks[tid] = *(const volatile uint32_t *)&ingress[0].event_mask[gw & 15u];
                    }
                }
                __syncthreads();

                int32_t  c_val = s_cval;
                uint32_t mask  = s_masks[warp_id];
                bool is_active = ((mask & (1u << lane_id)) != 0u);

                uint64_t t_math_c0 = clock64();
                uint64_t t_math_g0 = km_read_globaltimer();

                km_exec_hetero_operator(
                    reg_op, reg_inst, c_val, is_active,
                    reg_p0, reg_p1, reg_p2, reg_p3, reg_p4,
                    &reg_s0, &reg_s1, &reg_s2, &reg_s3, &reg_out, &reg_triggers
                );

                uint64_t t_math_c1 = clock64();
                uint64_t t_math_g1 = km_read_globaltimer();

                if (lane_id == 0u) {
                    s_warp_math_cyc[warp_id] = t_math_c1 - t_math_c0;
                    s_warp_math_gt[warp_id]  = t_math_g1 - t_math_g0;
                }
                if (is_active) {
                    egress->outputs[global_id] = reg_out;
                }
                __syncthreads();

                uint64_t t_e2e_c1 = clock64();
                uint64_t t_e2e_g1 = km_read_globaltimer();

                if (tid == 0u) {
                    uint32_t *ack_ptr = (ack_isolated != 0u)
                        ? &egress->isolated_ack[blockIdx.x].ack
                        : &egress->packed_ack[blockIdx.x];
                    km_st_release_sys_u32(ack_ptr, cur_seq);
                    if (cur_seq <= KM_TELEMETRY_CAP) {
                        uint64_t blk_math_cyc = s_warp_math_cyc[0];
                        uint64_t blk_math_gt  = s_warp_math_gt[0];
                        for (uint32_t w = 1u; w < warps_in_blk; w++) {
                            if (s_warp_math_cyc[w] > blk_math_cyc) blk_math_cyc = s_warp_math_cyc[w];
                            if (s_warp_math_gt[w]  > blk_math_gt)  blk_math_gt  = s_warp_math_gt[w];
                        }
                        uint32_t idx = cur_seq - 1u;
                        telemetry->t_math_cycles[blockIdx.x][idx] = blk_math_cyc;
                        telemetry->t_e2e_cycles[blockIdx.x][idx]  = t_e2e_c1 - t_e2e_c0;
                        telemetry->t_math_gt_ns[blockIdx.x][idx]  = blk_math_gt;
                        telemetry->t_e2e_gt_ns[blockIdx.x][idx]   = t_e2e_g1 - t_e2e_g0;
                        telemetry->recorded_samples[blockIdx.x]   = cur_seq;
                    }
                }
                last_seq = cur_seq;
            } else if (tid == 0u && sleep_ns > 0u) {
#if __CUDA_ARCH__ >= 700
                __nanosleep(sleep_ns);
#endif
            }
            __syncthreads();
        }
    }

    /* 2. Вивантаження фінальних станів із регістрів SM для побітової перевірки на CPU */
    st.s0            = reg_s0;
    st.s1            = reg_s1;
    st.s2            = reg_s2;
    st.s3            = reg_s3;
    st.out_val       = reg_out;
    st.trigger_count = reg_triggers;
    final_states[global_id] = st;
}

/* --- Калібрування дискретності %globaltimer --- */
__global__ void km_probe_globaltimer_quantum(uint64_t *out_min_step) {
    if (threadIdx.x == 0 && blockIdx.x == 0) {
        uint64_t min_delta = UINT64_MAX;
        uint64_t prev = km_read_globaltimer();
        for (int i = 0; i < 4096; i++) {
            uint64_t cur = km_read_globaltimer();
            if (cur > prev && (cur - prev) < min_delta) {
                min_delta = cur - prev;
            }
            prev = cur;
        }
        *out_min_step = (min_delta == UINT64_MAX) ? 0ULL : min_delta;
    }
}

/* ============================================================================
 * ДОПОМІЖНІ ФУНКЦІЇ ХОСТА: SYSFS, ІНІЦІАЛІЗАЦІЯ, ЕТАЛОННА CPU-МОДЕЛЬ, СТАТИСТИКА
 * ============================================================================ */

static uint64_t read_sysfs_u64(const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) return 0ULL;
    unsigned long long val = 0ULL;
    if (fscanf(f, "%llu", &val) != 1) val = 0ULL;
    fclose(f);
    return (uint64_t)val;
}

static uint64_t read_gpu_sysfs_freq_hz(const char *leaf) {
    char path[256];
    const char *bases[] = {
        "/sys/devices/platform/17000000.gpu/devfreq/17000000.gpu",
        "/sys/devices/gpu.0/devfreq/17000000.gpu",
        NULL
    };
    for (int i = 0; bases[i] != NULL; i++) {
        snprintf(path, sizeof(path), "%s/%s", bases[i], leaf);
        uint64_t hz = read_sysfs_u64(path);
        if (hz > 0ULL) return hz;
    }
    return 0ULL;
}

static uint64_t read_gpu_ctrl_u64(const char *leaf) {
    char path[256];
    const char *bases[] = {
        "/sys/devices/platform/17000000.gpu",
        "/sys/devices/gpu.0",
        NULL
    };
    for (int i = 0; bases[i] != NULL; i++) {
        snprintf(path, sizeof(path), "%s/%s", bases[i], leaf);
        uint64_t val = read_sysfs_u64(path);
        if (val > 0ULL) return val;
    }
    return 0ULL;
}

static uint64_t read_cpu_cur_freq_khz(int cpu_id) {
    char path[256];
    if (cpu_id < 0) cpu_id = 0;
    snprintf(path, sizeof(path), "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_cur_freq", cpu_id);
    uint64_t khz = read_sysfs_u64(path);
    if (khz > 0ULL) return khz;
    snprintf(path, sizeof(path), "/sys/devices/system/cpu/cpu%d/cpufreq/cpuinfo_cur_freq", cpu_id);
    return read_sysfs_u64(path);
}

static inline uint64_t host_monotonic_raw_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

static int cmp_u64(const void *a, const void *b) {
    uint64_t va = *(const uint64_t *)a;
    uint64_t vb = *(const uint64_t *)b;
    return (va > vb) - (va < vb);
}

typedef struct {
    double   mean;
    double   stddev;
    uint64_t min;
    uint64_t p50;
    uint64_t p99;
    uint64_t p99_ci_lo;
    uint64_t p99_ci_hi;
    uint64_t p999;
    uint64_t p999_ci_lo;
    uint64_t p999_ci_hi;
    uint64_t max;
} km_stats_t;

static uint64_t km_xorshift64(uint64_t *state) {
    uint64_t x = *state;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    *state = x;
    return x * 0x2545F4914F6CDD1DULL;
}

static km_stats_t compute_stats(const uint64_t *raw, uint32_t n, bool with_bootstrap) {
    km_stats_t st = {0};
    if (n == 0u) return st;

    uint64_t *sorted = (uint64_t *)malloc(n * sizeof(uint64_t));
    memcpy(sorted, raw, n * sizeof(uint64_t));
    qsort(sorted, n, sizeof(uint64_t), cmp_u64);

    double sum = 0.0;
    for (uint32_t i = 0; i < n; i++) {
        sum += (double)sorted[i];
    }
    st.mean = sum / (double)n;

    double var_sum = 0.0;
    for (uint32_t i = 0; i < n; i++) {
        double d = (double)sorted[i] - st.mean;
        var_sum += d * d;
    }
    st.stddev = sqrt(var_sum / (double)n);
    st.min    = sorted[0];
    st.p50    = sorted[(size_t)((n - 1u) * 0.50)];
    st.p99    = sorted[(size_t)((n - 1u) * 0.99)];
    st.p999   = sorted[(size_t)((n - 1u) * 0.999)];
    st.max    = sorted[n - 1u];

    if (with_bootstrap && n >= 2u) {
        uint64_t *boot_sample = (uint64_t *)malloc(n * sizeof(uint64_t));
        uint64_t  boot_p99[KM_BOOTSTRAP_ITERS];
        uint64_t  boot_p999[KM_BOOTSTRAP_ITERS];
        uint64_t  rng = KM_BOOTSTRAP_SEED;
        size_t    idx99  = (size_t)((n - 1u) * 0.99);
        size_t    idx999 = (size_t)((n - 1u) * 0.999);

        for (uint32_t it = 0; it < KM_BOOTSTRAP_ITERS; it++) {
            for (uint32_t i = 0; i < n; i++) {
                uint32_t r = (uint32_t)(km_xorshift64(&rng) % (uint64_t)n);
                boot_sample[i] = sorted[r];
            }
            qsort(boot_sample, n, sizeof(uint64_t), cmp_u64);
            boot_p99[it]  = boot_sample[idx99];
            boot_p999[it] = boot_sample[idx999];
        }
        qsort(boot_p99,  KM_BOOTSTRAP_ITERS, sizeof(uint64_t), cmp_u64);
        qsort(boot_p999, KM_BOOTSTRAP_ITERS, sizeof(uint64_t), cmp_u64);
        st.p99_ci_lo  = boot_p99[(size_t)((KM_BOOTSTRAP_ITERS - 1u) * 0.025)];
        st.p99_ci_hi  = boot_p99[(size_t)((KM_BOOTSTRAP_ITERS - 1u) * 0.975)];
        st.p999_ci_lo = boot_p999[(size_t)((KM_BOOTSTRAP_ITERS - 1u) * 0.025)];
        st.p999_ci_hi = boot_p999[(size_t)((KM_BOOTSTRAP_ITERS - 1u) * 0.975)];
        free(boot_sample);
    } else {
        st.p99_ci_lo  = st.p99_ci_hi  = st.p99;
        st.p999_ci_lo = st.p999_ci_hi = st.p999;
    }

    free(sorted);
    return st;
}

typedef enum {
    MASK_ALL = 0,
    MASK_ALT,
    MASK_ONE,
    MASK_ENDS,
    MASK_RAND,
    MASK_NONE
} km_mask_mode_t;

static uint32_t generate_mask_word(km_mask_mode_t mode, uint32_t ev, uint32_t word_idx) {
    switch (mode) {
        case MASK_ALL:  return 0xFFFFFFFFu;
        case MASK_ALT:  return 0x55555555u;
        case MASK_ONE:  return (word_idx == 0u) ? 0x00000001u : 0x00000000u;
        case MASK_ENDS: return 0x80000001u;
        case MASK_NONE: return 0x00000000u;
        case MASK_RAND: {
            uint32_t x = ev * 1664525u + word_idx * 1013904223u + 0x9E3779B9u;
            x ^= x >> 16;
            x *= 0x85EBCA6Bu;
            x ^= x >> 13;
            return (x == 0u) ? 1u : x;
        }
    }
    return 0xFFFFFFFFu;
}

/* Детермінований багаторежимний сигнал стану концепту (пилка + сходинкові імпульси) */
static int32_t generate_concept_val(uint32_t ev) {
    uint32_t phase = ev % 128u;
    int32_t base = (phase < 64u)
        ? (-320 + (int32_t)(phase * 10u))
        : (320 - (int32_t)((phase - 64u) * 10u));
    int32_t step = ((ev % 32u) == 0u) ? 260 : (((ev % 32u) == 16u) ? -260 : 0);
    return base + step;
}

static void init_subscriber_descriptor(
    km_hetero_state_t *st,
    uint32_t           gid,
    km_layout_mode_t   layout
) {
    uint32_t warp_global = gid >> 5u;
    uint32_t lane_id     = gid & 31u;
    uint32_t op_type     = OP_0_PID_Q8;
    uint32_t inst_id     = gid & 255u;

    if (layout == KM_LAYOUT_MIXED_WARP) {
        op_type = lane_id & 3u;
        inst_id = ((warp_global * 8u) + (lane_id >> 2u)) & 255u;
    } else if (layout == KM_LAYOUT_GROUPED_WARP) {
        op_type = warp_global & 3u;
        inst_id = (((warp_global >> 2u) * 32u) + lane_id) & 255u;
    }

    st->op_type       = op_type;
    st->inst_id       = inst_id;
    st->s0            = 0;
    st->s1            = 0;
    st->s2            = 0;
    st->s3            = 0;
    st->out_val       = -7777;
    st->trigger_count = 0u;

    switch (op_type) {
        case OP_0_PID_Q8: {
            st->p0 = -120 + (int32_t)((inst_id & 31u) * 8u);         /* target */
            st->p1 = 512 + (int32_t)((inst_id & 7u) * 32u);          /* kp_q8 */
            st->p2 = 48  + (int32_t)(((inst_id >> 3u) & 15u) * 4u);  /* ki_q8 */
            st->p3 = 256 + (int32_t)(((inst_id >> 5u) & 3u) * 64u);  /* kd_q8 */
            st->p4 = KM_PID_INT_MAX;                                 /* anti-windup +32767 */
            break;
        }
        case OP_1_BIQUAD_Q12: {
            /* Чотири BIBO-стійкі профілі полюсів (критерій Джурі у Q12, scale=4096) */
            static const int32_t b0_tab[4] = {  768,   519,  1048,   832 };
            static const int32_t b1_tab[4] = { 1536,  1038,     0,  1664 };
            static const int32_t b2_tab[4] = {  768,   519, -1048,   832 };
            static const int32_t a1_tab[4] = {-2048, -3620,     0, -3072 };
            static const int32_t a2_tab[4] = { 1024,  1600,  2000,  2304 };
            uint32_t k = inst_id & 3u;
            st->p0 = b0_tab[k];
            st->p1 = b1_tab[k];
            st->p2 = b2_tab[k];
            st->p3 = a1_tab[k];
            st->p4 = a2_tab[k];
            break;
        }
        case OP_2_HYST_WINDOW: {
            st->p0 = -20 + (int32_t)((inst_id & 15u) * 4u);          /* center */
            st->p1 = 24  + (int32_t)(((inst_id >> 4u) & 3u) * 8u);   /* deadband */
            st->p2 = 140 + (int32_t)((inst_id & 7u) * 12u);          /* th_hi */
            st->p3 = 60  + (int32_t)((inst_id & 7u) * 8u);           /* th_lo */
            st->p4 = 3   + (int32_t)((inst_id >> 3u) & 3u);          /* min_dwell */
            break;
        }
        default: { /* OP_3_EWMA_SLEW */
            st->p0 = 48  + (int32_t)((inst_id & 7u) * 16u);          /* alpha_q8 */
            st->p1 = 18  + (int32_t)(((inst_id >> 3u) & 7u) * 4u);   /* max_delta */
            st->p2 = 180 + (int32_t)(((inst_id >> 5u) & 3u) * 20u);  /* jump_thresh */
            st->p3 = 4;                                              /* jump_gain */
            st->p4 = 0;
            break;
        }
    }
}

/* Незалежна еталонна CPU-модель гетерогенних підписників (AGENTS.md §4.3) */
static void cpu_reference_hetero_step(
    km_hetero_state_t *ref_states,
    int32_t           *ref_outputs,
    uint32_t           total_subs,
    int32_t            c_val,
    const uint32_t    *mask_words
) {
    for (uint32_t gid = 0; gid < total_subs; gid++) {
        uint32_t w = gid >> 5u;
        uint32_t b = gid & 31u;
        bool active = ((mask_words[w] & (1u << b)) != 0u);
        if (!active) {
            continue;
        }

        km_hetero_state_t *st = &ref_states[gid];
        int32_t in_val = c_val + (int32_t)((st->inst_id & 31u) * 4u) - 60;

        if (st->op_type == OP_0_PID_Q8) {
            int32_t err     = in_val - st->p0;
            int32_t raw_int = st->s0 + err;
            int32_t clamped = (raw_int > st->p4 || raw_int < KM_PID_INT_MIN) ? 1 : 0;
            int32_t new_int = raw_int;
            if (new_int > st->p4)          new_int = st->p4;
            if (new_int < KM_PID_INT_MIN)  new_int = KM_PID_INT_MIN;

            int32_t p_term  = (err * st->p1) >> 8;
            int32_t i_term  = (new_int * st->p2) >> 8;
            int32_t d_term  = ((err - st->s1) * st->p3) >> 8;
            int32_t out_val = p_term + i_term + d_term;

            st->s0      = new_int;
            st->s1      = err;
            st->s2     += clamped;
            st->out_val = out_val;
            ref_outputs[gid] = out_val;
        } else if (st->op_type == OP_1_BIQUAD_Q12) {
            int32_t y_val  = (st->p0 * in_val + st->s0 + 2048) >> 12;
            int32_t new_z1 = st->p1 * in_val - st->p3 * y_val + st->s1;
            int32_t new_z2 = st->p2 * in_val - st->p4 * y_val;
            int32_t abs_y  = (y_val < 0) ? -y_val : y_val;

            st->s0 = new_z1;
            st->s1 = new_z2;
            if (abs_y > st->s2) st->s2 = abs_y;
            st->out_val = y_val;
            ref_outputs[gid] = y_val;
        } else if (st->op_type == OP_2_HYST_WINDOW) {
            int32_t d = in_val - st->p0;
            int32_t x_db = 0;
            if (d > st->p1)       x_db = d - st->p1;
            else if (d < -st->p1) x_db = d + st->p1;

            int32_t prev_st = st->s0;
            int32_t next_st = prev_st;
            if (prev_st == 1) {
                if (x_db < st->p3) {
                    next_st = (x_db <= -st->p2) ? -1 : 0;
                }
            } else if (prev_st == -1) {
                if (x_db > -st->p3) {
                    next_st = (x_db >= st->p2) ? 1 : 0;
                }
            } else {
                if (x_db >= st->p2)      next_st = 1;
                else if (x_db <= -st->p2) next_st = -1;
            }

            int32_t next_dwell = 0;
            if (next_st != 0) {
                next_dwell = (next_st == prev_st) ? (st->s1 + 1) : 1;
            }
            if (next_st != prev_st) {
                st->s2 += 1;
            }
            int32_t qual_term = (next_dwell >= st->p4) ? (next_st * 1000) : 0;
            int32_t clamp_dw  = (next_dwell < 64) ? next_dwell : 64;
            int32_t out_val   = qual_term + (next_st * 100) + clamp_dw;

            st->s0      = next_st;
            st->s1      = next_dwell;
            st->out_val = out_val;
            ref_outputs[gid] = out_val;
        } else {
            int32_t new_ewma_q8 = st->s0 + ((st->p0 * ((in_val << 8) - st->s0)) >> 8);
            int32_t ewma_val    = new_ewma_q8 >> 8;
            int32_t raw_delta   = ewma_val - st->s1;
            if (raw_delta > st->p1)       raw_delta = st->p1;
            else if (raw_delta < -st->p1) raw_delta = -st->p1;
            int32_t new_slew    = st->s1 + raw_delta;

            int32_t deriv     = in_val - st->s2;
            int32_t abs_deriv = (deriv < 0) ? -deriv : deriv;
            bool    is_jump   = (abs_deriv > st->p2);
            int32_t jump_term = is_jump ? ((deriv > 0) ? st->p3 : -st->p3) : 0;
            int32_t out_val   = new_slew + jump_term;

            st->s0 = new_ewma_q8;
            st->s1 = new_slew;
            st->s2 = in_val;
            if (is_jump) st->s3 += 1;
            st->out_val = out_val;
            ref_outputs[gid] = out_val;
        }

        st->trigger_count += 1u;
    }
}

int main(int argc, char **argv) {
    uint32_t         num_events        = 10000u;
    uint32_t         num_blocks        = 16u;
    uint32_t         threads           = 64u;
    uint32_t         sleep_ns          = 0u;
    km_layout_mode_t layout_mode       = KM_LAYOUT_GROUPED_WARP;
    const char      *layout_name       = "grouped_warp";
    km_mask_mode_t   mask_mode         = MASK_RAND;
    const char      *mask_name         = "rand";
    const char      *ack_mode_name     = "isolated";
    uint32_t         ack_isolated      = 1u;
    const char      *ingress_mode_name = "partitioned";
    uint32_t         ingress_mode      = KM_INGRESS_PARTITIONED;
    bool             rt_pin_requested  = false;
    int              rt_cpu            = 11;
    int              rt_prio           = 80;
    bool             allow_attr_clk    = false;
    const char      *json_out          = NULL;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--events") == 0 && i + 1 < argc) {
            num_events = (uint32_t)strtoul(argv[++i], NULL, 10);
        } else if (strcmp(argv[i], "--blocks") == 0 && i + 1 < argc) {
            num_blocks = (uint32_t)strtoul(argv[++i], NULL, 10);
        } else if (strcmp(argv[i], "--threads") == 0 && i + 1 < argc) {
            threads = (uint32_t)strtoul(argv[++i], NULL, 10);
        } else if (strcmp(argv[i], "--sleep-ns") == 0 && i + 1 < argc) {
            sleep_ns = (uint32_t)strtoul(argv[++i], NULL, 10);
        } else if (strcmp(argv[i], "--layout") == 0 && i + 1 < argc) {
            layout_name = argv[++i];
            if (strcmp(layout_name, "homo_pid") == 0) {
                layout_mode = KM_LAYOUT_HOMO_PID;
            } else if (strcmp(layout_name, "mixed_warp") == 0) {
                layout_mode = KM_LAYOUT_MIXED_WARP;
            } else if (strcmp(layout_name, "grouped_warp") == 0) {
                layout_mode = KM_LAYOUT_GROUPED_WARP;
            } else {
                fprintf(stderr, "[FATAL] Невідомий режим --layout: %s (очікується homo_pid|mixed_warp|grouped_warp)\n", layout_name);
                return 2;
            }
        } else if (strcmp(argv[i], "--rt-pin") == 0) {
            rt_pin_requested = true;
        } else if (strcmp(argv[i], "--rt-cpu") == 0 && i + 1 < argc) {
            rt_cpu = (int)strtol(argv[++i], NULL, 10);
        } else if (strcmp(argv[i], "--rt-prio") == 0 && i + 1 < argc) {
            rt_prio = (int)strtol(argv[++i], NULL, 10);
        } else if (strcmp(argv[i], "--ack-mode") == 0 && i + 1 < argc) {
            ack_mode_name = argv[++i];
            if (strcmp(ack_mode_name, "isolated") == 0) {
                ack_isolated = 1u;
            } else if (strcmp(ack_mode_name, "packed") == 0) {
                ack_isolated = 0u;
            } else {
                fprintf(stderr, "[FATAL] Невідомий режим --ack-mode: %s\n", ack_mode_name);
                return 2;
            }
        } else if (strcmp(argv[i], "--ingress-mode") == 0 && i + 1 < argc) {
            const char *arg_mode = argv[++i];
            if (strcmp(arg_mode, "partitioned") == 0) {
                ingress_mode_name = "partitioned";
                ingress_mode      = KM_INGRESS_PARTITIONED;
            } else if (strcmp(arg_mode, "shared_1line") == 0) {
                ingress_mode_name = "shared_1line";
                ingress_mode      = KM_INGRESS_SHARED_1LINE;
            } else {
                fprintf(stderr, "[FATAL] Невідомий режим --ingress-mode: %s\n", arg_mode);
                return 2;
            }
        } else if (strcmp(argv[i], "--allow-attr-clock") == 0) {
            allow_attr_clk = true;
        } else if (strcmp(argv[i], "--mask") == 0 && i + 1 < argc) {
            mask_name = argv[++i];
            if (strcmp(mask_name, "all") == 0)       mask_mode = MASK_ALL;
            else if (strcmp(mask_name, "alt") == 0)  mask_mode = MASK_ALT;
            else if (strcmp(mask_name, "one") == 0)  mask_mode = MASK_ONE;
            else if (strcmp(mask_name, "ends") == 0) mask_mode = MASK_ENDS;
            else if (strcmp(mask_name, "rand") == 0) mask_mode = MASK_RAND;
            else if (strcmp(mask_name, "none") == 0) mask_mode = MASK_NONE;
            else {
                fprintf(stderr, "[FATAL] Невідомий режим --mask: %s\n", mask_name);
                return 2;
            }
        } else if (strcmp(argv[i], "--json-out") == 0 && i + 1 < argc) {
            json_out = argv[++i];
        } else {
            fprintf(stderr, "[FATAL] Невідомий аргумент: %s\n", argv[i]);
            return 2;
        }
    }

    uint32_t total_subs = num_blocks * threads;
    if (num_events == 0u || num_blocks == 0u || num_blocks > KM_MAX_BLOCKS ||
        (threads % KM_WARP_SIZE) != 0u || threads > (KM_MAX_WARPS_PER_BLK * KM_WARP_SIZE) ||
        total_subs > KM_MAX_SUBSCRIBERS) {
        fprintf(stderr, "[FATAL] Некоректна геометрія: blocks=%u threads=%u total=%u\n",
                num_blocks, threads, total_subs);
        return 2;
    }

    cudaSetDeviceFlags(cudaDeviceMapHost);

    cudaDeviceProp prop;
    cudaGetDeviceProperties(&prop, 0);
    int attr_clock_khz = 0;
    cudaDeviceGetAttribute(&attr_clock_khz, cudaDevAttrClockRate, 0);

    uint64_t sysfs_min_before = read_gpu_sysfs_freq_hz("min_freq");
    uint64_t sysfs_max_before = read_gpu_sysfs_freq_hz("max_freq");
    uint64_t sysfs_cur_before = read_gpu_sysfs_freq_hz("cur_freq");
    uint64_t tsg_min_us       = read_gpu_ctrl_u64("tsg_timeslice_min_us");
    uint64_t tsg_max_us       = read_gpu_ctrl_u64("tsg_timeslice_max_us");

    uint64_t *d_gt_step = NULL;
    uint64_t  h_gt_step = 0ULL;
    cudaMalloc((void **)&d_gt_step, sizeof(uint64_t));
    km_probe_globaltimer_quantum<<<1, 1>>>(d_gt_step);
    cudaDeviceSynchronize();
    cudaMemcpy(&h_gt_step, d_gt_step, sizeof(uint64_t), cudaMemcpyDeviceToHost);
    cudaFree(d_gt_step);

    km_event_ingress_t *h_ingress = NULL, *d_ingress = NULL;
    km_event_egress_t  *h_egress  = NULL, *d_egress  = NULL;
    size_t ingress_alloc_bytes = KM_MAX_BLOCKS * sizeof(km_event_ingress_t);
    if (cudaHostAlloc((void **)&h_ingress, ingress_alloc_bytes,
                      cudaHostAllocMapped | cudaHostAllocPortable) != cudaSuccess ||
        cudaHostAlloc((void **)&h_egress, sizeof(km_event_egress_t),
                      cudaHostAllocMapped | cudaHostAllocPortable) != cudaSuccess) {
        fprintf(stderr, "[FATAL] Помилка cudaHostAlloc\n");
        return 1;
    }
    cudaHostGetDevicePointer((void **)&d_ingress, h_ingress, 0);
    cudaHostGetDevicePointer((void **)&d_egress,  h_egress,  0);
    memset(h_ingress, 0, ingress_alloc_bytes);
    memset(h_egress,  0, sizeof(km_event_egress_t));

    km_telemetry_t *d_telemetry = NULL;
    km_telemetry_t *h_telemetry = (km_telemetry_t *)calloc(1, sizeof(km_telemetry_t));
    cudaMalloc((void **)&d_telemetry, sizeof(km_telemetry_t));
    cudaMemset(d_telemetry, 0, sizeof(km_telemetry_t));

    km_hetero_state_t init_states[KM_MAX_SUBSCRIBERS];
    km_hetero_state_t ref_states[KM_MAX_SUBSCRIBERS];
    int32_t           ref_outputs[KM_MAX_SUBSCRIBERS];
    uint32_t          op_counts[KM_NUM_OP_TYPES] = {0u, 0u, 0u, 0u};

    for (uint32_t i = 0; i < total_subs; i++) {
        init_subscriber_descriptor(&init_states[i], i, layout_mode);
        if (init_states[i].op_type < KM_NUM_OP_TYPES) {
            op_counts[init_states[i].op_type]++;
        }
        ref_outputs[i]       = -7777;
        h_egress->outputs[i] = -7777;
    }
    memcpy(ref_states, init_states, sizeof(init_states));

    km_hetero_state_t *d_init = NULL, *d_final = NULL;
    cudaMalloc((void **)&d_init,  total_subs * sizeof(km_hetero_state_t));
    cudaMalloc((void **)&d_final, total_subs * sizeof(km_hetero_state_t));
    cudaMemcpy(d_init, init_states, total_subs * sizeof(km_hetero_state_t), cudaMemcpyHostToDevice);

    cudaStream_t stream;
    cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking);

    km_heterogeneous_subscribers_kernel<<<num_blocks, threads, 0, stream>>>(
        d_ingress, d_egress, d_telemetry, d_init, d_final, sleep_ns, ack_isolated, ingress_mode
    );
    cudaError_t launch_err = cudaGetLastError();
    if (launch_err != cudaSuccess) {
        fprintf(stderr, "[FATAL] Помилка запуску кернела: %s\n", cudaGetErrorString(launch_err));
        return 1;
    }

    usleep(30000); /* 30 мс на стабілізацію персистентних блоків SM у циклі опитування */

    /* Закріплення нитки публікації після ініціалізації CUDA, щоб фонові нитки драйвера не успадкували CPU 11 / SCHED_FIFO */
    bool cpu_affinity_active = false;
    int  pinned_cpu          = -1;
    bool sched_fifo_active   = false;
    int  active_fifo_prio    = 0;
    int  sched_fifo_errno    = 0;

    if (rt_pin_requested) {
        cpu_set_t cpuset;
        CPU_ZERO(&cpuset);
        CPU_SET(rt_cpu, &cpuset);
        if (sched_setaffinity(0, sizeof(cpuset), &cpuset) == 0) {
            cpu_set_t check_set;
            CPU_ZERO(&check_set);
            if (sched_getaffinity(0, sizeof(check_set), &check_set) == 0 &&
                CPU_ISSET(rt_cpu, &check_set) && CPU_COUNT(&check_set) == 1) {
                cpu_affinity_active = true;
                pinned_cpu          = rt_cpu;
            }
        } else {
            fprintf(stderr, "[WARN] sched_setaffinity(CPU %d) не вдалося: %s\n", rt_cpu, strerror(errno));
        }

        struct sched_param sp;
        memset(&sp, 0, sizeof(sp));
        sp.sched_priority = rt_prio;
        if (sched_setscheduler(0, SCHED_FIFO, &sp) == 0) {
            if (sched_getscheduler(0) == SCHED_FIFO) {
                sched_fifo_active = true;
                active_fifo_prio  = rt_prio;
            }
        } else {
            sched_fifo_errno = errno;
            fprintf(stderr, "[WARN] sched_setscheduler(SCHED_FIFO, %d) не встановлено: %s (errno=%d)\n",
                    rt_prio, strerror(sched_fifo_errno), sched_fifo_errno);
        }
        usleep(2000); /* Завершення міграції нитки на цільове ядро CPU */
    }

    int      observed_cpu_start = sched_getcpu();
    uint64_t sysfs_cur_mid      = read_gpu_sysfs_freq_hz("cur_freq");
    uint64_t cpu_cur_freq_khz   = read_cpu_cur_freq_khz(observed_cpu_start);

    uint64_t *host_rt_ns       = (uint64_t *)calloc(num_events, sizeof(uint64_t));
    uint64_t *host_pub_ns      = (uint64_t *)calloc(num_events, sizeof(uint64_t));
    uint64_t *host_wait_ack_ns = (uint64_t *)calloc(num_events, sizeof(uint64_t));
    uint32_t  mask_words_used  = (total_subs + 31u) / 32u;
    uint32_t  local_masks[KM_MASK_WORDS];
    memset(local_masks, 0, sizeof(local_masks));

    uint32_t warps_per_blk      = threads >> 5u;
    uint32_t mid_run_mismatches = 0u;
    uint64_t t_wall_start       = host_monotonic_raw_ns();

    for (uint32_t ev = 1u; ev <= num_events; ev++) {
        int32_t c_val = generate_concept_val(ev);
        if (ingress_mode == KM_INGRESS_SHARED_1LINE) {
            uint32_t nw1 = (mask_words_used < KM_SLOT_MASK_WORDS) ? mask_words_used : KM_SLOT_MASK_WORDS;
            for (uint32_t w = 0; w < nw1; w++) {
                local_masks[w] = generate_mask_word(mask_mode, ev, w);
            }
            for (uint32_t w = nw1; w < mask_words_used; w++) {
                local_masks[w] = local_masks[w & 15u];
            }
        } else {
            for (uint32_t w = 0; w < mask_words_used; w++) {
                local_masks[w] = generate_mask_word(mask_mode, ev, w);
            }
        }

        uint64_t t_pub0, t_pub1;
        if (ingress_mode == KM_INGRESS_PARTITIONED) {
            t_pub0 = host_monotonic_raw_ns();
            for (uint32_t b = 0; b < num_blocks; b++) {
                h_ingress[b].concept_val  = c_val;
                h_ingress[b].active_words = warps_per_blk;
                for (uint32_t w = 0; w < warps_per_blk; w++) {
                    h_ingress[b].event_mask[w] = local_masks[b * warps_per_blk + w];
                }
            }
            for (uint32_t b = 0; b < num_blocks; b++) {
                __atomic_store_n(&h_ingress[b].seq_id, ev, __ATOMIC_RELEASE);
            }
            t_pub1 = host_monotonic_raw_ns();
        } else {
            uint32_t nw1 = (mask_words_used < KM_SLOT_MASK_WORDS) ? mask_words_used : KM_SLOT_MASK_WORDS;
            t_pub0 = host_monotonic_raw_ns();
            h_ingress[0].concept_val  = c_val;
            h_ingress[0].active_words = nw1;
            for (uint32_t w = 0; w < nw1; w++) {
                h_ingress[0].event_mask[w] = local_masks[w];
            }
            __atomic_store_n(&h_ingress[0].seq_id, ev, __ATOMIC_RELEASE);
            t_pub1 = host_monotonic_raw_ns();
        }

        for (uint32_t b = 0; b < num_blocks; b++) {
            const volatile uint32_t *ack_ptr = (ack_isolated != 0u)
                ? (const volatile uint32_t *)&h_egress->isolated_ack[b].ack
                : (const volatile uint32_t *)&h_egress->packed_ack[b];
            while (__atomic_load_n(ack_ptr, __ATOMIC_ACQUIRE) != ev) {
#if defined(__aarch64__)
                asm volatile("yield" ::: "memory");
#endif
            }
        }
        uint64_t t1 = host_monotonic_raw_ns();
        host_pub_ns[ev - 1u]      = t_pub1 - t_pub0;
        host_wait_ack_ns[ev - 1u] = t1 - t_pub1;
        host_rt_ns[ev - 1u]       = t1 - t_pub0;

        if (ev == (num_events / 2u)) {
            uint64_t f_sample = read_gpu_sysfs_freq_hz("cur_freq");
            if (f_sample > sysfs_cur_mid) sysfs_cur_mid = f_sample;
            uint64_t c_sample = read_cpu_cur_freq_khz(sched_getcpu());
            if (c_sample > cpu_cur_freq_khz) cpu_cur_freq_khz = c_sample;
        }

        cpu_reference_hetero_step(ref_states, ref_outputs, total_subs, c_val, local_masks);

        if ((ev % 100u) == 0u || ev == num_events) {
            for (uint32_t i = 0; i < total_subs; i++) {
                if (h_egress->outputs[i] != ref_outputs[i]) {
                    mid_run_mismatches++;
                }
            }
        }
    }

    uint64_t t_wall_end       = host_monotonic_raw_ns();
    int      observed_cpu_end = sched_getcpu();
    uint64_t sysfs_cur_after  = read_gpu_sysfs_freq_hz("cur_freq");

    uint32_t stop_slots = (ingress_mode == KM_INGRESS_PARTITIONED) ? num_blocks : 1u;
    for (uint32_t b = 0; b < stop_slots; b++) {
        __atomic_store_n(&h_ingress[b].stop_flag, 1u, __ATOMIC_RELAXED);
        __atomic_store_n(&h_ingress[b].seq_id, num_events + 1u, __ATOMIC_RELEASE);
    }
    cudaStreamSynchronize(stream);

    cudaMemcpy(h_telemetry, d_telemetry, sizeof(km_telemetry_t), cudaMemcpyDeviceToHost);

    km_hetero_state_t gpu_final[KM_MAX_SUBSCRIBERS];
    cudaMemcpy(gpu_final, d_final, total_subs * sizeof(km_hetero_state_t), cudaMemcpyDeviceToHost);

    /* Побітова верифікація всіх внутрішніх станів s0..s3, out_val, trigger_count та outputs[] */
    uint32_t mismatches            = mid_run_mismatches;
    uint64_t pid_sat_events_total  = 0ULL;
    int32_t  biquad_max_peak_y     = 0;
    uint64_t hyst_transitions_tot  = 0ULL;
    uint64_t ewma_jumps_tot        = 0ULL;

    for (uint32_t i = 0; i < total_subs; i++) {
        if (gpu_final[i].op_type       != ref_states[i].op_type       ||
            gpu_final[i].inst_id       != ref_states[i].inst_id       ||
            gpu_final[i].s0            != ref_states[i].s0            ||
            gpu_final[i].s1            != ref_states[i].s1            ||
            gpu_final[i].s2            != ref_states[i].s2            ||
            gpu_final[i].s3            != ref_states[i].s3            ||
            gpu_final[i].out_val       != ref_states[i].out_val       ||
            gpu_final[i].trigger_count != ref_states[i].trigger_count ||
            h_egress->outputs[i]       != ref_outputs[i]) {
            mismatches++;
        }
        if (ref_states[i].op_type == OP_0_PID_Q8) {
            pid_sat_events_total += (uint64_t)(uint32_t)ref_states[i].s2;
        } else if (ref_states[i].op_type == OP_1_BIQUAD_Q12) {
            if (ref_states[i].s2 > biquad_max_peak_y) biquad_max_peak_y = ref_states[i].s2;
        } else if (ref_states[i].op_type == OP_2_HYST_WINDOW) {
            hyst_transitions_tot += (uint64_t)(uint32_t)ref_states[i].s2;
        } else if (ref_states[i].op_type == OP_3_EWMA_SLEW) {
            ewma_jumps_tot += (uint64_t)(uint32_t)ref_states[i].s3;
        }
    }

    if (sysfs_cur_mid == 0ULL && !allow_attr_clk) {
        fprintf(stderr, "[FATAL] Неможливо зчитати фактичну частоту GPU із sysfs devfreq (cur_freq == 0). "
                        "Тихий fallback на cudaDevAttrClockRate заборонено.\n");
        cudaStreamDestroy(stream);
        cudaFree(d_init);
        cudaFree(d_final);
        cudaFree(d_telemetry);
        cudaFreeHost(h_ingress);
        cudaFreeHost(h_egress);
        free(h_telemetry);
        free(host_rt_ns);
        free(host_pub_ns);
        free(host_wait_ack_ns);
        return 3;
    }

    uint64_t eff_freq_hz = sysfs_cur_mid;
    if (eff_freq_hz == 0ULL) {
        eff_freq_hz = (uint64_t)attr_clock_khz * 1000ULL;
    }
    double ns_per_cyc_actual = (eff_freq_hz > 0ULL) ? (1e9 / (double)eff_freq_hz) : 0.0;

    uint32_t n_samp = h_telemetry->recorded_samples[0];
    for (uint32_t b = 1u; b < num_blocks; b++) {
        if (h_telemetry->recorded_samples[b] < n_samp) {
            n_samp = h_telemetry->recorded_samples[b];
        }
    }

    uint64_t *max_math_cyc = (uint64_t *)calloc(n_samp ? n_samp : 1u, sizeof(uint64_t));
    uint64_t *max_e2e_cyc  = (uint64_t *)calloc(n_samp ? n_samp : 1u, sizeof(uint64_t));
    uint64_t *max_math_gt  = (uint64_t *)calloc(n_samp ? n_samp : 1u, sizeof(uint64_t));
    uint64_t *max_e2e_gt   = (uint64_t *)calloc(n_samp ? n_samp : 1u, sizeof(uint64_t));
    double    per_blk_e2e_ns_mean[KM_MAX_BLOCKS] = {0};

    uint32_t e2e_sm_spikes_gt_100us  = 0u;
    uint32_t e2e_sm_spikes_gt_1ms    = 0u;
    uint32_t math_spikes_gt_100us    = 0u;
    uint32_t host_rt_spikes_gt_100us = 0u;

    for (uint32_t i = 0u; i < n_samp; i++) {
        uint64_t mmc = 0ULL, mec = 0ULL, mmg = 0ULL, meg = 0ULL;
        for (uint32_t b = 0u; b < num_blocks; b++) {
            uint64_t mc = h_telemetry->t_math_cycles[b][i];
            uint64_t ec = h_telemetry->t_e2e_cycles[b][i];
            uint64_t mg = h_telemetry->t_math_gt_ns[b][i];
            uint64_t eg = h_telemetry->t_e2e_gt_ns[b][i];
            if (mc > mmc) mmc = mc;
            if (ec > mec) mec = ec;
            if (mg > mmg) mmg = mg;
            if (eg > meg) meg = eg;
            per_blk_e2e_ns_mean[b] += (double)ec * ns_per_cyc_actual;
        }
        max_math_cyc[i] = mmc;
        max_e2e_cyc[i]  = mec;
        max_math_gt[i]  = mmg;
        max_e2e_gt[i]   = meg;

        double ev_e2e_ns  = (double)mec * ns_per_cyc_actual;
        double ev_math_ns = (double)mmc * ns_per_cyc_actual;
        if (ev_e2e_ns > 100000.0)  e2e_sm_spikes_gt_100us++;
        if (ev_e2e_ns > 1000000.0) e2e_sm_spikes_gt_1ms++;
        if (ev_math_ns > 100000.0) math_spikes_gt_100us++;
    }
    for (uint32_t i = 0u; i < num_events; i++) {
        if (host_rt_ns[i] > 100000ULL) host_rt_spikes_gt_100us++;
    }
    if (n_samp > 0u) {
        for (uint32_t b = 0u; b < num_blocks; b++) {
            per_blk_e2e_ns_mean[b] /= (double)n_samp;
        }
    }

    km_stats_t st_math_cyc  = compute_stats(max_math_cyc,     n_samp,     false);
    km_stats_t st_e2e_cyc   = compute_stats(max_e2e_cyc,      n_samp,     true);
    km_stats_t st_math_gt   = compute_stats(max_math_gt,      n_samp,     false);
    km_stats_t st_e2e_gt    = compute_stats(max_e2e_gt,       n_samp,     true);
    km_stats_t st_e2e_b0    = compute_stats(h_telemetry->t_e2e_cycles[0], n_samp, false);
    km_stats_t st_host_pub  = compute_stats(host_pub_ns,      num_events, false);
    km_stats_t st_host_wait = compute_stats(host_wait_ack_ns, num_events, false);
    km_stats_t st_host_rt   = compute_stats(host_rt_ns,       num_events, true);

    printf("============================================================================\n");
    printf(" МАШИНА КУЗЬМІНА: HETEROGENEOUS GPU SUBSCRIBERS (EXP-GPU-03 / ISSUE #256)\n");
    printf("============================================================================\n");
    printf("  Пристрій GPU:                 %s (SM %d.%d)\n", prop.name, prop.major, prop.minor);
    printf("  Геометрія та layout:          %u x %u = %u підписників | layout=%s [%u, %u, %u, %u]\n",
           num_blocks, threads, total_subs, layout_name,
           op_counts[0], op_counts[1], op_counts[2], op_counts[3]);
    printf("  Режим маски / in / ack / slp: %s / %s / %s / %u нс\n", mask_name, ingress_mode_name, ack_mode_name, sleep_ns);
    printf("  Ізоляція хоста (--rt-pin):    req=%d affinity=%d(cpu=%d, obs=%d->%d) sched_fifo=%d(prio=%d)\n",
           rt_pin_requested ? 1 : 0, cpu_affinity_active ? 1 : 0, pinned_cpu,
           observed_cpu_start, observed_cpu_end, sched_fifo_active ? 1 : 0, active_fifo_prio);
    printf("  Частота GPU sysfs (до/під час/після, max): %.1f / %.1f / %.1f МГц (max %.1f МГц, CPU %.1f МГц)\n",
           (sysfs_cur_before > 0ULL) ? (double)sysfs_cur_before / 1e6 : 0.0,
           (double)sysfs_cur_mid / 1e6,
           (double)sysfs_cur_after / 1e6,
           (double)sysfs_max_before / 1e6,
           (double)cpu_cur_freq_khz / 1e3);
    printf("  Квант %%globaltimer / TSG us:  %" PRIu64 " нс | tsg_timeslice=[%" PRIu64 "..%" PRIu64 "] мкс\n",
           h_gt_step, tsg_min_us, tsg_max_us);
    printf("  Перевірка CPU-еталона:        %s (mismatch_count=%u, mid_run=%u із %u)\n",
           (mismatches == 0u) ? "PASS" : "FAIL", mismatches, mid_run_mismatches, total_subs);
    printf("  Активність операторів:        pid_sat=%" PRIu64 " biquad_pk=%d hyst_tr=%" PRIu64 " ewma_jmp=%" PRIu64 "\n",
           pid_sat_events_total, biquad_max_peak_y, hyst_transitions_tot, ewma_jumps_tot);
    printf("  Сплески >100 мкс (SM / Host): e2e_sm=%u (>1мс=%u) math=%u host_rt=%u із %u\n",
           e2e_sm_spikes_gt_100us, e2e_sm_spikes_gt_1ms, math_spikes_gt_100us, host_rt_spikes_gt_100us, num_events);
    printf("  --------------------------------------------------------------------------\n");
    printf("  1. ЧАС ОБЧИСЛЕННЯ ОПЕРАТОРІВ У РЕГІСТРАХ SM (max по %u варпах, %.1f МГц):\n",
           num_blocks * warps_per_blk, (double)eff_freq_hz / 1e6);
    printf("     Такти SM: mean=%.2f sigma=%.2f | min=%" PRIu64 " p50=%" PRIu64 " p99=%" PRIu64 " p99.9=%" PRIu64 " max=%" PRIu64 "\n",
           st_math_cyc.mean, st_math_cyc.stddev, st_math_cyc.min, st_math_cyc.p50, st_math_cyc.p99, st_math_cyc.p999, st_math_cyc.max);
    printf("     Фіз. нс:  mean=%.2f sigma=%.2f | min=%.2f p50=%.2f p99=%.2f p99.9=%.2f max=%.2f\n",
           st_math_cyc.mean * ns_per_cyc_actual, st_math_cyc.stddev * ns_per_cyc_actual,
           st_math_cyc.min * ns_per_cyc_actual, st_math_cyc.p50 * ns_per_cyc_actual,
           st_math_cyc.p99 * ns_per_cyc_actual, st_math_cyc.p999 * ns_per_cyc_actual,
           st_math_cyc.max * ns_per_cyc_actual);
    printf("     %%globaltimer нс: mean=%.2f | min=%" PRIu64 " p50=%" PRIu64 " p99=%" PRIu64 " max=%" PRIu64 "\n",
           st_math_gt.mean, st_math_gt.min, st_math_gt.p50, st_math_gt.p99, st_math_gt.max);
    printf("  --------------------------------------------------------------------------\n");
    printf("  2. ПОВНИЙ ЧАС НА SM (T_e2e_sm, max по %u блоках; блок 0 mean=%.2f нс):\n",
           num_blocks, st_e2e_b0.mean * ns_per_cyc_actual);
    printf("     Такти SM: mean=%.2f sigma=%.2f | min=%" PRIu64 " p50=%" PRIu64 " p99=%" PRIu64 " p99.9=%" PRIu64 " max=%" PRIu64 "\n",
           st_e2e_cyc.mean, st_e2e_cyc.stddev, st_e2e_cyc.min, st_e2e_cyc.p50, st_e2e_cyc.p99, st_e2e_cyc.p999, st_e2e_cyc.max);
    printf("     Фіз. нс:  mean=%.2f sigma=%.2f | min=%.2f p50=%.2f p99=%.2f [%.2f..%.2f] p99.9=%.2f [%.2f..%.2f] max=%.2f\n",
           st_e2e_cyc.mean * ns_per_cyc_actual, st_e2e_cyc.stddev * ns_per_cyc_actual,
           st_e2e_cyc.min * ns_per_cyc_actual, st_e2e_cyc.p50 * ns_per_cyc_actual,
           st_e2e_cyc.p99 * ns_per_cyc_actual, st_e2e_cyc.p99_ci_lo * ns_per_cyc_actual, st_e2e_cyc.p99_ci_hi * ns_per_cyc_actual,
           st_e2e_cyc.p999 * ns_per_cyc_actual, st_e2e_cyc.p999_ci_lo * ns_per_cyc_actual, st_e2e_cyc.p999_ci_hi * ns_per_cyc_actual,
           st_e2e_cyc.max * ns_per_cyc_actual);
    printf("     %%globaltimer нс: mean=%.2f sigma=%.2f | min=%" PRIu64 " p50=%" PRIu64 " p99=%" PRIu64 " [%" PRIu64 "..%" PRIu64 "] p99.9=%" PRIu64 " [%" PRIu64 "..%" PRIu64 "] max=%" PRIu64 "\n",
           st_e2e_gt.mean, st_e2e_gt.stddev, st_e2e_gt.min, st_e2e_gt.p50,
           st_e2e_gt.p99, st_e2e_gt.p99_ci_lo, st_e2e_gt.p99_ci_hi,
           st_e2e_gt.p999, st_e2e_gt.p999_ci_lo, st_e2e_gt.p999_ci_hi,
           st_e2e_gt.max);
    printf("  --------------------------------------------------------------------------\n");
    printf("  3. НАСКРІЗНИЙ ROUND-TRIP HOST CPU -> L2 -> SM -> L2 -> HOST CPU (CLOCK_MONOTONIC_RAW):\n");
    printf("     Pub нс:   mean=%.1f sigma=%.1f | min=%" PRIu64 " p50=%" PRIu64 " p99=%" PRIu64 " p99.9=%" PRIu64 " max=%" PRIu64 "\n",
           st_host_pub.mean, st_host_pub.stddev, st_host_pub.min, st_host_pub.p50, st_host_pub.p99, st_host_pub.p999, st_host_pub.max);
    printf("     Wait нс:  mean=%.1f sigma=%.1f | min=%" PRIu64 " p50=%" PRIu64 " p99=%" PRIu64 " p99.9=%" PRIu64 " max=%" PRIu64 "\n",
           st_host_wait.mean, st_host_wait.stddev, st_host_wait.min, st_host_wait.p50, st_host_wait.p99, st_host_wait.p999, st_host_wait.max);
    printf("     Фіз. нс:  mean=%.1f sigma=%.1f | min=%" PRIu64 " p50=%" PRIu64 " p99=%" PRIu64 " [%" PRIu64 "..%" PRIu64 "] p99.9=%" PRIu64 " [%" PRIu64 "..%" PRIu64 "] max=%" PRIu64 " (wall=%.2f мс)\n",
           st_host_rt.mean, st_host_rt.stddev, st_host_rt.min, st_host_rt.p50,
           st_host_rt.p99, st_host_rt.p99_ci_lo, st_host_rt.p99_ci_hi,
           st_host_rt.p999, st_host_rt.p999_ci_lo, st_host_rt.p999_ci_hi,
           st_host_rt.max, (double)(t_wall_end - t_wall_start) / 1e6);
    printf("============================================================================\n");

    if (json_out != NULL) {
        FILE *jf = fopen(json_out, "w");
        if (jf) {
            fprintf(jf,
                "{\n"
                "  \"experiment\": \"EXP-GPU-03\", \"issue\": 256,\n"
                "  \"blocks\": %u, \"threads\": %u, \"subscribers\": %u,\n"
                "  \"layout\": \"%s\", \"op_counts\": [%u, %u, %u, %u],\n"
                "  \"mask\": \"%s\", \"ingress_mode\": \"%s\", \"ack_mode\": \"%s\", \"sleep_ns\": %u, \"events\": %u,\n"
                "  \"rt_pin_requested\": %s, \"cpu_affinity_active\": %s, \"pinned_cpu\": %d,\n"
                "  \"observed_cpu_start\": %d, \"observed_cpu_end\": %d,\n"
                "  \"sched_fifo_active\": %s, \"sched_fifo_priority\": %d, \"sched_fifo_errno\": %d,\n"
                "  \"sysfs_cur_freq_hz\": %" PRIu64 ", \"sysfs_min_freq_hz\": %" PRIu64 ", \"sysfs_max_freq_hz\": %" PRIu64 ",\n"
                "  \"cpu_cur_freq_khz\": %" PRIu64 ", \"tsg_timeslice_min_us\": %" PRIu64 ", \"tsg_timeslice_max_us\": %" PRIu64 ",\n"
                "  \"globaltimer_quantum_ns\": %" PRIu64 ",\n"
                "  \"mid_run_mismatches\": %u, \"mismatches\": %u, \"mismatch_count\": %u,\n"
                "  \"pid_sat_events_total\": %" PRIu64 ", \"biquad_max_peak_y\": %d, \"hyst_transitions_total\": %" PRIu64 ", \"ewma_jumps_total\": %" PRIu64 ",\n"
                "  \"e2e_sm_spikes_gt_100us\": %u, \"e2e_sm_spikes_gt_1ms\": %u, \"math_spikes_gt_100us\": %u, \"host_rt_spikes_gt_100us\": %u,\n"
                "  \"bootstrap_iters\": %u, \"bootstrap_seed\": \"0x%llx\",\n"
                "  \"math_cycles_mean\": %.3f, \"math_cycles_sigma\": %.3f, \"math_cycles_min\": %" PRIu64 ", \"math_cycles_p50\": %" PRIu64 ", \"math_cycles_p99\": %" PRIu64 ", \"math_cycles_p999\": %" PRIu64 ", \"math_cycles_max\": %" PRIu64 ",\n"
                "  \"math_ns_mean\": %.3f, \"math_ns_sigma\": %.3f, \"math_ns_p50\": %.3f, \"math_ns_p99\": %.3f, \"math_ns_p999\": %.3f, \"math_ns_max\": %.3f,\n"
                "  \"math_gt_ns_mean\": %.3f, \"math_gt_ns_p50\": %" PRIu64 ", \"math_gt_ns_p99\": %" PRIu64 ", \"math_gt_ns_p999\": %" PRIu64 ", \"math_gt_ns_max\": %" PRIu64 ",\n"
                "  \"e2e_sm_cycles_mean\": %.3f, \"e2e_sm_cycles_sigma\": %.3f, \"e2e_sm_cycles_min\": %" PRIu64 ", \"e2e_sm_cycles_p50\": %" PRIu64 ", \"e2e_sm_cycles_p99\": %" PRIu64 ", \"e2e_sm_cycles_p999\": %" PRIu64 ", \"e2e_sm_cycles_max\": %" PRIu64 ",\n"
                "  \"e2e_sm_ns_mean\": %.3f, \"e2e_sm_ns_sigma\": %.3f, \"e2e_sm_ns_min\": %.3f, \"e2e_sm_ns_p50\": %.3f, \"e2e_sm_ns_p99\": %.3f, \"e2e_sm_ns_p99_ci95_lo\": %.3f, \"e2e_sm_ns_p99_ci95_hi\": %.3f, \"e2e_sm_ns_p999\": %.3f, \"e2e_sm_ns_p999_ci95_lo\": %.3f, \"e2e_sm_ns_p999_ci95_hi\": %.3f, \"e2e_sm_ns_max\": %.3f,\n"
                "  \"e2e_sm_b0_ns_mean\": %.3f, \"e2e_sm_b0_ns_p999\": %.3f,\n"
                "  \"e2e_gt_ns_mean\": %.3f, \"e2e_gt_ns_sigma\": %.3f, \"e2e_gt_ns_p50\": %" PRIu64 ", \"e2e_gt_ns_p99\": %" PRIu64 ", \"e2e_gt_ns_p99_ci95_lo\": %" PRIu64 ", \"e2e_gt_ns_p99_ci95_hi\": %" PRIu64 ", \"e2e_gt_ns_p999\": %" PRIu64 ", \"e2e_gt_ns_p999_ci95_lo\": %" PRIu64 ", \"e2e_gt_ns_p999_ci95_hi\": %" PRIu64 ", \"e2e_gt_ns_max\": %" PRIu64 ",\n"
                "  \"host_pub_ns_mean\": %.3f, \"host_pub_ns_sigma\": %.3f, \"host_pub_ns_p50\": %" PRIu64 ", \"host_pub_ns_p99\": %" PRIu64 ", \"host_pub_ns_p999\": %" PRIu64 ", \"host_pub_ns_max\": %" PRIu64 ",\n"
                "  \"host_wait_ack_ns_mean\": %.3f, \"host_wait_ack_ns_sigma\": %.3f, \"host_wait_ack_ns_p50\": %" PRIu64 ", \"host_wait_ack_ns_p99\": %" PRIu64 ", \"host_wait_ack_ns_p999\": %" PRIu64 ", \"host_wait_ack_ns_max\": %" PRIu64 ",\n"
                "  \"host_rt_ns_mean\": %.3f, \"host_rt_ns_sigma\": %.3f, \"host_rt_ns_p50\": %" PRIu64 ", \"host_rt_ns_p99\": %" PRIu64 ", \"host_rt_ns_p99_ci95_lo\": %" PRIu64 ", \"host_rt_ns_p99_ci95_hi\": %" PRIu64 ", \"host_rt_ns_p999\": %" PRIu64 ", \"host_rt_ns_p999_ci95_lo\": %" PRIu64 ", \"host_rt_ns_p999_ci95_hi\": %" PRIu64 ", \"host_rt_ns_max\": %" PRIu64 ",\n"
                "  \"host_rt_us_mean\": %.4f, \"host_rt_us_sigma\": %.4f, \"host_rt_us_p50\": %.4f, \"host_rt_us_p99\": %.4f, \"host_rt_us_p999\": %.4f, \"host_rt_us_max\": %.4f,\n"
                "  \"per_block_e2e_sm_ns_mean\": [",
                num_blocks, threads, total_subs,
                layout_name, op_counts[0], op_counts[1], op_counts[2], op_counts[3],
                mask_name, ingress_mode_name, ack_mode_name, sleep_ns, num_events,
                rt_pin_requested ? "true" : "false",
                cpu_affinity_active ? "true" : "false",
                pinned_cpu,
                observed_cpu_start, observed_cpu_end,
                sched_fifo_active ? "true" : "false",
                active_fifo_prio, sched_fifo_errno,
                eff_freq_hz, sysfs_min_before, sysfs_max_before,
                cpu_cur_freq_khz, tsg_min_us, tsg_max_us,
                h_gt_step,
                mid_run_mismatches, mismatches, mismatches,
                pid_sat_events_total, biquad_max_peak_y, hyst_transitions_tot, ewma_jumps_tot,
                e2e_sm_spikes_gt_100us, e2e_sm_spikes_gt_1ms, math_spikes_gt_100us, host_rt_spikes_gt_100us,
                KM_BOOTSTRAP_ITERS, (unsigned long long)KM_BOOTSTRAP_SEED,
                st_math_cyc.mean, st_math_cyc.stddev, st_math_cyc.min, st_math_cyc.p50, st_math_cyc.p99, st_math_cyc.p999, st_math_cyc.max,
                st_math_cyc.mean * ns_per_cyc_actual, st_math_cyc.stddev * ns_per_cyc_actual,
                st_math_cyc.p50 * ns_per_cyc_actual, st_math_cyc.p99 * ns_per_cyc_actual,
                st_math_cyc.p999 * ns_per_cyc_actual, st_math_cyc.max * ns_per_cyc_actual,
                st_math_gt.mean, st_math_gt.p50, st_math_gt.p99, st_math_gt.p999, st_math_gt.max,
                st_e2e_cyc.mean, st_e2e_cyc.stddev, st_e2e_cyc.min, st_e2e_cyc.p50, st_e2e_cyc.p99, st_e2e_cyc.p999, st_e2e_cyc.max,
                st_e2e_cyc.mean * ns_per_cyc_actual, st_e2e_cyc.stddev * ns_per_cyc_actual, st_e2e_cyc.min * ns_per_cyc_actual,
                st_e2e_cyc.p50 * ns_per_cyc_actual,
                st_e2e_cyc.p99 * ns_per_cyc_actual, st_e2e_cyc.p99_ci_lo * ns_per_cyc_actual, st_e2e_cyc.p99_ci_hi * ns_per_cyc_actual,
                st_e2e_cyc.p999 * ns_per_cyc_actual, st_e2e_cyc.p999_ci_lo * ns_per_cyc_actual, st_e2e_cyc.p999_ci_hi * ns_per_cyc_actual,
                st_e2e_cyc.max * ns_per_cyc_actual,
                st_e2e_b0.mean * ns_per_cyc_actual, st_e2e_b0.p999 * ns_per_cyc_actual,
                st_e2e_gt.mean, st_e2e_gt.stddev, st_e2e_gt.p50,
                st_e2e_gt.p99, st_e2e_gt.p99_ci_lo, st_e2e_gt.p99_ci_hi,
                st_e2e_gt.p999, st_e2e_gt.p999_ci_lo, st_e2e_gt.p999_ci_hi,
                st_e2e_gt.max,
                st_host_pub.mean, st_host_pub.stddev, st_host_pub.p50, st_host_pub.p99, st_host_pub.p999, st_host_pub.max,
                st_host_wait.mean, st_host_wait.stddev, st_host_wait.p50, st_host_wait.p99, st_host_wait.p999, st_host_wait.max,
                st_host_rt.mean, st_host_rt.stddev, st_host_rt.p50,
                st_host_rt.p99, st_host_rt.p99_ci_lo, st_host_rt.p99_ci_hi,
                st_host_rt.p999, st_host_rt.p999_ci_lo, st_host_rt.p999_ci_hi,
                st_host_rt.max,
                st_host_rt.mean / 1000.0, st_host_rt.stddev / 1000.0,
                (double)st_host_rt.p50 / 1000.0, (double)st_host_rt.p99 / 1000.0,
                (double)st_host_rt.p999 / 1000.0, (double)st_host_rt.max / 1000.0
            );
            for (uint32_t b = 0u; b < num_blocks; b++) {
                fprintf(jf, "%s%.3f", (b > 0u) ? ", " : "", per_blk_e2e_ns_mean[b]);
            }
            fprintf(jf, "]\n}\n");
            fclose(jf);
        }
    }

    free(max_math_cyc);
    free(max_e2e_cyc);
    free(max_math_gt);
    free(max_e2e_gt);
    cudaStreamDestroy(stream);
    cudaFree(d_init);
    cudaFree(d_final);
    cudaFree(d_telemetry);
    cudaFreeHost(h_ingress);
    cudaFreeHost(h_egress);
    free(h_telemetry);
    free(host_rt_ns);
    free(host_pub_ns);
    free(host_wait_ack_ns);

    return (mismatches == 0u) ? 0 : 1;
}
