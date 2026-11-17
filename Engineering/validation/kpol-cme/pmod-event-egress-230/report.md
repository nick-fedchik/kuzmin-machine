# Звіт #230 / #241: RTL-модуль `km_pmod_event_egress.sv`, інтеграція в PYNQ-Z1 egress top та закриття #234

* **Версія:** 0.2.1
* **Дата:** 2026-11-17
* **Тип WP:** Report
* **Issue:** [#230](https://github.com/nick-fedchik/kuzmin-machine/issues/230), [#234](https://github.com/nick-fedchik/kuzmin-machine/issues/234), [#241](https://github.com/nick-fedchik/kuzmin-machine/issues/241), [#247](https://github.com/nick-fedchik/kuzmin-machine/issues/247) (sub-issue [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226); не закриває `#226`). **PR:** у гілці `fix/247-level-shifter-and-commit-cid-test`.
* **Виконавець:** GitHub Copilot CLI (`gemini-4-hydrogen`). **Рецензент:** не призначений (очікує перехресної рецензії моделлю іншої родини).
* **Коміт коду, на якому знято `*-02.log`:** `0e01996d4eb35858e9479e5cf8ec88dbfc65a94d` (базовий зріз `0.1.0`: `3c89b4e4fe35286e9c9b670553eccf2db5088835`). **Хост / плата:** Linux x86_64 (`AORUS-5-SE`); фізична плата FPGA / GPU не залучалася. **Бітстрім (SHA-256):** не генерувався.
* **Критерії успіху (зафіксовано до виконання):** [#230](https://github.com/nick-fedchik/kuzmin-machine/issues/230), [#234](https://github.com/nick-fedchik/kuzmin-machine/issues/234), [#241](https://github.com/nick-fedchik/kuzmin-machine/issues/241) та перша інженерна передумова протоколу [EXP-GPU-01](../../../../Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-01/protocol.md).

---

## 1. Що не вдалося і обмеження

* **Лише симуляція (mock `PS7` / `BUFG`), лінт і логічний синтез XC7:** усі перевірки у цьому пакеті виконані в симуляції (`iverilog -g2012` + `vvp` із поведінковими моделями `PS7` та `BUFG`), статичному лінті (`verilator --lint-only -Wall`) та логічному синтезі `yosys synth_xilinx` (без P&R `nextpnr-xilinx`, без генерації бітстріму і без статичного таймінгового аналізу на кристалі).
* **Фізичний HIL-захват та перевірка перетворювача рівнів (`#226` залишається відкритою):** фізичний HIL-захват `RP2040 PIO` між PYNQ-Z1 (`3.3V LVCMOS`) і Jetson J501 (`1.8V`) очікує монтажу та осцилографування перетворювача рівнів у межах [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226). Вибір між наявним у лабораторії `TXS0108E` (при зниженій частоті SPI або в режимі `PAR8` з короткими провідниками) та буферизованим `SN74AVC8T245` сформульовано як інженерну гіпотезу та критерій перевірки для натурного HIL (#226), а не як апріорний факт до осцилографування (§2.4, [#247](https://github.com/nick-fedchik/kuzmin-machine/issues/247)).
* **Обсяг поля маски події:** у 64-бітному кадрі передаються молодші 16 біт маски підписок `event_mask_i[15:0]`; старші 16 біт `event_mask_i[31:16]` у цій версії не пакуються в кадр (закладено в заголовок порту для майбутнього розширення без зміни інтерфейсу).
* **Незмінність ядра та сумісність `CFG-P`:** файли в `Engineering/hw/rtl/core/`, базовий `kpol_bram_pipeline_pynq_z1_top.v`, `Engineering/hw/scripts/run_open_flow.sh`, `Project/registers/open-work-items.md` та попередні сирі логи `raw/*-01.log` не змінювалися. У `kpol_bram_pipeline_axi.sv` додано лише чисті діагностичні виходи `hw_commit_cid_o` та `hw_last_committed_state_o` без зміни логіки ядра чи існуючої поведінки AXI4-Lite.
* **Межі `run_open_flow.sh` (уточнення #234 п. 5):** скрипт `Engineering/hw/scripts/run_open_flow.sh` виконує `pytest` для тестбенчів та `verilator`/`yosys` безпосередньо для `rtl/core` і `rtl/bus/kpol_bram_pipeline_axi.sv`, тоді як lint, логічний синтез XC7 та наскрізну E2E-симуляцію `km_pmod_event_egress` і `kpol_bram_pipeline_pynq_z1_egress_top` виконує pytest-обгортка [`test_km_pmod_event_egress.py`](../../../hw/tests/test_km_pmod_event_egress.py).

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
2. **Самоперевірний тестбенч [`km_pmod_event_egress_tb.sv`](../../../hw/tb/km_pmod_event_egress_tb.sv) та pytest-обгортка [`test_km_pmod_event_egress.py`](../../../hw/tests/test_km_pmod_event_egress.py) (закриття #234):**
   * Незалежні приймачі-декодери SPI Mode 0 та 8-бітної паралельної шини у SV перевіряють розпаковані поля `tag`, `cid`, `mask16`, `state`, `crc8`, кількість тактів `busy_o`, строб `event_start_o` і лічильники `tx_count_o` / `drop_count_o`.
   * Додано перевірки станів спокою (`spi_cs_n_o == 1`, `spi_sck_o == 0`, `par_valid_o == 0`, `par_clk_o == 0`), обрамлення `spi_cs_n_o == 0` у `S_SPI_END` та `par_valid_o == 1` у `S_PAR_END`, setup/hold стабільності даних (`>= 10 нс` до фронту, без змін при високому такті), глобальний `watchdog` (`#200000`) і граничні колізії (`event_valid_i` у такті `S_*_END`, у перший такт `S_IDLE`, багатотактовий `event_valid_i`).
   * Незалежний Python-розрахунок CRC-8 (`_py_crc8`) звіряє 64-бітні кадри, виведені з симуляції.
   * Мутантний негативний контроль (`AGENTS.md §4.1`) розширено до **8 мутантів**: `corrupt_crc_poly`, `corrupt_spi_shift_bit`, `corrupt_par8_byte_shift`, `cs_high_in_end`, `par_valid_drop_end`, `broken_drop_count`, `missing_event_start`, `stuck_not_busy` — усі мають провалювати симуляцію (`returncode != 0`).
3. **Інтеграція у топовий модуль [`kpol_bram_pipeline_pynq_z1_egress_top.v`](../../../hw/boards/pynq-z1/kpol_bram_pipeline_pynq_z1_egress_top.v) + [`kpol_bram_pipeline_egress.xdc`](../../../hw/boards/pynq-z1/kpol_bram_pipeline_egress.xdc) (#241):**
   * Інстанційовано `kpol_bram_pipeline_axi` та `km_pmod_event_egress` із 1-тактовим вирівнюванням `hw_commit_pulse_o` до діагностичних виходів `hw_commit_cid_o` і `hw_last_committed_state_o`.
   * Розподіл пінів PMOD JA (`LVCMOS33`): `JA1..JA4` (`Y18, Y19, Y16, Y17`) — зовнішній тригер і статус конвеєра; `JA7` (`U18`, `egress_par8_mode_i` з `PULLDOWN` і 2-FF CDC) — вибір режиму `0=SPI / 1=PAR8`; `JA8..JA10` (`U19, W18, W19`) — `event_start_o`, `par_valid_o`, `par_clk_o`.
   * Розподіл пінів PMOD JB (`LVCMOS33`, стандарт Digilent PYNQ-Z1): `JB1..JB4` (`W14, Y14, T11, T10`) і `JB7..JB10` (`V16, W16, V12, W13`) передають `par_data_o[7:0]` у режимі PAR8 або `{2'b00, egress_drop_seen, egress_busy, egress_event_start, spi_sck, spi_mosi, spi_cs_n}` у режимі SPI; `led[3]` (`M14`) індикує `fifo_overflow | egress_drop_seen`.
   * Наскрізний тестбенч [`kpol_bram_pipeline_pynq_z1_egress_top_tb.sv`](../../../hw/tests/kpol_bram_pipeline_pynq_z1_egress_top_tb.sv) (mock `PS7`/`BUFG`) перевіряє запис правила в BRAM через AXI, тригер `ja1`, коміт у BRAM та декодування валідного 64-бітного кадра з CRC-8 на виходах PMOD JB у обох режимах (SPI та PAR8).
4. **Паспортна характеристика `TXS0108E` (`SCES642I`) проти односпрямованого тракту `SN74AVC8T245` (`SCES172`) для `3.3V -> 1.8V` (#247):**
   * PMOD-інтерфейси PYNQ-Z1 працюють у домені `3.3V LVCMOS`, тоді як лінії роз'єму розширення `Jetson AGX Orin J501` мають домен `1.8V`.
   * За даташитом Texas Instruments `TXS0108E` (`SCES642I`, Table 6.6 / 6.7 *Switching Characteristics* для $V_{CCA} = 1.8\text{ V} \pm 0.15\text{ V}$, $V_{CCB} = 3.3\text{ V} \pm 0.3\text{ V}$, Push-Pull driving):
     * максимальна паспортна швидкість передачі в режимі Push-Pull при трансляції $1.8\text{ V} \leftrightarrow 3.3\text{ V}$ становить **`60 Mbps`** (`30 МГц` тактової частоти з періодом `33.3 нс`; режим `110 Mbps` досягається лише при $V_{CCA} \ge 2.5\text{ V} \to 3.3\text{ V}$), а в режимі Open-Drain — `2 Mbps`;
     * для **паралельного 8-бітного режиму `PAR8`** (де частота строба `par_valid` становить `50 МГц` / тривалість високого й низького рівнів по `10 нс`, тобто еквівалент `100 Mbps`, або з 2-тактовим утриманням — `25 МГц` / `50 Mbps`) робота на `TXS0108E` при $1.8\text{ В}$ лежить у межах або на межі паспортних `60 Mbps`;
     * для **SPI `50 МГц` (`100 Mbps` по лінії `SCK`)** режим перевищує паспортний максимум `60 Mbps` для пари `1.8V/3.3V` і додатково чутливий до ємності макетних дротів через відсутність буферизації після закінчення імпульсу one-shot (`~10 нс` edge-rate accelerator + внутрішній `10 kΩ` pull-up);
     * тому вибір між наявним у лабораторії `TXS0108E` (при зниженій частоті SPI або режимі `PAR8` з короткими провідниками) та буферизованим `SN74AVC8T245` формулюється як **інженерна гіпотеза та критерій перевірки для натурного HIL ([#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226))**, а не апріорний факт до осцилографування.
   * **Схемотехнічний чекліст увімкнення `SN74AVC8T245` (`SCES172`) для односпрямованого тракту `3.3V -> 1.8V`:**

| Сигнал / Шина | Підключення | Призначення та примітки |
| :--- | :--- | :--- |
| `VCCA` | `3.3V` (шини PMOD `JA/JB` плати `PYNQ-Z1`) | Живлення сторони A (вхідна сторона від ПЛІС Zynq-7000). |
| `VCCB` | `1.8V` (шини GPIO роз'єму розширення `Jetson AGX Orin J501`) | Живлення сторони B (вихідна сторона до приймача). |
| `DIR` (8 ліній `JB`) | `HIGH` (`VCCA = 3.3V`, жорстко на шині живлення) | Напрямок `A -> B` (`3.3V -> 1.8V`). Окремий пін ПЛІС для перемикання напрямку не потрібен, оскільки шина односпрямована від ПЛІС до GPU; для зворотного сигналу `ext_ready_i` (`1.8V -> 3.3V`) використовується окремий канал з `DIR = LOW (GND)` або одноканальний транслятор `SN74AVC1T45`. |
| `/OE` (Output Enable, активний низький) | Підтяжка `10 kΩ` до `VCCA (3.3V)` під час подачі живлення; після стабілізації — `GND` (або опційний керуючий сигнал дозволу) | Гарантує стан `Hi-Z` під час power sequencing (`I_off` partial-power-down protection до встановлення обох напруг `VCCA` та `VCCB`). |

## 3. Результати

* **Симуляція `iverilog -g2012` / `vvp` ([`raw/sim-iverilog-02.log`](raw/sim-iverilog-02.log)):**
  * `km_pmod_event_egress_tb.sv`: `ALL KM_PMOD_EVENT_EGRESS SIMULATION TESTS PASSED`, `$finish` на `6095000 ps` (усі 6 тестів включно з колізіями `S_SPI_END` / `S_PAR_END`, першим тактом `S_IDLE`, багатотактовим `event_valid_i`, перевірками станів спокою, обрамлення CS/`par_valid_o` та setup/hold).
  * `kpol_bram_pipeline_pynq_z1_egress_top_tb.sv` (mock `PS7`/`BUFG`): `PASS: ALL PYNQ_Z1_EGRESS_TOP E2E TESTS PASSED`, `$finish` на `17670000 ps` — кадри `0x8d420000000000c9` (SPI, `cid=2, state=201`) та `0x84420000000000ca` (PAR8, `cid=2, state=202`).
* **Лінтер `Verilator 5.032` та pytest-обгортка ([`raw/pytest-egress-02.log`](raw/pytest-egress-02.log)):** `14 passed in 8.78s` — перевірено Python-оракул CRC-8 (модульний та E2E top), `verilator --lint-only -Wall` (для `km_pmod_event_egress` та `kpol_bram_pipeline_pynq_z1_egress_top`), `yosys synth_xilinx` (для обох модулів) і **усі 8 мутантів** (усі 8 очікувано впали у симуляції).
* **Логічний синтез XC7 топа `kpol_bram_pipeline_pynq_z1_egress_top` у `Yosys 0.52` ([`raw/yosys-synth-xc7-02.log`](raw/yosys-synth-xc7-02.log)):** `synth_xilinx` + `check` — `0 problems`, `5154` комірки (`1 RAMB36E1`, `162 CARRY4`, `1031 FDCE`, `2 FDPE`, `608 FDRE`, `1180 INV`, `LUT1..LUT6`, `16 MUXF7`, `8 MUXF8`, `1 BUFG`, `1 PS7`).
* **Відкритий апаратний потік ([`raw/open-flow-02.log`](raw/open-flow-02.log)):** `bash Engineering/hw/scripts/run_open_flow.sh` — `171 passed in 15.17s`, lint та синтез XC7 для `rtl/core` і `rtl/bus` завершилися з кодом `0`.
* **Фінальна перевірка пакета ([`raw/final-verification-02.log`](raw/final-verification-02.log)):** `KM_SKIP_LIVE_HIL=1 python3 -m pytest -q` (`387 passed, 1 skipped, 385 subtests passed`), `check_links.py` (`0` битих посилань), `check_wp_documents.py` (`153` документи, `0` помилок).

## 4. Перевірка гіпотези / критеріїв

| Критерій (`#230`, `#234`, `#241`) | Очікувано | Отримано | Висновок |
| :--- | :--- | :--- | :--- |
| Закриття 5 пунктів `#234` (TB-перевірки, `watchdog`, граничні колізії, `>=7` мутантів, провенанс) | 8/8 мутантів гинуть, TB перевіряє CS/`par_valid_o`/idle/setup-hold, нові логи з кодовим SHA | Підтверджено: `14 passed in 8.78s`, 8/8 мутантів killed, SHA `0e01996` у `raw/*-02.log` ([`raw/pytest-egress-02.log`](raw/pytest-egress-02.log), [`raw/sim-iverilog-02.log`](raw/sim-iverilog-02.log)) | Виконано |
| Інтеграція `kpol_bram_pipeline_pynq_z1_egress_top.v` + `kpol_bram_pipeline_egress.xdc` (`#241`) | Наскрізна симуляція (mock PS7) `ja1 -> BRAM -> PMOD JB` з CRC-8, чистий `verilator` та `yosys synth_xilinx` | Підтверджено: SPI (`0x8d420000000000c9`) і PAR8 (`0x84420000000000ca`), `0` проблем Yosys (`5154` комірки) ([`raw/sim-iverilog-02.log`](raw/sim-iverilog-02.log), [`raw/yosys-synth-xc7-02.log`](raw/yosys-synth-xc7-02.log)) | Виконано (симуляція / синтез XC7) |
| Повна перевірка репозиторію | `pytest`, `run_open_flow.sh`, `check_links.py`, `check_wp_documents.py`, `git diff --check` == `0` | Усі 5 перевірок пройшли з кодом `0` ([`raw/open-flow-02.log`](raw/open-flow-02.log), [`raw/final-verification-02.log`](raw/final-verification-02.log)) | Виконано |

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
| 0.2.1 | 2026-11-17 | Закрито знахідки [#247](https://github.com/nick-fedchik/kuzmin-machine/issues/247): уточнено паспортні характеристики `TXS0108E` (`SCES642I`, `60 Mbps` Push-Pull для `1.8V <-> 3.3V`, `110 Mbps` лише при $V_{CCA} \ge 2.5\text{ V}$) як інженерну гіпотезу до HIL ([#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226)), додано табличний чекліст увімкнення `SN74AVC8T245` (`DIR`, `/OE`, `VCCA/VCCB`, power sequencing) та ізольований unit-тест із мутантним контролем для `hw_commit_cid_o` у `kpol_bram_pipeline_axi_tb.sv` / `test_kpol_bram_pipeline.py`. |
| 0.2.0 | 2026-11-16 | Закрито 5 знахідок [#234](https://github.com/nick-fedchik/kuzmin-machine/issues/234) (посилений TB, 8 мутантів, `watchdog`, провенанс `*-02.log`, уточнення `run_open_flow.sh`), інтегровано `kpol_bram_pipeline_pynq_z1_egress_top.v` + `kpol_bram_pipeline_egress.xdc` та обґрунтування перетворювача рівнів `3.3V <-> 1.8V` ([#241](https://github.com/nick-fedchik/kuzmin-machine/issues/241)). |
| 0.1.0 | 2026-11-15 | Перша редакція звіту реалізації та верифікації симуляцією/синтезом XC7 модуля `km_pmod_event_egress.sv` ([#230](https://github.com/nick-fedchik/kuzmin-machine/issues/230)). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| CRC-8 | 8-бітна циклічна контрольна сума (поліном `0x07`, init `0x00`). |
| HIL | Hardware-in-the-Loop (фізичний запуск на платах PYNQ-Z1 / Jetson J501; не виконувався). |
| LC | Logic Cell (оцінка логічних комірок XC7 у Yosys). |
| PMOD | Peripheral Module (інтерфейсний роз'єм плати PYNQ-Z1). |
| SPI | Serial Peripheral Interface (послідовний периферійний інтерфейс, Mode 0). |
