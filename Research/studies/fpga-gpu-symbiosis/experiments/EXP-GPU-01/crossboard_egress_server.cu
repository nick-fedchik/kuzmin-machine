/* ============================================================================
 * Машина Кузьміна (Kuzmin Machine) — Міжплатний приймач EXP-GPU-01 (Issue #226)
 * Файл: crossboard_egress_server.cu
 * Платформа: Seeed Studio reServer Industrial J501 (Jetson AGX Orin 64GB, SM 8.7)
 *
 * Приймає по GbE UDP (SO_BUSY_POLL) 64-бітні кадри подій у форматі
 * km_pmod_event_egress.sv від PYNQ-Z1 (XC7Z020 PL), перевіряє CRC-8 (poly 0x07)
 * та тег 2'b01, публікує подію в 16 секціонованих 128-Б ліній L2 Event Mailbox
 * (cudaHostAllocMapped), очікує ack_seq_id від 16 блоків x 64 нитки = 1024
 * підписників у персистентному кернелі GPU, відправляє ACK назад на PYNQ-Z1
 * та звіряє всі 1024 фінальні стани підписників із незалежною моделлю CPU.
 * ============================================================================ */

#include <arpa/inet.h>
#include <cuda_runtime.h>
#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <netinet/in.h>
#include <sched.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define KM_WARP_SIZE          32u
#define KM_MAX_WARPS_PER_BLK  16u
#define KM_MAX_SUBSCRIBERS    1024u
#define KM_NUM_BLOCKS         16u
#define KM_THREADS_PER_BLK    64u
#define KM_SLOT_MASK_WORDS    16u
#define KM_TELEMETRY_CAP      4096u

typedef struct __align__(128) {
    uint32_t seq_id;
    uint32_t stop_flag;
    int32_t  concept_val;
    uint32_t active_words;
    uint32_t event_mask[KM_SLOT_MASK_WORDS];
    uint32_t reserved[12];
} km_event_ingress_t;

static_assert(sizeof(km_event_ingress_t) == 128, "km_event_ingress_t must be 128B");

typedef struct __align__(128) {
    uint32_t ack;
    uint32_t pad[31];
} km_ack_line_t;

static_assert(sizeof(km_ack_line_t) == 128, "km_ack_line_t must be 128B");

typedef struct __align__(128) {
    uint32_t      packed_ack[KM_NUM_BLOCKS];
    uint32_t      pad_packed[16];
    km_ack_line_t isolated_ack[KM_NUM_BLOCKS];
    int32_t       outputs[KM_MAX_SUBSCRIBERS];
} km_event_egress_t;

typedef struct {
    int32_t  target;
    int32_t  kp;
    int32_t  ki_q8;
    int32_t  kd;
    int32_t  integral;
    int32_t  prev_err;
    int32_t  out_val;
    uint32_t trigger_count;
} km_sub_state_t;

typedef struct {
    uint64_t t_math_cycles[KM_NUM_BLOCKS][KM_TELEMETRY_CAP];
    uint64_t t_e2e_cycles[KM_NUM_BLOCKS][KM_TELEMETRY_CAP];
    uint64_t t_math_gt_ns[KM_NUM_BLOCKS][KM_TELEMETRY_CAP];
    uint64_t t_e2e_gt_ns[KM_NUM_BLOCKS][KM_TELEMETRY_CAP];
    uint32_t recorded_samples[KM_NUM_BLOCKS];
} km_telemetry_t;

/* Мережевий пакет запиту PYNQ-Z1 -> Jetson (16 байтів, little-endian) */
typedef struct __attribute__((packed)) {
    uint32_t req_seq;
    uint32_t pl_mmio_ns;
    uint64_t egress_frame64;
} km_udp_req_t;

/* Мережевий пакет підтвердження Jetson -> PYNQ-Z1 (32 байти, little-endian) */
typedef struct __attribute__((packed)) {
    uint32_t req_seq;
    uint32_t ack_seq_id;
    uint32_t status;          /* 0 = OK, 1 = CRC8/TAG error, 2 = STOP_OK */
    uint32_t crc_drop_count;
    uint64_t t_jetson_host_ns;
    uint64_t last_frame64;
} km_udp_ack_t;

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

__global__ void __launch_bounds__(64, 1) km_crossboard_persistent_kernel(
    const km_event_ingress_t * __restrict__ ingress,
    km_event_egress_t        * __restrict__ egress,
    km_telemetry_t           * __restrict__ telemetry,
    const km_sub_state_t     * __restrict__ init_states,
    km_sub_state_t           * __restrict__ final_states
) {
    const uint32_t tid       = threadIdx.x;
    const uint32_t lane_id   = tid & 31u;
    const uint32_t warp_id   = tid >> 5u;
    const uint32_t global_id = blockIdx.x * blockDim.x + tid;
    const km_event_ingress_t *my_in = &ingress[blockIdx.x];

    __shared__ uint32_t s_cur_seq;
    __shared__ uint32_t s_stop;
    __shared__ int32_t  s_cval;
    __shared__ uint32_t s_masks[2];

    km_sub_state_t st = init_states[global_id];
    int32_t  reg_target   = st.target;
    int32_t  reg_kp       = st.kp;
    int32_t  reg_ki_q8    = st.ki_q8;
    int32_t  reg_kd       = st.kd;
    int32_t  reg_integral = st.integral;
    int32_t  reg_prev_err = st.prev_err;
    int32_t  reg_out_val  = st.out_val;
    uint32_t reg_triggers = st.trigger_count;

    __syncthreads();
    uint32_t last_seq = 0u;

    while (true) {
        if (tid == 0u) {
            s_cur_seq = km_ld_acquire_sys_u32(&my_in->seq_id);
            s_stop    = *(const volatile uint32_t *)&my_in->stop_flag;
        }
        __syncthreads();

        uint32_t cur_seq = s_cur_seq;
        if (s_stop != 0u) {
            break;
        }

        if (cur_seq != last_seq) {
            uint64_t t_e2e_c0 = clock64();
            uint64_t t_e2e_g0 = km_read_globaltimer();

            if (tid == 0u) {
                s_cval = *(const volatile int32_t *)&my_in->concept_val;
            }
            if (tid < 2u) {
                s_masks[tid] = *(const volatile uint32_t *)&my_in->event_mask[tid];
            }
            __syncthreads();

            int32_t  c_val = s_cval;
            uint32_t mask  = s_masks[warp_id];
            bool is_active = ((mask & (1u << lane_id)) != 0u);

            uint64_t t_math_c0 = clock64();
            uint64_t t_math_g0 = km_read_globaltimer();

            int32_t in_val   = c_val + (int32_t)global_id;
            int32_t err      = in_val - reg_target;
            int32_t p_term   = err * reg_kp;
            int32_t d_term   = (err - reg_prev_err) * reg_kd;
            int32_t cand_int = reg_integral + err;
            int32_t i_term   = (cand_int * reg_ki_q8) >> 8;
            int32_t cand_out = p_term + d_term + i_term;

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
                km_st_release_sys_u32(&egress->isolated_ack[blockIdx.x].ack, cur_seq);
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
        }
        __syncthreads();
    }

    st.integral      = reg_integral;
    st.prev_err      = reg_prev_err;
    st.out_val       = reg_out_val;
    st.trigger_count = reg_triggers;
    final_states[global_id] = st;
}

static uint8_t km_calc_crc8(uint64_t payload_56) {
    uint8_t crc = 0x00u;
    for (int bit = 55; bit >= 0; --bit) {
        uint8_t fb = (uint8_t)(((crc >> 7) ^ ((payload_56 >> bit) & 1ULL)) & 1u);
        crc = (uint8_t)(((crc << 1) & 0xFFu) ^ (fb ? 0x07u : 0x00u));
    }
    return crc;
}

static bool km_verify_egress_frame64(
    uint64_t frame64,
    uint8_t *out_cid,
    uint16_t *out_mask16,
    int32_t *out_state
) {
    uint8_t got_crc = (uint8_t)((frame64 >> 56) & 0xFFULL);
    uint64_t payload_56 = frame64 & 0x00FFFFFFFFFFFFFFULL;
    uint8_t exp_crc = km_calc_crc8(payload_56);
    if (got_crc != exp_crc) {
        return false;
    }
    uint8_t tag = (uint8_t)((payload_56 >> 54) & 0x3ULL);
    if (tag != 0x1u) {
        return false;
    }
    *out_cid    = (uint8_t)((payload_56 >> 48) & 0x3FULL);
    *out_mask16 = (uint16_t)((payload_56 >> 32) & 0xFFFFULL);
    *out_state  = (int32_t)(uint32_t)(payload_56 & 0xFFFFFFFFULL);
    return true;
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

int main(int argc, char **argv) {
    int port = 55226;
    const char *json_out = "jetson_crossboard_server_report.json";
    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--port") == 0 && i + 1 < argc) {
            port = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--json-out") == 0 && i + 1 < argc) {
            json_out = argv[++i];
        }
    }

    cudaSetDeviceFlags(cudaDeviceMapHost);

    km_event_ingress_t *h_ingress = NULL, *d_ingress = NULL;
    km_event_egress_t  *h_egress  = NULL, *d_egress  = NULL;
    km_sub_state_t     *h_init    = NULL, *d_init    = NULL;
    km_sub_state_t     *h_final   = NULL, *d_final   = NULL;
    km_sub_state_t     *cpu_ref   = (km_sub_state_t *)calloc(KM_MAX_SUBSCRIBERS, sizeof(km_sub_state_t));
    km_telemetry_t     *d_telem   = NULL;
    km_telemetry_t     *h_telem   = (km_telemetry_t *)calloc(1, sizeof(km_telemetry_t));

    cudaHostAlloc((void **)&h_ingress, KM_NUM_BLOCKS * sizeof(km_event_ingress_t), cudaHostAllocMapped);
    cudaHostAlloc((void **)&h_egress,  sizeof(km_event_egress_t), cudaHostAllocMapped);
    cudaHostAlloc((void **)&h_init,    KM_MAX_SUBSCRIBERS * sizeof(km_sub_state_t), cudaHostAllocMapped);
    cudaHostAlloc((void **)&h_final,   KM_MAX_SUBSCRIBERS * sizeof(km_sub_state_t), cudaHostAllocMapped);
    cudaMalloc((void **)&d_telem, sizeof(km_telemetry_t));
    cudaMemset(d_telem, 0, sizeof(km_telemetry_t));

    memset(h_ingress, 0, KM_NUM_BLOCKS * sizeof(km_event_ingress_t));
    memset(h_egress,  0, sizeof(km_event_egress_t));

    for (uint32_t i = 0; i < KM_MAX_SUBSCRIBERS; ++i) {
        h_init[i].target        = 100 + (int32_t)(i & 63u);
        h_init[i].kp            = 3;
        h_init[i].ki_q8         = 64;
        h_init[i].kd            = 2;
        h_init[i].integral      = 0;
        h_init[i].prev_err      = 0;
        h_init[i].out_val       = 0;
        h_init[i].trigger_count = 0;
        cpu_ref[i]              = h_init[i];
    }

    cudaHostGetDevicePointer((void **)&d_ingress, h_ingress, 0);
    cudaHostGetDevicePointer((void **)&d_egress,  h_egress,  0);
    cudaHostGetDevicePointer((void **)&d_init,    h_init,    0);
    cudaHostGetDevicePointer((void **)&d_final,   h_final,   0);

    cudaStream_t stream;
    cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking);

    km_crossboard_persistent_kernel<<<KM_NUM_BLOCKS, KM_THREADS_PER_BLK, 0, stream>>>(
        d_ingress, d_egress, d_telem, d_init, d_final
    );

    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        perror("socket");
        return 1;
    }
    int opt = 1;
    setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
#ifdef SO_BUSY_POLL
    int busy_us = 50;
    setsockopt(sock, SOL_SOCKET, SO_BUSY_POLL, &busy_us, sizeof(busy_us));
#endif

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port        = htons((uint16_t)port);
    if (bind(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind");
        return 1;
    }

    printf("READY port=%d blocks=%u threads=%u subscribers=%u\n",
           port, KM_NUM_BLOCKS, KM_THREADS_PER_BLK, KM_MAX_SUBSCRIBERS);
    fflush(stdout);

    uint32_t cur_seq = 0u;
    uint32_t crc_drop_count = 0u;

    while (true) {
        km_udp_req_t req;
        struct sockaddr_in cli_addr;
        socklen_t cli_len = sizeof(cli_addr);
        ssize_t n = recvfrom(sock, &req, sizeof(req), 0, (struct sockaddr *)&cli_addr, &cli_len);
        if (n != (ssize_t)sizeof(req)) {
            continue;
        }

        uint64_t t0_ns = host_monotonic_raw_ns();
        km_udp_ack_t ack;
        memset(&ack, 0, sizeof(ack));
        ack.req_seq      = req.req_seq;
        ack.last_frame64 = req.egress_frame64;

        if (req.req_seq == 0xFFFFFFFFu) {
            for (uint32_t b = 0; b < KM_NUM_BLOCKS; ++b) {
                *(volatile uint32_t *)&h_ingress[b].stop_flag = 1u;
                __atomic_store_n(&h_ingress[b].seq_id, cur_seq + 1u, __ATOMIC_RELEASE);
            }
            ack.ack_seq_id       = cur_seq;
            ack.status           = 2u;
            ack.crc_drop_count   = crc_drop_count;
            ack.t_jetson_host_ns = host_monotonic_raw_ns() - t0_ns;
            sendto(sock, &ack, sizeof(ack), 0, (struct sockaddr *)&cli_addr, cli_len);
            break;
        }

        uint8_t  cid    = 0;
        uint16_t mask16 = 0;
        int32_t  state  = 0;
        if (!km_verify_egress_frame64(req.egress_frame64, &cid, &mask16, &state)) {
            crc_drop_count++;
            ack.ack_seq_id       = cur_seq;
            ack.status           = 1u;
            ack.crc_drop_count   = crc_drop_count;
            ack.t_jetson_host_ns = host_monotonic_raw_ns() - t0_ns;
            sendto(sock, &ack, sizeof(ack), 0, (struct sockaddr *)&cli_addr, cli_len);
            continue;
        }

        cur_seq++;
        uint32_t mask32 = ((uint32_t)mask16 << 16) | (uint32_t)mask16;

        for (uint32_t b = 0; b < KM_NUM_BLOCKS; ++b) {
            h_ingress[b].concept_val   = state;
            h_ingress[b].active_words  = 2u;
            h_ingress[b].event_mask[0] = mask32;
            h_ingress[b].event_mask[1] = mask32;
        }
        __atomic_thread_fence(__ATOMIC_RELEASE);
        for (uint32_t b = 0; b < KM_NUM_BLOCKS; ++b) {
            __atomic_store_n(&h_ingress[b].seq_id, cur_seq, __ATOMIC_RELEASE);
        }

        for (uint32_t b = 0; b < KM_NUM_BLOCKS; ++b) {
            while (__atomic_load_n(&h_egress->isolated_ack[b].ack, __ATOMIC_ACQUIRE) != cur_seq) {
                /* active spin on L2-coherent isolated_ack */
            }
        }

        /* Незалежна еталонна CPU-модель для всіх 1024 підписників */
        for (uint32_t b = 0; b < KM_NUM_BLOCKS; ++b) {
            for (uint32_t t = 0; t < KM_THREADS_PER_BLK; ++t) {
                uint32_t gid  = b * KM_THREADS_PER_BLK + t;
                uint32_t lane = t & 31u;
                bool active   = ((mask32 & (1u << lane)) != 0u);
                if (active) {
                    int32_t in_val   = state + (int32_t)gid;
                    int32_t err      = in_val - cpu_ref[gid].target;
                    int32_t p_term   = err * cpu_ref[gid].kp;
                    int32_t d_term   = (err - cpu_ref[gid].prev_err) * cpu_ref[gid].kd;
                    int32_t cand_int = cpu_ref[gid].integral + err;
                    int32_t i_term   = (cand_int * cpu_ref[gid].ki_q8) >> 8;
                    cpu_ref[gid].integral      = cand_int;
                    cpu_ref[gid].prev_err      = err;
                    cpu_ref[gid].out_val       = p_term + d_term + i_term;
                    cpu_ref[gid].trigger_count += 1u;
                }
            }
        }

        uint64_t t1_ns = host_monotonic_raw_ns();
        ack.ack_seq_id       = cur_seq;
        ack.status           = 0u;
        ack.crc_drop_count   = crc_drop_count;
        ack.t_jetson_host_ns = t1_ns - t0_ns;
        sendto(sock, &ack, sizeof(ack), 0, (struct sockaddr *)&cli_addr, cli_len);
    }

    cudaStreamSynchronize(stream);
    cudaMemcpy(h_telem, d_telem, sizeof(km_telemetry_t), cudaMemcpyDeviceToHost);

    uint32_t mismatches = 0u;
    for (uint32_t i = 0; i < KM_MAX_SUBSCRIBERS; ++i) {
        if (h_final[i].out_val != cpu_ref[i].out_val ||
            h_final[i].integral != cpu_ref[i].integral ||
            h_final[i].trigger_count != cpu_ref[i].trigger_count) {
            mismatches++;
        }
    }

    uint32_t n_rec = h_telem->recorded_samples[0];
    uint64_t *arr_math = (uint64_t *)calloc(n_rec ? n_rec : 1, sizeof(uint64_t));
    uint64_t *arr_e2e  = (uint64_t *)calloc(n_rec ? n_rec : 1, sizeof(uint64_t));
    for (uint32_t i = 0; i < n_rec; ++i) {
        uint64_t max_m = 0, max_e = 0;
        for (uint32_t b = 0; b < KM_NUM_BLOCKS; ++b) {
            if (h_telem->t_math_gt_ns[b][i] > max_m) max_m = h_telem->t_math_gt_ns[b][i];
            if (h_telem->t_e2e_gt_ns[b][i]  > max_e) max_e = h_telem->t_e2e_gt_ns[b][i];
        }
        arr_math[i] = max_m;
        arr_e2e[i]  = max_e;
    }
    if (n_rec > 0) {
        qsort(arr_math, n_rec, sizeof(uint64_t), cmp_u64);
        qsort(arr_e2e,  n_rec, sizeof(uint64_t), cmp_u64);
    }

    uint64_t math_p50   = n_rec ? arr_math[n_rec / 2] : 0;
    uint64_t math_p99   = n_rec ? arr_math[(n_rec * 99) / 100] : 0;
    uint64_t e2e_p50    = n_rec ? arr_e2e[n_rec / 2] : 0;
    uint64_t e2e_p99    = n_rec ? arr_e2e[(n_rec * 99) / 100] : 0;
    uint64_t e2e_p99_9  = n_rec ? arr_e2e[(n_rec * 999) / 1000] : 0;
    uint64_t e2e_max    = n_rec ? arr_e2e[n_rec - 1] : 0;

    FILE *fp = fopen(json_out, "w");
    if (fp) {
        fprintf(fp,
                "{\n"
                "  \"valid_events_processed\": %u,\n"
                "  \"crc_drop_count\": %u,\n"
                "  \"state_mismatches\": %u,\n"
                "  \"subscribers_verified\": %u,\n"
                "  \"gpu_math_gt_ns_p50\": %" PRIu64 ",\n"
                "  \"gpu_math_gt_ns_p99\": %" PRIu64 ",\n"
                "  \"gpu_e2e_gt_ns_p50\": %" PRIu64 ",\n"
                "  \"gpu_e2e_gt_ns_p99\": %" PRIu64 ",\n"
                "  \"gpu_e2e_gt_ns_p99_9\": %" PRIu64 ",\n"
                "  \"gpu_e2e_gt_ns_max\": %" PRIu64 "\n"
                "}\n",
                cur_seq, crc_drop_count, mismatches, KM_MAX_SUBSCRIBERS,
                math_p50, math_p99, e2e_p50, e2e_p99, e2e_p99_9, e2e_max);
        fclose(fp);
    }

    close(sock);
    return (mismatches == 0u) ? 0 : 2;
}
