# Звіт #230: RTL-модуль `km_pmod_event_egress.sv` (SPI + 8-бітна шина) та верифікація симуляцією і синтезом XC7

* **Версія:** 0.1.0
* **Дата:** 2026-11-15
* **Тип WP:** Report
* **Issue:** [#230](https://github.com/nick-fedchik/kuzmin-machine/issues/230) (sub-issue [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226); не закриває `#226`). **PR:** у гілці `feat/230-pmod-event-egress-rtl`.
* **Виконавець:** GitHub Copilot CLI (`gemini-4-hydrogen`). **Рецензент:** не призначений (очікує перехресної рецензії моделлю іншої родини).
* **Коміт бази, на якому виконано:** `3c89b4e4fe35286e9c9b670553eccf2db5088835`. **Хост / плата:** Linux x86_64 (`AORUS-5-SE`); фізична плата FPGA / GPU не залучалася. **Бітстрім (SHA-256):** не генерувався.
* **Критерії успіху (зафіксовано до виконання):** [#230](https://github.com/nick-fedchik/kuzmin-machine/issues/230) та перша інженерна передумова протоколу [EXP-GPU-01](../../../../Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-01/protocol.md).

---

## 1. Що не вдалося і обмеження

* **Лише симуляція, лінт і логічний синтез XC7:** усі перевірки у цьому пакеті виконані в симуляції (`iverilog -g2012` + `vvp`), статичному лінті (`verilator --lint-only -Wall`) та логічному синтезі `yosys synth_xilinx` (без P&R `nextpnr-xilinx`, без генерації бітстріму і без статичного таймінгового аналізу на кристалі).
* **Відсутній фізичний HIL-запуск (`#226` залишається відкритою):** фізичне підключення PYNQ-Z1 (`3.3V LVCMOS`) до Jetson J501 (`1.8V` / буферизовані домени) через перетворювач рівнів та вимірювання логічним аналізатором `RP2040 PIO` не виконувалися.
* **Обсяг поля маски події:** у 64-бітному кадрі передаються молодші 16 біт маски підписок `event_mask_i[15:0]`; старші 16 біт `event_mask_i[31:16]` у цій версії не пакуються в кадр (закладено в заголовок порту для майбутнього розширення до 128-бітного кадра без зміни інтерфейсу).
* **Незмінність ядра:** файли в `Engineering/hw/rtl/core/`, `Engineering/hw/rtl/bus/`, `Engineering/hw/scripts/run_open_flow.sh` і `Project/registers/open-work-items.md` не змінювалися.

## 2. Метод

1. **RTL-модуль [`km_pmod_event_egress.sv`](../../../hw/rtl/io/km_pmod_event_egress.sv):**
   * Приймає 1-тактовий строб `event_valid_i` (`100 МГц`), `mode_par8_i`, `event_cid_i[5:0]`, `event_mask_i[31:0]`, `event_state_i[31:0]`.
   * Формує 64-бітний кадр `[63:0]`:
     * `[63:56]` — `crc8[7:0]` (поліном `0x07`, ініціалізація `0x00`, MSB-first по 56 бітах `[55:0]`);
     * `[55:54]` — `2'b01` (тег формату з CRC-8);
     * `[53:48]` — `event_cid_i[5:0]`;
     * `[47:32]` — `event_mask_i[15:0]`;
     * `[31:0]` — `event_state_i[31:0]`.
   * Режим `mode_par8_i == 0` (SPI Master Mode 0, CPOL=0, CPHA=0, MSB-first, `clk/2 = 50 МГц`): видає 64 імпульси `spi_sck_o` при `spi_cs_n_o == 0` (`129` тактів активного стану `busy_o`, або `1.29 мкс` при `100 МГц`).
   * Режим `mode_par8_i == 1` (8-бітна джерельно-синхронна паралельна шина, MSB byte first, `clk/2 = 50 МГц`): видає 8 байтів на `par_data_o[7:0]` із `par_valid_o == 1` та 8 імпульсами `par_clk_o` (`17` тактів активного стану `busy_o`, або `170 нс` при `100 МГц`, у межах порогу $`T_{\text{par}} \le 600\text{ нс}`$ з `EXP-GPU-01`).
   * Генерує 1-тактовий строб `event_start_o` при старті прийнятої події (для `GP0` аналізатора `RP2040 PIO`). При надходженні `event_valid_i` під час `busy_o == 1` активна передача не псується, а `drop_count_o` інкрементується.
2. **Самоперевірний тестбенч [`km_pmod_event_egress_tb.sv`](../../../hw/tb/km_pmod_event_egress_tb.sv) та pytest-обгортка [`test_km_pmod_event_egress.py`](../../../hw/tests/test_km_pmod_event_egress.py):**
   * Незалежні приймачі-декодери SPI Mode 0 та 8-бітної паралельної шини у SV перевіряють розпаковані поля `tag`, `cid`, `mask16`, `state`, `crc8`, кількість тактів `busy_o`, строб `event_start_o` і лічильники `tx_count_o` / `drop_count_o` (включаючи колізії в обох режимах).
   * Незалежний Python-розрахунок CRC-8 (`_py_crc8`) звіряє 64-бітні кадри, виведені з симуляції.
   * Мутантний негативний контроль (`AGENTS.md §4.1`): три мутанти RTL (зіпсований поліном CRC-8 `8'h07 -> 8'h05`, зсув на 2 біти в SPI та зсув на 9 біт у паралельному режимі) повинні гарантовано провалювати симуляцію (`returncode != 0`).
3. **Реєстрація та відкритий потік:** тестбенч додано до `TESTBENCHES` у [`test_testbenches.py`](../../../hw/tests/test_testbenches.py), пройдено `run_open_flow.sh`, `pytest`, `check_links.py`, `check_wp_documents.py`.

## 3. Результати

* **Симуляція `iverilog -g2012` / `vvp` ([`raw/sim-iverilog-01.log`](raw/sim-iverilog-01.log)):** `ALL KM_PMOD_EVENT_EGRESS SIMULATION TESTS PASSED`, `$finish` на `3065000 ps`:
  * Test 1 (SPI Mode 0): `64` фронти `spi_sck_o`, `129` тактів `busy_o`, кадр `0x8e45a55a12345678`, `tx=1`, `drop=0`.
  * Test 2 (SPI Collision): `2` колізійні імпульси під час `busy_o` відхилені без пошкодження кадра (`tx=2`, `drop=2`).
  * Test 3 (PAR8 Mode + Collision): `8` байтів, `17` тактів `busy_o` (`170 нс` @ `100 МГц`), кадр `0x6e7fffff80000001`, `tx=3`, `drop=3`.
  * Test 4 (PAR8 Zero boundary): `8` байтів, `17` тактів `busy_o`, кадр `0x4540000000000000`, `tx=4`, `drop=3`.
* **Лінтер `Verilator 5.032` ([`raw/verilator-lint-01.log`](raw/verilator-lint-01.log)):** `verilator --lint-only -Wall --top-module km_pmod_event_egress` завершився з кодом `0`, попереджень немає.
* **Логічний синтез XC7 `Yosys 0.52` ([`raw/yosys-synth-xc7-01.log`](raw/yosys-synth-xc7-01.log)):** `synth_xilinx -top km_pmod_event_egress` + `check` — `0 problems`, `661` комірок (`145` LCs, `154` `FDCE`, `2` `FDPE`, `19` `CARRY4`, `4` `MUXF7`, `LUT2..LUT6`).
* **Pytest-обгортка з Python-оракулом CRC-8 та 3 мутантами ([`raw/pytest-egress-01.log`](raw/pytest-egress-01.log)):** `6 passed in 2.03s` (усі 3 мутанти очікувано впали у симуляції).
* **Відкритий апаратний потік ([`raw/open-flow-01.log`](raw/open-flow-01.log)):** `bash Engineering/hw/scripts/run_open_flow.sh` — `171 passed in 14.24s`, lint та синтез XC7 завершилися з кодом `0`.
* **Фінальна перевірка пакета ([`raw/final-verification-01.log`](raw/final-verification-01.log)):** повний `python3 -m pytest -q`, `check_links.py`, `check_wp_documents.py` та `git diff --check` завершилися з кодом `0`.

## 4. Перевірка гіпотези / критеріїв

| Критерій (`#230`) | Очікувано | Отримано | Висновок |
| :--- | :--- | :--- | :--- |
| Модуль `km_pmod_event_egress.sv` (SPI `clk/2` + 8-бітна шина + `event_start_o` + `drop_count_o`) | Побітова/побайтова передача 64-бітного кадра з CRC-8, захист від колізій при `busy_o` | Підтверджено в `iverilog` (`129` тактів SPI, `17` тактів PAR8) та незалежним Python-оракулом ([`raw/sim-iverilog-01.log`](raw/sim-iverilog-01.log), [`raw/pytest-egress-01.log`](raw/pytest-egress-01.log)) | Виконано (симуляція) |
| Чистий лінт і логічний синтез XC7 | `verilator --lint-only -Wall` і `yosys synth_xilinx` з кодом `0` | `0` попереджень Verilator, `0` проблем Yosys (`145` LCs) ([`raw/verilator-lint-01.log`](raw/verilator-lint-01.log), [`raw/yosys-synth-xc7-01.log`](raw/yosys-synth-xc7-01.log)) | Виконано (синтез XC7) |
| Мутантний негативний контроль (`AGENTS.md §4.1`) | Навмисно зіпсований RTL провалює тестбенч | Усі 3 мутанти (`corrupt_crc_poly`, `corrupt_spi_shift_bit`, `corrupt_par8_byte_shift`) впали (`returncode != 0`) ([`raw/pytest-egress-01.log`](raw/pytest-egress-01.log)) | Виконано |
| Повна перевірка репозиторію | `pytest`, `run_open_flow.sh`, `check_links.py`, `check_wp_documents.py`, `git diff --check` == `0` | Усі 5 перевірок пройшли з кодом `0` ([`raw/open-flow-01.log`](raw/open-flow-01.log), [`raw/final-verification-01.log`](raw/final-verification-01.log)) | Виконано |

## 5. Відтворення

```bash
python3 -m pytest -v Engineering/hw/tests/test_km_pmod_event_egress.py
python3 -m pytest -q
bash Engineering/hw/scripts/run_open_flow.sh
KM_DRAFTS_REPO=/home/mfedchyk/GitHub/nick-fedchik/drafts python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
```

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-15 | Перша редакція звіту реалізації та верифікації симуляцією/синтезом XC7 модуля `km_pmod_event_egress.sv` ([#230](https://github.com/nick-fedchik/kuzmin-machine/issues/230)). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| CRC-8 | 8-бітна циклічна контрольна сума (поліном `0x07`, init `0x00`). |
| HIL | Hardware-in-the-Loop (фізичний запуск на платах PYNQ-Z1 / Jetson J501; не виконувався). |
| LC | Logic Cell (оцінка логічних комірок XC7 у Yosys). |
| PMOD | Peripheral Module (інтерфейсний роз'єм плати PYNQ-Z1). |
| SPI | Serial Peripheral Interface (послідовний периферійний інтерфейс, Mode 0). |
