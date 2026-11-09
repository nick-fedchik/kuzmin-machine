#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <time.h>
#include <math.h>
#include <string.h>
#include <unistd.h>
#include "kpol_gate.h"

#define BATCH_N 1000000
#define SINGLE_N 10000

/* Псевдовипадковий генератор xorshift32 із детермінованим seed */
static inline uint32_t xorshift32(uint32_t *state) {
    uint32_t x = *state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

static inline double timespec_to_ns(const struct timespec *ts) {
    return (double)ts->tv_sec * 1e9 + (double)ts->tv_nsec;
}

static inline double timespec_diff_ns(const struct timespec *start, const struct timespec *end) {
    return ((double)(end->tv_sec - start->tv_sec) * 1e9) + ((double)(end->tv_nsec - start->tv_nsec));
}

#if defined(__aarch64__)
static inline uint64_t read_cntfrq_el0(void) {
    uint64_t val;
    asm volatile("mrs %0, cntfrq_el0" : "=r"(val));
    return val;
}

static inline uint64_t read_cntvct_el0(void) {
    uint64_t val;
    asm volatile("mrs %0, cntvct_el0" : "=r"(val));
    return val;
}
#endif

static int compare_doubles(const void *a, const void *b) {
    double da = *(const double *)a;
    double db = *(const double *)b;
    if (da < db) return -1;
    if (da > db) return 1;
    return 0;
}

int main(int argc, char **argv) {
    const char *csv_out_path = (argc > 1) ? argv[1] : "av03_single_samples.csv";
    const char *json_out_path = (argc > 2) ? argv[2] : "av03_summary.json";

    printf("===================================================================\n");
    printf("   AV-03: BENCHMARK ПРОГРАМНОЇ ФУНКЦІЇ РІШЕННЯ ШЛЮЗУ KPOL (C)      \n");
    printf("===================================================================\n");

    /* Ініціалізація псевдовипадкових входів */
    uint32_t rng_state = 0x4B504F4C; /* "KPOL" */
    kpol_gate_input_t *inputs = (kpol_gate_input_t *)malloc(sizeof(kpol_gate_input_t) * SINGLE_N);
    kpol_gate_output_t out;
    if (!inputs) {
        fprintf(stderr, "Помилка виділення пам'яті для inputs\n");
        return 1;
    }

    for (int i = 0; i < SINGLE_N; i++) {
        uint32_t r1 = xorshift32(&rng_state);
        uint32_t r2 = xorshift32(&rng_state);
        inputs[i].event_valid = (r1 >> 0) & 1;
        inputs[i].candidate_known = (r1 >> 1) & 1;
        inputs[i].candidate_value = r2;
        inputs[i].assumption_known = (r1 >> 2) & 1;
        inputs[i].assumption_true = (r1 >> 3) & 1;
        inputs[i].invariant_known = (r1 >> 4) & 1;
        inputs[i].invariant_true = (r1 >> 5) & 1;
        inputs[i].hazard_known = (r1 >> 6) & 1;
        inputs[i].hazard_true = (r1 >> 7) & 1;
        inputs[i].state_current = r1;
    }

    /* ------------------------------------------------------------- */
    /* 1. ПАКЕТНИЙ ТЕСТ ПРОПУСКНОЇ ЗДАТНОСТІ: N = 1,000,000          */
    /* ------------------------------------------------------------- */
    printf("\n[1/2] Вимірювання пакетної пропускної здатності (N = %d)...\n", BATCH_N);
    kpol_gate_input_t batch_in;
    batch_in.event_valid = 1;
    batch_in.candidate_known = 1;
    batch_in.candidate_value = 0xAA55AA55;
    batch_in.assumption_known = 1;
    batch_in.assumption_true = 1;
    batch_in.invariant_known = 1;
    batch_in.invariant_true = 1;
    batch_in.hazard_known = 1;
    batch_in.hazard_true = 0;
    batch_in.state_current = 0x00000000;

    struct timespec batch_start, batch_end;
    clock_gettime(CLOCK_MONOTONIC_RAW, &batch_start);

    /* Запобігаємо оптимізації через volatile накопичувач */
    volatile uint32_t acc_sink = 0;
    for (int i = 0; i < BATCH_N; i++) {
        batch_in.candidate_value = (uint32_t)i;
        kpol_txn_gate_decision(&batch_in, &out);
        acc_sink += out.state_next + out.committed;
    }

    clock_gettime(CLOCK_MONOTONIC_RAW, &batch_end);
    double batch_total_ns = timespec_diff_ns(&batch_start, &batch_end);
    double batch_avg_ns = batch_total_ns / (double)BATCH_N;
    double batch_ops_sec = ((double)BATCH_N / batch_total_ns) * 1e9;

    printf("  -> Загальний час: %.3f мс\n", batch_total_ns / 1e6);
    printf("  -> Середній час на 1 рішення: %.2f нс\n", batch_avg_ns);
    printf("  -> Пропускна здатність: %.2f млн рішень/с\n", batch_ops_sec / 1e6);

    /* ------------------------------------------------------------- */
    /* 2. ОДИНОЧНІ ВИКЛИКИ З ФІКСАЦІЄЮ РОЗПОДІЛУ: N = 10,000         */
    /* ------------------------------------------------------------- */
    printf("\n[2/2] Вимірювання розподілу одиночних викликів (N = %d)...\n", SINGLE_N);
    double *latencies_ns = (double *)malloc(sizeof(double) * SINGLE_N);
    if (!latencies_ns) {
        fprintf(stderr, "Помилка виділення пам'яті для latencies\n");
        free(inputs);
        return 1;
    }

    FILE *csv_file = fopen(csv_out_path, "w");
    if (!csv_file) {
        fprintf(stderr, "Не вдалося відкрити %s для запису CSV\n", csv_out_path);
        free(inputs);
        free(latencies_ns);
        return 1;
    }
    fprintf(csv_file, "sample_idx,latency_ns,committed,rejected\n");

#if defined(__aarch64__)
    uint64_t timer_freq = read_cntfrq_el0();
    double ns_per_tick = 1e9 / (double)timer_freq;
    printf("  -> Метод виміру: cntvct_el0 (частота %lu Гц, %.2f нс/тік)\n", timer_freq, ns_per_tick);

    for (int i = 0; i < SINGLE_N; i++) {
        uint64_t t0 = read_cntvct_el0();
        kpol_txn_gate_decision(&inputs[i], &out);
        uint64_t t1 = read_cntvct_el0();
        double dt_ns = (double)(t1 - t0) * ns_per_tick;
        latencies_ns[i] = dt_ns;
        fprintf(csv_file, "%d,%.2f,%u,%u\n", i, dt_ns, out.committed, out.rejected);
    }
#else
    printf("  -> Метод виміру: clock_gettime(CLOCK_MONOTONIC_RAW)\n");
    struct timespec t0, t1;
    for (int i = 0; i < SINGLE_N; i++) {
        clock_gettime(CLOCK_MONOTONIC_RAW, &t0);
        kpol_txn_gate_decision(&inputs[i], &out);
        clock_gettime(CLOCK_MONOTONIC_RAW, &t1);
        double dt_ns = timespec_diff_ns(&t0, &t1);
        latencies_ns[i] = dt_ns;
        fprintf(csv_file, "%d,%.2f,%u,%u\n", i, dt_ns, out.committed, out.rejected);
    }
#endif
    fclose(csv_file);
    printf("  -> Сирі вибірки збережено в: %s\n", csv_out_path);

    /* Статистичний аналіз розподілу */
    double *sorted = (double *)malloc(sizeof(double) * SINGLE_N);
    memcpy(sorted, latencies_ns, sizeof(double) * SINGLE_N);
    qsort(sorted, SINGLE_N, sizeof(double), compare_doubles);

    double sum = 0.0;
    for (int i = 0; i < SINGLE_N; i++) sum += sorted[i];
    double mean = sum / (double)SINGLE_N;

    double var_sum = 0.0;
    for (int i = 0; i < SINGLE_N; i++) {
        double diff = sorted[i] - mean;
        var_sum += diff * diff;
    }
    double stddev = sqrt(var_sum / (double)SINGLE_N);

    double min_lat = sorted[0];
    double median_lat = sorted[SINGLE_N / 2];
    double p99_lat = sorted[(int)(SINGLE_N * 0.99)];
    double p999_lat = sorted[(int)(SINGLE_N * 0.999)];
    double max_lat = sorted[SINGLE_N - 1];

    printf("\n--- СТАТИСТИКА РОЗПОДІЛУ ЛАТЕНТНОСТІ (нс) ---\n");
    printf("  N:       %d\n", SINGLE_N);
    printf("  Min:     %.2f нс\n", min_lat);
    printf("  Середнє: %.2f нс\n", mean);
    printf("  Медіана: %.2f нс\n", median_lat);
    printf("  p99.0:   %.2f нс\n", p99_lat);
    printf("  p99.9:   %.2f нс\n", p999_lat);
    printf("  Max:     %.2f нс\n", max_lat);
    printf("  StdDev:  %.2f нс\n", stddev);

    /* Запис JSON-резюме */
    FILE *jf = fopen(json_out_path, "w");
    if (jf) {
        fprintf(jf, "{\n");
        fprintf(jf, "  \"experiment\": \"AV-03\",\n");
        fprintf(jf, "  \"batch_n\": %d,\n", BATCH_N);
        fprintf(jf, "  \"batch_avg_ns\": %.2f,\n", batch_avg_ns);
        fprintf(jf, "  \"batch_ops_sec\": %.2f,\n", batch_ops_sec);
        fprintf(jf, "  \"single_n\": %d,\n", SINGLE_N);
        fprintf(jf, "  \"min_ns\": %.2f,\n", min_lat);
        fprintf(jf, "  \"mean_ns\": %.2f,\n", mean);
        fprintf(jf, "  \"median_ns\": %.2f,\n", median_lat);
        fprintf(jf, "  \"p99_ns\": %.2f,\n", p99_lat);
        fprintf(jf, "  \"p999_ns\": %.2f,\n", p999_lat);
        fprintf(jf, "  \"max_ns\": %.2f,\n", max_lat);
        fprintf(jf, "  \"stddev_ns\": %.2f\n", stddev);
        fprintf(jf, "}\n");
        fclose(jf);
        printf("  -> JSON резюме збережено в: %s\n", json_out_path);
    }

    free(inputs);
    free(latencies_ns);
    free(sorted);
    return 0;
}
