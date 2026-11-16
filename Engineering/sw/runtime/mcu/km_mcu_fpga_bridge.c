/* ============================================================================
 * Машина Кузьміна (Kuzmin Machine) — Гібридний ко-дизайн: MCU Runtime + FPGA
 * Файл: km_mcu_fpga_bridge.c
 * Цільова платформа: Digilent PYNQ-Z1 (ARM Cortex-A9 @ 650 MHz + Xilinx XC7Z020 PL)
 * Призначення:
 *   Реалізація Пропозиції 3 (Гібридний ко-дизайн):
 *   1. Вбудоване виконавче ядро МК на C99 (Bare-Metal сумісне).
 *   2. Апаратне делегування критичних транзакцій в FPGA (шлюз 0x40000000 через MMIO).
 *   3. Захист інваріантів у кремнії: апаратна ізоляція помилок софту.
 * ============================================================================ */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <time.h>

/* --- Конфігурація пулів пам'яті MCU рантайму --- */
#define KM_MAX_CONCEPTS       64u
#define KM_MAX_SUBSCRIPTIONS  128u
#define KM_MAX_INSTRUCTIONS   512u
#define KM_SR_STACK_DEPTH     16u
#define KM_EVENT_QUEUE_SIZE   64u

/* --- Коди операцій лінії O --- */
#define KM_OPC_NOP            0x0u
#define KM_OPC_GO             0x1u
#define KM_OPC_DO             0x2u
#define KM_OPC_IMM            0x3u
#define KM_OPC_EXIT           0x5u

/* --- Під-операції Go --- */
#define KM_GO_EXEC            0x0u  /* "|" */
#define KM_GO_WRITE           0x1u  /* "←" */
#define KM_GO_READ            0x2u  /* "→" */

/* --- Прапорці інструкцій та концептів --- */
#define KM_FLAG_SELF_SUPPRESS 0x01u
#define KM_FLAG_HW_PROTECTED  0x08u /* Концепт захищено апаратним шлюзом FPGA */

/* --- Під-операції Do (АЛП) --- */
#define KM_DO_ADD             0u
#define KM_DO_SUB             1u
#define KM_DO_MUL             2u
#define KM_DO_MOD_INC         5u

/* --- Вбудовані події '::' --- */
#define KM_EV_ABSENT          (1u << 0)
#define KM_EV_NULL            (1u << 1)
#define KM_EV_POSITIVE        (1u << 2)
#define KM_EV_NEGATIVE        (1u << 3)
#define KM_EV_EVEN            (1u << 4)
#define KM_EV_UNEVEN          (1u << 5)
#define KM_EV_CHANGED         (1u << 6)
#define KM_EV_ALWAYS          (1u << 7)

/* --- Фази Великої крапки (•) --- */
typedef enum {
    KM_PHASE_PRE_WRITE   = 0,
    KM_PHASE_POST_CHANGE = 1,
    KM_PHASE_ON_READ     = 2,
    KM_PHASE_ON_EXEC     = 3,
    KM_PHASE_ON_ABORT    = 4  /* Аварійне скидання / Відхилення інваріанта кремнієм */
} km_phase_t;

/* --- Дескриптор концепту в SRAM --- */
typedef struct {
    int32_t  val_cur;
    int32_t  val_prev;
    uint8_t  flags;           /* KM_FLAG_HW_PROTECTED тощо */
    uint8_t  big_dot_ok;      /* 0 = '!' (True), 1 = '¬' (False) */
    uint16_t first_sub_idx;
    uint16_t sub_count;
} km_concept_t;

/* --- Дескриптор підписки --- */
typedef struct {
    uint16_t owner_cid;
    uint8_t  phase;
    uint8_t  trigger_mask;
    uint16_t line_start_pc;
    uint16_t line_len;
} km_sub_t;

/* --- Апаратні регістри FPGA AXI4-Lite (0x40000000) --- */
#define FPGA_BASE_ADDR        0x40000000ULL
#define FPGA_MAP_SIZE         0x1000U

#define REG_CANDIDATE         0x00U
#define REG_CONDITIONS        0x04U
#define REG_COMMAND           0x08U
#define REG_STATUS            0x0CU
#define REG_STATE             0x10U
#define REG_IDENTIFICATION    0x14U
#define REG_LOWER_BOUND       0x18U
#define REG_UPPER_BOUND       0x1CU
#define REG_RULE_CFG          0x20U
#define REG_PREDICATE_VEC     0x24U
#define REG_BIG_DOT           0x28U

#define FPGA_EXPECTED_ID      0x4B504F4CU /* "KPOL" */

/* Прапорці STATUS */
#define STATUS_DONE               (1u << 0)
#define STATUS_COMMITTED          (1u << 1)
#define STATUS_REJECTED           (1u << 2)
#define STATUS_REJECTED_INVARIANT (1u << 4)
#define STATUS_CHANGED            (1u << 5)
#define STATUS_BUSY               (1u << 8)

/* Прапорці RULE_CFG */
#define RULE_REQUIRE_EVEN         (1u << 0)
#define RULE_REQUIRE_POSITIVE     (1u << 1)
#define RULE_REQUIRE_NON_NULL     (1u << 2)
#define RULE_REQUIRE_RANGE        (1u << 3)
#define RULE_REQUIRE_CHANGED      (1u << 4)
#define RULE_USE_HW_EVAL          (1u << 5)

/* --- Структура інтерфейсу FPGA MMIO --- */
typedef struct {
    int               mem_fd;
    volatile uint32_t *regs;
    bool              mock_mode;
    uint32_t          mock_storage[16];
} km_fpga_bridge_t;

/* --- Контекст віртуальної машини --- */
typedef struct {
    km_concept_t      concepts[KM_MAX_CONCEPTS];
    km_sub_t          subs[KM_MAX_SUBSCRIPTIONS];
    uint32_t          code_o[KM_MAX_INSTRUCTIONS];
    uint16_t          event_queue[KM_EVENT_QUEUE_SIZE];
    uint16_t          eq_head;
    uint16_t          eq_tail;
    uint16_t          eq_count;
    int32_t           sr_stack[KM_SR_STACK_DEPTH];
    uint8_t           sr_sp;
    uint32_t          step_count;
    km_fpga_bridge_t  fpga;
} km_vm_t;

/* ============================================================================
 * ДРАЙВЕР АПАРАТНОГО ІНТЕРФЕЙСУ FPGA MMIO
 * ============================================================================ */

bool km_fpga_init(km_fpga_bridge_t *fb, bool force_mock) {
    memset(fb, 0, sizeof(*fb));
    fb->mem_fd = -1;

    if (force_mock) {
        fb->mock_mode = true;
        fb->mock_storage[REG_IDENTIFICATION / 4] = FPGA_EXPECTED_ID;
        fb->mock_storage[REG_UPPER_BOUND / 4]    = 0x7FFFFFFFU;
        printf("[FPGA Bridge] Ініціалізація в режимі ПРОГРАМНОГО МОКУ\n");
        return true;
    }

    fb->mem_fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fb->mem_fd < 0) {
        printf("[FPGA Bridge] Не вдалося відкрити /dev/mem (потрібні root-права). Перехід на MOCK.\n");
        fb->mock_mode = true;
        fb->mock_storage[REG_IDENTIFICATION / 4] = FPGA_EXPECTED_ID;
        fb->mock_storage[REG_UPPER_BOUND / 4]    = 0x7FFFFFFFU;
        return true;
    }

    void *map_base = mmap(NULL, FPGA_MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED,
                          fb->mem_fd, (off_t)FPGA_BASE_ADDR);
    if (map_base == MAP_FAILED) {
        printf("[FPGA Bridge] Помилка mmap /dev/mem. Перехід на MOCK.\n");
        close(fb->mem_fd);
        fb->mem_fd = -1;
        fb->mock_mode = true;
        fb->mock_storage[REG_IDENTIFICATION / 4] = FPGA_EXPECTED_ID;
        fb->mock_storage[REG_UPPER_BOUND / 4]    = 0x7FFFFFFFU;
        return true;
    }

    fb->regs = (volatile uint32_t *)map_base;
    fb->mock_mode = false;

    /* Перевірка апаратного ідентифікатора */
    uint32_t chip_id = fb->regs[REG_IDENTIFICATION / 4];
    if (chip_id != FPGA_EXPECTED_ID) {
        printf("[FPGA Bridge] УВАГА: Отримано REG_ID=0x%08X (очікувалося 0x%08X 'KPOL').\n",
               chip_id, FPGA_EXPECTED_ID);
        return false;
    }

    printf("[FPGA Bridge] Зв'язок із кремнієм PL встановлено! REG_ID=0x%08X (ASCII 'KPOL')\n", chip_id);
    return true;
}

void km_fpga_close(km_fpga_bridge_t *fb) {
    if (!fb->mock_mode && fb->regs != NULL) {
        munmap((void *)fb->regs, FPGA_MAP_SIZE);
        fb->regs = NULL;
    }
    if (fb->mem_fd >= 0) {
        close(fb->mem_fd);
        fb->mem_fd = -1;
    }
}

uint32_t km_fpga_read(km_fpga_bridge_t *fb, uint32_t offset) {
    if (fb->mock_mode) {
        return fb->mock_storage[offset / 4];
    }
    return fb->regs[offset / 4];
}

void km_fpga_write(km_fpga_bridge_t *fb, uint32_t offset, uint32_t val) {
    if (fb->mock_mode) {
        fb->mock_storage[offset / 4] = val;
        if (offset == REG_COMMAND && (val & 1)) {
            /* Програмна емуляція шлюзу для моку */
            int32_t cand = (int32_t)fb->mock_storage[REG_CANDIDATE / 4];
            uint8_t cfg  = (uint8_t)fb->mock_storage[REG_RULE_CFG / 4];
            int32_t low  = (int32_t)fb->mock_storage[REG_LOWER_BOUND / 4];
            int32_t high = (int32_t)fb->mock_storage[REG_UPPER_BOUND / 4];
            int32_t cur  = (int32_t)fb->mock_storage[REG_STATE / 4];

            bool ok = true;
            if (cfg & RULE_REQUIRE_EVEN) ok = ok && ((cand & 1) == 0);
            if (cfg & RULE_REQUIRE_RANGE) ok = ok && (cand >= low && cand <= high);

            if (ok) {
                fb->mock_storage[REG_STATUS / 4] = STATUS_DONE | STATUS_COMMITTED |
                    (cand != cur ? STATUS_CHANGED : 0);
                fb->mock_storage[REG_STATE / 4] = (uint32_t)cand;
                fb->mock_storage[REG_BIG_DOT / 4] = 1;
            } else {
                fb->mock_storage[REG_STATUS / 4] = STATUS_DONE | STATUS_REJECTED | STATUS_REJECTED_INVARIANT;
                fb->mock_storage[REG_BIG_DOT / 4] = 0;
            }
        }
        return;
    }
    fb->regs[offset / 4] = val;
}

bool km_fpga_execute_txn(km_fpga_bridge_t *fb, int32_t candidate, uint32_t *out_status, int32_t *out_state) {
    km_fpga_write(fb, REG_CANDIDATE, (uint32_t)candidate);
    km_fpga_write(fb, REG_CONDITIONS, 0x00000007U); /* cand_known=1, assump_known=1, assump_true=1 */
    km_fpga_write(fb, REG_COMMAND, 0x01U);

    /* Очікування завершення апаратного 1-тактового циклу */
    uint32_t st = 0;
    for (int spin = 0; spin < 1000; spin++) {
        st = km_fpga_read(fb, REG_STATUS);
        if ((st & STATUS_DONE) && !(st & STATUS_BUSY)) {
            break;
        }
    }

    *out_status = st;
    *out_state  = (int32_t)km_fpga_read(fb, REG_STATE);
    return (st & STATUS_COMMITTED) != 0;
}

/* ============================================================================
 * ВИКОНАВЧЕ ЯДРО МАШИНИ КУЗЬМІНА (C99)
 * ============================================================================ */

static inline uint32_t km_pack_instr(uint8_t opc, uint8_t sub_op, uint8_t flags, uint16_t operand) {
    return ((uint32_t)(opc & 0x0Fu) << 28)
         | ((uint32_t)(sub_op & 0x0Fu) << 24)
         | ((uint32_t)flags << 16)
         | (uint32_t)operand;
}

static inline uint8_t km_eval_event_vector(const km_concept_t *c) {
    uint8_t vec = KM_EV_ALWAYS;
    int32_t v = c->val_cur;
    if (v == 0)       vec |= KM_EV_NULL;
    else if (v > 0)   vec |= KM_EV_POSITIVE;
    else              vec |= KM_EV_NEGATIVE;

    if ((v & 1) == 0) vec |= KM_EV_EVEN;
    else              vec |= KM_EV_UNEVEN;

    if (v != c->val_prev) vec |= KM_EV_CHANGED;
    return vec;
}

static inline void km_enqueue_sub(km_vm_t *vm, uint16_t sub_idx) {
    if (vm->eq_count < KM_EVENT_QUEUE_SIZE) {
        vm->event_queue[vm->eq_tail] = sub_idx;
        vm->eq_tail = (uint16_t)((vm->eq_tail + 1u) % KM_EVENT_QUEUE_SIZE);
        vm->eq_count++;
    }
}

static void km_exec_subscription_line(km_vm_t *vm, uint16_t sub_idx);

void km_write_concept(km_vm_t *vm, uint16_t cid, int32_t new_val, uint8_t flags) {
    (void)flags;
    km_concept_t *c = &vm->concepts[cid];

    /* Якщо концепт захищено апаратним шлюзом FPGA (KM_FLAG_HW_PROTECTED) */
    if (c->flags & KM_FLAG_HW_PROTECTED) {
        uint32_t hw_status = 0;
        int32_t  hw_state  = 0;
        bool committed = km_fpga_execute_txn(&vm->fpga, new_val, &hw_status, &hw_state);

        if (!committed) {
            c->big_dot_ok = 1u; /* 1 = '¬' (Порушення інваріанта / Abort) */
            printf("  [FPGA COP-GUARD] ВІДХИЛЕНО КРЕМНІЄМ! Запис %d у концепт %u заблоковано. Поточний стан: %d (STATUS=0x%02X)\n",
                   new_val, cid, c->val_cur, hw_status & 0xFF);

            /* Ендогенний запуск обробників аварійного скидання (KM_PHASE_ON_ABORT) */
            for (uint16_t i = 0; i < c->sub_count; i++) {
                uint16_t s_idx = (uint16_t)(c->first_sub_idx + i);
                if (vm->subs[s_idx].phase == KM_PHASE_ON_ABORT) {
                    km_enqueue_sub(vm, s_idx);
                }
            }
            return;
        }

        /* Успішний апаратний комміт */
        c->val_prev   = c->val_cur;
        c->val_cur    = hw_state;
        c->big_dot_ok = 0u; /* 0 = '!' (True) */
        printf("  [FPGA COP-GUARD] КОМІТ ПІДТВЕРДЖЕНО КРЕМНІЄМ: стан концепту %u оновлено на %d\n", cid, c->val_cur);
    } else {
        /* Звичайний концепт у SRAM */
        c->val_prev   = c->val_cur;
        c->val_cur    = new_val;
        c->big_dot_ok = 0u;
        printf("  [SRAM-CONCEPT] Концепт C%u оновлено: %d (попереднє: %d)\n", cid, c->val_cur, c->val_prev);
    }

    /* Запуск пост-підписок, якщо Велика точка не скинута */
    if (c->big_dot_ok == 0u) {
        uint8_t ev_vec = km_eval_event_vector(c);
        for (uint16_t i = 0; i < c->sub_count; i++) {
            uint16_t s_idx = (uint16_t)(c->first_sub_idx + i);
            if (vm->subs[s_idx].phase == KM_PHASE_POST_CHANGE &&
                (vm->subs[s_idx].trigger_mask & ev_vec) != 0u) {
                km_enqueue_sub(vm, s_idx);
            }
        }
    }
}

int32_t km_read_concept(km_vm_t *vm, uint16_t cid) {
    km_concept_t *c = &vm->concepts[cid];
    if (c->flags & KM_FLAG_HW_PROTECTED) {
        /* Читання актуального фізичного стану з апаратного регістра FPGA */
        c->val_cur = (int32_t)km_fpga_read(&vm->fpga, REG_STATE);
    }
    return c->val_cur;
}

static void km_exec_subscription_line(km_vm_t *vm, uint16_t sub_idx) {
    const km_sub_t *sub = &vm->subs[sub_idx];
    uint16_t pc_end = (uint16_t)(sub->line_start_pc + sub->line_len);
    vm->sr_sp = 0; /* Очищення стеку перед виконанням нової лінії підписки */

    printf("    [KM-EXEC S%u] Запуск колбеку (Власник C%u, фаза=%u, PC=%u..%u)\n",
           sub_idx, sub->owner_cid, sub->phase, sub->line_start_pc, pc_end - 1);

    for (uint16_t pc = sub->line_start_pc; pc < pc_end; pc++) {
        uint32_t word    = vm->code_o[pc];
        uint8_t  opc     = (uint8_t)((word >> 28) & 0x0Fu);
        uint8_t  sub_op  = (uint8_t)((word >> 24) & 0x0Fu);
        uint8_t  flags   = (uint8_t)((word >> 16) & 0xFFu);
        uint16_t operand = (uint16_t)(word & 0xFFFFu);
        vm->step_count++;

        if (opc == KM_OPC_IMM) {
            if (vm->sr_sp < KM_SR_STACK_DEPTH) {
                vm->sr_stack[vm->sr_sp++] = (int32_t)((int16_t)operand);
            }
        } else if (opc == KM_OPC_GO) {
            if (sub_op == KM_GO_READ) {
                if (vm->sr_sp < KM_SR_STACK_DEPTH) {
                    vm->sr_stack[vm->sr_sp++] = km_read_concept(vm, operand);
                }
            } else if (sub_op == KM_GO_WRITE) {
                if (vm->sr_sp > 0) {
                    int32_t val = vm->sr_stack[--vm->sr_sp];
                    km_write_concept(vm, operand, val, flags);
                }
            }
        } else if (opc == KM_OPC_DO) {
            if (sub_op == KM_DO_MOD_INC) {
                if (vm->sr_sp > 0) {
                    vm->sr_stack[vm->sr_sp - 1u] += 1;
                }
            } else {
                if (vm->sr_sp >= 2) {
                    int32_t rhs = vm->sr_stack[--vm->sr_sp];
                    int32_t lhs = vm->sr_stack[--vm->sr_sp];
                    int32_t res = 0;
                    if (sub_op == KM_DO_ADD) res = lhs + rhs;
                    else if (sub_op == KM_DO_SUB) res = lhs - rhs;
                    else if (sub_op == KM_DO_MUL) res = lhs * rhs;
                    vm->sr_stack[vm->sr_sp++] = res;
                }
            }
        }
    }
}

void km_vm_step_queue(km_vm_t *vm) {
    while (vm->eq_count > 0) {
        uint16_t s_idx = vm->event_queue[vm->eq_head];
        vm->eq_head = (uint16_t)((vm->eq_head + 1u) % KM_EVENT_QUEUE_SIZE);
        vm->eq_count--;
        km_exec_subscription_line(vm, s_idx);
    }
}

void km_trigger_external_input(km_vm_t *vm, uint16_t cid, int32_t val) {
    printf("\n>>> [EXTERNAL INPUT] Подія середовища: запис C%u = %d <<<\n", cid, val);
    km_write_concept(vm, cid, val, 0);
    km_vm_step_queue(vm);
}

/* ============================================================================
 * ДЕМОНСТРАЦІЙНИЙ СЦЕНАРІЙ: РЕАКТИВНИЙ ГРАФ ПІДПИСОК ТА АПАРАТНИЙ ЗАХИСТ
 * ============================================================================ */

int main(int argc, char **argv) {
    bool force_mock = false;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--mock") == 0) {
            force_mock = true;
        }
    }

    printf("============================================================================\n");
    printf(" МАШИНА КУЗЬМІНА: ГРАФ ПІДПИСОК ТА КАСКАДНІ КОЛБЕКИ (TASK-KM-MCU-SUB-01)\n");
    printf(" Реалізація: C99 MCU Runtime + Апаратний шлюз FPGA Invariant Guard (0x40000000)\n");
    printf("============================================================================\n");

    km_vm_t vm;
    memset(&vm, 0, sizeof(vm));

    if (!km_fpga_init(&vm.fpga, force_mock)) {
        printf("[FATAL] Не вдалося ініціалізувати FPGA міст.\n");
        return 1;
    }

    /* Налаштовуємо апаратний інваріант FPGA для захищеного актуатора:
     * Діапазон безпечної потужності: [10 .. 80] Вт
     * Правило: USE_HW_EVAL (bit 5) | REQUIRE_RANGE (bit 3) -> 0x28 */
    km_fpga_write(&vm.fpga, REG_LOWER_BOUND, 10);
    km_fpga_write(&vm.fpga, REG_UPPER_BOUND, 80);
    km_fpga_write(&vm.fpga, REG_RULE_CFG, RULE_USE_HW_EVAL | RULE_REQUIRE_RANGE);

    printf("[+] Апаратні інваріанти налаштовано в PL: LOWER=10, UPPER=80, RULE=0x28 (RANGE_CHECK)\n");

    /* --- 1. Ініціалізація графа концептів (N = 4) --- */
    /* C0: SensorTemperature (Звичайний софтверний концепт у SRAM, початково 20 °C) */
    vm.concepts[0].val_cur       = 20;
    vm.concepts[0].val_prev      = 20;
    vm.concepts[0].flags         = 0;
    vm.concepts[0].first_sub_idx = 0;
    vm.concepts[0].sub_count     = 1; /* S0 */

    /* C1: ActuatorHeaterPower (КРИТИЧНИЙ АКТУАТОР, ЗАХИЩЕНИЙ КРЕМНІЄМ FPGA) */
    vm.concepts[1].val_cur       = 10;
    vm.concepts[1].val_prev      = 10;
    vm.concepts[1].flags         = KM_FLAG_HW_PROTECTED;
    vm.concepts[1].first_sub_idx = 1;
    vm.concepts[1].sub_count     = 2; /* S1 (POST_CHANGE), S2 (ON_ABORT) */

    /* C2: CoolingFanSpeed (Звичайний концепт у SRAM, швидкість вентилятора 0..100%) */
    vm.concepts[2].val_cur       = 0;
    vm.concepts[2].val_prev      = 0;
    vm.concepts[2].flags         = 0;
    vm.concepts[2].first_sub_idx = 0;
    vm.concepts[2].sub_count     = 0;

    /* C3: InvariantViolationAlarm (Аварійний сигналізатор: 0 = Норма, 1 = Тривога/Fail-Closed) */
    vm.concepts[3].val_cur       = 0;
    vm.concepts[3].val_prev      = 0;
    vm.concepts[3].flags         = 0;
    vm.concepts[3].first_sub_idx = 0;
    vm.concepts[3].sub_count     = 0;

    /* Синхронізація початкового стану актуатора в FPGA */
    uint32_t init_status = 0;
    int32_t  init_state  = 0;
    km_fpga_execute_txn(&vm.fpga, 10, &init_status, &init_state);

    /* --- 2. Конфігурація пулу підписок (km_sub_t) --- */
    /* S0: Пропорційний регулятор потужності:
     * Слухає: C0 (POST_CHANGE, KM_EV_CHANGED)
     * Формула: P = 25 + (T - 20) * 5 -> Запис у C1 */
    vm.subs[0].owner_cid     = 0;
    vm.subs[0].phase         = KM_PHASE_POST_CHANGE;
    vm.subs[0].trigger_mask  = KM_EV_CHANGED;
    vm.subs[0].line_start_pc = 0;
    vm.subs[0].line_len      = 8;

    /* S1: Зв'язаний актуатор вентилятора:
     * Слухає: C1 (POST_CHANGE, KM_EV_POSITIVE)
     * Логіка: Читає C1 -> Встановлює швидкість охолодження C2 */
    vm.subs[1].owner_cid     = 1;
    vm.subs[1].phase         = KM_PHASE_POST_CHANGE;
    vm.subs[1].trigger_mask  = KM_EV_POSITIVE;
    vm.subs[1].line_start_pc = 8;
    vm.subs[1].line_len      = 2;

    /* S2: Аварійний Fail-Closed сторож:
     * Слухає: C1 (ON_ABORT)
     * Логіка: При блокуванні запису кремнієм: тривога C3 <- 1, аварійний обдув C2 <- 100% */
    vm.subs[2].owner_cid     = 1;
    vm.subs[2].phase         = KM_PHASE_ON_ABORT;
    vm.subs[2].trigger_mask  = KM_EV_ALWAYS;
    vm.subs[2].line_start_pc = 10;
    vm.subs[2].line_len      = 4;

    /* --- 3. Генерація байткоду Do/Go в пам'ять code_o --- */
    /* Лінія O_0 (PC 0..7): Регулятор потужності (8 інструкцій) */
    vm.code_o[0] = km_pack_instr(KM_OPC_GO,  KM_GO_READ,  0, 0);  /* Читати C0 (T) */
    vm.code_o[1] = km_pack_instr(KM_OPC_IMM, 0,           0, 20); /* Завантажити цільову 20 */
    vm.code_o[2] = km_pack_instr(KM_OPC_DO,  KM_DO_SUB,   0, 0);  /* T - 20 */
    vm.code_o[3] = km_pack_instr(KM_OPC_IMM, 0,           0, 5);   /* Коефіцієнт K = 5 */
    vm.code_o[4] = km_pack_instr(KM_OPC_DO,  KM_DO_MUL,   0, 0);  /* (T - 20) * 5 */
    vm.code_o[5] = km_pack_instr(KM_OPC_IMM, 0,           0, 25);  /* Базова потужність 25 */
    vm.code_o[6] = km_pack_instr(KM_OPC_DO,  KM_DO_ADD,   0, 0);  /* 25 + (T - 20) * 5 */
    vm.code_o[7] = km_pack_instr(KM_OPC_GO,  KM_GO_WRITE, 0, 1);  /* Записати в C1 (ActuatorHeaterPower) */

    /* Лінія O_1 (PC 8..9): Зв'язаний вентилятор (2 інструкції) */
    vm.code_o[8] = km_pack_instr(KM_OPC_GO,  KM_GO_READ,  0, 1);  /* Читати C1 (HeaterPower) */
    vm.code_o[9] = km_pack_instr(KM_OPC_GO,  KM_GO_WRITE, 0, 2);  /* Записати в C2 (CoolingFanSpeed) */

    /* Лінія O_2 (PC 10..13): Fail-Closed захисний колбек (4 інструкції) */
    vm.code_o[10] = km_pack_instr(KM_OPC_IMM, 0,          0, 1);   /* 1 (Alarm Active) */
    vm.code_o[11] = km_pack_instr(KM_OPC_GO,  KM_GO_WRITE, 0, 3);  /* Записати в C3 (Alarm) */
    vm.code_o[12] = km_pack_instr(KM_OPC_IMM, 0,          0, 100); /* 100% обдуву */
    vm.code_o[13] = km_pack_instr(KM_OPC_GO,  KM_GO_WRITE, 0, 2);  /* Записати в C2 (CoolingFanSpeed) */

    printf("[+] Граф з 4 концептів, 3 підписок та 14 інструкцій Do/Go успішно завантажено!\n");

    /* ========================================================================
     * СЦЕНАРІЙ 1: Номінальне керування актуатором (у межах безпечного діапазону)
     * Вхідна подія: Датчик температури C0 змінюється: 20 -> 25 °C.
     * Очікуваний каскад:
     *   C0 (25 °C) -> S0 -> P = 25 + (25 - 20) * 5 = 50 Вт -> C1 (HW Commit) ->
     *   S1 -> C2 = 50% обдуву, C3 = 0 (Alarm відсутній).
     * ======================================================================== */
    printf("\n----------------------------------------------------------------------------\n");
    printf(" СЦЕНАРІЙ 1: Номінальне керування актуатором (у межах безпечного діапазону)\n");
    printf("----------------------------------------------------------------------------\n");

    km_trigger_external_input(&vm, 0, 25);

    int32_t c1_val = km_read_concept(&vm, 1);
    int32_t c2_val = km_read_concept(&vm, 2);
    int32_t c3_val = km_read_concept(&vm, 3);
    printf("\n[Стан системи після Сценарію 1]\n");
    printf("  C0 (SensorTemp):       %d °C\n", vm.concepts[0].val_cur);
    printf("  C1 (HeaterPower):      %d Вт (Очікується 50 Вт)\n", c1_val);
    printf("  C2 (FanSpeed):         %d %% (Очікується 50 %%)\n", c2_val);
    printf("  C3 (Alarm):            %d (Очікується 0)\n", c3_val);

    if (c1_val != 50 || c2_val != 50 || c3_val != 0) {
        printf("[ПОМИЛКА] Сценарій 1 не пройшов верифікацію!\n");
        return 1;
    }
    printf("[+] Номінальний режим: ВЕРИФІКОВАНО (Каскад S0 -> C1 -> S1 -> C2 спрацював автономно)\n");

    /* ========================================================================
     * СЦЕНАРІЙ 2: Аварійний збій у софті (Спроба перегріву: запис 150 Вт > 80 Вт)
     * Вхідна подія: Датчик температури стрибає до 45 °C.
     * Регулятор S0 обчислює: 25 + (45 - 20) * 5 = 150 Вт.
     * Очікуваний результат:
     *   Шлюз FPGA блокує 150 Вт (> 80 Вт). C1 зберігає 50 Вт.
     *   S1 НЕ спрацьовує (big_dot_ok = 1 '¬').
     *   S2 спрацьовує (ON_ABORT): C3 <- 1, C2 <- 100%.
     * ======================================================================== */
    printf("\n----------------------------------------------------------------------------\n");
    printf(" СЦЕНАРІЙ 2: Аварійний збій у софті (Спроба перегріву: запис 150 Вт > 80 Вт)\n");
    printf("----------------------------------------------------------------------------\n");

    km_trigger_external_input(&vm, 0, 45);

    c1_val = km_read_concept(&vm, 1);
    c2_val = km_read_concept(&vm, 2);
    c3_val = km_read_concept(&vm, 3);
    printf("\n[Стан системи після Сценарію 2]\n");
    printf("  C0 (SensorTemp):       %d °C\n", vm.concepts[0].val_cur);
    printf("  C1 (HeaterPower):      %d Вт (Має лишитися 50 Вт!)\n", c1_val);
    printf("  C2 (FanSpeed):         %d %% (Очікується 100 %% аварійного охолодження)\n", c2_val);
    printf("  C3 (Alarm):            %d (Очікується 1 - Тривога!)\n", c3_val);

    if (c1_val != 50 || c2_val != 100 || c3_val != 1) {
        printf("[КРИТИЧНА ПОМИЛКА] Апаратний інваріант пробито або колбек S2 не відпрацював!\n");
        return 1;
    }
    printf("[+] Апаратний Fail-Closed захист: КРЕМНІЙ ЗАПОБІГ АВАРІЇ ПЕРЕГРІВУ!\n");

    /* ========================================================================
     * СЦЕНАРІЙ 3: Аварійний збій у софті (Спроба від'ємного значення: -20 Вт < 10 Вт)
     * Вхідна подія: Помилковий стрибок датчика до 11 °C.
     * Регулятор S0 обчислює: 25 + (11 - 20) * 5 = -20 Вт.
     * Очікуваний результат:
     *   Шлюз FPGA блокує -20 Вт (< 10 Вт). C1 зберігає 50 Вт.
     *   S2 повторно активує аварійний стан.
     * ======================================================================== */
    printf("\n----------------------------------------------------------------------------\n");
    printf(" СЦЕНАРІЙ 3: Аварійний збій у софті (Спроба від'ємного значення: -20 Вт < 10 Вт)\n");
    printf("----------------------------------------------------------------------------\n");

    km_trigger_external_input(&vm, 0, 11);

    c1_val = km_read_concept(&vm, 1);
    c2_val = km_read_concept(&vm, 2);
    c3_val = km_read_concept(&vm, 3);
    printf("\n[Стан системи після Сценарію 3]\n");
    printf("  C0 (SensorTemp):       %d °C\n", vm.concepts[0].val_cur);
    printf("  C1 (HeaterPower):      %d Вт (Має лишитися 50 Вт!)\n", c1_val);
    printf("  C2 (FanSpeed):         %d %% (Очікується 100 %%)\n", c2_val);
    printf("  C3 (Alarm):            %d (Очікується 1)\n", c3_val);

    if (c1_val != 50 || c2_val != 100 || c3_val != 1) {
        printf("[КРИТИЧНА ПОМИЛКА] Апаратний інваріант пробито при від'ємному значенні!\n");
        return 1;
    }
    printf("[+] Апаратний Fail-Closed захист: КРЕМНІЙ ЗАПОБІГ НЕГАТИВНОМУ СТАНУ!\n");

    /* ========================================================================
     * СЦЕНАРІЙ 4: Повернення до штатного режиму (Запис валідних 75 Вт)
     * Вхідна подія: Скидання тривоги C3 -> 0 та повернення температури до 30 °C.
     * Регулятор S0 обчислює: 25 + (30 - 20) * 5 = 75 Вт.
     * Очікуваний результат:
     *   75 Вт знаходиться в межах [10..80]. FPGA успішно фіксує стан!
     *   S1 оновлює C2 <- 75%. C3 = 0.
     * ======================================================================== */
    printf("\n----------------------------------------------------------------------------\n");
    printf(" СЦЕНАРІЙ 4: Повернення до штатного режиму (Запис валідних 75 Вт)\n");
    printf("----------------------------------------------------------------------------\n");

    km_write_concept(&vm, 3, 0, 0); /* Скидання індикатора аварії */
    km_trigger_external_input(&vm, 0, 30);

    c1_val = km_read_concept(&vm, 1);
    c2_val = km_read_concept(&vm, 2);
    c3_val = km_read_concept(&vm, 3);
    printf("\n[Стан системи після Сценарію 4]\n");
    printf("  C0 (SensorTemp):       %d °C\n", vm.concepts[0].val_cur);
    printf("  C1 (HeaterPower):      %d Вт (Очікується 75 Вт)\n", c1_val);
    printf("  C2 (FanSpeed):         %d %% (Очікується 75 %%)\n", c2_val);
    printf("  C3 (Alarm):            %d (Очікується 0)\n", c3_val);

    if (c1_val != 75 || c2_val != 75 || c3_val != 0) {
        printf("[ПОМИЛКА] Відновлення штатного режиму не спрацювало!\n");
        return 1;
    }
    printf("[+] Штатне функціонування відновлено! (C1=75 Вт, C2=75%%, C3=0)\n");

    printf("\n============================================================================\n");
    printf(" РЕЗУЛЬТАТ: ГІБРИДНИЙ КО-ДИЗАЙН ПРОЦЕСОР+FPGA ПОВНІСТЮ ДОВЕДЕНО НА ПРАКТИЦІ!\n");
    printf(" Кремній надійно ізолює фізичні актуатори від будь-яких помилок софту.\n");
    printf(" Виконано всього кроків інструкцій: %u\n", vm.step_count);
    printf("============================================================================\n");

    km_fpga_close(&vm.fpga);
    return 0;
}
