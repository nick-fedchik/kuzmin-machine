/* ============================================================================
 * File: bms_c99_hil_bench.c
 * Issue: #270 — Commercial B2B Case 1 (Automotive BMS Safety Cascade)
 * Description:
 *   Strict ISO C99 (-std=c99 -O2 -Wall -Wextra -Werror -pedantic) verification
 *   and L1-cache WCET benchmark driver for the auto-generated BMS safety module
 *   (bms_safety_cascade_gen.c).
 * ============================================================================ */

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <time.h>

#include "bms_safety_cascade_gen.c"

typedef struct {
    uint8_t root_cid;
    int32_t param;
    int     param_valid;
    int32_t exp_c0;
    int32_t exp_c1;
    int32_t exp_c2;
    int32_t exp_c3;
    uint32_t exp_events;
    uint32_t exp_commits;
    uint32_t exp_rejects;
    uint32_t exp_faults;
} bms_test_step_t;

int main(void) {
    km_safety_ctx_t ctx;
    km_safety_ctx_t fault_ctx;
    km_safety_ctx_t bench_ctx;
    km_safety_step_result_t step_res;
    km_safety_step_result_t (*volatile step_fn)(km_safety_ctx_t *, uint8_t, int32_t, bool) =
        km_safety_step_event;

    /* 1. Hardware-compatible 8-event BMS trace (verified against CFG-P RTL & Zynq-7020 PL) */
    static const bms_test_step_t hw_trace[8] = {
        /* ev 0: nominal 15 mV (< 50 mV threshold) -> reject at C0 */
        { 0u,   15, 1, 0, 0, 2, 10,  1u,  0u, 1u, 0u },
        /* ev 1: out-of-range spike 5500 mV (> 5000 mV) -> reject at C0 */
        { 0u, 5500, 1, 0, 0, 2, 10,  2u,  0u, 2u, 0u },
        /* ev 2: imbalance 120 mV -> full 4-stage cascade C0->C1->C2->C3 (pre-trip=1) */
        { 0u,  120, 1, 1, 1, 1,  1,  6u,  4u, 2u, 0u },
        /* ev 3: nominal 49 mV -> reject at C0 */
        { 0u,   49, 1, 1, 1, 1,  1,  7u,  4u, 3u, 0u },
        /* ev 4: imbalance 180 mV -> full 4-stage cascade C0->C1->C2->C3 (contactor open=0) */
        { 0u,  180, 1, 2, 2, 0,  0, 11u,  8u, 3u, 0u },
        /* ev 5: imbalance 250 mV -> C0, C1 commit; C2 (0-1=-1) blocked by inv >= 0; C3 stays 0 */
        { 0u,  250, 1, 3, 3, 0,  0, 14u, 10u, 4u, 0u },
        /* ev 6: boundary 5000 mV -> C0, C1 commit; C2 blocked by inv >= 0; C3 stays 0 */
        { 0u, 5000, 1, 4, 4, 0,  0, 17u, 12u, 5u, 0u },
        /* ev 7: negative -10 mV -> reject at C0 */
        { 0u,  -10, 1, 4, 4, 0,  0, 18u, 12u, 6u, 0u }
    };

    uint32_t i;
    clock_t t0, t1;
    double ns_single_reject;
    double ns_fault_reject;
    double ns_full_cascade4;
    const uint32_t bench_iters = 200000u;

    km_safety_init(&ctx);
    for (i = 0u; i < 8u; ++i) {
        const bms_test_step_t *s = &hw_trace[i];
        step_res = step_fn(&ctx, s->root_cid, s->param, s->param_valid != 0);
        (void)step_res;
        if ((ctx.state[0] != s->exp_c0) ||
            (ctx.state[1] != s->exp_c1) ||
            (ctx.state[2] != s->exp_c2) ||
            (ctx.state[3] != s->exp_c3) ||
            (ctx.events_processed != s->exp_events) ||
            (ctx.commits != s->exp_commits) ||
            (ctx.rejects != s->exp_rejects) ||
            (ctx.fault_propagations != s->exp_faults)) {
            fprintf(
                stderr,
                "FAIL at hw_trace[%u]: state=[%d,%d,%d,%d] ev=%u comm=%u rej=%u fault=%u\n",
                (unsigned)i,
                (int)ctx.state[0],
                (int)ctx.state[1],
                (int)ctx.state[2],
                (int)ctx.state[3],
                (unsigned)ctx.events_processed,
                (unsigned)ctx.commits,
                (unsigned)ctx.rejects,
                (unsigned)ctx.fault_propagations
            );
            return 2;
        }
    }

    /* 2. isoUART Sensor Fault & Uncertainty ('_') Propagation Trace */
    km_safety_init(&fault_ctx);

    /* 2a. Broken sensor sends 0 mV with param_valid=false (CRC error): must NOT mask as benign */
    step_res = step_fn(&fault_ctx, 0u, 0, false);
    if ((step_res.status != KM_SAFETY_STEP_REJECTED_FAULT) ||
        (!step_res.fault_propagated) ||
        (fault_ctx.fault_propagations != 1u) ||
        (fault_ctx.commits != 0u) ||
        (fault_ctx.rejects != 1u)) {
        fprintf(stderr, "FAIL at fault_trace 2a (zero param with param_valid=false)\n");
        return 2;
    }

    /* 2b. Broken sensor sends 120 mV with param_valid=false: must NOT trigger cascade */
    step_res = step_fn(&fault_ctx, 0u, 120, false);
    if ((step_res.status != KM_SAFETY_STEP_REJECTED_FAULT) ||
        (fault_ctx.fault_propagations != 2u) ||
        (fault_ctx.commits != 0u) ||
        (fault_ctx.state[0] != 0) ||
        (fault_ctx.state[3] != 10)) {
        fprintf(stderr, "FAIL at fault_trace 2b (120 mV with param_valid=false)\n");
        return 2;
    }

    /* 2c. Invalidate Pack_Fault_Latch (CID 2 = '_') and send valid 120 mV to CID 0:
     * C0 and C1 commit, then cascade halts Fail-Closed at CID 2 with fault_propagations++ */
    km_safety_invalidate_concept(&fault_ctx, 2u);
    step_res = step_fn(&fault_ctx, 0u, 120, true);
    if ((fault_ctx.state[0] != 1) ||
        (fault_ctx.state[1] != 1) ||
        (fault_ctx.state[2] != 2) ||
        (fault_ctx.state[3] != 10) ||
        (fault_ctx.commits != 2u) ||
        (fault_ctx.rejects != 3u) ||
        (fault_ctx.fault_propagations != 3u) ||
        (!step_res.fault_propagated)) {
        fprintf(stderr, "FAIL at fault_trace 2c (mid-cascade concept uncertainty)\n");
        return 2;
    }

    /* 2d. Revalidate CID 2 and verify full 4-stage cascade completes */
    km_safety_revalidate_concept(&fault_ctx, 2u, 2);
    step_res = step_fn(&fault_ctx, 0u, 120, true);
    if ((fault_ctx.state[0] != 2) ||
        (fault_ctx.state[1] != 2) ||
        (fault_ctx.state[2] != 1) ||
        (fault_ctx.state[3] != 1) ||
        (fault_ctx.commits != 6u) ||
        (fault_ctx.fault_propagations != 3u)) {
        fprintf(stderr, "FAIL at fault_trace 2d (revalidated cascade)\n");
        return 2;
    }

    /* 3. L1-Cache Deterministic Execution Timing Benchmark (N = 200,000) */
    km_safety_init(&bench_ctx);
    /* Warmup */
    for (i = 0u; i < 2000u; ++i) {
        (void)step_fn(&bench_ctx, 0u, 15, true);
    }

    km_safety_init(&bench_ctx);
    t0 = clock();
    for (i = 0u; i < bench_iters; ++i) {
        (void)step_fn(&bench_ctx, 0u, 15, true);
    }
    t1 = clock();
    ns_single_reject = ((double)(t1 - t0) * 1.0e9 / (double)CLOCKS_PER_SEC) / (double)bench_iters;

    km_safety_init(&bench_ctx);
    t0 = clock();
    for (i = 0u; i < bench_iters; ++i) {
        (void)step_fn(&bench_ctx, 0u, 120, false);
    }
    t1 = clock();
    ns_fault_reject = ((double)(t1 - t0) * 1.0e9 / (double)CLOCKS_PER_SEC) / (double)bench_iters;

    km_safety_init(&bench_ctx);
    bench_ctx.state[2] = 1000000;
    t0 = clock();
    for (i = 0u; i < bench_iters; ++i) {
        (void)step_fn(&bench_ctx, 0u, 120, true);
    }
    t1 = clock();
    ns_full_cascade4 = ((double)(t1 - t0) * 1.0e9 / (double)CLOCKS_PER_SEC) / (double)bench_iters;

    printf("{\n");
    printf("  \"verdict\": \"PASS\",\n");
    printf("  \"hw_trace_final_state\": [%d, %d, %d, %d],\n",
           (int)ctx.state[0], (int)ctx.state[1], (int)ctx.state[2], (int)ctx.state[3]);
    printf("  \"hw_trace_events\": %u,\n", (unsigned)ctx.events_processed);
    printf("  \"hw_trace_commits\": %u,\n", (unsigned)ctx.commits);
    printf("  \"hw_trace_rejects\": %u,\n", (unsigned)ctx.rejects);
    printf("  \"hw_trace_fault_propagations\": %u,\n", (unsigned)ctx.fault_propagations);
    printf("  \"fault_trace_commits\": %u,\n", (unsigned)fault_ctx.commits);
    printf("  \"fault_trace_rejects\": %u,\n", (unsigned)fault_ctx.rejects);
    printf("  \"fault_trace_fault_propagations\": %u,\n", (unsigned)fault_ctx.fault_propagations);
    printf("  \"bench_iterations\": %u,\n", (unsigned)bench_iters);
    printf("  \"ns_per_single_reject\": %.2f,\n", ns_single_reject);
    printf("  \"ns_per_fault_reject\": %.2f,\n", ns_fault_reject);
    printf("  \"ns_per_full_4stage_cascade\": %.2f,\n", ns_full_cascade4);
    printf("  \"ns_per_cascade_concept_step\": %.2f\n", ns_full_cascade4 / 4.0);
    printf("}\n");

    return 0;
}
