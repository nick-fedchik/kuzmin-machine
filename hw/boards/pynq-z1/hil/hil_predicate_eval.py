#!/usr/bin/env python3
"""
Машина Кузьміна (Kuzmin Machine) — HIL тест Апаратного обчислювача предикатів (::)
Цільова платформа: Digilent PYNQ-Z1 (Xilinx Zynq-7000 XC7Z020-1CLG400C)
Призначення:
  Фізична верифікація гіпотез H1 (Паралельна безпобічна перевірка предикатів)
  та H6 (Транзакційна модель оператора «Велика точка» • і fail-closed захист стану).
"""

import argparse
import sys
import time

try:
    import pynq.pl_server.embedded_device
    from pynq import MMIO, Bitstream
except ImportError:
    print("[ERROR] PYNQ runtime not found. Run with sudo inside pynq-venv.")
    sys.exit(1)

REG_CANDIDATE = 0x00
REG_CONDITIONS = 0x04
REG_COMMAND = 0x08
REG_STATUS = 0x0C
REG_STATE = 0x10
REG_ID = 0x14
REG_LOWER_BOUND = 0x18
REG_UPPER_BOUND = 0x1C
REG_RULE_CFG = 0x20
REG_PRED_VEC = 0x24
REG_BIG_DOT = 0x28

EXPECTED_ID = 0x4B504F4C

# STATUS bit definitions
STATUS_DONE = 1 << 0
STATUS_COMMITTED = 1 << 1
STATUS_REJECTED = 1 << 2
STATUS_REJECTED_INPUT = 1 << 3
STATUS_REJECTED_INVARIANT = 1 << 4
STATUS_CHANGED = 1 << 5
STATUS_BUSY = 1 << 8

# RULE_CFG bit definitions
RULE_REQUIRE_EVEN = 1 << 0
RULE_REQUIRE_POSITIVE = 1 << 1
RULE_REQUIRE_NON_NULL = 1 << 2
RULE_REQUIRE_RANGE = 1 << 3
RULE_REQUIRE_CHANGED = 1 << 4
RULE_USE_HW_EVAL = 1 << 5
RULE_REQUIRE_UNEVEN = 1 << 6


def wait_transaction_done(mmio, timeout=1.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        raw_status = mmio.read(REG_STATUS)
        done = (raw_status & STATUS_DONE) != 0
        busy = (raw_status & STATUS_BUSY) != 0
        if done and not busy:
            return raw_status & 0xFF
        time.sleep(0.001)
    raise TimeoutError(
        f"Transaction timed out, status=0x{mmio.read(REG_STATUS):08X}"
    )


def run_hil_tests(bitstream_path=None, program=False):
    print("=" * 76)
    print(" HIL-ТЕСТУВАННЯ АПАРАТНОГО ОБЧИСЛЮВАЧА ПРЕДИКАТІВ МК (::) ТА ВЕЛИКОЇ ТОЧКИ (•)")
    print(" Платформа: Digilent PYNQ-Z1 (Xilinx Zynq-7000 XC7Z020)")
    print("=" * 76)

    if program and bitstream_path:
        print(f"[*] Завантаження бітстріму у volatile PL SRAM: {bitstream_path}")
        t0 = time.time()
        bs = Bitstream(bitstream_path)
        bs.download()
        print(f"[+] PL успішно сконфігурована за {(time.time() - t0)*1000:.1f} мс")

    mmio = MMIO(0x40000000, 0x1000)

    # 1. Перевірка ID
    chip_id = mmio.read(REG_ID)
    print(f"[*] Зчитування REG_ID: 0x{chip_id:08X}")
    assert (
        chip_id == EXPECTED_ID
    ), f"Невірний ID: 0x{chip_id:08X} != 0x{EXPECTED_ID:08X}"
    print("    -> [PASS] Ядро KPOL ідентифіковано")

    # 2. Перевірка дефолтних налаштувань
    lower = mmio.read(REG_LOWER_BOUND)
    upper = mmio.read(REG_UPPER_BOUND)
    cfg = mmio.read(REG_RULE_CFG)
    print(
        f"[*] Регістри інваріантів за замовчуванням: LOWER={lower}, UPPER=0x{upper:08X}, RULE_CFG=0x{cfg:02X}"
    )
    assert lower == 0 and upper == 0x7FFFFFFF and cfg == 0
    print("    -> [PASS] Дефолтні конфігураційні регістри валідні")

    # 3. ТЕСТ ГІПОТЕЗИ H1: Паралельне обчислення вектора предикатів '::' (REG_PRED_VEC 0x24)
    print("-" * 76)
    print("ЕТАП 1 (ГІПОТЕЗА H1): Паралельне комбінаційне обчислення предикатів '::'")
    print("-" * 76)

    # 3A. Кандидат = 4 при candidate_known=0 (uninit=1 -> 0xD5) та candidate_known=1 (uninit=0 -> 0xD4)
    mmio.write(REG_CANDIDATE, 4)
    # Зчитуємо вектор предикатів безпосередньо (candidate_known=0 за замовчуванням):
    pvec_4_uninit = mmio.read(REG_PRED_VEC) & 0xFF
    print(f"[*] Candidate = 4 (known=0): PREDICATE_VECTOR = 0x{pvec_4_uninit:02X} (очікується 0xD5, бо uninit=1)")
    assert pvec_4_uninit == 0xD5, f"Невідповідність PREDICATE_VECTOR при known=0: 0x{pvec_4_uninit:02X}"
    print("    -> [PASS] Предикат Uninit '_' коректно визначено для неініціалізованого кандидата")

    # Встановлюємо candidate_known = 1
    mmio.write(REG_CONDITIONS, 0x00000001)
    pvec_4 = mmio.read(REG_PRED_VEC) & 0xFF
    print(f"[*] Candidate = 4 (known=1): PREDICATE_VECTOR = 0x{pvec_4:02X} (очікується 0xD4, бо uninit=0)")
    assert pvec_4 == 0xD4, f"Невідповідність PREDICATE_VECTOR при known=1: 0x{pvec_4:02X}"
    print("    -> [PASS] Предикати Even, Positive, Range, Changed обчислено апаратно")

    # 3B. Кандидат = 0 (Null=1, Even=1, Changed=0, known=1 -> 0x92)
    mmio.write(REG_CANDIDATE, 0)
    pvec_0 = mmio.read(REG_PRED_VEC) & 0xFF
    print(f"[*] Candidate = 0: PREDICATE_VECTOR = 0x{pvec_0:02X} (очікується 0x92)")
    assert pvec_0 == 0x92, f"Невідповідність PREDICATE_VECTOR: 0x{pvec_0:02X}"
    print("    -> [PASS] Предикат Null і незмінність стану обчислено апаратно")

    # 3C. Кандидат = -5 (Negative=1, Uneven=1, known=1 -> 0x68)
    mmio.write(REG_CANDIDATE, 0xFFFFFFFB)
    pvec_neg = mmio.read(REG_PRED_VEC) & 0xFF
    print(f"[*] Candidate = -5: PREDICATE_VECTOR = 0x{pvec_neg:02X} (очікується 0x68)")
    assert pvec_neg == 0x68, f"Невідповідність PREDICATE_VECTOR: 0x{pvec_neg:02X}"
    print("    -> [PASS] Предикати Negative та Uneven обчислено апаратно без побічних дій")

    # 4. ТЕСТ ГІПОТЕЗИ H6: Фазовий оператор «Велика точка» (•) та апаратний захист інваріанта
    print("-" * 76)
    print(
        "ЕТАП 2 (ГІПОТЕЗА H6): Апаратний інваріант 'Even' та Велика точка (•)"
    )
    print("-" * 76)

    # Вмикаємо правило: USE_HW_EVAL (bit 5) | REQUIRE_EVEN (bit 0) -> 0x21
    mmio.write(REG_RULE_CFG, RULE_USE_HW_EVAL | RULE_REQUIRE_EVEN)
    mmio.write(
        REG_CONDITIONS, 0x00000007
    )  # cand_known=1, assump_known=1, assump_true=1

    # 4A. Кандидат = 10 (Парний) -> • = ! (1) -> успішний комміт
    mmio.write(REG_CANDIDATE, 10)
    big_dot = mmio.read(REG_BIG_DOT) & 0x01
    print(f"[*] Candidate = 10 (парний): Регістр BIG_DOT = {big_dot} (• = !)")
    assert big_dot == 1, "Велика точка повинна бути TRUE для парного 10"

    mmio.write(REG_COMMAND, 0x01)
    st = wait_transaction_done(mmio)
    cur_state = mmio.read(REG_STATE)
    print(
        f"    -> Транзакція завершена: STATUS=0x{st:02X}, STATE={cur_state} (очікується 10)"
    )
    assert (
        st & STATUS_COMMITTED
    ) and cur_state == 10, "Помилка коміту парного числа"
    print("    -> [PASS] Транзакція успішно зафіксована апаратурою")

    # 4B. Кандидат = 11 (Непарний) -> • = ¬ (0) -> Апаратне відхилення (Fail-Closed)
    mmio.write(REG_CANDIDATE, 11)
    big_dot_uneven = mmio.read(REG_BIG_DOT) & 0x01
    print(
        f"[*] Candidate = 11 (непарний): Регістр BIG_DOT = {big_dot_uneven} (• = ¬)"
    )
    assert big_dot_uneven == 0, "Велика точка повинна бути FALSE для непарного 11"

    mmio.write(REG_COMMAND, 0x01)
    st_uneven = wait_transaction_done(mmio)
    state_after_reject = mmio.read(REG_STATE)
    print(
        f"    -> Транзакція завершена: STATUS=0x{st_uneven:02X}, STATE={state_after_reject}"
    )
    assert (
        st_uneven & STATUS_REJECTED
    ) and (st_uneven & STATUS_REJECTED_INVARIANT), (
        "Транзакція повинна бути відхилена за інваріантом!"
    )
    assert (
        state_after_reject == 10
    ), f"FAIL-CLOSED ПОРУШЕНО: стан змінився на {state_after_reject}!"
    print(
        "    -> [PASS] Апаратний Fail-Closed захист: стан 10 збережено без жодних мутацій!"
    )

    # 5. ТЕСТ ДІАПАЗОННОГО ІНВАРІАНТА (Range Invariant)
    print("-" * 76)
    print("ЕТАП 3: Апаратний контроль діапазону [20 .. 50]")
    print("-" * 76)

    # Налаштовуємо діапазон [20 .. 50]
    mmio.write(REG_LOWER_BOUND, 20)
    mmio.write(REG_UPPER_BOUND, 50)
    # Правило: USE_HW_EVAL | REQUIRE_RANGE -> 0x28
    mmio.write(REG_RULE_CFG, RULE_USE_HW_EVAL | RULE_REQUIRE_RANGE)

    # 5A. Кандидат = 35 (у межах [20..50]) -> Commit OK
    mmio.write(REG_CANDIDATE, 35)
    mmio.write(REG_COMMAND, 0x01)
    st_range_ok = wait_transaction_done(mmio)
    state_range = mmio.read(REG_STATE)
    print(
        f"[*] Candidate = 35: STATUS=0x{st_range_ok:02X}, STATE={state_range}"
    )
    assert (
        st_range_ok & STATUS_COMMITTED
    ) and state_range == 35, "Кандидат 35 мав зафіксуватися"
    print("    -> [PASS] Кандидат у діапазоні успішно прийнято")

    # 5B. Кандидат = 99 (поза межами > 50) -> Rejected, state remains 35
    mmio.write(REG_CANDIDATE, 99)
    mmio.write(REG_COMMAND, 0x01)
    st_range_viol = wait_transaction_done(mmio)
    state_after_range_viol = mmio.read(REG_STATE)
    print(
        f"[*] Candidate = 99: STATUS=0x{st_range_viol:02X}, STATE={state_after_range_viol}"
    )
    assert (
        st_range_viol & STATUS_REJECTED
    ) and (st_range_viol & STATUS_REJECTED_INVARIANT), (
        "Кандидат 99 мав бути відхилений!"
    )
    assert (
        state_after_range_viol == 35
    ), "FAIL-CLOSED ПОРУШЕНО при перевірці діапазону"
    print(
        "    -> [PASS] Кандидат за межами діапазону відхилено, стан 35 незмінний"
    )

    print("=" * 76)
    print(
        " ВСІ АПАРАТНІ ТЕСТИ УСПІШНІ: ГІПОТЕЗИ H1 ТА H6 ПОВНІСТЮ ДОВЕДЕНО НА КРЕМНІЇ!"
    )
    print("=" * 76)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="HIL Test for Hardware Predicate Evaluator"
    )
    parser.add_argument(
        "--bitstream",
        default="/home/xilinx/kpol_pynq.bit",
        help="Шлях до бітстріму",
    )
    parser.add_argument(
        "--program", action="store_true", help="Завантажити бітстрім у PL SRAM"
    )
    args = parser.parse_args()

    run_hil_tests(bitstream_path=args.bitstream, program=args.program)
