#!/usr/bin/env python3
"""
Драйвер прямого керування транзакційним шлюзом Машини Кузьміна через pynq.MMIO (без .hwh)
Цільова платформа: Digilent PYNQ-Z1 (Xilinx Zynq-7000 XC7Z020-1CLG400C)

Принцип:
Файл .hwh не потрібен. Бітстрім завантажується за допомогою pynq.Bitstream або pynq.PL,
а взаємодія з регістрами AXI4-Lite здійснюється напряму через базову бібліотеку pynq.MMIO
за фізичними адресами шини M_AXI_GP0 (0x4000_0000).
"""

import argparse
import sys
import time
from typing import Dict, Any, Optional, Tuple

# Регістрова карта kpol_txn_gate_axi_lite.sv
REG_CANDIDATE_VALUE = 0x00  # R/W: Кандидатне значення стану
REG_CONDITIONS      = 0x04  # R/W: Вектор передумов та інваріантів
REG_COMMAND         = 0x08  # W:   Командний регістр (bit 0: start)
REG_STATUS          = 0x0C  # R:   Статусний регістр
REG_STATE           = 0x10  # R:   Поточний зафіксований стан
REG_IDENTIFICATION  = 0x14  # R:   Ідентифікатор ядра ("KPOL" = 0x4B504F4C)

EXPECTED_IDENT = 0x4B504F4C  # "KPOL"

# Бітові маски статусів (REG_STATUS)
STATUS_DONE             = 1 << 0
STATUS_COMMITTED        = 1 << 1
STATUS_REJECTED         = 1 << 2
STATUS_REJECTED_INPUT   = 1 << 3
STATUS_REJECTED_INV     = 1 << 4
STATUS_CHANGED          = 1 << 5
STATUS_HAZARD_OBSERVED  = 1 << 6
STATUS_UNKNOWN_HAZARD   = 1 << 7
STATUS_BUSY             = 1 << 8

# Бітові маски умов (REG_CONDITIONS)
COND_CAND_KNOWN         = 1 << 0
COND_ASSUMP_KNOWN       = 1 << 1
COND_ASSUMP_TRUE        = 1 << 2
COND_INV_KNOWN          = 1 << 3
COND_INV_TRUE           = 1 << 4
COND_HAZARD_KNOWN       = 1 << 5
COND_HAZARD_TRUE        = 1 << 6


class MockMMIO:
    """Програмний емулятор регістрової пам'яті для автономного тестування без плати."""

    def __init__(self, base_addr: int = 0x40000000, length: int = 0x1000):
        self.base_addr = base_addr
        self.length = length
        self._regs: Dict[int, int] = {
            REG_CANDIDATE_VALUE: 0,
            REG_CONDITIONS: 0,
            REG_COMMAND: 0,
            REG_STATUS: 0,
            REG_STATE: 0,
            REG_IDENTIFICATION: EXPECTED_IDENT
        }

    def read(self, offset: int) -> int:
        return self._regs.get(offset, 0)

    def write(self, offset: int, value: int):
        self._regs[offset] = value & 0xFFFFFFFF
        if offset == REG_COMMAND and (value & 1):
            self._simulate_gate_cycle()

    def _simulate_gate_cycle(self):
        """Емуляція апаратного транзакційного шлюзу kpol_txn_gate.sv."""
        cand = self._regs[REG_CANDIDATE_VALUE]
        cond = self._regs[REG_CONDITIONS]
        old_state = self._regs[REG_STATE]

        cand_known = bool(cond & COND_CAND_KNOWN)
        assump_known = bool(cond & COND_ASSUMP_KNOWN)
        assump_true = bool(cond & COND_ASSUMP_TRUE)
        inv_known = bool(cond & COND_INV_KNOWN)
        inv_true = bool(cond & COND_INV_TRUE)
        hazard_known = bool(cond & COND_HAZARD_KNOWN)
        hazard_true = bool(cond & COND_HAZARD_TRUE)

        hazard_obs = hazard_known and hazard_true
        unk_hazard = not hazard_known
        input_valid = cand_known and assump_known and assump_true
        inv_valid = inv_known and inv_true
        commit = input_valid and inv_valid and (not hazard_obs) and (not unk_hazard)

        status = STATUS_DONE
        if hazard_obs:
            status |= STATUS_HAZARD_OBSERVED
        if unk_hazard:
            status |= STATUS_UNKNOWN_HAZARD

        if commit:
            status |= STATUS_COMMITTED
            if cand != old_state:
                status |= STATUS_CHANGED
            self._regs[REG_STATE] = cand
        else:
            status |= STATUS_REJECTED
            if not input_valid:
                status |= STATUS_REJECTED_INPUT
            if not inv_valid:
                status |= STATUS_REJECTED_INV

        self._regs[REG_STATUS] = status


class KuzminMachineDirectMMIO:
    """
    Драйвер прямого доступу до регістрів Машини Кузьміна через pynq.MMIO.
    Працює без файлу .hwh.
    """

    def __init__(self, base_addr: int = 0x40000000, length: int = 0x1000,
                 bitfile: Optional[str] = None, mock: bool = False):
        self.base_addr = base_addr
        self.length = length
        self.mock = mock

        if self.mock:
            self.mmio = MockMMIO(base_addr, length)
        else:
            try:
                import pynq
                if bitfile:
                    print(f"[*] Скидання стану PL та завантаження бітстріму {bitfile} (без .hwh)...")
                    try:
                        pynq.PL.reset()
                    except Exception as rst_err:
                        print(f"[!] PL.reset(): {rst_err} (продовжуємо завантаження)")
                    bit = pynq.Bitstream(bitfile)
                    bit.download()
                    print(f"[+] Бітстрім успішно прошито в PL.")
                self.mmio = pynq.MMIO(base_addr, length)
            except ImportError:
                print("[ПОПЕРЕДЖЕННЯ] Модуль pynq не знайдено, перехід в режим емуляції (Mock).")
                self.mock = True
                self.mmio = MockMMIO(base_addr, length)

    def read_ident(self) -> Tuple[int, str]:
        """Зчитує ідентифікатор ядра МК."""
        val = self.mmio.read(REG_IDENTIFICATION)
        try:
            ascii_str = val.to_bytes(4, byteorder='big').decode('ascii')
        except Exception:
            ascii_str = "????"
        return val, ascii_str

    def read_state(self) -> int:
        """Зчитує поточний стан МК."""
        return self.mmio.read(REG_STATE)

    def read_status(self) -> int:
        """Зчитує поточний регістр статусу."""
        return self.mmio.read(REG_STATUS)

    def execute_transaction(self, candidate: int, conditions: int,
                            timeout_sec: float = 0.05) -> Dict[str, Any]:
        """
        Виконує атомарну транзакцію в апаратному шлюзі:
        1. Записує кандидатне значення (0x00).
        2. Записує умови (0x04).
        3. Запускає команду (0x08).
        4. Опитує статус завершення (0x0C).
        5. Зчитує новий зафіксований стан (0x10).
        """
        t_start = time.perf_counter()

        # 1. Запис кандидатного значення
        self.mmio.write(REG_CANDIDATE_VALUE, candidate)

        # 2. Запис верифікаційних умов
        self.mmio.write(REG_CONDITIONS, conditions)

        # 3. Пуск команди
        self.mmio.write(REG_COMMAND, 0x01)

        # 4. Опитування завершення (polling done)
        done = False
        status_val = 0
        while (time.perf_counter() - t_start) < timeout_sec:
            status_val = self.mmio.read(REG_STATUS)
            if (status_val & STATUS_DONE) and not (status_val & STATUS_BUSY):
                done = True
                break
            time.sleep(0.0001)

        elapsed_us = (time.perf_counter() - t_start) * 1_000_000.0

        if not done:
            raise TimeoutError(f"Таймаут очікування завершення транзакції ({timeout_sec*1000:.1f} мс)")

        # 5. Зчитування фінального стану
        new_state = self.mmio.read(REG_STATE)

        return {
            "elapsed_us": elapsed_us,
            "status_raw": status_val,
            "done": bool(status_val & STATUS_DONE),
            "committed": bool(status_val & STATUS_COMMITTED),
            "rejected": bool(status_val & STATUS_REJECTED),
            "rejected_input": bool(status_val & STATUS_REJECTED_INPUT),
            "rejected_inv": bool(status_val & STATUS_REJECTED_INV),
            "changed": bool(status_val & STATUS_CHANGED),
            "hazard_observed": bool(status_val & STATUS_HAZARD_OBSERVED),
            "unknown_hazard": bool(status_val & STATUS_UNKNOWN_HAZARD),
            "new_state": new_state
        }

    def run_validation_suite(self) -> bool:
        """
        Повний цикл верифікації 4-х транзакційних гілок:
        1. Валідний Commit
        2. Відхилення за хибними вхідними даними (Input Reject)
        3. Відхилення за порушенням інваріанта (Invariant Reject)
        4. Запобігання аварії при спостереженні Hazard
        """
        print("=" * 68)
        print(" ЗАПУСК ВЕРИФІКАЦІЙНОГО СЮЇТУ ДРАЙВЕРА ПРЯМОГО MMIO (БЕЗ .HWH)")
        print("=" * 68)

        ident_val, ident_str = self.read_ident()
        print(f"[*] Ідентифікатор ядра: {hex(ident_val)} (ASCII: '{ident_str}')")
        if ident_val != EXPECTED_IDENT:
            print(f"[ПОМИЛКА] Невідповідність ідентифікатора ядра! Очікувалось {hex(EXPECTED_IDENT)}")
            return False

        # Гілка 1: Валідний Commit
        print("\n--- [Гілка 1/4] Валідна транзакція (Commit) ---")
        cond_valid = COND_CAND_KNOWN | COND_ASSUMP_KNOWN | COND_ASSUMP_TRUE | COND_INV_KNOWN | COND_INV_TRUE | COND_HAZARD_KNOWN
        res1 = self.execute_transaction(candidate=0xA5A50001, conditions=cond_valid)
        print(f"      Результат: committed={res1['committed']}, rejected={res1['rejected']}, стан={hex(res1['new_state'])}")
        assert res1["committed"] and not res1["rejected"], "Гілка 1 провалена"
        assert res1["new_state"] == 0xA5A50001, "Стан не оновився"
        print("      Статус: [PASS]")

        # Гілка 2: Відхилення за вхідними даними (assump_true = 0)
        print("\n--- [Гілка 2/4] Відхилення за вхідними даними (Input Reject) ---")
        cond_invalid_in = COND_CAND_KNOWN | COND_ASSUMP_KNOWN | COND_INV_KNOWN | COND_INV_TRUE | COND_HAZARD_KNOWN
        res2 = self.execute_transaction(candidate=0xDEADBEEF, conditions=cond_invalid_in)
        print(f"      Результат: committed={res2['committed']}, rejected_input={res2['rejected_input']}, стан={hex(res2['new_state'])}")
        assert res2["rejected"] and res2["rejected_input"], "Гілка 2 провалена"
        assert res2["new_state"] == 0xA5A50001, "Стан змінився попри відхилення!"
        print("      Статус: [PASS]")

        # Гілка 3: Відхилення за інваріантом (inv_true = 0)
        print("\n--- [Гілка 3/4] Відхилення за інваріантом (Invariant Reject) ---")
        cond_invalid_inv = COND_CAND_KNOWN | COND_ASSUMP_KNOWN | COND_ASSUMP_TRUE | COND_INV_KNOWN | COND_HAZARD_KNOWN
        res3 = self.execute_transaction(candidate=0xCAFE0002, conditions=cond_invalid_inv)
        print(f"      Результат: committed={res3['committed']}, rejected_inv={res3['rejected_inv']}, стан={hex(res3['new_state'])}")
        assert res3["rejected"] and res3["rejected_inv"], "Гілка 3 провалена"
        assert res3["new_state"] == 0xA5A50001, "Стан змінився попри відхилення інваріанта!"
        print("      Статус: [PASS]")

        # Гілка 4: Аварійне блокування при спостереженні Hazard
        print("\n--- [Гілка 4/4] Блокування небезпеки (Hazard Observed) ---")
        cond_hazard = COND_CAND_KNOWN | COND_ASSUMP_KNOWN | COND_ASSUMP_TRUE | COND_INV_KNOWN | COND_INV_TRUE | COND_HAZARD_KNOWN | COND_HAZARD_TRUE
        res4 = self.execute_transaction(candidate=0xBAD00003, conditions=cond_hazard)
        print(f"      Результат: committed={res4['committed']}, hazard={res4['hazard_observed']}, стан={hex(res4['new_state'])}")
        assert res4["rejected"] and res4["hazard_observed"], "Гілка 4 провалена"
        assert res4["new_state"] == 0xA5A50001, "Стан оновився під час аварії!"
        print("      Статус: [PASS]")

        print("\n" + "=" * 68)
        print(" ВСІ 4 ГІЛКИ ДРАЙВЕРА ПРЯМОГО MMIO УСПІШНО ВЕРИФІКОВАНІ [100% PASS]")
        print("=" * 68)
        return True


def main():
    parser = argparse.ArgumentParser(description="Драйвер прямого доступу до МК через pynq.MMIO (без .hwh)")
    parser.add_argument("--base-addr", type=lambda x: int(x, 0), default=0x40000000,
                        help="Фізична HEX-адреса на шині M_AXI_GP0 (за замовчуванням 0x40000000)")
    parser.add_argument("--bitfile", type=str, default=None,
                        help="Шлях до файлу .bit для завантаження в PL")
    parser.add_argument("--mock", action="store_true",
                        help="Запустити в режимі локальної емуляції без плати")
    parser.add_argument("--test", action="store_true",
                        help="Виконати повний верифікаційний тест 4-х гілок")
    args = parser.parse_args()

    driver = KuzminMachineDirectMMIO(base_addr=args.base_addr, bitfile=args.bitfile, mock=args.mock)

    if args.test or args.mock or args.bitfile is None:
        success = driver.run_validation_suite()
        sys.exit(0 if success else 1)
    else:
        ident_val, ident_str = driver.read_ident()
        print(f"Ідентифікатор: {hex(ident_val)} ('{ident_str}')")
        print(f"Поточний стан: {hex(driver.read_state())}")
        print(f"Статус:        {hex(driver.read_status())}")


if __name__ == "__main__":
    main()
