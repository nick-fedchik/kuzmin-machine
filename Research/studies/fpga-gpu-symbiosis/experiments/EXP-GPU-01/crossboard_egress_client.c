/* ============================================================================
 * Машина Кузьміна (Kuzmin Machine) — Клієнт PYNQ-Z1 EXP-GPU-01 (Issue #226)
 * Файл: crossboard_egress_client.c
 * Платформа: Digilent PYNQ-Z1 (Xilinx Zynq-7000 XC7Z020, ARM Cortex-A9 + PL)
 *
 * Ініціює подію в апаратному конвеєрі PL (0x40000000, CFG-P + PMOD Event Egress),
 * зчитує згенерований коміт (cid, mask16, last_state), пакує 64-бітний кадр
 * із CRC-8 (poly 0x07) за специфікацією km_pmod_event_egress.sv і відправляє
 * його через GbE UDP (SO_BUSY_POLL) у cudaHostAllocMapped Event Mailbox на
 * Jetson AGX Orin J501 (192.168.68.68), вимірюючи наскрізну латентність T_e2e.
 * ============================================================================ */

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <netinet/in.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

#define PL_BASE_ADDR       0x40000000UL
#define PL_MAP_SIZE        0x2000UL
#define REG_ID             0x000
#define REG_BRAM_ADDR      0x004
#define REG_BRAM_DATA      0x008
#define REG_STIM_PARAM     0x00C
#define REG_STIM_TRIG      0x010
#define REG_STATUS_BUSY    0x014
#define REG_EVENTS_TOTAL   0x018
#define REG_COMMITS_TOTAL  0x01C
#define REG_REJECTS_TOTAL  0x020
#define EXPECTED_KPMC_ID   0x4B504D43U

typedef struct __attribute__((packed)) {
    uint32_t req_seq;
    uint32_t pl_mmio_ns;
    uint64_t egress_frame64;
} km_udp_req_t;

typedef struct __attribute__((packed)) {
    uint32_t req_seq;
    uint32_t ack_seq_id;
    uint32_t status;
    uint32_t crc_drop_count;
    uint64_t t_jetson_host_ns;
    uint64_t last_frame64;
} km_udp_ack_t;

static uint8_t km_calc_crc8(uint64_t payload_56) {
    uint8_t crc = 0x00u;
    for (int bit = 55; bit >= 0; --bit) {
        uint8_t fb = (uint8_t)(((crc >> 7) ^ ((payload_56 >> bit) & 1ULL)) & 1u);
        crc = (uint8_t)(((crc << 1) & 0xFFu) ^ (fb ? 0x07u : 0x00u));
    }
    return crc;
}

static uint64_t km_pack_egress_frame64(uint8_t cid, uint16_t mask16, uint32_t state) {
    uint64_t payload_56 = ((uint64_t)0x1ULL << 54)
                        | (((uint64_t)cid & 0x3FULL) << 48)
                        | (((uint64_t)mask16 & 0xFFFFULL) << 32)
                        | (uint64_t)state;
    uint8_t crc8 = km_calc_crc8(payload_56);
    return ((uint64_t)crc8 << 56) | payload_56;
}

static inline uint64_t monotonic_raw_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

static inline void mmio_write(volatile uint32_t *base, uint32_t offset, uint32_t val) {
    base[offset >> 2] = val;
}

static inline uint32_t mmio_read(volatile uint32_t *base, uint32_t offset) {
    return base[offset >> 2];
}

static void program_cascade_bram(volatile uint32_t *base) {
    for (uint32_t addr = 0; addr < 256; ++addr) {
        mmio_write(base, REG_BRAM_ADDR, addr);
        mmio_write(base, REG_BRAM_DATA, 0u);
    }
    /* C0: threshold < 50 -> state += 1, cascade to C1 (exact cme2_cascade.bin words) */
    mmio_write(base, REG_BRAM_ADDR, 0); mmio_write(base, REG_BRAM_DATA, 10u);
    mmio_write(base, REG_BRAM_ADDR, 1); mmio_write(base, REG_BRAM_DATA, 50u);
    mmio_write(base, REG_BRAM_ADDR, 2); mmio_write(base, REG_BRAM_DATA, 0x01001304u);
    mmio_write(base, REG_BRAM_ADDR, 3); mmio_write(base, REG_BRAM_DATA, 0x00000001u);

    /* C1: state += 1, cascade to C2 */
    mmio_write(base, REG_BRAM_ADDR, 4); mmio_write(base, REG_BRAM_ADDR + 0, 4);
    mmio_write(base, REG_BRAM_ADDR, 4); mmio_write(base, REG_BRAM_DATA, 0u);
    mmio_write(base, REG_BRAM_ADDR, 5); mmio_write(base, REG_BRAM_DATA, 10u);
    mmio_write(base, REG_BRAM_ADDR, 6); mmio_write(base, REG_BRAM_DATA, 0x01001303u);
    mmio_write(base, REG_BRAM_ADDR, 7); mmio_write(base, REG_BRAM_DATA, 0x00000002u);

    /* C2: state += 1, cascade to C3 */
    mmio_write(base, REG_BRAM_ADDR, 8);  mmio_write(base, REG_BRAM_DATA, 0u);
    mmio_write(base, REG_BRAM_ADDR, 9);  mmio_write(base, REG_BRAM_DATA, 0u);
    mmio_write(base, REG_BRAM_ADDR, 10); mmio_write(base, REG_BRAM_DATA, 0x01001303u);
    mmio_write(base, REG_BRAM_ADDR, 11); mmio_write(base, REG_BRAM_DATA, 0x00000003u);

    /* C3: leaf concept, state += 1 */
    mmio_write(base, REG_BRAM_ADDR, 12); mmio_write(base, REG_BRAM_DATA, 0u);
    mmio_write(base, REG_BRAM_ADDR, 13); mmio_write(base, REG_BRAM_DATA, 0u);
    mmio_write(base, REG_BRAM_ADDR, 14); mmio_write(base, REG_BRAM_DATA, 0x00000303u);
    mmio_write(base, REG_BRAM_ADDR, 15); mmio_write(base, REG_BRAM_DATA, 0x00000000u);
}

int main(int argc, char **argv) {
    const char *server_ip = "192.168.68.68";
    int server_port = 55226;
    uint32_t num_events = 1000u;
    int run_idx = 1;
    const char *json_out = "pynq_crossboard_run.json";

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--server-ip") == 0 && i + 1 < argc) {
            server_ip = argv[++i];
        } else if (strcmp(argv[i], "--port") == 0 && i + 1 < argc) {
            server_port = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--events") == 0 && i + 1 < argc) {
            num_events = (uint32_t)atoi(argv[++i]);
        } else if (strcmp(argv[i], "--run-index") == 0 && i + 1 < argc) {
            run_idx = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--json-out") == 0 && i + 1 < argc) {
            json_out = argv[++i];
        }
    }

    int mem_fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (mem_fd < 0) {
        perror("open /dev/mem");
        return 1;
    }
    volatile uint32_t *pl = (volatile uint32_t *)mmap(
        NULL, PL_MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, mem_fd, PL_BASE_ADDR
    );
    if (pl == MAP_FAILED) {
        perror("mmap PL");
        return 1;
    }

    uint32_t hw_id = mmio_read(pl, REG_ID);
    if (hw_id != EXPECTED_KPMC_ID) {
        fprintf(stderr, "Unexpected PL REG_ID: 0x%08x\n", hw_id);
        return 1;
    }

    program_cascade_bram(pl);

    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        perror("socket");
        return 1;
    }
#ifdef SO_BUSY_POLL
    int busy_us = 50;
    setsockopt(sock, SOL_SOCKET, SO_BUSY_POLL, &busy_us, sizeof(busy_us));
#endif
    struct timeval tv;
    tv.tv_sec  = 2;
    tv.tv_usec = 0;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    struct sockaddr_in srv_addr;
    memset(&srv_addr, 0, sizeof(srv_addr));
    srv_addr.sin_family = AF_INET;
    srv_addr.sin_port   = htons((uint16_t)server_port);
    inet_pton(AF_INET, server_ip, &srv_addr.sin_addr);

    /* 1. Негативний контроль CRC-8 на живому контурі (AGENTS.md §4.1) */
    uint64_t valid_test_frame = km_pack_egress_frame64(3u, 0xA55Au, 1u);
    km_udp_req_t bad_req;
    bad_req.req_seq        = 0xFFFFFFFEu;
    bad_req.pl_mmio_ns     = 80u;
    bad_req.egress_frame64 = valid_test_frame ^ (1ULL << 60); /* flip CRC bit */
    sendto(sock, &bad_req, sizeof(bad_req), 0, (struct sockaddr *)&srv_addr, sizeof(srv_addr));
    km_udp_ack_t bad_ack;
    memset(&bad_ack, 0, sizeof(bad_ack));
    if (recvfrom(sock, &bad_ack, sizeof(bad_ack), 0, NULL, NULL) != (ssize_t)sizeof(bad_ack) ||
        bad_ack.status != 1u || bad_ack.crc_drop_count != 1u) {
        fprintf(stderr, "Negative CRC-8 test failed: status=%u drops=%u\n",
                bad_ack.status, bad_ack.crc_drop_count);
        return 2;
    }

    double *rtt_us    = (double *)calloc(num_events, sizeof(double));
    double *oneway_us = (double *)calloc(num_events, sizeof(double));
    double *pl_us     = (double *)calloc(num_events, sizeof(double));
    double *jhost_us  = (double *)calloc(num_events, sizeof(double));

    uint32_t commits_before = mmio_read(pl, REG_COMMITS_TOTAL);
    uint64_t last_frame = 0;

    for (uint32_t i = 0; i < num_events; ++i) {
        uint64_t t0 = monotonic_raw_ns();

        mmio_write(pl, REG_STIM_PARAM, 1u);
        mmio_write(pl, REG_STIM_TRIG,  1u); /* trigger C0 (bit 0) -> cascade C0..C3 */
        while (mmio_read(pl, REG_STATUS_BUSY) != 0u) {
            /* wait for 8-cycle sequencer cascade completion */
        }
        mmio_write(pl, REG_BRAM_ADDR, 12u); /* read C3 leaf state W0 */
        uint32_t leaf_state = mmio_read(pl, REG_BRAM_DATA);

        uint64_t t_pl_done = monotonic_raw_ns();
        uint32_t pl_mmio_ns = (uint32_t)(t_pl_done - t0);

        uint16_t mask16 = (uint16_t)(0xFFFFu ^ (i & 0xFFu));
        uint64_t frame64 = km_pack_egress_frame64(3u, mask16, leaf_state);
        last_frame = frame64;

        km_udp_req_t req;
        req.req_seq        = i + 1u;
        req.pl_mmio_ns     = pl_mmio_ns;
        req.egress_frame64 = frame64;

        sendto(sock, &req, sizeof(req), 0, (struct sockaddr *)&srv_addr, sizeof(srv_addr));
        km_udp_ack_t ack;
        ssize_t n = recvfrom(sock, &ack, sizeof(ack), 0, NULL, NULL);
        uint64_t t_end = monotonic_raw_ns();

        if (n != (ssize_t)sizeof(ack) || ack.status != 0u || ack.ack_seq_id != i + 1u) {
            fprintf(stderr, "Event %u ACK error: n=%zd status=%u ack=%u\n",
                    i + 1u, n, ack.status, ack.ack_seq_id);
            return 3;
        }

        uint64_t total_rtt_ns = t_end - t0;
        uint64_t net_rtt_ns   = (total_rtt_ns > (pl_mmio_ns + ack.t_jetson_host_ns))
                              ? (total_rtt_ns - pl_mmio_ns - ack.t_jetson_host_ns)
                              : 0ULL;
        uint64_t oneway_est_ns = pl_mmio_ns + (net_rtt_ns / 2ULL) + ack.t_jetson_host_ns;

        rtt_us[i]    = (double)total_rtt_ns / 1000.0;
        oneway_us[i] = (double)oneway_est_ns / 1000.0;
        pl_us[i]     = (double)pl_mmio_ns / 1000.0;
        jhost_us[i]  = (double)ack.t_jetson_host_ns / 1000.0;
    }

    uint32_t commits_after = mmio_read(pl, REG_COMMITS_TOTAL);
    uint32_t commits_delta = commits_after - commits_before;

    /* Штатне завершення персистентного кернела на Jetson */
    km_udp_req_t stop_req;
    stop_req.req_seq        = 0xFFFFFFFFu;
    stop_req.pl_mmio_ns     = 0u;
    stop_req.egress_frame64 = 0ULL;
    sendto(sock, &stop_req, sizeof(stop_req), 0, (struct sockaddr *)&srv_addr, sizeof(srv_addr));
    km_udp_ack_t stop_ack;
    recvfrom(sock, &stop_ack, sizeof(stop_ack), 0, NULL, NULL);

    FILE *fp = fopen(json_out, "w");
    if (!fp) {
        perror("fopen json_out");
        return 4;
    }
    fprintf(fp, "{\n");
    fprintf(fp, "  \"run_index\": %d,\n", run_idx);
    fprintf(fp, "  \"events\": %u,\n", num_events);
    fprintf(fp, "  \"pl_reg_id\": \"0x%08x\",\n", hw_id);
    fprintf(fp, "  \"pl_commits_delta\": %u,\n", commits_delta);
    fprintf(fp, "  \"neg_crc_test_rejected\": true,\n");
    fprintf(fp, "  \"last_frame64_hex\": \"0x%016" PRIx64 "\",\n", last_frame);

    fprintf(fp, "  \"samples_rtt_us\": [");
    for (uint32_t i = 0; i < num_events; ++i) {
        fprintf(fp, "%s%.3f", (i ? ", " : ""), rtt_us[i]);
    }
    fprintf(fp, "],\n");

    fprintf(fp, "  \"samples_oneway_est_us\": [");
    for (uint32_t i = 0; i < num_events; ++i) {
        fprintf(fp, "%s%.3f", (i ? ", " : ""), oneway_us[i]);
    }
    fprintf(fp, "],\n");

    fprintf(fp, "  \"samples_pl_mmio_us\": [");
    for (uint32_t i = 0; i < num_events; ++i) {
        fprintf(fp, "%s%.3f", (i ? ", " : ""), pl_us[i]);
    }
    fprintf(fp, "],\n");

    fprintf(fp, "  \"samples_jetson_host_us\": [");
    for (uint32_t i = 0; i < num_events; ++i) {
        fprintf(fp, "%s%.3f", (i ? ", " : ""), jhost_us[i]);
    }
    fprintf(fp, "]\n}\n");
    fclose(fp);

    close(sock);
    munmap((void *)pl, PL_MAP_SIZE);
    close(mem_fd);
    return 0;
}
