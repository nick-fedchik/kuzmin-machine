/*
 * c99_cascade_bench.c
 *
 * Comparative software baseline for Issue #254:
 *   1. Variant 1: Direct in-memory C99 (-O3) cascade engine on ARM Cortex-A9
 *      (user-space Linux with mlockall(MCL_CURRENT | MCL_FUTURE), N = 100000).
 *   2. Variant 2: OS kernel event dispatch via Linux eventfd + poll wakeup
 *      between producer and handler threads on ARM Cortex-A9 (N = 10000).
 *   3. Trace equivalence mode (--trace <image.hex> <events.hex> <num_events>)
 *      executing the exact same 64-slot CME-RAW-1 descriptor semantics for
 *      100% bit-exact verification against kpol_reference.py,
 *      km_reg_configurable_cascade_axi.sv, and kpol_bram_pipeline_axi.sv.
 */

#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <poll.h>
#include <pthread.h>
#include <sched.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/eventfd.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define KM_MAX_CONCEPTS 64u
#define KM_MAX_CASCADE_STEPS 64u

typedef struct {
    int32_t  state;
    uint32_t operand;
    uint8_t  pred_opcode;
    uint8_t  guard_flags;
    uint8_t  hazard_limit;
    uint8_t  action_opcode;
    uint32_t subscriber_cid;
} km_concept_desc_t;

typedef struct {
    km_concept_desc_t slots[KM_MAX_CONCEPTS];
    uint32_t events_processed;
    uint32_t committed_count;
    uint32_t rejected_count;
    uint32_t last_committed_state;
} km_engine_t;

typedef struct {
    uint32_t steps;
    uint32_t commits;
    uint32_t rejects;
} km_step_stats_t;

static inline uint64_t km_now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

__attribute__((noinline))
void km_unpack_word(km_engine_t *eng, uint8_t word_idx, uint32_t w) {
    uint8_t cid  = (uint8_t)(word_idx >> 2);
    uint8_t wsel = (uint8_t)(word_idx & 0x3u);
    if (cid >= KM_MAX_CONCEPTS) {
        return;
    }
    km_concept_desc_t *d = &eng->slots[cid];
    switch (wsel) {
        case 0u:
            d->state = (int32_t)w;
            break;
        case 1u:
            d->operand = w;
            break;
        case 2u:
            d->pred_opcode   = (uint8_t)(w & 0xffu);
            d->guard_flags   = (uint8_t)((w >> 8) & 0xffu);
            d->hazard_limit  = (uint8_t)((w >> 16) & 0xffu);
            d->action_opcode = (uint8_t)((w >> 24) & 0xffu);
            break;
        case 3u:
            d->subscriber_cid = w;
            break;
    }
}

__attribute__((noinline))
uint32_t km_pack_word(const km_engine_t *eng, uint8_t word_idx) {
    uint8_t cid  = (uint8_t)(word_idx >> 2);
    uint8_t wsel = (uint8_t)(word_idx & 0x3u);
    if (cid >= KM_MAX_CONCEPTS) {
        return 0u;
    }
    const km_concept_desc_t *d = &eng->slots[cid];
    switch (wsel) {
        case 0u:
            return (uint32_t)d->state;
        case 1u:
            return d->operand;
        case 2u:
            return (uint32_t)d->pred_opcode |
                   ((uint32_t)d->guard_flags << 8) |
                   ((uint32_t)d->hazard_limit << 16) |
                   ((uint32_t)d->action_opcode << 24);
        case 3u:
        default:
            return d->subscriber_cid;
    }
}

__attribute__((noinline))
void km_update_rules_ram(km_engine_t *eng, const km_concept_desc_t *src, size_t count) {
    if (count > KM_MAX_CONCEPTS) {
        count = KM_MAX_CONCEPTS;
    }
    memcpy(eng->slots, src, count * sizeof(km_concept_desc_t));
    __asm__ volatile("" : "+m"(eng->slots) : : "memory");
}

__attribute__((noinline))
km_step_stats_t km_eval_cascade(km_engine_t *eng, uint8_t start_cid, uint32_t start_param) {
    km_step_stats_t st = {0u, 0u, 0u};
    uint8_t  cid   = start_cid;
    uint32_t param = start_param;

    for (uint32_t hop = 0u; hop < KM_MAX_CASCADE_STEPS; ++hop) {
        if (cid >= KM_MAX_CONCEPTS) {
            break;
        }
        km_concept_desc_t *d = &eng->slots[cid];
        st.steps++;
        eng->events_processed++;

        bool pred_raw = false;
        switch (d->pred_opcode) {
            case 0x00u: /* NOP */
                pred_raw = true;
                break;
            case 0x01u: /* EQ */
                pred_raw = (param == d->operand);
                break;
            case 0x02u: /* NEQ */
                pred_raw = (param != d->operand);
                break;
            case 0x03u: /* GT */
#ifdef MUTANT_C_FLIP_GT
                pred_raw = ((int32_t)param >= (int32_t)d->operand);
#else
                pred_raw = ((int32_t)param > (int32_t)d->operand);
#endif
                break;
            case 0x04u: /* LT */
                pred_raw = ((int32_t)param < (int32_t)d->operand);
                break;
            case 0x05u: { /* RANGE (signed int16 lo/hi) */
                int16_t lo16 = (int16_t)(d->operand & 0xffffu);
                int16_t hi16 = (int16_t)((d->operand >> 16) & 0xffffu);
                int32_t sp   = (int32_t)param;
                pred_raw = (sp >= (int32_t)lo16) && (sp <= (int32_t)hi16);
                break;
            }
            case 0x06u: /* BITMASK */
                pred_raw = ((param & d->operand) != 0u);
                break;
            default:
                pred_raw = false;
                break;
        }

        uint32_t cur_u32 = (uint32_t)d->state;
        uint32_t cand_u32 = cur_u32;
        bool action_valid = true;
        bool arith_overflow = false;

        switch (d->action_opcode) {
            case 0x00u: /* ASSIGN */
                cand_u32 = param;
                break;
            case 0x01u: /* INC */
                cand_u32 = cur_u32 + 1u;
                arith_overflow = (cur_u32 == 0x7fffffffu);
                break;
            case 0x02u: /* DEC */
                cand_u32 = cur_u32 - 1u;
                arith_overflow = (cur_u32 == 0x80000000u);
                break;
            case 0x03u: /* ADD */
                cand_u32 = cur_u32 + d->operand;
                arith_overflow = (((cur_u32 ^ d->operand) & 0x80000000u) == 0u) &&
                                 (((cand_u32 ^ cur_u32) & 0x80000000u) != 0u);
                break;
            case 0x04u: /* SUB */
                cand_u32 = cur_u32 - d->operand;
                arith_overflow = (((cur_u32 ^ d->operand) & 0x80000000u) != 0u) &&
                                 (((cand_u32 ^ cur_u32) & 0x80000000u) != 0u);
                break;
            default:
                cand_u32 = cur_u32;
                action_valid = false;
                break;
        }

        bool assumption_known = (d->guard_flags & 0x01u) != 0u;
        bool assumption_true  = ((d->guard_flags & 0x08u) != 0u) ? !pred_raw : pred_raw;
        bool invariant_known  = (d->guard_flags & 0x02u) != 0u;
#ifdef MUTANT_C_SKIP_INVARIANT
        bool invariant_true   = true;
#else
        bool invariant_true   = !arith_overflow && ((int32_t)cand_u32 >= 0);
#endif
        bool hazard_true      = ((d->guard_flags & 0x04u) != 0u) &&
                                (d->hazard_limit != 0u) &&
                                ((int32_t)param > (int32_t)(uint32_t)d->hazard_limit);

        bool commit = action_valid && assumption_known && assumption_true &&
                      invariant_known && invariant_true && !hazard_true;

        if (!commit) {
            eng->rejected_count++;
            st.rejects++;
            break;
        }

        d->state = (int32_t)cand_u32;
        eng->committed_count++;
        eng->last_committed_state = cand_u32;
        st.commits++;

#ifdef MUTANT_C_DROP_CASCADE
        break;
#else
        bool sub_target_valid = (d->subscriber_cid < KM_MAX_CONCEPTS);
        bool sub_enabled = ((d->guard_flags & 0x10u) != 0u) || (d->subscriber_cid != 0u);
        uint8_t next_cid = (uint8_t)(d->subscriber_cid & 0x3fu);
        if (sub_target_valid && sub_enabled && (next_cid != cid)) {
            cid   = next_cid;
            param = cand_u32;
        } else {
            break;
        }
#endif
    }

    return st;
}

static void init_canonical_4concept_rules(km_concept_desc_t out[4], int32_t c2_init) {
    memset(out, 0, 4 * sizeof(km_concept_desc_t));
    /* C0: RANGE [10, 1000], INC, cascade -> C1 */
    out[0].state          = 10;
    out[0].operand        = (1000u << 16) | 10u;
    out[0].pred_opcode    = 0x05u;
    out[0].guard_flags    = 0x13u;
    out[0].action_opcode  = 0x01u;
    out[0].subscriber_cid = 1u;

    /* C1: GT 10, INC, cascade -> C2 */
    out[1].state          = 0;
    out[1].operand        = 10u;
    out[1].pred_opcode    = 0x03u;
    out[1].guard_flags    = 0x13u;
    out[1].action_opcode  = 0x01u;
    out[1].subscriber_cid = 2u;

    /* C2: LT 1 inverted (>= 1), DEC, cascade -> C3 */
    out[2].state          = c2_init;
    out[2].operand        = 1u;
    out[2].pred_opcode    = 0x04u;
    out[2].guard_flags    = 0x1bu;
    out[2].action_opcode  = 0x02u;
    out[2].subscriber_cid = 3u;

    /* C3: EQ c2_init inverted (!= c2_init), ASSIGN, leaf */
    out[3].state          = 0;
    out[3].operand        = (uint32_t)c2_init;
    out[3].pred_opcode    = 0x01u;
    out[3].guard_flags    = 0x0bu;
    out[3].action_opcode  = 0x00u;
    out[3].subscriber_cid = 0u;
}

static int cmp_u64(const void *a, const void *b) {
    uint64_t va = *(const uint64_t *)a;
    uint64_t vb = *(const uint64_t *)b;
    return (va > vb) - (va < vb);
}

typedef struct {
    double   mean_ns;
    double   sigma_ns;
    uint64_t min_ns;
    uint64_t p50_ns;
    uint64_t p99_ns;
    uint64_t p999_ns;
    uint64_t max_ns;
} km_dist_t;

static km_dist_t compute_dist(uint64_t *samples, size_t n) {
    km_dist_t r = {0.0, 0.0, 0u, 0u, 0u, 0u, 0u};
    if (n == 0u) {
        return r;
    }
    double sum = 0.0;
    for (size_t i = 0u; i < n; ++i) {
        sum += (double)samples[i];
    }
    r.mean_ns = sum / (double)n;

    double var_sum = 0.0;
    for (size_t i = 0u; i < n; ++i) {
        double d = (double)samples[i] - r.mean_ns;
        var_sum += d * d;
    }
    r.sigma_ns = (n > 1u) ? sqrt(var_sum / (double)(n - 1u)) : 0.0;

    qsort(samples, n, sizeof(uint64_t), cmp_u64);
    r.min_ns  = samples[0];
    r.p50_ns  = samples[(size_t)((n - 1u) * 0.50)];
    r.p99_ns  = samples[(size_t)((n - 1u) * 0.99)];
    r.p999_ns = samples[(size_t)((n - 1u) * 0.999)];
    r.max_ns  = samples[n - 1u];
    return r;
}

/* Variant 2: Linux kernel eventfd + poll wakeup context */
typedef struct {
    int          req_efd;
    int          ack_efd;
    size_t       iterations;
    km_engine_t *eng;
    volatile uint64_t t_send_ns;
    uint64_t    *latencies_ns;
    int          worker_cpu;
} km_eventfd_ctx_t;

static void pin_to_cpu_if_available(int cpu_id) {
    long nprocs = sysconf(_SC_NPROCESSORS_ONLN);
    if (nprocs <= 0 || cpu_id < 0 || cpu_id >= nprocs) {
        return;
    }
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu_id, &set);
    (void)sched_setaffinity(0, sizeof(set), &set);
}

static void *eventfd_worker_thread(void *arg) {
    km_eventfd_ctx_t *ctx = (km_eventfd_ctx_t *)arg;
    pin_to_cpu_if_available(ctx->worker_cpu);

    struct pollfd pfd;
    pfd.fd     = ctx->req_efd;
    pfd.events = POLLIN;

    for (size_t i = 0u; i < ctx->iterations; ++i) {
        int rc;
        do {
            rc = poll(&pfd, 1, -1);
        } while (rc < 0 && errno == EINTR);
        if (rc <= 0) {
            abort();
        }
        uint64_t val = 0u;
        if (read(ctx->req_efd, &val, sizeof(val)) != (ssize_t)sizeof(val)) {
            abort();
        }
        (void)km_eval_cascade(ctx->eng, 0u, 25u);
        uint64_t t1 = km_now_ns();
        ctx->latencies_ns[i] = t1 - ctx->t_send_ns;

        uint64_t one = 1u;
        if (write(ctx->ack_efd, &one, sizeof(one)) != (ssize_t)sizeof(one)) {
            abort();
        }
    }
    return NULL;
}

static int run_trace_mode(const char *image_hex, const char *events_hex, int num_events) {
    km_engine_t eng;
    memset(&eng, 0, sizeof(eng));

    FILE *f_img = fopen(image_hex, "r");
    if (!f_img) {
        perror("fopen image_hex");
        return 2;
    }
    for (int i = 0; i < 256; ++i) {
        uint32_t w = 0u;
        if (fscanf(f_img, "%x", &w) != 1) {
            fclose(f_img);
            fprintf(stderr, "short image_hex at word %d\n", i);
            return 2;
        }
        km_unpack_word(&eng, (uint8_t)i, w);
    }
    fclose(f_img);

    FILE *f_ev = fopen(events_hex, "r");
    if (!f_ev) {
        perror("fopen events_hex");
        return 2;
    }
    for (int e = 0; e < num_events; ++e) {
        uint32_t cmd_w = 0u, arg_w = 0u;
        if (fscanf(f_ev, "%x %x", &cmd_w, &arg_w) != 2) {
            fclose(f_ev);
            fprintf(stderr, "short events_hex at event %d\n", e);
            return 2;
        }
        if (((cmd_w >> 24) & 0xffu) == 0x01u) {
            km_unpack_word(&eng, (uint8_t)(cmd_w & 0xffu), arg_w);
        } else {
            (void)km_eval_cascade(&eng, (uint8_t)(cmd_w & 0x3fu), arg_w);
        }
    }
    fclose(f_ev);

    for (int c = 0; c < 64; ++c) {
        printf("SLOT %d %08" PRIx32 " %08" PRIx32 " %08" PRIx32 " %08" PRIx32 "\n",
               c,
               km_pack_word(&eng, (uint8_t)(c * 4 + 0)),
               km_pack_word(&eng, (uint8_t)(c * 4 + 1)),
               km_pack_word(&eng, (uint8_t)(c * 4 + 2)),
               km_pack_word(&eng, (uint8_t)(c * 4 + 3)));
    }
    printf("SUMMARY events=%" PRIu32 " commits=%" PRIu32 " rejects=%" PRIu32 " last_state=%08" PRIx32 "\n",
           eng.events_processed, eng.committed_count, eng.rejected_count, eng.last_committed_state);
    return 0;
}

static int run_benchmarks(size_t n_direct, size_t n_os) {
    int mlock_rc = mlockall(MCL_CURRENT | MCL_FUTURE);
    bool mlock_ok = (mlock_rc == 0);

    pin_to_cpu_if_available(0);

    uint64_t *samples_clock  = (uint64_t *)calloc(n_direct, sizeof(uint64_t));
    uint64_t *samples_reject = (uint64_t *)calloc(n_direct, sizeof(uint64_t));
    uint64_t *samples_casc4  = (uint64_t *)calloc(n_direct, sizeof(uint64_t));
    uint64_t *samples_update = (uint64_t *)calloc(n_direct, sizeof(uint64_t));
    uint64_t *samples_os     = (uint64_t *)calloc(n_os, sizeof(uint64_t));
    if (!samples_clock || !samples_reject || !samples_casc4 || !samples_update || !samples_os) {
        fprintf(stderr, "allocation failure\n");
        return 2;
    }

    /* 0. Measure CLOCK_MONOTONIC_RAW back-to-back call overhead */
    for (size_t i = 0u; i < 1000u; ++i) {
        (void)km_now_ns();
    }
    for (size_t i = 0u; i < n_direct; ++i) {
        uint64_t t0 = km_now_ns();
        uint64_t t1 = km_now_ns();
        samples_clock[i] = t1 - t0;
    }
    km_dist_t dist_clock = compute_dist(samples_clock, n_direct);

    /* 1A. Variant 1: Single rejected event (1 concept C0, p0 = 5 < 10), per-event */
    km_engine_t eng;
    km_concept_desc_t rules_a[4];
    km_concept_desc_t rules_b[4];
    init_canonical_4concept_rules(rules_a, 10000000);
    init_canonical_4concept_rules(rules_b, 20000000);
    rules_b[0].operand = (800u << 16) | 20u;

    memset(&eng, 0, sizeof(eng));
    km_update_rules_ram(&eng, rules_a, 4u);
    for (size_t i = 0u; i < 1000u; ++i) {
        (void)km_eval_cascade(&eng, 0u, 5u);
    }
    memset(&eng, 0, sizeof(eng));
    km_update_rules_ram(&eng, rules_a, 4u);

    for (size_t i = 0u; i < n_direct; ++i) {
        uint64_t t0 = km_now_ns();
        (void)km_eval_cascade(&eng, 0u, 5u);
        uint64_t t1 = km_now_ns();
        samples_reject[i] = t1 - t0;
    }
    uint32_t rej_check_rejects = eng.rejected_count;
    uint32_t rej_check_commits = eng.committed_count;
    km_dist_t dist_reject = compute_dist(samples_reject, n_direct);

    /* 1A-amortized: Batch of 100 calls per timestamp pair (N = n_direct total calls) */
    memset(&eng, 0, sizeof(eng));
    km_update_rules_ram(&eng, rules_a, 4u);
    uint64_t batch_rej_t0 = km_now_ns();
    for (size_t i = 0u; i < n_direct; ++i) {
        (void)km_eval_cascade(&eng, 0u, 5u);
    }
    uint64_t batch_rej_t1 = km_now_ns();
    double amortized_reject_ns = (double)(batch_rej_t1 - batch_rej_t0) / (double)n_direct;

    /* 1B. Variant 1: Full 4-concept cascade C0 -> C1 -> C2 -> C3 (p0 = 25), per-event */
    memset(&eng, 0, sizeof(eng));
    km_update_rules_ram(&eng, rules_a, 4u);
    for (size_t i = 0u; i < 1000u; ++i) {
        (void)km_eval_cascade(&eng, 0u, 25u);
    }
    memset(&eng, 0, sizeof(eng));
    km_update_rules_ram(&eng, rules_a, 4u);

    for (size_t i = 0u; i < n_direct; ++i) {
        uint64_t t0 = km_now_ns();
        (void)km_eval_cascade(&eng, 0u, 25u);
        uint64_t t1 = km_now_ns();
        samples_casc4[i] = t1 - t0;
    }
    uint32_t casc4_commits = eng.committed_count;
    uint32_t casc4_rejects = eng.rejected_count;
    int32_t  casc4_c3_end  = eng.slots[3].state;
    km_dist_t dist_casc4 = compute_dist(samples_casc4, n_direct);

    /* 1B-amortized: Pure CPU tight loop without per-event syscall/clock overhead */
    memset(&eng, 0, sizeof(eng));
    km_update_rules_ram(&eng, rules_a, 4u);
    uint64_t batch_c4_t0 = km_now_ns();
    for (size_t i = 0u; i < n_direct; ++i) {
        (void)km_eval_cascade(&eng, 0u, 25u);
    }
    uint64_t batch_c4_t1 = km_now_ns();
    double amortized_casc4_ns = (double)(batch_c4_t1 - batch_c4_t0) / (double)n_direct;

    /* 1C. Variant 1: Online rule table update in RAM (4 concepts = 64 bytes) */
    for (size_t i = 0u; i < n_direct; ++i) {
        const km_concept_desc_t *src = ((i & 1u) == 0u) ? rules_b : rules_a;
        uint64_t t0 = km_now_ns();
        km_update_rules_ram(&eng, src, 4u);
        uint64_t t1 = km_now_ns();
        samples_update[i] = t1 - t0;
    }
    km_dist_t dist_update = compute_dist(samples_update, n_direct);

    uint64_t batch_upd_t0 = km_now_ns();
    for (size_t i = 0u; i < n_direct; ++i) {
        const km_concept_desc_t *src = ((i & 1u) == 0u) ? rules_b : rules_a;
        km_update_rules_ram(&eng, src, 4u);
    }
    uint64_t batch_upd_t1 = km_now_ns();
    double amortized_update_4_ns = (double)(batch_upd_t1 - batch_upd_t0) / (double)n_direct;

    /* Also measure full 64-concept (1024-byte) RAM table update amortized */
    km_concept_desc_t full64_a[KM_MAX_CONCEPTS];
    km_concept_desc_t full64_b[KM_MAX_CONCEPTS];
    memset(full64_a, 0, sizeof(full64_a));
    memset(full64_b, 0, sizeof(full64_b));
    memcpy(full64_a, rules_a, sizeof(rules_a));
    memcpy(full64_b, rules_b, sizeof(rules_b));
    uint64_t batch_u64_t0 = km_now_ns();
    for (size_t i = 0u; i < n_direct; ++i) {
        const km_concept_desc_t *src = ((i & 1u) == 0u) ? full64_b : full64_a;
        km_update_rules_ram(&eng, src, KM_MAX_CONCEPTS);
    }
    uint64_t batch_u64_t1 = km_now_ns();
    double amortized_update_64_ns = (double)(batch_u64_t1 - batch_u64_t0) / (double)n_direct;

    /* 2. Variant 2: Linux kernel eventfd + poll wakeup + 4-concept cascade */
    memset(&eng, 0, sizeof(eng));
    km_update_rules_ram(&eng, rules_a, 4u);

    int req_efd = eventfd(0u, EFD_CLOEXEC);
    int ack_efd = eventfd(0u, EFD_CLOEXEC);
    if (req_efd < 0 || ack_efd < 0) {
        perror("eventfd");
        return 2;
    }

    long nprocs = sysconf(_SC_NPROCESSORS_ONLN);
    /* Same-core preemption/context-switch mode (CPU 0) vs cross-core if requested */
    km_eventfd_ctx_t ctx;
    memset(&ctx, 0, sizeof(ctx));
    ctx.req_efd      = req_efd;
    ctx.ack_efd      = ack_efd;
    ctx.iterations   = n_os + 200u; /* 200 warmup + n_os measured */
    ctx.eng          = &eng;
    ctx.latencies_ns = (uint64_t *)calloc(ctx.iterations, sizeof(uint64_t));
    ctx.worker_cpu   = (nprocs > 1) ? 1 : 0;

    pthread_t th;
    if (pthread_create(&th, NULL, eventfd_worker_thread, &ctx) != 0) {
        perror("pthread_create");
        return 2;
    }

    struct pollfd ack_pfd;
    ack_pfd.fd     = ack_efd;
    ack_pfd.events = POLLIN;

    for (size_t i = 0u; i < ctx.iterations; ++i) {
        uint64_t one = 1u;
        ctx.t_send_ns = km_now_ns();
        if (write(req_efd, &one, sizeof(one)) != (ssize_t)sizeof(one)) {
            abort();
        }
        int rc;
        do {
            rc = poll(&ack_pfd, 1, -1);
        } while (rc < 0 && errno == EINTR);
        uint64_t ack_val = 0u;
        if (read(ack_efd, &ack_val, sizeof(ack_val)) != (ssize_t)sizeof(ack_val)) {
            abort();
        }
    }
    pthread_join(th, NULL);

    memcpy(samples_os, ctx.latencies_ns + 200u, n_os * sizeof(uint64_t));
    uint32_t os_commits = eng.committed_count;
    uint32_t os_rejects = eng.rejected_count;
    km_dist_t dist_os = compute_dist(samples_os, n_os);

    /* Also measure same-core context switch on CPU 0 (single-core / forced preemption) */
    memset(&eng, 0, sizeof(eng));
    km_update_rules_ram(&eng, rules_a, 4u);
    uint64_t *samples_os_samecpu = (uint64_t *)calloc(ctx.iterations, sizeof(uint64_t));
    ctx.latencies_ns = samples_os_samecpu;
    ctx.worker_cpu   = 0;
    if (pthread_create(&th, NULL, eventfd_worker_thread, &ctx) != 0) {
        perror("pthread_create samecpu");
        return 2;
    }
    for (size_t i = 0u; i < ctx.iterations; ++i) {
        uint64_t one = 1u;
        ctx.t_send_ns = km_now_ns();
        if (write(req_efd, &one, sizeof(one)) != (ssize_t)sizeof(one)) {
            abort();
        }
        int rc;
        do {
            rc = poll(&ack_pfd, 1, -1);
        } while (rc < 0 && errno == EINTR);
        uint64_t ack_val = 0u;
        if (read(ack_efd, &ack_val, sizeof(ack_val)) != (ssize_t)sizeof(ack_val)) {
            abort();
        }
    }
    pthread_join(th, NULL);
    uint64_t *samples_os_sc_meas = (uint64_t *)calloc(n_os, sizeof(uint64_t));
    memcpy(samples_os_sc_meas, samples_os_samecpu + 200u, n_os * sizeof(uint64_t));
    km_dist_t dist_os_samecpu = compute_dist(samples_os_sc_meas, n_os);

    close(req_efd);
    close(ack_efd);

    printf("{\n");
    printf("  \"mlockall_succeeded\": %s,\n", mlock_ok ? "true" : "false");
    printf("  \"online_cpus\": %ld,\n", nprocs);
    printf("  \"n_direct\": %zu,\n", n_direct);
    printf("  \"n_os_eventfd\": %zu,\n", n_os);
    printf("  \"sanity\": {\n");
    printf("    \"reject_bench_commits\": %" PRIu32 ",\n", rej_check_commits);
    printf("    \"reject_bench_rejects\": %" PRIu32 ",\n", rej_check_rejects);
    printf("    \"cascade4_bench_commits\": %" PRIu32 ",\n", casc4_commits);
    printf("    \"cascade4_bench_rejects\": %" PRIu32 ",\n", casc4_rejects);
    printf("    \"cascade4_final_c3\": %" PRId32 ",\n", casc4_c3_end);
    printf("    \"os_eventfd_total_commits\": %" PRIu32 ",\n", os_commits);
    printf("    \"os_eventfd_total_rejects\": %" PRIu32 "\n", os_rejects);
    printf("  },\n");
    printf("  \"clock_monotonic_raw_floor_ns\": {\"mean\": %.3f, \"sigma\": %.3f, \"min\": %" PRIu64 ", \"p50\": %" PRIu64 ", \"p99\": %" PRIu64 ", \"p99_9\": %" PRIu64 ", \"max\": %" PRIu64 "},\n",
           dist_clock.mean_ns, dist_clock.sigma_ns, dist_clock.min_ns, dist_clock.p50_ns, dist_clock.p99_ns, dist_clock.p999_ns, dist_clock.max_ns);
    printf("  \"c99_o3_reject_1concept_ns\": {\"amortized_mean\": %.3f, \"mean\": %.3f, \"sigma\": %.3f, \"min\": %" PRIu64 ", \"p50\": %" PRIu64 ", \"p99\": %" PRIu64 ", \"p99_9\": %" PRIu64 ", \"max\": %" PRIu64 "},\n",
           amortized_reject_ns, dist_reject.mean_ns, dist_reject.sigma_ns, dist_reject.min_ns, dist_reject.p50_ns, dist_reject.p99_ns, dist_reject.p999_ns, dist_reject.max_ns);
    printf("  \"c99_o3_cascade_4concepts_ns\": {\"amortized_mean\": %.3f, \"mean\": %.3f, \"sigma\": %.3f, \"min\": %" PRIu64 ", \"p50\": %" PRIu64 ", \"p99\": %" PRIu64 ", \"p99_9\": %" PRIu64 ", \"max\": %" PRIu64 "},\n",
           amortized_casc4_ns, dist_casc4.mean_ns, dist_casc4.sigma_ns, dist_casc4.min_ns, dist_casc4.p50_ns, dist_casc4.p99_ns, dist_casc4.p999_ns, dist_casc4.max_ns);
    printf("  \"c99_o3_rule_update_ram_ns\": {\"amortized_4concepts_mean\": %.3f, \"amortized_64concepts_mean\": %.3f, \"mean\": %.3f, \"sigma\": %.3f, \"min\": %" PRIu64 ", \"p50\": %" PRIu64 ", \"p99\": %" PRIu64 ", \"p99_9\": %" PRIu64 ", \"max\": %" PRIu64 "},\n",
           amortized_update_4_ns, amortized_update_64_ns, dist_update.mean_ns, dist_update.sigma_ns, dist_update.min_ns, dist_update.p50_ns, dist_update.p99_ns, dist_update.p999_ns, dist_update.max_ns);
    printf("  \"linux_eventfd_poll_crosscpu_cascade4_ns\": {\"mean\": %.3f, \"sigma\": %.3f, \"min\": %" PRIu64 ", \"p50\": %" PRIu64 ", \"p99\": %" PRIu64 ", \"p99_9\": %" PRIu64 ", \"max\": %" PRIu64 "},\n",
           dist_os.mean_ns, dist_os.sigma_ns, dist_os.min_ns, dist_os.p50_ns, dist_os.p99_ns, dist_os.p999_ns, dist_os.max_ns);
    printf("  \"linux_eventfd_poll_samecpu_cascade4_ns\": {\"mean\": %.3f, \"sigma\": %.3f, \"min\": %" PRIu64 ", \"p50\": %" PRIu64 ", \"p99\": %" PRIu64 ", \"p99_9\": %" PRIu64 ", \"max\": %" PRIu64 "}\n",
           dist_os_samecpu.mean_ns, dist_os_samecpu.sigma_ns, dist_os_samecpu.min_ns, dist_os_samecpu.p50_ns, dist_os_samecpu.p99_ns, dist_os_samecpu.p999_ns, dist_os_samecpu.max_ns);
    printf("}\n");

    free(samples_clock);
    free(samples_reject);
    free(samples_casc4);
    free(samples_update);
    free(samples_os);
    free(samples_os_samecpu);
    free(samples_os_sc_meas);
    return 0;
}

int main(int argc, char **argv) {
    if (argc == 5 && strcmp(argv[1], "--trace") == 0) {
        return run_trace_mode(argv[2], argv[3], atoi(argv[4]));
    }
    size_t n_direct = 100000u;
    size_t n_os     = 10000u;
    if (argc >= 3 && strcmp(argv[1], "--bench") == 0) {
        n_direct = (size_t)strtoull(argv[2], NULL, 10);
        if (argc >= 4) {
            n_os = (size_t)strtoull(argv[3], NULL, 10);
        }
    }
    return run_benchmarks(n_direct, n_os);
}
