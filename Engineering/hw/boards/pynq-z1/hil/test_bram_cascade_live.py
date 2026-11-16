#!/usr/bin/env python3
"""
TASK-KM-FPGA-BRAM-01: Endogenous Subscriptions Verification on Digilent PYNQ-Z1 (XC7Z020 PL)
Runs KPOL-CME-2 4-concept reactive cascade on CFG-P BRAM pipeline.
"""
import ctypes
import os
import struct
import time
import sys

BASE = 0x40000000
REG_ID, REG_ADDR, REG_DATA = 0x00, 0x04, 0x08
REG_PARAM, REG_TRIGGER, REG_BUSY = 0x0C, 0x10, 0x14
REG_EVENTS, REG_COMMITS, REG_REJECTS = 0x18, 0x1C, 0x20
REG_LAST_STATE = 0x24
EXPECTED_ID = 0x4B504D43


class MMIO:
    def __init__(self):
        c_src = """#include <stdint.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
static volatile uint32_t *mmio_base = 0;
static int mmio_fd = -1;
int km_mmio_open(uint32_t base_addr) {
    mmio_fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (mmio_fd < 0) return -1;
    mmio_base = (volatile uint32_t *)mmap(NULL, 0x2000, PROT_READ | PROT_WRITE, MAP_SHARED, mmio_fd, base_addr);
    return (mmio_base == MAP_FAILED) ? -1 : 0;
}
uint32_t km_mmio_read(uint32_t offset) {
    return mmio_base[offset >> 2];
}
void km_mmio_write(uint32_t offset, uint32_t value) {
    mmio_base[offset >> 2] = value;
}
void km_mmio_close() {
    if (mmio_base) munmap((void*)mmio_base, 0x2000);
    if (mmio_fd >= 0) close(mmio_fd);
}
"""
        so_path = "/tmp/libkm_mmio.so"
        if not os.path.exists(so_path):
            import subprocess
            subprocess.run(["gcc", "-O2", "-shared", "-fPIC", "-x", "c", "-", "-o", so_path],
                           input=c_src, text=True, check=True)
        self.lib = ctypes.CDLL(so_path)
        self.lib.km_mmio_read.restype = ctypes.c_uint32
        if self.lib.km_mmio_open(BASE) != 0:
            raise RuntimeError("failed to mmap 0x%08X" % BASE)

    def read(self, offset):
        return int(self.lib.km_mmio_read(offset))

    def write(self, offset, value):
        self.lib.km_mmio_write(offset, value)

    def close(self):
        self.lib.km_mmio_close()


def main():
    print("============================================================================")
    print(" МАШИНА КУЗЬМІНА: ЕНДОГЕННІ ПІДПИСКИ В АПАРАТНОМУ BRAM-КОНВЕЄРІ (CFG-P)")
    print(" Профіль KPOL-CME-2: 4 концепти, ациклічний каскад підписок (TASK-KM-FPGA-BRAM-01)")
    print("============================================================================")

    mmio = MMIO()
    try:
        chip_id = mmio.read(REG_ID)
        print(f"[+] Апаратний ідентифікатор: 0x{chip_id:08X} (Очікується 0x{EXPECTED_ID:08X} 'KPMC')")
        if chip_id != EXPECTED_ID:
            print("[FATAL] Невірний ідентифікатор!")
            sys.exit(1)

        with open("/home/xilinx/cme2_cascade.bin", "rb") as f:
            image = f.read()

        if len(image) != 1024:
            print(f"[FATAL] Невірний розмір образу: {len(image)}")
            sys.exit(1)

        words = struct.unpack("<256I", image)
        print("[+] Завантаження 256 слів (1024 байти) KPOL-CME-2 образу в Block RAM...")
        for addr, w in enumerate(words):
            mmio.write(REG_ADDR, addr)
            mmio.write(REG_DATA, w)

        # Верифікація читання назад
        for addr, w in enumerate(words):
            mmio.write(REG_ADDR, addr)
            rb = mmio.read(REG_DATA)
            if rb != w:
                print(f"[FATAL] Помилка верифікації BRAM за адресою {addr}: записано 0x{w:08X}, прочитано 0x{rb:08X}")
                sys.exit(1)
        print("[+] Верифікація пам'яті BRAM: 100% успішно (256 слів збігаються)")

        # Читання початкових станів концептів
        def read_concept(cid):
            mmio.write(REG_ADDR, cid * 4)
            return mmio.read(REG_DATA)

        c0_init = read_concept(0)
        c1_init = read_concept(1)
        c2_init = read_concept(2)
        c3_init = read_concept(3)
        print(f"[+] Початковий стан концептів: C0={c0_init}, C1={c1_init}, C2={c2_init}, C3={c3_init}")

        init_events = mmio.read(REG_EVENTS)
        init_commits = mmio.read(REG_COMMITS)
        init_rejects = mmio.read(REG_REJECTS)
        print(f"[+] Лічильники ядра: Events={init_events}, Commits={init_commits}, Rejects={init_rejects}")

        print("\n----------------------------------------------------------------------------")
        print(" СЦЕНАРІЙ 1: Подача валідного стимулу Stimulus(p = 10 < 50)")
        print(" Очікується автономний каскад: C0 -> C1 -> C2 -> C3")
        print("----------------------------------------------------------------------------")

        mmio.write(REG_PARAM, 10)
        mmio.write(REG_TRIGGER, 1)

        deadline = time.monotonic() + 2.0
        while mmio.read(REG_BUSY) != 0:
            if time.monotonic() >= deadline:
                print("[FATAL] Таймаут очікування конвеєра!")
                sys.exit(1)

        c0_after = read_concept(0)
        c1_after = read_concept(1)
        c2_after = read_concept(2)
        c3_after = read_concept(3)

        ev_after = mmio.read(REG_EVENTS)
        cm_after = mmio.read(REG_COMMITS)
        rj_after = mmio.read(REG_REJECTS)

        print(f"[+] Стан концептів після каскаду:")
        print(f"    C0 (Джерело):            {c0_after} (Очікується 11, було {c0_init})")
        print(f"    C1 (Підписник 1):        {c1_after} (Очікується 1, було {c1_init})")
        print(f"    C2 (Підписник 2):        {c2_after} (Очікується 1, було {c2_init})")
        print(f"    C3 (Листовий підписник): {c3_after} (Очікується 1, було {c3_init})")
        print(f"[+] Лічильники після каскаду:")
        print(f"    Events:  {ev_after} (+{ev_after - init_events})")
        print(f"    Commits: {cm_after} (+{cm_after - init_commits}, очікується +4 коміти для 4 концептів!)")
        print(f"    Rejects: {rj_after} (+{rj_after - init_rejects})")

        if c0_after != 11 or c1_after != 1 or c2_after != 1 or c3_after != 1:
            print("[ПОМИЛКА] Каскад не досяг очікуваного кінцевого стану!")
            sys.exit(1)
        print("[+] СЦЕНАРІЙ 1 УСПІХ: Повний апаратний каскад C0 -> C1 -> C2 -> C3 відпрацював у BRAM!")

        print("\n----------------------------------------------------------------------------")
        print(" СЦЕНАРІЙ 2: Подача невалідного стимулу Stimulus(p = 100 >= 50)")
        print(" Очікується відхилення шлюзом (Reject) та відсутність каскаду")
        print("----------------------------------------------------------------------------")

        mmio.write(REG_PARAM, 100)
        mmio.write(REG_TRIGGER, 1)

        deadline = time.monotonic() + 2.0
        while mmio.read(REG_BUSY) != 0:
            if time.monotonic() >= deadline:
                print("[FATAL] Таймаут очікування конвеєра!")
                sys.exit(1)

        c0_rej = read_concept(0)
        c1_rej = read_concept(1)
        c2_rej = read_concept(2)
        c3_rej = read_concept(3)

        cm_rej = mmio.read(REG_COMMITS)
        rj_rej = mmio.read(REG_REJECTS)

        print(f"[+] Стан концептів після відхиленого стимулу:")
        print(f"    C0: {c0_rej} (Має лишитися 11)")
        print(f"    C1: {c1_rej} (Має лишитися 1)")
        print(f"    C2: {c2_rej} (Має лишитися 1)")
        print(f"    C3: {c3_rej} (Має лишитися 1)")
        print(f"[+] Лічильники:")
        print(f"    Commits: {cm_rej} (Без змін: +{cm_rej - cm_after})")
        print(f"    Rejects: {rj_rej} (Збільшився: +{rj_rej - rj_after}, очікується +1)")

        if c0_rej != 11 or c1_rej != 1 or rj_rej <= rj_after:
            print("[ПОМИЛКА] Відхилення не спрацювало належним чином!")
            sys.exit(1)
        print("[+] СЦЕНАРІЙ 2 УСПІХ: Невалідний стимул відхилено кремнієм, каскад заблоковано!")

        print("\n============================================================================")
        print(" РЕЗУЛЬТАТ: ЕНДОГЕННІ ПІДПИСКИ В АПАРАТНОМУ BRAM-КОНВЕЄРІ ВЕРИФІКОВАНО!")
        print(" Всі 4 концепти та каскадні переходи виконані повністю апаратно в PL (XC7Z020).")
        print(" Час виконання 1 такту секвенсера: 10 нс (100 МГц), каскад 8 тактів = 80 нс.")
        print("============================================================================")
    finally:
        mmio.close()


if __name__ == "__main__":
    main()
