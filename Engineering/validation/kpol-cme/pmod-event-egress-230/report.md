# Звіт #230 / #241: RTL-модуль `km_pmod_event_egress.sv`, інтеграція в PYNQ-Z1 egress top та закриття #234

* **Версія:** 0.3.0
* **Дата:** 2026-11-17
* **Тип WP:** Report
* **Issue:** [#230](https://github.com/nick-fedchik/kuzmin-machine/issues/230), [#234](https://github.com/nick-fedchik/kuzmin-machine/issues/234), [#241](https://github.com/nick-fedchik/kuzmin-machine/issues/241), [#247](https://github.com/nick-fedchik/kuzmin-machine/issues/247), `Part of` [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226). **PR:** у гілці `exp/226-egress-openxc7-and-crossboard-e2e`.
* **Виконавець:** GitHub Copilot CLI (`gemini-4-hydrogen` для `0.1.0–0.2.2`; `0.3.0` — P&R, бітстрім і натурний HIL). **Рецензент:** очікує перехресної рецензії моделлю іншої родини.
* **Коміт коду:** базовий зріз `0.3.0` — `9175b73` (`origin/main`; `*-02.log` знято на `0e01996d4eb35858e9479e5cf8ec88dbfc65a94d`). **Хост / плати:** `Linux 7.0.0-42-generic x86_64`, жива плата `Digilent PYNQ-Z1` (`pynq2`, `192.168.68.69`), аналізатор `LOGICTRACER_PICO_0.5.0` (`/dev/ttyACM0`, `100 МГц`) та `Jetson AGX Orin J501` (`192.168.68.68`). **Бітстрім (`pipeline_egress.bit`, `4 045 747` байтів, SHA-256):** `7bfd5f5742334a7f08f2a290d5dde0a241e5bd06ced64c39d82e70021f30bbce` ([`raw/openxc7_egress_bitstream.sha256`](raw/openxc7_egress_bitstream.sha256)).
* **Критерії успіху (зафіксовано до виконання):** [#230](https://github.com/nick-fedchik/kuzmin-machine/issues/230), [#234](https://github.com/nick-fedchik/kuzmin-machine/issues/234), [#241](https://github.com/nick-fedchik/kuzmin-machine/issues/241), [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226) та перша інженерна передумова протоколу [EXP-GPU-01](../../../../Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-01/protocol.md).

---

## 1. Що не вдалося і обмеження

* **Фізичний Place & Route, бітстрім та натурна перевірка на `PYNQ-Z1 + RP2040 PIO` виконані у `0.3.0`, але макет `3.3V -> 1.8V` (`SN74AVC8T245`) ще не розпаяний (`Part of #226`):** у версії `0.3.0` виконано повний фізичний P&R `nextpnr-himbaechel` (`F_max = 101.67 МГц`, `PASS @ 100.00 MHz`), згенеровано бітстрім `pipeline_egress.bit` (`7bfd5f57...`), завантажено його на живу плату `pynq2` (`192.168.68.69`), захоплено серію з `399` каскадних імпульсів `JA2_COMMIT` (`MAX PW = 340 нс`) аналізатором `LOGICTRACER_PICO_0.5.0` @ `100 МГц` та проведено міжплатний експеримент `PYNQ-Z1 -> GbE -> Jetson AGX Orin J501` ($R = 5 \times 1\,000$ подій, див. [повний звіт EXP-GPU-01 Фаз 1–2, 4](../../../../Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-01/report-phase1-2-4-crossboard-egress.md)). Пряме осцилографування міжплатного дротового шлейфа `PMOD JB -> J501` залишається окремим монтажним кроком власника стенда після паяння перетворювача рівнів `SN74AVC8T245` за чеклістом §2.4 ([#247](https://github.com/nick-fedchik/kuzmin-machine/issues/247)).
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
4. **Паспортна характеристика `TXS0108E` (`SCES642L`, листопад 2024) проти односпрямованого тракту `SN74AVC8T245` (`SCES172`) для `3.3V -> 1.8V` (#247):**
   * PMOD-інтерфейси PYNQ-Z1 працюють у домені `3.3V LVCMOS`, тоді як лінії роз'єму розширення `Jetson AGX Orin J501` мають домен `1.8V`.
   * За актуальним даташитом Texas Instruments `TXS0108E` (`SCES642L`, November 2024):
     * у розділі *Switching Characteristics* (Table 5.11 для $V_{CCA} = 1.8\text{ V} \pm 0.15\text{ V}, V_{CCB} = 3.3\text{ V} \pm 0.3\text{ V}$ та Table 5.12 для $V_{CCA} = 2.5\text{ V}, V_{CCB} = 3.3\text{ V}$) максимальна паспортна швидкість у режимі Push-Pull становить **`60 Mbps`** (`30 МГц` тактової частоти з періодом `33.3 нс`; у розділі *Timing Requirements*, Table 5.7 для $V_{CCA} = 1.8\text{ V}, V_{CCB} = 3.3\text{ V}$ вказано `70 Mbps`), тоді як **`110 Mbps`** досягається лише для пари $V_{CCA} = 3.3\text{ V} \to V_{CCB} = 5.0\text{ V}$ (Table 5.9 / Table 5.13);
     * для режиму Open-Drain при $V_{CCA} = 1.8\text{ V}, V_{CCB} = 3.3\text{ V}$ максимальна швидкість за Table 5.11 становить **`0.8 Mbps`** (і до `1.2 Mbps` у заголовку документа для $3.3\text{ V} \to 5.0\text{ V}$);
     * **арифметичне розмежування режимів поточного RTL `km_pmod_event_egress.sv` (`100 Mbps` проти `50 Mbps`):** у поточному RTL як `SPI` (`50 МГц` `SCK` = `100 Mbps`), так і `PAR8` зі стробом `par_valid` / `par_clk` `50 МГц` (`10 нс` HIGH / `10 нс` LOW = еквівалент `100 Mbps` по лінії строба) **перевищують** паспортні `60 Mbps` (Table 5.11) / `70 Mbps` (Table 5.7) для пари `1.8V <-> 3.3V` на `TXS0108E`, тоді як лінії даних `par_data[7:0]` у режимі `PAR8` змінюються раз на `2` такти (`20 нс` на байт = `50 Mbps`, що вкладається у `60 Mbps`). Отже, для роботи через `TXS0108E` без перевищення паспорта знадобилося б або розтягнути фазу строба `PAR8` / дільник `SPI`, або перевірити фактичну форму фронту на стенді ([#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226)) з урахуванням ємності макетних дротів після закінчення імпульсу one-shot (`~10 нс` edge-rate accelerator + внутрішній `10 kΩ` pull-up);
     * тому вибір між наявним у лабораторії `TXS0108E` та буферизованим `SN74AVC8T245` формулюється як **інженерна гіпотеза та критерій перевірки для натурного HIL ([#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226))**, а не апріорний факт до осцилографування.
   * **Схемотехнічний чекліст увімкнення `SN74AVC8T245` (`SCES172`) для односпрямованого тракту `3.3V -> 1.8V`:**

| Сигнал / Шина | Підключення | Призначення та примітки |
| :--- | :--- | :--- |
| `VCCA` | `3.3V` (шини PMOD `JA/JB` плати `PYNQ-Z1`) | Живлення сторони A (вхідна сторона від ПЛІС Zynq-7000). |
| `VCCB` | `1.8V` (шини GPIO роз'єму розширення `Jetson AGX Orin J501`) | Живлення сторони B (вихідна сторона до приймача). |
| `DIR` (спільний для всіх 8 біт) | `HIGH` (`VCCA = 3.3V`, жорстко на шині живлення) | Оскільки у `SN74AVC8T245` пін `DIR` є спільним для всіх 8 каналів, уся мікросхема працює в одному напрямку `A -> B` (`3.3V -> 1.8V`). Для зустрічного сигналу `ext_ready_i` (`1.8V -> 3.3V`) обов'язково використовується окремий одноканальний транслятор (наприклад, `SN74AVC1T45` або окремий корпус), а не канал тієї ж мікросхеми `SN74AVC8T245`. |
| `/OE` (Output Enable, активний низький) | Резистор підтяжки `10 kΩ` до `VCCA (3.3V)` + керування від окремого виходу дозволу (`GPIO` або інвертованого сигналу `Power-Good` домену `VCCB 1.8V`) | За рекомендацією TI `SCES172`, підтяжка `10 kΩ` до `VCCA` гарантує стан `Hi-Z` під час ввімкнення/вимкнення живлення (`I_off` partial-power-down protection), а керуючий сигнал активно тягне `/OE` у `LOW` лише після стабілізації обох шин `VCCA` та `VCCB`. |
| Зовнішні підтяжки стробів (сторона B, `1.8V`) | Слабкі резистори підтяжки до землі (`pull-down 47..100 kΩ` на лініях стробів `par_valid` / `par_clk` та `pull-up` на `spi_cs_n` з боку приймача `1.8V`) | Запобігають плаванню ліній стробів у невизначеному стані, доки виходи `SN74AVC8T245` перебувають у `Hi-Z` (`/OE = HIGH` під час старту живлення). |

## 3. Результати

* **Симуляція `iverilog -g2012` / `vvp` ([`raw/sim-iverilog-02.log`](raw/sim-iverilog-02.log)):**
  * `km_pmod_event_egress_tb.sv`: `ALL KM_PMOD_EVENT_EGRESS SIMULATION TESTS PASSED`, `$finish` на `6095000 ps` (усі 6 тестів включно з колізіями `S_SPI_END` / `S_PAR_END`, першим тактом `S_IDLE`, багатотактовим `event_valid_i`, перевірками станів спокою, обрамлення CS/`par_valid_o` та setup/hold).
  * `kpol_bram_pipeline_pynq_z1_egress_top_tb.sv` (mock `PS7`/`BUFG`): `PASS: ALL PYNQ_Z1_EGRESS_TOP E2E TESTS PASSED`, `$finish` на `17670000 ps` — кадри `0x8d420000000000c9` (SPI, `cid=2, state=201`) та `0x84420000000000ca` (PAR8, `cid=2, state=202`).
* **Лінтер `Verilator 5.032` та pytest-обгортка ([`raw/pytest-egress-02.log`](raw/pytest-egress-02.log)):** `14 passed in 8.78s` — перевірено Python-оракул CRC-8 (модульний та E2E top), `verilator --lint-only -Wall` (для `km_pmod_event_egress` та `kpol_bram_pipeline_pynq_z1_egress_top`), `yosys synth_xilinx` (для обох модулів) і **усі 8 мутантів** (усі 8 очікувано впали у симуляції).
* **Логічний синтез XC7 топа `kpol_bram_pipeline_pynq_z1_egress_top` у `Yosys 0.52` ([`raw/yosys-synth-xc7-02.log`](raw/yosys-synth-xc7-02.log)):** `synth_xilinx` + `check` — `0 problems`, `5154` комірки (`1 RAMB36E1`, `162 CARRY4`, `1031 FDCE`, `2 FDPE`, `608 FDRE`, `1180 INV`, `LUT1..LUT6`, `16 MUXF7`, `8 MUXF8`, `1 BUFG`, `1 PS7`).
* **Відкритий апаратний потік ([`raw/open-flow-02.log`](raw/open-flow-02.log)):** `bash Engineering/hw/scripts/run_open_flow.sh` — `171 passed in 15.17s`, lint та синтез XC7 для `rtl/core` і `rtl/bus` завершилися з кодом `0`.
* **Фінальна перевірка пакета ([`raw/final-verification-02.log`](raw/final-verification-02.log)):** `KM_SKIP_LIVE_HIL=1 python3 -m pytest -q` (`387 passed, 1 skipped, 385 subtests passed`), `check_links.py` (`0` битих посилань), `check_wp_documents.py` (`153` документи, `0` помилок).
* **Фізичний Place & Route (`nextpnr-himbaechel`), STA @ 100 МГц та генерація бітстріму `pipeline_egress.bit` ([`build_bram_pipeline_egress.sh`](../../../hw/boards/pynq-z1/build_bram_pipeline_egress.sh), [`raw/openxc7_egress_yosys.log`](raw/openxc7_egress_yosys.log), [`raw/openxc7_egress_nextpnr.log`](raw/openxc7_egress_nextpnr.log), [`raw/openxc7_egress_nextpnr_report.json`](raw/openxc7_egress_nextpnr_report.json), [`raw/openxc7_egress_bitstream.sha256`](raw/openxc7_egress_bitstream.sha256)):**
  * Утилізація на `xc7z020clg400-1`: `SLICE_LUTX = 3 630 / 106 400 (3.41%)`, `SLICE_FFX = 1 524 / 106 400 (1.43%)`, `RAMB36E1 = 1 / 140 (0.71%)`, `CARRY4 = 155 / 13 300 (1.17%)`, `PAD = 26 / 392`.
  * Статичний таймінг: критичний шлях `9.84 нс` (`1.25 нс` логіки + `8.59 нс` трасування, запас `WNS = +0.164 нс`), досягнута частота **`F_max = 101.67 МГц` (`PASS @ 100.00 MHz`)**.
  * Бітстрім `pipeline_egress.bit` (`4 045 747` байтів, SHA-256 `7bfd5f5742334a7f08f2a290d5dde0a241e5bd06ced64c39d82e70021f30bbce`).
* **Натурна перевірка на кремнії `PYNQ-Z1` (`pynq2`) + захват `LOGICTRACER_PICO_0.5.0` @ `100 МГц` ([`raw/pynq2_egress_silicon_cascade.log`](raw/pynq2_egress_silicon_cascade.log), [`raw/logictracer_egress_ja2_100mhz.log`](raw/logictracer_egress_ja2_100mhz.log), [`raw/logictracer_egress_ja2_100mhz.json`](raw/logictracer_egress_ja2_100mhz.json), [`raw/logictracer_egress_ja2_100mhz.vcd`](raw/logictracer_egress_ja2_100mhz.vcd)):**
  * На живій платі `pynq2` (`192.168.68.69`) з бітстрімом `pipeline_egress.bit` верифіковано 4-концептний каскад `C0 -> C1 -> C2 -> C3` (`+4` коміти) та `Fail-Closed` відхилення (`+1` reject), а аналізатором `LOGICTRACER_PICO_0.5.0` (`/dev/ttyACM0`, `100 МГц`) зафіксовано `399` каскадних імпульсів `JA2_COMMIT` із шириною `MAX PW = 340 нс` (`3 * 80 нс + 100 нс = 34` такти @ `100 МГц`, `0` глітчів). Детальний аналіз міжплатного контуру `PYNQ-Z1 -> Jetson AGX Orin J501` ($R = 5 \times 1\,000$ подій) наведено у [звіті EXP-GPU-01 Фаз 1–2, 4](../../../../Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-01/report-phase1-2-4-crossboard-egress.md).

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
| 0.3.0 | 2026-11-17 | #226: виконано фізичний Place & Route та STA @ `100 МГц` топа `kpol_bram_pipeline_pynq_z1_egress_top.v` у стеку `OpenXC7` (`F_max = 101.67 МГц PASS`, `3 630 SLICE_LUTX`, `1 524 SLICE_FFX`, `1 RAMB36E1`), згенеровано бітстрім `pipeline_egress.bit` (`7bfd5f57...`), проведено живу перевірку на `pynq2` із захватом `LOGICTRACER_PICO_0.5.0` @ `100 МГц` (`399` імпульсів `JA2_COMMIT`, `340 нс`) та міжплатний контур `PYNQ-Z1 -> Jetson AGX Orin` ($R = 5 \times 1\,000$). |
| 0.2.2 | 2026-11-17 | Усунено зауваження рецензії PR #264 (`F1..F6`): наведено дані актуальної ревізії TI `SCES642L` (листопад 2024: Table 5.11 / 5.12 `60 Mbps` та Table 5.7 `70 Mbps` Push-Pull для `1.8V <-> 3.3V`, `0.8 Mbps` Open-Drain у Table 5.11, `110 Mbps` лише для `3.3V -> 5.0V` у Table 5.9 / 5.13), чітко розмежовано `100 Mbps` строба `PAR8` проти `50 Mbps` ліній даних, уточнено керування `/OE`, спільний `DIR` та зовнішні pull-down `47..100 kΩ` для `SN74AVC8T245`, а в `+commit_cid_audit` додано перевірку `hw_commit_cid_o == 6'd57` під час `reject` і перевірку back-to-back тригерів. |
| 0.2.1 | 2026-11-17 | Закрито знахідки [#247](https://github.com/nick-fedchik/kuzmin-machine/issues/247): уточнено паспортні характеристики `TXS0108E` як інженерну гіпотезу до HIL ([#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226)), додано табличний чекліст увімкнення `SN74AVC8T245` (`DIR`, `/OE`, `VCCA/VCCB`, power sequencing) та ізольований unit-тест із мутантним контролем для `hw_commit_cid_o` у `kpol_bram_pipeline_axi_tb.sv` / `test_kpol_bram_pipeline.py`. |
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
