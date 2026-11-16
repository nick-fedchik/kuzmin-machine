# Пакет дослідження #254: порівняльний Baseline реактивності, площі кристала та оновлення правил проти CFG-P

* **Версія:** 0.1.0
* **Дата:** 2026-11-16
* **Тип WP редакції NG:** Guide
* **Issue:** [#254](https://github.com/nick-fedchik/kuzmin-machine/issues/254)

---

## Призначення пакета

Цей каталог містить код, автоматизований раннер, первинні журнали вимірювань і синтезу (`raw/`) та зведений інженерний звіт ([`report.md`](report.md)) для прямого порівняння дескрипторного BRAM-конвеєра `CFG-P` ([`kpol_bram_pipeline_axi.sv`](../../../Engineering/hw/rtl/bus/kpol_bram_pipeline_axi.sv)) на тотожній 4-концептній каскадній задачі профілю `KPOL-CME-2` із трьома альтернативними реалізаціями:

1. **Варіант 1 (`C99 -O3` у пам'яті процесора):** скомпільований код [`c99_cascade_bench.c`](c99_cascade_bench.c) (`gcc -O3 -mcpu=cortex-a9 -mfpu=neon`, `mlockall`) на фізичному ядрі `ARM Cortex-A9 @ 650 МГц` плати `PYNQ-Z1` у просторі користувача Linux без переривань на подію.
2. **Варіант 2 (Диспетчеризація подій ядра Linux):** пробудження потоку-обробника через `eventfd` + `poll` ядра Linux `6.6.10-xilinx` із виконанням того самого 4-концептного каскаду на `ARM Cortex-A9 @ 650 МГц`.
3. **Варіант 3 (Регістрово-конфігурований RTL у ПЛІС):** параметризований модуль [`km_reg_configurable_cascade_axi.sv`](../../../Engineering/hw/rtl/baseline/km_reg_configurable_cascade_axi.sv) (`NUM_CONCEPTS = 4, 16, 64`), що зберігає стани й правила у тригерах (`0 RAMB36E1`), оновлюється через AXI4-Lite без пересинтезу бітстріму та виконує один крок каскаду за `1` такт.
4. **Варіант 4 (`CFG-P`):** незмінний дескрипторний конвеєр [`kpol_bram_pipeline_axi.sv`](../../../Engineering/hw/rtl/bus/kpol_bram_pipeline_axi.sv) (`64` концепти в `1 RAMB36E1`, `8` тактів на концепт).

## Структура каталогу

* [`report.md`](report.md) — зведений звіт дослідження з обмеженнями, методикою, таблицями затримки/площі та розрахунком порога окупності $K^*$.
* [`c99_cascade_bench.c`](c99_cascade_bench.c) — еталонна реалізація C99 для мікробенчмаркінгу на `ARM Cortex-A9` та побітової перевірки трас (`--trace`).
* [`run_baseline_suite.py`](run_baseline_suite.py) — відтворюваний скрипт збору замірів `ARM Cortex-A9`, потактової RTL-симуляції та повного циклу `Yosys + nextpnr-himbaechel` (`xc7z020clg400-1`).
* `raw/` — незмінні сирі артефакти з заголовками `# cmd:` і `# timestamp:` та підсумковий маніфест контрольних сум [`raw/baseline_254_summary.json`](raw/baseline_254_summary.json).

## Пов'язані артефакти в `Engineering/`

* [`Engineering/hw/rtl/baseline/km_reg_configurable_cascade_axi.sv`](../../../Engineering/hw/rtl/baseline/km_reg_configurable_cascade_axi.sv) — RTL регістрово-конфігурованого каскадного конвеєра.
* [`Engineering/hw/tests/km_reg_configurable_cascade_axi_tb.sv`](../../../Engineering/hw/tests/km_reg_configurable_cascade_axi_tb.sv) — SystemVerilog тестбенч перевірки тактової точності та AXI4-Lite конфігурації.
* [`Engineering/hw/tests/test_comparative_baseline_254.py`](../../../Engineering/hw/tests/test_comparative_baseline_254.py) — набір тестів `pytest` побітової 4-сторонньої еквівалентності та 6 мутантних контролів (`3` RTL + `3` C99).

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-16 | Перша редакція пакета порівняльного baseline за Issue #254. |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| **CFG-P** | Конфігурація програмованого дескрипторного конвеєра Машини Кузьміна з пам'яттю концептів у `RAMB36E1`. |
| **MMIO** | Memory-Mapped Input/Output, регістровий ввід-вивід у адресному просторі шини AXI4-Lite. |
| **P&R** | Place-and-Route, фізичне розміщення та трасування елементів на матриці ПЛІС. |
| **LUT / FF** | Таблиця перекодування (`SLICE_LUTX`) та тригер (`SLICE_FFX`) логічної скибки ПЛІС серії Xilinx 7. |
| **WP** | Work Product, документований робочий продукт проєкту. |
