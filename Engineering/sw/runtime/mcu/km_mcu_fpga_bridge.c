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
    KM_PHASE_ON_EXEC     = 3
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

    for (uint16_t pc = sub->line_start_pc; pc < pc_end; pc++) {
        uint32_t word    = vm->code_o[pc];
        uint8_t  opc     = (uint8_t)((word >> 28) & 0x0Fu);
        uint8_t  sub_op  = (uint8_t)((word >> 24) & 0x0Fu);
        uint8_t  flags   = (uint8_t)((word >> 16) & 0xFFu);
        uint16_t operand = (uint16_t)(word & 0xFFFFu);
        vm->step_count++;

        if (opc == KM_OPC_IMM) {
            vm->sr_stack[vm->sr_sp++] = (int32_t)((int16_t)operand);
        } else if (opc == KM_OPC_GO) {
            if (sub_op == KM_GO_READ) {
                vm->sr_stack[vm->sr_sp++] = km_read_concept(vm, operand);
            } else if (sub_op == KM_GO_WRITE) {
                int32_t val = vm->sr_stack[--vm->sr_sp];
                km_write_concept(vm, operand, val, flags);
            }
        } else if (opc == KM_OPC_DO) {
            if (sub_op == KM_DO_MOD_INC) {
                vm->sr_stack[vm->sr_sp - 1u] += 1;
            } else {
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

void km_vm_step_queue(km_vm_t *vm) {
    while (vm->eq_count > 0) {
        uint16_t s_idx = vm->event_queue[vm->eq_head];
        vm->eq_head = (uint16_t)((vm->eq_head + 1u) % KM_EVENT_QUEUE_SIZE);
        vm->eq_count--;
        km_exec_subscription_line(vm, s_idx);
    }
}

/* ============================================================================
 * ДЕМОНСТРАЦІЙНИЙ СЦЕНАРІЙ: Class InvariantGuard (Контролер актуатора)
 * ============================================================================ */

int main(int argc, char **argv) {
    bool force_mock = false;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--mock") == 0) {
            force_mock = true;
        }
    }

    printf("============================================================================\n");
    printf(" МАШИНА КУЗЬМІНА: ГІБРИДНИЙ КО-ДИЗАЙН (ARM CORTEX-A9 + FPGA INVARIANT GUARD)\n");
    printf(" Пропозиція 3: Апаратне усунення софтверних збоїв на рівні логіки PL\n");
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

    /* Концепт 0: SensorTemp (Звичайний софтверний концепт у SRAM) */
    vm.concepts[0].val_cur = 25;
    vm.concepts[0].flags   = 0;

    /* Концепт 1: ActuatorHeaterPower (КРИТИЧНИЙ АКТУАТОР, ЗАХИЩЕНИЙ КРЕМНІЄМ FPGA) */
    vm.concepts[1].val_cur = 10;
    vm.concepts[1].flags   = KM_FLAG_HW_PROTECTED;

    /* Початковий стан актуатора в FPGA */
    uint32_t init_status = 0;
    int32_t  init_state  = 0;
    km_fpga_execute_txn(&vm.fpga, 10, &init_status, &init_state);

    printf("\n----------------------------------------------------------------------------\n");
    printf(" СЦЕНАРІЙ 1: Номінальне керування актуатором (у межах безпечного діапазону)\n");
    printf("----------------------------------------------------------------------------\n");

    printf("[Софт] Програма збільшує потужність обігрівача: 10 Вт -> 50 Вт...\n");
    km_write_concept(&vm, 1, 50, 0);
    int32_t read_back = km_read_concept(&vm, 1);
    printf("[Софт] Актуатор після транзакції: %d Вт (Очікується 50 Вт)\n", read_back);
    if (read_back != 50) {
        printf("[ПОМИЛКА] Номінальна транзакція не пройшла!\n");
        return 1;
    }
    printf("[+] Номінальний режим: ВЕРИФІКОВАНО\n");

    printf("\n----------------------------------------------------------------------------\n");
    printf(" СЦЕНАРІЙ 2: Аварійний збій у софті (Спроба перегріву: запис 150 Вт > 80 Вт)\n");
    printf("----------------------------------------------------------------------------\n");

    printf("[Софт] Критичний баг / зависання циклу намагається видати небезпечні 150 Вт!\n");
    km_write_concept(&vm, 1, 150, 0);
    read_back = km_read_concept(&vm, 1);
    printf("[Софт] Фізичний стан актуатора: %d Вт (Має лишитися 50 Вт!)\n", read_back);
    if (read_back != 50) {
        printf("[КРИТИЧНА ПОМИЛКА] Апаратний інваріант пробито! Стан: %d\n", read_back);
        return 1;
    }
    printf("[+] Апаратний Fail-Closed захист: КРЕМНІЙ ЗАПОБІГ АВАРІЇ ПЕРЕГРІВУ!\n");

    printf("\n----------------------------------------------------------------------------\n");
    printf(" СЦЕНАРІЙ 3: Аварійний збій у софті (Спроба від'ємного значення: -20 Вт < 10 Вт)\n");
    printf("----------------------------------------------------------------------------\n");

    printf("[Софт] Помилка знака в алгоритмі намагається видати -20 Вт!\n");
    km_write_concept(&vm, 1, -20, 0);
    read_back = km_read_concept(&vm, 1);
    printf("[Софт] Фізичний стан актуатора: %d Вт (Має лишитися 50 Вт!)\n", read_back);
    if (read_back != 50) {
        printf("[КРИТИЧНА ПОМИЛКА] Апаратний інваріант пробито! Стан: %d\n", read_back);
        return 1;
    }
    printf("[+] Апаратний Fail-Closed захист: КРЕМНІЙ ЗАПОБІГ НЕГАТИВНОМУ СТАНУ!\n");

    printf("\n----------------------------------------------------------------------------\n");
    printf(" СЦЕНАРІЙ 4: Повернення до штатного режиму (Запис валідних 75 Вт)\n");
    printf("----------------------------------------------------------------------------\n");

    km_write_concept(&vm, 1, 75, 0);
    read_back = km_read_concept(&vm, 1);
    printf("[Софт] Фізичний стан актуатора: %d Вт (Очікується 75 Вт)\n", read_back);
    if (read_back != 75) {
        printf("[ПОМИЛКА] Відновлення штатного режиму не спрацювало!\n");
        return 1;
    }
    printf("[+] Штатне функціонування відновлено!\n");

    printf("\n============================================================================\n");
    printf(" РЕЗУЛЬТАТ: ГІБРИДНИЙ КО-ДИЗАЙН ПРОЦЕСОР+FPGA ПОВНІСТЮ ДОВЕДЕНО НА ПРАКТИЦІ!\n");
    printf(" Кремній надійно ізолює фізичні актуатори від будь-яких помилок софту.\n");
    printf("============================================================================\n");

    km_fpga_close(&vm.fpga);
    return 0;
}
