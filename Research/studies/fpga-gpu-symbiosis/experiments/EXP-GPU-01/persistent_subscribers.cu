/* ============================================================================
 * Машина Кузьміна (Kuzmin Machine) — Гетерогенний симбіоз з GPU (ADR B6)
 * Файл: persistent_subscribers.cu
 * Issue: #225 (EXP-GPU-01 Фаза 3–4: метрологічна герметизація та масштабування)
 * Цільова платформа: Seeed Studio reServer Industrial J501 (Jetson AGX Orin 64GB)
 * Архітектура GPU: NVIDIA Ampere (GA10B, SM 8.7)
 *
 * Ключові архітектурні інваріанти (виправлення дефектів прототипу):
 *   1. Суворе розділення L2 кеш-ліній (128 Б):
 *      - km_event_ingress_t (рівно 128 Б) — лише читання з боку GPU;
 *      - km_event_egress_t  (вирівняно по 128 Б) — окремі лінії ack та виходів,
 *        умовний предикатний запис outputs[] ЛИШЕ для активних підписників.
 *   2. Стан підписників утримується виключно в регістровому файлі SM під час
 *      персистентного циклу (1 такт, 0 банкових конфліктів); фіксована кома Q8.
 *   3. Подвійна апаратна метрологія без захардкоджених частот:
 *      - clock64() (такти SM) + фактична частота GPU із sysfs devfreq;
 *      - %globaltimer (фізичний 64-бітний апаратний таймер нс, незалежний від DVFS);
 *      - буфер телеметрії у device-local пам'яті (cudaMalloc), без snooping-трафіку;
 *      - CLOCK_MONOTONIC_RAW по кожній події на боці хоста (p50/p99/p99.9/max/sigma).
 *   4. Масштабування 32..512 підписників:
 *      - Single-SM Multi-Warp (1 блок x 1..16 варпів): лише tid==0 опитує L2;
 *      - Multi-SM (K блоків x 1 варп): емпірична перевірка L2 snoop contention.
 *   5. Незалежна побітова перевірка всіх станів/виходів проти еталонної CPU-моделі.
 * ============================================================================ */

#include <cuda_runtime.h>
#include <inttypes.h>
#include <math.h>
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
#define KM_BOOTSTRAP_SEED     0x5EED22901234ULL

/* --- Вхідна когерентна скринька подій: рівно одна 128-байтна лінія L2 на слот SM --- */
typedef struct __align__(128) {
    uint32_t seq_id;                         /* [0..3]    Лічильник події (release/acquire) */
    uint32_t stop_flag;                      /* [4..7]    1 = штатне завершення кернела */
    int32_t  concept_val;                    /* [8..11]   Стан концепту після коміту (•) */
    uint32_t active_words;                   /* [12..15]  Кількість слів маски у слоті (1..16) */
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
    uint32_t      packed_ack[KM_MAX_BLOCKS];   /* [0..63]     Суміжний масив для A/B (packed) */
    uint32_t      pad_packed[16];              /* [64..127]   Ізоляція від isolated_ack */
    km_ack_line_t isolated_ack[KM_MAX_BLOCKS]; /* [128..2175] Окрема 128-Б лінія на кожен блок */
    int32_t       outputs[KM_MAX_SUBSCRIBERS]; /* [2176..]    Виходи підписників (предикатний запис) */
} km_event_egress_t;

static_assert(offsetof(km_event_egress_t, isolated_ack) == 128, "isolated_ack must start on a separate 128B cache line");
static_assert(offsetof(km_event_egress_t, outputs) == 128 + KM_MAX_BLOCKS * 128, "outputs must start on a separate 128B cache line");

/* --- Дескриптор стану підписника (ініціалізація та фінальна верифікація) --- */
typedef struct {
    int32_t  target;
    int32_t  kp;
    int32_t  ki_q8;        /* Масштабований у Q8 інтегральний коефіцієнт (>> 8 замість ділення) */
    int32_t  kd;
    int32_t  integral;
    int32_t  prev_err;
    int32_t  out_val;
    uint32_t trigger_count;
} km_sub_state_t;

/* --- Буфер телеметрії у локальній пам'яті GPU (cudaMalloc, окремо для кожного блока) --- */
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

__device__ __forceinline__ uint32_t km_ld_cg_u32(const uint32_t *ptr) {
    uint32_t val = 0;
#if __CUDA_ARCH__ >= 700
    asm volatile("ld.global.cg.u32 %0, [%1];" : "=r"(val) : "l"(ptr));
#else
    val = *(const volatile uint32_t *)ptr;
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

/* ============================================================================
 * ПЕРСИСТЕНТНЕ ЯДРО GPU (1..16 варпів у блоці, 1..16 блоків)
 * ============================================================================ */
__global__ void __launch_bounds__(512, 1) km_persistent_subscribers_kernel(
    const km_event_ingress_t * __restrict__ ingress,
    km_event_egress_t        * __restrict__ egress,
    km_telemetry_t           * __restrict__ telemetry,
    const km_sub_state_t     * __restrict__ init_states,
    km_sub_state_t           * __restrict__ final_states,
    uint32_t                                sleep_ns,
    uint32_t                                ack_isolated,
    uint32_t                                ingress_partitioned
) {
    const uint32_t tid        = threadIdx.x;
    const uint32_t lane_id    = tid & 31u;
    const uint32_t warp_id    = tid >> 5u;
    const uint32_t global_id  = blockIdx.x * blockDim.x + tid;
    const uint32_t mask_word  = global_id >> 5u;
    const bool     single_warp = (blockDim.x == KM_WARP_SIZE);
    const km_event_ingress_t *my_in = (ingress_partitioned != 0u) ? &ingress[blockIdx.x] : &ingress[0];

    __shared__ uint32_t s_cur_seq;
    __shared__ uint32_t s_stop;
    __shared__ int32_t  s_cval;
    __shared__ uint32_t s_masks[KM_MAX_WARPS_PER_BLK];

    /* 1. Завантаження робочого стану підписника у регістровий файл SM */
    km_sub_state_t st = init_states[global_id];
    int32_t  reg_target   = st.target;
    int32_t  reg_kp       = st.kp;
    int32_t  reg_ki_q8    = st.ki_q8;
    int32_t  reg_kd       = st.kd;
    int32_t  reg_integral = st.integral;
    int32_t  reg_prev_err = st.prev_err;
    int32_t  reg_out_val  = st.out_val;
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
            /* Шлях 1 варпа (32 нитки): обмін виключно через регістровий __shfl_sync */
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
                    if (ingress_partitioned != 0u) {
                        mask = *(const volatile uint32_t *)&my_in->event_mask[0];
                    } else {
                        mask = (mask_word < KM_SLOT_MASK_WORDS)
                            ? *(const volatile uint32_t *)&ingress[0].event_mask[mask_word]
                            : *(const volatile uint32_t *)&ingress[1].event_mask[mask_word - KM_SLOT_MASK_WORDS];
                    }
                }
                c_val = __shfl_sync(0xFFFFFFFFu, c_val, 0);
                mask  = __shfl_sync(0xFFFFFFFFu, mask, 0);

                bool is_active = ((mask & (1u << lane_id)) != 0u);

                uint64_t t_math_c0 = clock64();
                uint64_t t_math_g0 = km_read_globaltimer();

                /* Бездивергентне обчислення ПІД у регістрах SM (предикати SEL) */
                int32_t in_val    = c_val + (int32_t)global_id;
                int32_t err       = in_val - reg_target;
                int32_t p_term    = err * reg_kp;
                int32_t d_term    = (err - reg_prev_err) * reg_kd;
                int32_t cand_int  = reg_integral + err;
                int32_t i_term    = (cand_int * reg_ki_q8) >> 8;
                int32_t cand_out  = p_term + d_term + i_term;

                reg_integral = is_active ? cand_int : reg_integral;
                reg_prev_err = is_active ? err      : reg_prev_err;
                reg_out_val  = is_active ? cand_out : reg_out_val;
                reg_triggers = is_active ? (reg_triggers + 1u) : reg_triggers;

                uint64_t t_math_c1 = clock64();
                uint64_t t_math_g1 = km_read_globaltimer();

                /* Предикатний запис у вихідну лінію ЛИШЕ для активних підписників */
                if (is_active) {
                    egress->outputs[global_id] = reg_out_val;
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
            /* Шлях 1 блока x 2..16 варпів (64..512 ниток на одному SM):
             * ЛИШЕ tid == 0 опитує власний слот L2 під час очікування,
             * а s_cval та s_masks читаються ПІСЛЯ acquire-бар'єра! */
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
                if (tid < (blockDim.x >> 5u)) {
                    if (ingress_partitioned != 0u) {
                        s_masks[tid] = *(const volatile uint32_t *)&my_in->event_mask[tid];
                    } else {
                        uint32_t gw = (blockIdx.x * (blockDim.x >> 5u)) + tid;
                        s_masks[tid] = (gw < KM_SLOT_MASK_WORDS)
                            ? *(const volatile uint32_t *)&ingress[0].event_mask[gw]
                            : *(const volatile uint32_t *)&ingress[1].event_mask[gw - KM_SLOT_MASK_WORDS];
                    }
                }
                __syncthreads();

                int32_t  c_val = s_cval;
                uint32_t mask  = s_masks[warp_id];
                bool is_active = ((mask & (1u << lane_id)) != 0u);

                uint64_t t_math_c0 = clock64();
                uint64_t t_math_g0 = km_read_globaltimer();

                int32_t in_val    = c_val + (int32_t)global_id;
                int32_t err       = in_val - reg_target;
                int32_t p_term    = err * reg_kp;
                int32_t d_term    = (err - reg_prev_err) * reg_kd;
                int32_t cand_int  = reg_integral + err;
                int32_t i_term    = (cand_int * reg_ki_q8) >> 8;
                int32_t cand_out  = p_term + d_term + i_term;

                reg_integral = is_active ? cand_int : reg_integral;
                reg_prev_err = is_active ? err      : reg_prev_err;
                reg_out_val  = is_active ? cand_out : reg_out_val;
                reg_triggers = is_active ? (reg_triggers + 1u) : reg_triggers;

                uint64_t t_math_c1 = clock64();
                uint64_t t_math_g1 = km_read_globaltimer();

                if (is_active) {
                    egress->outputs[global_id] = reg_out_val;
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
                        uint32_t idx = cur_seq - 1u;
                        telemetry->t_math_cycles[blockIdx.x][idx] = t_math_c1 - t_math_c0;
                        telemetry->t_e2e_cycles[blockIdx.x][idx]  = t_e2e_c1  - t_e2e_c0;
                        telemetry->t_math_gt_ns[blockIdx.x][idx]  = t_math_g1 - t_math_g0;
                        telemetry->t_e2e_gt_ns[blockIdx.x][idx]   = t_e2e_g1  - t_e2e_g0;
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

    /* 2. Вивантаження фінальних регістрових станів для незалежної CPU-верифікації */
    st.integral      = reg_integral;
    st.prev_err      = reg_prev_err;
    st.out_val       = reg_out_val;
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
 * ДОПОМІЖНІ ФУНКЦІЇ ХОСТА: SYSFS ЧАСТОТА, СТАТИСТИКА, ЕТАЛОННА CPU-МОДЕЛЬ
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
        st.p99_ci_lo = st.p99_ci_hi = st.p99;
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

/* Незалежна еталонна CPU-модель (AGENTS.md §4.3 — без тавтологій) */
static void cpu_reference_step(
    km_sub_state_t *ref_states,
    int32_t        *ref_outputs,
    uint32_t        total_subs,
    int32_t         c_val,
    const uint32_t *mask_words
) {
    for (uint32_t gid = 0; gid < total_subs; gid++) {
        uint32_t w = gid >> 5u;
        uint32_t b = gid & 31u;
        bool active = ((mask_words[w] & (1u << b)) != 0u);
        if (active) {
            int32_t in_val   = c_val + (int32_t)gid;
            int32_t err      = in_val - ref_states[gid].target;
            int32_t p_term   = err * ref_states[gid].kp;
            int32_t d_term   = (err - ref_states[gid].prev_err) * ref_states[gid].kd;
            int32_t new_int  = ref_states[gid].integral + err;
            int32_t i_term   = (new_int * ref_states[gid].ki_q8) >> 8;
            int32_t out_val  = p_term + d_term + i_term;

            ref_states[gid].integral      = new_int;
            ref_states[gid].prev_err      = err;
            ref_states[gid].out_val       = out_val;
            ref_states[gid].trigger_count += 1u;
            ref_outputs[gid]              = out_val;
        }
    }
}

int main(int argc, char **argv) {
    uint32_t       num_events      = 1000u;
    uint32_t       num_blocks      = 1u;
    uint32_t       threads         = 32u;
    uint32_t       sleep_ns        = 0u;
    km_mask_mode_t mask_mode       = MASK_ALL;
    const char    *mask_name        = "all";
    const char    *ack_mode_name    = "isolated";
    uint32_t       ack_isolated     = 1u;
    const char    *ingress_mode_name = "partitioned";
    uint32_t       ingress_part     = 1u;
    bool           allow_attr_clk   = false;
    const char    *json_out         = NULL;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--events") == 0 && i + 1 < argc) {
            num_events = (uint32_t)strtoul(argv[++i], NULL, 10);
        } else if (strcmp(argv[i], "--blocks") == 0 && i + 1 < argc) {
            num_blocks = (uint32_t)strtoul(argv[++i], NULL, 10);
        } else if (strcmp(argv[i], "--threads") == 0 && i + 1 < argc) {
            threads = (uint32_t)strtoul(argv[++i], NULL, 10);
        } else if (strcmp(argv[i], "--sleep-ns") == 0 && i + 1 < argc) {
            sleep_ns = (uint32_t)strtoul(argv[++i], NULL, 10);
        } else if (strcmp(argv[i], "--ack-mode") == 0 && i + 1 < argc) {
            ack_mode_name = argv[++i];
            if (strcmp(ack_mode_name, "isolated") == 0) {
                ack_isolated = 1u;
            } else if (strcmp(ack_mode_name, "packed") == 0) {
                ack_isolated = 0u;
            } else {
                fprintf(stderr, "[FATAL] Невідомий режим --ack-mode: %s (очікується isolated|packed)\n", ack_mode_name);
                return 2;
            }
        } else if (strcmp(argv[i], "--ingress-mode") == 0 && i + 1 < argc) {
            ingress_mode_name = argv[++i];
            if (strcmp(ingress_mode_name, "partitioned") == 0) {
                ingress_part = 1u;
            } else if (strcmp(ingress_mode_name, "shared") == 0) {
                ingress_part = 0u;
            } else {
                fprintf(stderr, "[FATAL] Невідомий режим --ingress-mode: %s (очікується partitioned|shared)\n", ingress_mode_name);
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

    km_sub_state_t init_states[KM_MAX_SUBSCRIBERS];
    km_sub_state_t ref_states[KM_MAX_SUBSCRIBERS];
    int32_t        ref_outputs[KM_MAX_SUBSCRIBERS];
    for (uint32_t i = 0; i < total_subs; i++) {
        init_states[i].target        = 20 + (int32_t)(i & 63u);
        init_states[i].kp            = 2;
        init_states[i].ki_q8         = 26; /* ~0.1015625 у форматі Q8 */
        init_states[i].kd            = 1;
        init_states[i].integral      = 0;
        init_states[i].prev_err      = 0;
        init_states[i].out_val       = -7777;
        init_states[i].trigger_count = 0u;
        ref_outputs[i]               = -7777;
        h_egress->outputs[i]         = -7777;
    }
    memcpy(ref_states, init_states, sizeof(init_states));

    km_sub_state_t *d_init = NULL, *d_final = NULL;
    cudaMalloc((void **)&d_init,  total_subs * sizeof(km_sub_state_t));
    cudaMalloc((void **)&d_final, total_subs * sizeof(km_sub_state_t));
    cudaMemcpy(d_init, init_states, total_subs * sizeof(km_sub_state_t), cudaMemcpyHostToDevice);

    cudaStream_t stream;
    cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking);

    km_persistent_subscribers_kernel<<<num_blocks, threads, 0, stream>>>(
        d_ingress, d_egress, d_telemetry, d_init, d_final, sleep_ns, ack_isolated, ingress_part
    );
    cudaError_t launch_err = cudaGetLastError();
    if (launch_err != cudaSuccess) {
        fprintf(stderr, "[FATAL] Помилка запуску кернела: %s\n", cudaGetErrorString(launch_err));
        return 1;
    }

    usleep(30000); /* 30 мс на вихід SM у цикл очікування */
    uint64_t sysfs_cur_mid = read_gpu_sysfs_freq_hz("cur_freq");

    uint64_t *host_rt_ns = (uint64_t *)calloc(num_events, sizeof(uint64_t));
    uint32_t  mask_words_used = (total_subs + 31u) / 32u;
    uint32_t  local_masks[KM_MASK_WORDS];
    memset(local_masks, 0, sizeof(local_masks));

    uint32_t  warps_per_blk = threads >> 5u;
    uint32_t  mid_run_mismatches = 0u;
    uint64_t  t_wall_start = host_monotonic_raw_ns();

    for (uint32_t ev = 1u; ev <= num_events; ev++) {
        int32_t c_val = (int32_t)(25 + (ev % 15u));
        for (uint32_t w = 0; w < mask_words_used; w++) {
            local_masks[w] = generate_mask_word(mask_mode, ev, w);
        }

        uint64_t t0;
        if (ingress_part != 0u) {
            for (uint32_t b = 0; b < num_blocks; b++) {
                h_ingress[b].concept_val  = c_val;
                h_ingress[b].active_words = warps_per_blk;
                for (uint32_t w = 0; w < warps_per_blk; w++) {
                    h_ingress[b].event_mask[w] = local_masks[b * warps_per_blk + w];
                }
            }
            t0 = host_monotonic_raw_ns();
            for (uint32_t b = 0; b < num_blocks; b++) {
                __atomic_store_n(&h_ingress[b].seq_id, ev, __ATOMIC_RELEASE);
            }
        } else {
            h_ingress[0].concept_val  = c_val;
            h_ingress[0].active_words = mask_words_used;
            for (uint32_t w = 0; w < mask_words_used; w++) {
                if (w < KM_SLOT_MASK_WORDS) {
                    h_ingress[0].event_mask[w] = local_masks[w];
                } else {
                    h_ingress[1].event_mask[w - KM_SLOT_MASK_WORDS] = local_masks[w];
                }
            }
            t0 = host_monotonic_raw_ns();
            __atomic_store_n(&h_ingress[0].seq_id, ev, __ATOMIC_RELEASE);
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
        host_rt_ns[ev - 1u] = t1 - t0;

        if (ev == (num_events / 2u)) {
            uint64_t f_sample = read_gpu_sysfs_freq_hz("cur_freq");
            if (f_sample > sysfs_cur_mid) sysfs_cur_mid = f_sample;
        }

        cpu_reference_step(ref_states, ref_outputs, total_subs, c_val, local_masks);

        if ((ev % 100u) == 0u || ev == num_events) {
            for (uint32_t i = 0; i < total_subs; i++) {
                if (h_egress->outputs[i] != ref_outputs[i]) {
                    mid_run_mismatches++;
                }
            }
        }
    }

    uint64_t t_wall_end   = host_monotonic_raw_ns();
    uint64_t sysfs_cur_after = read_gpu_sysfs_freq_hz("cur_freq");

    /* Штатна зупинка персистентного кернела на всіх вхідних слотах */
    for (uint32_t b = 0; b < num_blocks; b++) {
        __atomic_store_n(&h_ingress[b].stop_flag, 1u, __ATOMIC_RELAXED);
        __atomic_store_n(&h_ingress[b].seq_id, num_events + 1u, __ATOMIC_RELEASE);
    }
    cudaStreamSynchronize(stream);

    cudaMemcpy(h_telemetry, d_telemetry, sizeof(km_telemetry_t), cudaMemcpyDeviceToHost);

    km_sub_state_t gpu_final[KM_MAX_SUBSCRIBERS];
    cudaMemcpy(gpu_final, d_final, total_subs * sizeof(km_sub_state_t), cudaMemcpyDeviceToHost);

    /* Незалежна побітова перевірка станів та поштових виходів проти CPU-еталона */
    uint32_t mismatches = mid_run_mismatches;
    for (uint32_t i = 0; i < total_subs; i++) {
        if (gpu_final[i].integral      != ref_states[i].integral ||
            gpu_final[i].prev_err      != ref_states[i].prev_err ||
            gpu_final[i].out_val       != ref_states[i].out_val  ||
            gpu_final[i].trigger_count != ref_states[i].trigger_count ||
            h_egress->outputs[i]       != ref_outputs[i]) {
            mismatches++;
        }
    }

    if (sysfs_cur_mid == 0ULL && !allow_attr_clk) {
        fprintf(stderr, "[FATAL] Неможливо зчитати фактичну частоту GPU із sysfs devfreq (cur_freq == 0). "
                        "Тихий fallback на cudaDevAttrClockRate заборонено (F-5). "
                        "Використовуйте --allow-attr-clock лише для діагностики.\n");
        cudaStreamDestroy(stream);
        cudaFree(d_init);
        cudaFree(d_final);
        cudaFree(d_telemetry);
        cudaFreeHost(h_ingress);
        cudaFreeHost(h_egress);
        free(h_telemetry);
        free(host_rt_ns);
        return 3;
    }

    uint64_t eff_freq_hz = sysfs_cur_mid;
    if (eff_freq_hz == 0ULL) {
        fprintf(stderr, "[WARN] Вимушений fallback на cudaDevAttrClockRate (%d кГц) через --allow-attr-clock.\n",
                attr_clock_khz);
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
    }
    if (n_samp > 0u) {
        for (uint32_t b = 0u; b < num_blocks; b++) {
            per_blk_e2e_ns_mean[b] /= (double)n_samp;
        }
    }

    km_stats_t st_math_cyc  = compute_stats(max_math_cyc, n_samp, false);
    km_stats_t st_e2e_cyc   = compute_stats(max_e2e_cyc,  n_samp, true);
    km_stats_t st_math_gt   = compute_stats(max_math_gt,  n_samp, false);
    km_stats_t st_e2e_gt    = compute_stats(max_e2e_gt,   n_samp, true);
    km_stats_t st_e2e_b0    = compute_stats(h_telemetry->t_e2e_cycles[0], n_samp, false);
    km_stats_t st_host_rt   = compute_stats(host_rt_ns,   num_events, true);

    printf("============================================================================\n");
    printf(" МАШИНА КУЗЬМІНА: PERSISTENT GPU SUBSCRIBERS (ISSUE #225 / #229 / ADR B6)\n");
    printf("============================================================================\n");
    printf("  Пристрій GPU:                 %s (SM %d.%d)\n", prop.name, prop.major, prop.minor);
    printf("  Геометрія запуску:            %u блок(ів) x %u ниток = %u підписників\n", num_blocks, threads, total_subs);
    printf("  Режим маски / in / ack / slp: %s / %s / %s / %u нс\n", mask_name, ingress_mode_name, ack_mode_name, sleep_ns);
    printf("  Кількість подій (вибірка SM): %u (%u)\n", num_events, n_samp);
    printf("  Розмір ingress / offset out:  %zu Б / %zu Б\n", sizeof(km_event_ingress_t), offsetof(km_event_egress_t, outputs));
    printf("  Частота GPU sysfs (до/під час/після, max): %.1f / %.1f / %.1f МГц (max %.1f МГц, CUDA attr %.1f МГц)\n",
           (sysfs_cur_before > 0ULL) ? (double)sysfs_cur_before / 1e6 : 0.0,
           (double)sysfs_cur_mid / 1e6,
           (double)sysfs_cur_after / 1e6,
           (double)sysfs_max_before / 1e6,
           (double)attr_clock_khz / 1e3);
    printf("  Квант апаратного %%globaltimer: %" PRIu64 " нс\n", h_gt_step);
    printf("  Перевірка CPU-еталона:        %s (total=%u, mid_run=%u із %u підписників)\n",
           (mismatches == 0u) ? "PASS" : "FAIL", mismatches, mid_run_mismatches, total_subs);
    printf("  --------------------------------------------------------------------------\n");
    printf("  1. ЧИСТИЙ ЧАС ОБЧИСЛЕННЯ У РЕГІСТРАХ SM (clock64 -> нс за фактичної %.1f МГц):\n", (double)eff_freq_hz / 1e6);
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
                "  \"blocks\": %u, \"threads\": %u, \"subscribers\": %u,\n"
                "  \"mask\": \"%s\", \"ingress_mode\": \"%s\", \"ack_mode\": \"%s\", \"sleep_ns\": %u, \"events\": %u,\n"
                "  \"sysfs_cur_freq_hz\": %" PRIu64 ", \"sysfs_max_freq_hz\": %" PRIu64 ",\n"
                "  \"globaltimer_quantum_ns\": %" PRIu64 ", \"mid_run_mismatches\": %u, \"mismatches\": %u,\n"
                "  \"bootstrap_iters\": %u, \"bootstrap_seed\": \"0x%llx\",\n"
                "  \"math_cycles_mean\": %.3f, \"math_cycles_sigma\": %.3f, \"math_cycles_p50\": %" PRIu64 ", \"math_cycles_p999\": %" PRIu64 ", \"math_cycles_max\": %" PRIu64 ",\n"
                "  \"math_ns_mean\": %.3f, \"math_ns_p999\": %.3f,\n"
                "  \"e2e_sm_cycles_mean\": %.3f, \"e2e_sm_cycles_sigma\": %.3f, \"e2e_sm_cycles_p50\": %" PRIu64 ", \"e2e_sm_cycles_p99\": %" PRIu64 ", \"e2e_sm_cycles_p999\": %" PRIu64 ", \"e2e_sm_cycles_max\": %" PRIu64 ",\n"
                "  \"e2e_sm_ns_mean\": %.3f, \"e2e_sm_ns_p50\": %.3f, \"e2e_sm_ns_p99\": %.3f, \"e2e_sm_ns_p99_ci95_lo\": %.3f, \"e2e_sm_ns_p99_ci95_hi\": %.3f, \"e2e_sm_ns_p999\": %.3f, \"e2e_sm_ns_p999_ci95_lo\": %.3f, \"e2e_sm_ns_p999_ci95_hi\": %.3f, \"e2e_sm_ns_max\": %.3f,\n"
                "  \"e2e_sm_b0_ns_mean\": %.3f, \"e2e_sm_b0_ns_p999\": %.3f,\n"
                "  \"e2e_gt_ns_mean\": %.3f, \"e2e_gt_ns_p50\": %" PRIu64 ", \"e2e_gt_ns_p99\": %" PRIu64 ", \"e2e_gt_ns_p99_ci95_lo\": %" PRIu64 ", \"e2e_gt_ns_p99_ci95_hi\": %" PRIu64 ", \"e2e_gt_ns_p999\": %" PRIu64 ", \"e2e_gt_ns_p999_ci95_lo\": %" PRIu64 ", \"e2e_gt_ns_p999_ci95_hi\": %" PRIu64 ", \"e2e_gt_ns_max\": %" PRIu64 ",\n"
                "  \"host_rt_ns_mean\": %.3f, \"host_rt_ns_p50\": %" PRIu64 ", \"host_rt_ns_p99\": %" PRIu64 ", \"host_rt_ns_p99_ci95_lo\": %" PRIu64 ", \"host_rt_ns_p99_ci95_hi\": %" PRIu64 ", \"host_rt_ns_p999\": %" PRIu64 ", \"host_rt_ns_p999_ci95_lo\": %" PRIu64 ", \"host_rt_ns_p999_ci95_hi\": %" PRIu64 ", \"host_rt_ns_max\": %" PRIu64 ",\n"
                "  \"per_block_e2e_sm_ns_mean\": [",
                num_blocks, threads, total_subs,
                mask_name, ingress_mode_name, ack_mode_name, sleep_ns, num_events,
                eff_freq_hz, sysfs_max_before,
                h_gt_step, mid_run_mismatches, mismatches,
                KM_BOOTSTRAP_ITERS, (unsigned long long)KM_BOOTSTRAP_SEED,
                st_math_cyc.mean, st_math_cyc.stddev, st_math_cyc.p50, st_math_cyc.p999, st_math_cyc.max,
                st_math_cyc.mean * ns_per_cyc_actual, st_math_cyc.p999 * ns_per_cyc_actual,
                st_e2e_cyc.mean, st_e2e_cyc.stddev, st_e2e_cyc.p50, st_e2e_cyc.p99, st_e2e_cyc.p999, st_e2e_cyc.max,
                st_e2e_cyc.mean * ns_per_cyc_actual, st_e2e_cyc.p50 * ns_per_cyc_actual,
                st_e2e_cyc.p99 * ns_per_cyc_actual, st_e2e_cyc.p99_ci_lo * ns_per_cyc_actual, st_e2e_cyc.p99_ci_hi * ns_per_cyc_actual,
                st_e2e_cyc.p999 * ns_per_cyc_actual, st_e2e_cyc.p999_ci_lo * ns_per_cyc_actual, st_e2e_cyc.p999_ci_hi * ns_per_cyc_actual,
                st_e2e_cyc.max * ns_per_cyc_actual,
                st_e2e_b0.mean * ns_per_cyc_actual, st_e2e_b0.p999 * ns_per_cyc_actual,
                st_e2e_gt.mean, st_e2e_gt.p50,
                st_e2e_gt.p99, st_e2e_gt.p99_ci_lo, st_e2e_gt.p99_ci_hi,
                st_e2e_gt.p999, st_e2e_gt.p999_ci_lo, st_e2e_gt.p999_ci_hi,
                st_e2e_gt.max,
                st_host_rt.mean, st_host_rt.p50,
                st_host_rt.p99, st_host_rt.p99_ci_lo, st_host_rt.p99_ci_hi,
                st_host_rt.p999, st_host_rt.p999_ci_lo, st_host_rt.p999_ci_hi,
                st_host_rt.max
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

    return (mismatches == 0u) ? 0 : 1;
}
