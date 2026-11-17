# Звіт EXP-GPU-02 (Етапи 1–3, Issues #252, #253): Двобанковий RTL CFG-P-HA без torn-read, формальна SMT-верифікація, OpenXC7 Place & Route та бітстрім для PYNQ-Z1

* **Версія:** 0.2.0
* **Дата:** 2026-11-17
* **Тип WP редакції NG:** Report
* **Issue:** [#252](https://github.com/nick-fedchik/kuzmin-machine/issues/252), [#259](https://github.com/nick-fedchik/kuzmin-machine/issues/259), `Part of` [#253](https://github.com/nick-fedchik/kuzmin-machine/issues/253) (пов'язаний стендовий захват: [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226)). **PR:** [#258](https://github.com/nick-fedchik/kuzmin-machine/pull/258) (`0.1.0`), [#262](https://github.com/nick-fedchik/kuzmin-machine/pull/262) (`0.1.1`), оновлення `0.2.0` у гілці `exp/253-cfg-p-ha-openxc7-bitstream`.
* **Виконавець:** GitHub Copilot CLI (`0.1.0`, `0.1.1`, `0.2.0`). **Рецензент `0.1.0`:** `claude-sonnet-5.5` у [PR #258](https://github.com/nick-fedchik/kuzmin-machine/pull/258#issuecomment-6926646753) («Прийняти з зауваженнями», неблокувальні `N1..N5`); рецензія `0.2.0` очікується.
* **Базовий коміт:** `467cd4e` (`origin/main`; `0.1.1` виконано на `4079aa4`, `0.1.0` — на `41ac644e8da44a7463983a205012c1feea234728`). **Хост верифікації:** `Linux 7.0.0-42-generic x86_64` (`Icarus Verilog 12.0`, `Verilator 5.032`, `Yosys 0.52`, `OpenXC7 Yosys 0.69`, `nextpnr-himbaechel` + `fasm2frames`/`xc7frames2bit` для `xc7z020clg400-1`, `Z3 4.13.3`, `Python 3.14.4`). **Бітстрім (`kpol_pynq_ha.bit`, `4 045 751` байт, SHA-256):** `0796dba1b457d725e2a33b965fc220cc121459f271299ff472ebcbf2c7096e33` ([`openxc7_ha_bitstream.sha256`](../../data/exp-gpu-02-sim/openxc7_ha_bitstream.sha256); згенеровано й верифіковано після P&R без запису на живу плату `PYNQ-Z1`).
* **Критерії приймання (зафіксовані до виконання):** розділ 3 в [#252](https://github.com/nick-fedchik/kuzmin-machine/issues/252), розділи 2–3 в [#253](https://github.com/nick-fedchik/kuzmin-machine/issues/253), [протокол EXP-GPU-02](protocol.md) та [план EXP-GPU-02](plan.md). Зафіксоване розмежування: у версії `0.2.0` виконано синтез, фізичне трасування *Place & Route + STA* в `OpenXC7`, генерацію бітстріму `kpol_pynq_ha.bit` та топ-рівневу верифікацію пінів `PMOD JA`/`PMOD JB`; фізичне завантаження бітстріму на плату `PYNQ-Z1` та натурний захват трас `RP2040 PIO` залишено в [#253](https://github.com/nick-fedchik/kuzmin-machine/issues/253) до окремого дозволу на перепрошивання плати та завершення монтажу стенда.

---

## 1. Що не вдалося і обмеження

1. **Відсутність фізичного завантаження бітстріму на живу плату `PYNQ-Z1` та натурних осцилограм `RP2040 PIO` у версії `0.2.0` (`Part of #253`):**
   * У межах цього кроку створено топовий модуль [`kpol_bram_pipeline_pynq_z1_ha_top.v`](../../../../../Engineering/hw/boards/pynq-z1/kpol_bram_pipeline_pynq_z1_ha_top.v), файл фізичних обмежень [`kpol_bram_pipeline_ha.xdc`](../../../../../Engineering/hw/boards/pynq-z1/kpol_bram_pipeline_ha.xdc), виконано повне фізичне розміщення і трасування (`nextpnr-himbaechel --device xc7z020clg400-1 --router router2 --seed 1 --freq 100`), згенеровано бітстрім `kpol_pynq_ha.bit` (`4 045 751` байт, SHA-256 `0796dba1b457d725e2a33b965fc220cc121459f271299ff472ebcbf2c7096e33`) та перевірено потактову роботу виводів `ja1..ja4` і `jb1..jb4, jb7, jb8` у тестбенчі [`kpol_bram_pipeline_pynq_z1_ha_top_tb.sv`](../../../../../Engineering/hw/tests/kpol_bram_pipeline_pynq_z1_ha_top_tb.sv). Проте фізичне перепрошивання живої плати `PYNQ-Z1` та захват зовнішніх ліній `GP0..GP4` аналізатором `RP2040 PIO` не виконувалися і залишаються у відкритій частині [#253](https://github.com/nick-fedchik/kuzmin-machine/issues/253) до окремої авторизації перепрошивання плати та монтажу дротів `PMOD JB -> RP2040` (`AGENTS.md §4.2`).
2. **Після-трасувальна частота `F_max = 28.86 МГц` через комбінаційний каскад 256-бітного пріоритетного енкодера `dirty_next_w` у `nextpnr-himbaechel`:**
   * За звітом статичного аналізу таймінгу [`openxc7_ha_nextpnr_report.json`](../../data/exp-gpu-02-sim/openxc7_ha_nextpnr_report.json) та журналом [`openxc7_ha_nextpnr.log`](../../data/exp-gpu-02-sim/openxc7_ha_nextpnr.log) після повного трасування `2` блоків `RAMB36E1`, `5 934` `SLICE_LUTX` (`5.58%`) та `1 935` `SLICE_FFX` (`1.82%`) досягнута максимальна тактова частота становить `F_max = 28.86 МГц` (критичний шлях `34.651 нс`: `8.47 нс` логіки + `25.31 нс` трасування, негативний запас `WNS = -24.651 нс` відносно цільових `10.0 нс` @ `100.0 МГц`).
   * Критичний шлях проходить через однотактовий комбінаційний цикл пошуку першого зміненого слова `for (idx = 0; idx < 256; idx++)` у масці `dirty_next_w[255:0]` модуля `km_concept_bram_dual_ha.sv` (`> 25` послідовних рівнів `LUT6` для обчислення `next_dirty_addr_w`). Оскільки фонова досинхронізація `SYNC_READ -> SYNC_WRITE` виконується лише після гарячого патчу, для досягнення `F_max >= 100 МГц` у наступній ревізії RTL достатньо замінити 256-бітний пріоритетний скан на 8-бітний лічильник обходу зміненого концепту (`4` слова `cid * 4 .. cid * 4 + 3`) або двоступеневий конвеєризований деревоподібний енкодер `16 x 16`.
3. **Подвоєння Block RAM та зростання логічної площі відносно однобанкового `CFG-P`:**
   * За журналом синтезу [`yosys_xc7_cfg_p_ha.log`](../../data/exp-gpu-02-sim/yosys_xc7_cfg_p_ha.log) перехід від однобанкового `kpol_bram_pipeline_axi` (`CFG-P`) до двобанкового `kpol_bram_pipeline_axi_ha` (`CFG-P-HA`) збільшує використання блоків `RAMB36E1` із `1` (`0.71%` кристала `XC7Z020`) до `2` (`1.43%`), кількість тригерів `FDCE + FDRE` — із `1363` (`1.28%`) до `1897` (`1.78%`, приріст `+534` тригери за рахунок 256-бітної маски `dirty_word_q`, 64-бітної маски `shadow_w0_override_q` та регістрів `0x030..0x044`), а показник `Estimated number of LCs` — із `1750` (`3.29%`) до `3867` (`7.27%`). У повному топі плати [`kpol_bram_pipeline_pynq_z1_ha_top.v`](../../../../../Engineering/hw/boards/pynq-z1/kpol_bram_pipeline_pynq_z1_ha_top.v) (`OpenXC7 Yosys 0.69 -flatten -abc9`) оцінка становить `3 610` `Estimated LCs`, а після пакування в `nextpnr-himbaechel` — `5 934` `SLICE_LUTX` та `1 935` `SLICE_FFX`. Базовий `CFG-P` збережено без змін.
4. **Кінцеве вікно фонової досинхронізації між двома сусідніми гарячими патчами (`sync_busy_o == 1`) та поведінка AXI4-Lite під час `sync_busy` (`#259`, `N4`):**
   * Перемикання активного банку (`bank_swap_commit_o`) не додає жодного такту затримки до 8-тактового секвенсера подій (`0` stall-тактів), проте після перемикання фоновий автомат `Port A` копіює змінені слова з нового активного банку в новий тіньовий банк за `2 * K` тактів (`6` тактів = `60 нс` при оновленні правил `W1..W3`, `8` тактів = `80 нс` при оновленні `W0..W3`). Протягом інтервалу `swap_pending_o || sync_busy_o` нові транзакції запису на `0x030..0x038` повертають `AXI_RESP_SLVERR`; програмний інжектор має опитувати біти `[2:1]` регістра `0x038` перед відправленням наступного пакета.
   * Спроба запису з повним стробом (`wstrb == 4'hf`) у read-only регістри телеметрії `0x03C` (`SWAP_COUNT`), `0x040` (`LAST_SWAP_WAIT_CYCLES`) та `0x044` (`SEQ_EXEC_MONITOR`) потрапляє в гілку `default` декодера запису й повертає `AXI_RESP_DECERR` (`2'b11`) без зміни стану; будь-який запис із неповним байтовим стробом (`wstrb != 4'hf`) на будь-яку адресу повертає `AXI_RESP_SLVERR` (`2'b10`).
   * Читання (`arvalid`) регістрів даних Block RAM `0x008` (`BRAM_DATA`) або `0x034` (`SHADOW_DATA`) під час `sync_busy_o == 1` приймає адресу в `read_pending`, але утримує `rvalid == 0` до звільнення `Port A` (`!sync_busy && !bram_we && !shadow_we`), затримуючи відповідь читання до `2 * K` тактів (`K <= 256` брудних слів, максимум `512` тактів = `5.12 мкс` @ `100 МГц`, без внутрішнього апаратного таймауту). Натомість читання статусних і телеметричних регістрів (`0x000`, `0x014..0x030`, `0x038..0x044`) не звертається до `Port A` і завершується за `1` такт навіть під час `sync_busy_o == 1`.
5. **Параметричний масштаб формальної SMT-моделі та розрядність зрізу в 30-тактовому BMC `H3` (`#259`, `N2`):**
   * Формальний доказ `Z3` (`H1..H7`, `C1..C4`, мутанти `M1..M5`) виконано на параметризованій конфігурації того самого RTL-модуля верхнього рівня `kpol_bram_pipeline_axi_ha` за `NUM_CONCEPTS = 4, QUEUE_DEPTH = 4, DATA_WIDTH = 32, ADDR_WIDTH = 4` (`16` слів на банк) для скінченної розмірності простору станів солвера.
   * Повна 32-бітна розрядність даних дескриптора (`DATA_WIDTH = 32`, усі `128` біт `{W3, W2, W1, W0}` без `cutpoint`) у властивостях `H1..H7` та `H6b` доведена базою `bmc t=3` і необмеженою $k$-індукцією `ind t=2`. Окремий допоміжний 30-тактовий прогін `H2_H3_safety_bmc` (`bmc t=30`) виконується з `cutpoint` виходів `CME` на **1-бітному зрізі даних на слово** (`WOLPER_1BIT_SLICE`: перевіряється біт `[0]` кожного зі слів `W0..W3`, оскільки тракт комутації та читання `km_concept_bram_dual_ha` побітово симетричний і не виконує арифметичних чи міжбітових операцій над вмістом дескриптора).
   * Повнорозмірна конфігурація `NUM_CONCEPTS = 64, QUEUE_DEPTH = 16, ADDR_WIDTH = 8` (`256` слів на банк) перевірена статичним лінтом `Verilator`, синтезом `Yosys XC7` та симуляцією `10 003` перемикань (`43 460` подій) у `Icarus Verilog`.

---

## 2. Метод та архітектура CFG-P-HA (B4 Варіант 2)

1. **Двобанкова обгортка дескрипторів [`km_concept_bram_dual_ha.sv`](../../../../../Engineering/hw/rtl/core/km_concept_bram_dual_ha.sv):**
   * Інстанціює два незмінні екземпляри [`km_concept_bram.sv`](../../../../../Engineering/hw/rtl/core/km_concept_bram.sv) (`bank0` та `bank1`), не модифікуючи жодного з базових файлів `CFG-P`.
   * Початкове завантаження (`a_shadow_only_i == 0` при неактивному конвеєрі) синхронно записує слова в `Port A` обох банків.
   * Гаряча інжекція (`a_shadow_only_i == 1`, дозволена при `busy == 1`, коли `swap_pending_o == 0` і `sync_busy_o == 0`) пише лише в `Port A` тіньового банку та виставляє біт `dirty_word_q[a_addr_i]`. Якщо записуються лише правила `W1..W3`, біт `shadow_w0_override_q[cid]` залишається нульовим і всі коміти живого стану `W0` з `Port B` секвенсера дзеркалюються одночасно в обидва банки. Якщо хост явно записує `W0` (`a_addr_i[1:0] == 2'b00`), виставляється `shadow_w0_override_q[cid]`, що захищає підготовлене ініціалізаційне значення в тіньовому банку від перезапису старими подіями до моменту перемикання.
   * Сигнал запису в `Port B` тіньового банку блокується при одночасному зверненні `Port A` тіньового банку до тієї самої адреси, що виключає на рівні логіки керування портами міжпортову колізію (`collision_detected_o == 0`).
   * Перемикання `active_bank_q` виконується строго у такт `seq_at_idle_boundary_i == 1` (`ST_IDLE`), коли всі чотири слова попередньої події вже вичитані зі старого банку, а адреса `W0` нової події буде засемпльована регістрами Block RAM на наступному фронті вже з нового активного банку. Після перемикання скінченний автомат `SYNC_READ -> SYNC_WRITE` на вільних портах `Port A` переносить змінені слова в новий тіньовий банк з урахуванням пріоритету свіжіших записів `Port B`.
2. **Шинний інтегратор AXI4-Lite [`kpol_bram_pipeline_axi_ha.sv`](../../../../../Engineering/hw/rtl/bus/kpol_bram_pipeline_axi_ha.sv):**
   * Зберігає карту регістрів `0x000..0x02C` базового `CFG-P` (регістр `0x000` повертає `0x4B504841` — ASCII `"KPHA"`) і додає регістри онлайн-оновлення та внутрішньокристальної метрології:
     * `0x030` (`SHADOW_ADDR`) — адреса слова `0..255` у тіньовому банку (дозволено при `busy == 1`);
     * `0x034` (`SHADOW_DATA`) — запис слова в тіньовий банк із автоінкрементом `shadow_addr` та діагностичне читання тіньового банку (дозволено при `busy == 1` без блокування `hw_trigger_ready_o`; при читанні під час `sync_busy == 1` очікує завершення фонового копіювання `Port A`);
     * `0x038` (`BANK_SWAP_CTRL`) — запит перемикання банку при записі `1` та читання статусу `{28'b0, collision_detected, sync_busy, swap_pending, active_bank}`;
     * `0x03C` (`SWAP_COUNT`, read-only; запис повертає `DECERR`) — лічильник виконаних імпульсів `bank_swap_commit_o`;
     * `0x040` (`LAST_SWAP_WAIT_CYCLES`, read-only; запис повертає `DECERR`) — кількість тактів очікування від прийняття `swap_req` до перемикання;
     * `0x044` (`SEQ_EXEC_MONITOR`, read-only; запис повертає `DECERR`) — у `[15:0]` тривалість останньої події секвенсера в тактах (норма `8`), у `[31:16]` лічильник відхилень від `8` тактів (норма `0`).
   * Містить зовнішній 3-бітний lockstep-детектор фази секвенсера `seq_phase_q` та п'ять діагностичних виходів протоколу `EXP-GPU-02`: `inject_strobe_o`, `bank_swap_commit_o`, `stimulus_accepted_o`, `reaction_out_o`, `seq_cycle_done_o`.
3. **Програмний інжектор правил [`rule_injector.py`](rule_injector.py):**
   * Формує 16-байтні кадри оновлення правил `W1..W3` (`4` байти заголовка з `CRC-8/CCITT` + `12` байтів корисного навантаження) або 20-байтні кадри повного дескриптора `W0..W3` (`4 + 16` байтів), перевіряє контрольну суму й допустимість опкодів CME, генерує послідовність транзакцій AXI4-Lite (`0x030`, `0x034`, `0x038`) і містить побітову еталонну модель `DualBankCfgPHAModel`.

---

## 3. Результати

### 3.1. Порівняльний логічний синтез `Yosys synth_xilinx -arch xc7`

Джерело первинних даних: [`yosys_xc7_cfg_p_ha.log`](../../data/exp-gpu-02-sim/yosys_xc7_cfg_p_ha.log) (інструмент `Yosys 0.52`, цільова архітектура `Xilinx 7-series xc7`, перевірка `hierarchy -check` та `check` — `0` помилок; лінт `Verilator 5.032 -Wall` на `km_concept_bram_dual_ha.sv` — `0` попереджень).

| Показник ресурсів (`XC7Z020`) | Базовий `CFG-P` (`kpol_bram_pipeline_axi`) | Двобанковий `CFG-P-HA` (`kpol_bram_pipeline_axi_ha`) | Різниця (`CFG-P-HA - CFG-P`) | Частка від `XC7Z020` для `CFG-P-HA` |
|---|---:|---:|---:|---:|
| Блоки пам'яті `RAMB36E1` (усього `140`) | `1` | `2` | `+1` | `1.43%` |
| `Estimated number of LCs` (усього `53 200` LUT) | `1750` | `3867` | `+2117` | `7.27%` |
| Тригери `FDCE + FDRE` (усього `106 400` FF) | `1363` (`755 + 608`) | `1897` (`1289 + 608`) | `+534` | `1.78%` |
| Каскади переносу `CARRY4` (усього `13 300`) | `111` | `149` | `+38` | `1.12%` |

### 3.2. Формальна SMT-верифікація (`yosys-smtbmc + Z3 4.13.3`) та мутантні контролі

Джерела первинних даних: [`cfg_p_ha_formal_results.csv`](formal/raw/cfg_p_ha_formal_results.csv), [`cfg_p_ha_formal_provenance.json`](formal/raw/cfg_p_ha_formal_provenance.json) та журнали `formal/raw/*.log` і контрприклади `formal/raw/M*.vcd` за параметрів `NUM_CONCEPTS = 4, QUEUE_DEPTH = 4, DATA_WIDTH = 32, ADDR_WIDTH = 4` (блок індуктивних інваріантів `FORMAL_INDUCTION` містить `0` операторів `assume`).

| Модель / перевірка | Формальний режим (`yosys-smtbmc + Z3`) | Статус | Час (`с`) | Спрацювання / досягнуті цілі |
|---|---|---|---:|---|
| `original (CFG-P-HA)`: `H1_H6_base_bmc` | Конкретна 32-бітна база індукції `bmc t=3` | `PASSED` | `0.540` | `H1..H7 + H6b + INV_*` |
| `original (CFG-P-HA)`: `H1_H6_safety_ind` | Необмежена 32-бітна $k$-індукція `ind t=2` | `PASSED` | `131.466` | `H1..H7 + H6b` для всіх $t \ge 0$ |
| `original (CFG-P-HA)`: `H1_H2_H4_H5_safety_bmc` | 30-тактовий `bmc t=30` (з `cutpoint` виходів CME) | `PASSED` | `10.509` | `H1, H2, H4, H5` |
| `original (CFG-P-HA)`: `H2_H3_safety_bmc` | 30-тактовий `bmc t=30` (1-бітний зріз даних на слово `W0..W3`) | `PASSED` | `7.223` | `H2, H3_no_torn_descriptor_read` |
| `original (CFG-P-HA)`: `cover_non_vacuity` | Пошук невакуумних свідків `cover t=30` | `PASSED` | `154.487` | `C1, C2, C3, C4_b_we_at_swap` досягнуто |
| `M1_unsafe_immediate_swap` | Конкретний `bmc t=18` | `FAILED` | `2.737` | `H3_no_torn_descriptor_read` (`M1_unsafe_immediate_swap.vcd`) |
| `M2_write_active_bank_while_busy` | Конкретний `bmc t=16` | `FAILED` | `1.559` | `H3_no_torn_descriptor_read` (`M2_write_active_bank_while_busy.vcd`) |
| `M3_drop_w0_mirror` | Конкретний `bmc t=20` | `FAILED` | `29.655` | `H6_live_state_preserved` (`M3_drop_w0_mirror.vcd`) |
| `M4_block_trigger_on_shadow` | Конкретний `bmc t=10` | `FAILED` | `0.644` | `H4_zero_sequencer_stall` (`M4_block_trigger_on_shadow.vcd`) |
| `M5_skip_port_a_resync` | Конкретний `bmc t=20` | `FAILED` | `7.724` | `H7_multi_patch_rule_persistence` (`M5_skip_port_a_resync.vcd`) |

* **Формально доведені властивості на незміненому `CFG-P-HA` (`Status: PASSED`):**
  * `H1_lockstep_phase` — зовнішній детектор `seq_phase_q` дорівнює `sequencer.state_q[2:0]` у кожному такті;
  * `H2_zero_bram_collision` — `collision_detected == 0` на обох банках за довільних одночасних AXI-записів, фонової досинхронізації та комітів `Port B`;
  * `H3_no_torn_descriptor_read` — на такті оцінки `cme_event_valid` усі чотири слова дескриптора `{W3, W2, W1, W0}` збігаються з атомарним знімком одного банку на вході `ST_REQ_W0` і не змішують слова різних поколінь (повна 32-бітна версія доведена `bmc t=3` + `ind t=2`; 30-тактовий BMC виконано на 1-бітному зрізі біта `[0]` кожного слова `W0..W3`);
  * `H4_zero_sequencer_stall` — кожна подія триває рівно `8` тактів (`seq_anomaly_count_q == 0`), а `hw_trigger_ready_o` не блокується записами у тіньовий банк (`0x030..0x038`);
  * `H5_bounded_swap_latency` — час очікування від прийняття `swap_req` до імпульсу `bank_swap_commit_o` становить від `1` до `8` тактів;
  * `H6_live_state_preserved`, `H6b_banks_identical_after_resync` та `H7_multi_patch_rule_persistence` — живі стани `W0` зберігаються під час перемикання банків, після завершення фонової досинхронізації (`sync_busy_o == 0, dirty_word_q == 0`) обидва банки побітово тотожні на всіх `16` словах, а при серії послідовних часткових патчів різних концептів правила `W1..W3` попередніх патчів не втрачаються;
  * Невакуумні свідки досяжності (`cover_non_vacuity`): досягнуто всі чотири цілі `C1_full_online_update_lifecycle` (крок `27`), `C2_swap_after_pending_wait` (крок `11`), `C3_back_to_back_events_across_swap` (крок `3`) та `C4_b_we_at_swap` (`obs_b_we && obs_swap_commit_w`, крок `14` у [`orig_cover.log`](formal/raw/orig_cover.log)). Примітка щодо фазування строба (`#259`, `N3`): фактичний запис `b_we == 1` і перемикання `active_bank_q <= ~active_bank_q` (`swap_commit_w == 1`) відбуваються на одному фронті такту в стані `ST_IDLE`, тоді як зовнішній вихід `bank_swap_commit_o` є однотактовим регістровим стробом `bank_swap_commit_q` після `ST_IDLE`, на якому `b_we` вже дорівнює `0` (доведено інваріантом `INV_swap_pulse_after_idle: !bank_swap_commit_o || !obs_b_we`).
* **Перевірка чутливості на мутантах (`AGENTS.md §4.1`, усі п'ять відхилені солвером `Z3` зі збереженням `.vcd`):**
  * `M1_unsafe_immediate_swap` (негайне перемикання без очікування `seq_at_idle_boundary_i`) — `FAILED` на властивості `H3_no_torn_descriptor_read` ([`M1_unsafe_immediate_swap.vcd`](formal/raw/M1_unsafe_immediate_swap.vcd));
  * `M2_write_active_bank_while_busy` (спрямування гарячого запису в `active_bank_q` замість тіньового банку) — `FAILED` на властивості `H3_no_torn_descriptor_read` ([`M2_write_active_bank_while_busy.vcd`](formal/raw/M2_write_active_bank_while_busy.vcd));
  * `M3_drop_w0_mirror` (вимкнення дзеркалювання `b_we_i` у тіньовий банк) — `FAILED` на властивості `H6_live_state_preserved` ([`M3_drop_w0_mirror.vcd`](formal/raw/M3_drop_w0_mirror.vcd));
  * `M4_block_trigger_on_shadow` (блокування `hw_trigger_ready_o` сигналом `shadow_we`) — `FAILED` на властивості `H4_zero_sequencer_stall` ([`M4_block_trigger_on_shadow.vcd`](formal/raw/M4_block_trigger_on_shadow.vcd));
  * `M5_skip_port_a_resync` (`#259`, `N1`: очищення `dirty_word_q` на `swap_commit_w` без запуску `SYNC_READ -> SYNC_WRITE`) — `FAILED` на властивості `H7_multi_patch_rule_persistence` ([`M5_skip_port_a_resync.vcd`](formal/raw/M5_skip_port_a_resync.vcd): на другому частковому патчі іншого концепту активний банк повертається до застарілого правила з-перед першого патчу).

### 3.3. Потактова RTL-симуляція Фаз 1–4 та серії `10 000` гарячих перемикань (`Icarus Verilog`)

Джерела первинних даних (явно позначені `evidence_kind: "rtl_simulation_iverilog"`, `not_physical_hil: true`): [`exp_gpu_02_sim_10k_swaps_summary.json`](../../data/exp-gpu-02-sim/exp_gpu_02_sim_10k_swaps_summary.json), [`exp_gpu_02_sim_timing.csv`](../../data/exp-gpu-02-sim/exp_gpu_02_sim_timing.csv), [`exp_gpu_02_sim_phases1_4.vcd`](../../data/exp-gpu-02-sim/exp_gpu_02_sim_phases1_4.vcd), [`iverilog_10k_swaps.log`](../../data/exp-gpu-02-sim/iverilog_10k_swaps.log).

1. **Відтворення Фаз 1–4 протоколу `EXP-GPU-02` на Концепті 5 (`CID = 5`):**
   * **Фаза 1 (Bank 0, правило $X \ge 100$):** подія $X = 50$ відхилена рівно за `8` тактів (`80 нс` номінального часу ядра @ `100 МГц`, `W0 = 0`); подія $X = 120$ зафіксована за `8` тактів (`W0 = 1`).
   * **Фази 2–3 (потік `1 МГц` = `1 подія / 100 тактів` + інжекція $X \ge 40$ у Bank 1):** під час активного конвеєра (`busy == 1`) прямий запис у базовий регістр `0x008` та частковий строб `wstrb = 0x3` коректно відхилені з `SLVERR`, тоді як запис правила $X \ge 40$ через `0x030`/`0x034` та команда `0x038 = 1` на фазі `seq_phase_q == 2` прийняті з `OKAY` без зняття `hw_trigger_ready_o`; перемикання `BANK_SWAP_COMMIT` відбулося за `6` тактів очікування межі `ST_IDLE`, показник `SEQ_EXEC_MONITOR` дорівнює `0x00000008` (`0` аномалій, `8` тактів на подію).
   * **Фаза 4 (перевірка реакції після перемикання + back-to-back потік `12.5 МГц`):** перша ж подія з параметром $X = 50$ після `BANK_SWAP_COMMIT` дала `REACTION_OUT == 1` рівно за `8` тактів зі збереженням і нарощенням живого лічильника стану `W0` (`3 -> 4`), після чого виконано ще `2` гарячі перемикання під безперервним потоком `1 подія / 8 тактів` (`12.5 МГц`) із `0` stall-тактів.
2. **Підсумки стрес-серії `10 000` гарячих перемикань (`total_bank_swaps = 10 003`, `468 523` такти симуляції):**
   * Оброблено подій: `43 460` (`24 763` комітів, `18 697` відхилень) на концептах `CID 0..7`, включно з `9 000` оновленнями правил `12 Б` (`W1..W3`) та `1 000` повними перезаписами `16 Б` (`W0..W3`);
   * Випадків `torn-read`: `0` (`torn_read_errors = 0`);
   * Розбіжностей із незалежною еталонною моделлю: `0` (`golden_mismatch_count = 0`, плюс фінальна звірка всіх `256` слів `bank0 == bank1 == golden`);
   * Додаткових тактів простою секвенсера: `0` (`seq_stall_anomaly_count = 0`, `last_seq_exec_cycles = 8`);
   * Колізій портів Block RAM та втрачених подій: `0` (`bram_collision_count = 0`, `events_dropped_count = 0`, `ready_drop_on_shadow_count = 0`);
   * Розподіл часу очікування перемикання `LAST_SWAP_WAIT_CYCLES` на `10 000` стрес-перемиканнях: мінімум `1` такт, максимум `8` тактів, середнє `4.0083` такти (`40 083 / 10 000`), гістограма за тактами `1..8`: `{1: 2621, 2: 1004, 3: 751, 4: 1183, 5: 1247, 6: 1001, 7: 1316, 8: 877}`;
   * Лічильник одночасного запису `Port B` і перемикання банку в одному такті (`b_we && swap_commit_w`, `#259`, `N3`, журнал [`sim_c4_b_we_at_swap.log`](formal/raw/sim_c4_b_we_at_swap.log)): `4 678` збігів із `10 003` перемикань (`4 629` без `shadow_w0_override_q` із дзеркалюванням `W0` у обидва банки та `49` із активним `shadow_w0_override_q` із збереженням підготовленого `W0` у новому активному банку), `0` розбіжностей із еталонною моделлю.

### 3.4. Фізичне трасування *Place & Route + STA* (`OpenXC7`), бітстрім `kpol_pynq_ha.bit` та топ-рівнева верифікація `PMOD JB` (`Part of #253`)

Джерела первинних даних: топовий модуль [`kpol_bram_pipeline_pynq_z1_ha_top.v`](../../../../../Engineering/hw/boards/pynq-z1/kpol_bram_pipeline_pynq_z1_ha_top.v), обмеження пінів [`kpol_bram_pipeline_ha.xdc`](../../../../../Engineering/hw/boards/pynq-z1/kpol_bram_pipeline_ha.xdc), скрипт збірки [`build_bram_pipeline_ha.sh`](../../../../../Engineering/hw/boards/pynq-z1/build_bram_pipeline_ha.sh), тестбенч [`kpol_bram_pipeline_pynq_z1_ha_top_tb.sv`](../../../../../Engineering/hw/tests/kpol_bram_pipeline_pynq_z1_ha_top_tb.sv), журнали [`openxc7_ha_yosys.log`](../../data/exp-gpu-02-sim/openxc7_ha_yosys.log), [`openxc7_ha_nextpnr.log`](../../data/exp-gpu-02-sim/openxc7_ha_nextpnr.log), звіт трасування [`openxc7_ha_nextpnr_report.json`](../../data/exp-gpu-02-sim/openxc7_ha_nextpnr_report.json) та контрольна сума бітстріму [`openxc7_ha_bitstream.sha256`](../../data/exp-gpu-02-sim/openxc7_ha_bitstream.sha256).

1. **Мапінг сигналів протоколу `EXP-GPU-02` на фізичні виводи `PMOD JA` та `PMOD JB` (`3.3V LVCMOS33`):**
   * На роз'ємі `PMOD JA` збережено штатні контакти стенда: `ja1` (`Y18`, вхід зовнішнього тригера з 2-FF CDC та детектором фронту), `ja2` (`Y19`, розтягнутий імпульс `commit` `10` тактів = `100 нс`), `ja3` (`Y16`, розтягнутий імпульс `reject` `10` тактів = `100 нс`), `ja4` (`Y17`, індикатор `pipeline_busy`).
   * На роз'єм `PMOD JB` виведено `5` нерозтягнутих однотактових (`10 нс` @ `100 МГц`) стробів для прямого підключення каналів `GP0..GP4` логічного аналізатора `RP2040 PIO` та сигнал рівня активного банку:
     * `jb1` (`W14`, Pin 1) = `inject_strobe_o` (`GP0`: `INJECT_STROBE`);
     * `jb2` (`Y14`, Pin 2) = `bank_swap_commit_o` (`GP1`: `BANK_SWAP_COMMIT`);
     * `jb3` (`T11`, Pin 3) = `stimulus_accepted_o` (`GP2`: `STIMULUS_EVENT`);
     * `jb4` (`T10`, Pin 4) = `reaction_out_o` (`GP3`: `REACTION_OUT`);
     * `jb7` (`V16`, Pin 7) = `seq_cycle_done_o` (`GP4`: `SEQ_CYCLE_DONE`);
     * `jb8` (`W16`, Pin 8) = `active_bank_o` (рівень активного банку `0`/`1`, що синхронно інвертується на кожному імпульсі `bank_swap_commit_o`).
2. **Підсумки синтезу `OpenXC7 Yosys 0.69`, трасування `nextpnr-himbaechel` та збірки бітстріму на `xc7z020clg400-1`:**

| Показник (`kpol_bram_pipeline_pynq_z1_ha_top`, `xc7z020clg400-1`) | Значення | Доступно на кристалі | Частка / примітка |
|---|---:|---:|---|
| Оцінні комірки `Yosys Estimated LCs` (`-flatten -abc9`) | `3 610` | `53 200` | `6.79%` ([`openxc7_ha_yosys.log`](../../data/exp-gpu-02-sim/openxc7_ha_yosys.log)) |
| Фізичні `SLICE_LUTX` після пакування `nextpnr` | `5 934` | `106 400` | `5.58%` ([`openxc7_ha_nextpnr_report.json`](../../data/exp-gpu-02-sim/openxc7_ha_nextpnr_report.json)) |
| Фізичні тригери `SLICE_FFX` (`1326 FDCE + 608 FDRE + 1 FDPE`) | `1 935` | `106 400` | `1.82%` |
| Блоки пам'яті `RAMB36E1` (`bank0` + `bank1`) | `2` | `140` | `1.43%` (`RAMB18E1 = 0`) |
| Каскади швидкого переносу `CARRY4` | `178` | `13 300` | `1.34%` |
| Мультиплексори `SELMUX2_1` (`18 MUXF7 + 8 MUXF8`) | `26` | `40 700` | `0.06%` |
| Примітиви `PS7` / `BUFGCTRL` / фізичні порти `PAD` | `1` / `1` / `20` | `1` / `32` / `392` | `7` `IOB33_INBUF_EN` + `13` `IOB33_OUTBUF` |
| Досягнута частота `F_max` (`clk`, ціль `100.00 МГц`) | `28.86 МГц` | `100.00 МГц` | Критичний шлях `34.651 нс` (`8.47 нс` логіка + `25.31 нс` трасування, `0` порушень трасування `overused = 0`) |
| Згенерований бітстрім `kpol_pynq_ha.bit` | `4 045 751` Б | — | SHA-256: `0796dba1b457d725e2a33b965fc220cc121459f271299ff472ebcbf2c7096e33` |

3. **Топ-рівнева верифікація пінів `PMOD JA` / `PMOD JB` та мутантні контролі (`kpol_bram_pipeline_pynq_z1_ha_top_tb.sv`):**
   * У потактовій симуляції [`kpol_bram_pipeline_pynq_z1_ha_top_tb.sv`](../../../../../Engineering/hw/tests/kpol_bram_pipeline_pynq_z1_ha_top_tb.sv) (явно позначеній `evidence_kind = "rtl_top_simulation_iverilog"`, не живий захват `RP2040 PIO`) перевірено проходження всіх 4 фаз `EXP-GPU-02` через фізичний вхід `ja1` (через 2-FF CDC) і транзакції `PS7 AXI4-Lite GP0` (`0x4000_0030`, `0x4000_0034`, `0x4000_0038`): кожен імпульс на `jb1..jb4, jb7` має ширину рівно `1` такт (`10 нс`), інтервал `jb3 (STIMULUS_EVENT) -> jb7 (SEQ_CYCLE_DONE)` дорівнює рівно `8` тактів на всіх подіях до і після перемикання, імпульси на `ja2`/`ja3` розтягнуті рівно на `10` тактів (`100 нс`), а лінія `jb8` (`active_bank_o`) перемикається `0 -> 1 -> 0` строго на наступному такті після строба `jb2` (`BANK_SWAP_COMMIT`).
   * Додано `3` мутантні контролі мапінгу пінів топового модуля в `test_exp_gpu_02_cfg_p_ha.py` (`stuck_jb2_zero`, `swapped_jb1_jb2`, `stuck_jb8_zero`): усі три детерміновано відхиляються тестбенчем із `[FAIL]`.

---

## 4. Перевірка гіпотези та критеріїв

| Критерій ([#252](https://github.com/nick-fedchik/kuzmin-machine/issues/252), [#253](https://github.com/nick-fedchik/kuzmin-machine/issues/253), [протокол EXP-GPU-02](protocol.md)) | Очікувано | Отримано (Етапи 1–3: RTL / SMT / OpenXC7 P&R + Бітстрім) | Висновок |
| :--- | :--- | :--- | :--- |
| Відсутність `torn-read` чотирьох слів дескриптора `W0..W3` | `0` випадків | `0` у формальному доказі `Z3` (`H3_no_torn_descriptor_read`) та `0` на `43 460` подіях і `10 003` перемиканнях у `iverilog` | Підтверджено на рівні RTL/SMT |
| Відсутність колізій портів A/B Block RAM | `collision_detected == 0` | `0` у формальному доказі `Z3` (`H2_zero_bram_collision`) та `0` у симуляції `468 523` тактів | Підтверджено на рівні RTL/SMT |
| Відсутність додаткових stall-тактів секвенсера та блокування `hw_trigger_ready_o` | Рівно `8` тактів на подію (`0` аномалій) | `8` тактів на всіх `43 460` подіях (`seq_stall_anomaly_count = 0`), доведено в `Z3` (`H4_zero_sequencer_stall`) | Підтверджено на рівні RTL/SMT |
| Верхня межа очікування перемикання банку від `swap_req` | `1..8` тактів (`<= 80 нс` @ `100 МГц`) | Доведено в `Z3` (`H5_bounded_swap_latency`), у симуляції `10 000` перемикань діапазон `1..8` тактів (середнє `4.01`) | Підтверджено на рівні RTL/SMT |
| Збереження живого стану `W0` через перемикання правил `W1..W3` | Без втрати лічильника `W0` | Доведено в `Z3` (`H6_live_state_preserved`), підтверджено на Фазі 4 (`W0: 3 -> 4`) та `10 003` перемиканнях | Підтверджено на рівні RTL/SMT |
| Чутливість тестів до дефектів (`AGENTS.md §4.1`) | Відхилення мутантів солвером і тестбенчем | `5/5` мутантів `M1..M5` відхилені в `Z3`; мутант негайного swap у `iverilog`, `3/3` мутанти пінів `PMOD JB` у топ-тестбенчі та пошкоджені `CRC-8`/опкоди в `pytest` відхилені | Підтверджено |
| Топовий модуль, XDC, P&R та бітстрім `OpenXC7` (`Part of #253`) | `2 x RAMB36E1`, `1 x PS7`, `1 x BUFG`, валідний `.bit` та виводи `JB1..JB4, JB7, JB8` | Трасування завершено з `0` порушень (`5 934` `SLICE_LUTX`, `1 935` `SLICE_FFX`, `2` `RAMB36E1`, `F_max = 28.86 МГц`), згенеровано `kpol_pynq_ha.bit` (`4 045 751` Б, SHA-256 `0796dba1...`) | Виконано (P&R та `.bit`; `F_max` обмежено комбінаційним сканом `dirty_next_w`) |
| Фізичне прошивання `PYNQ-Z1` та натурна осцилограма `RP2040 PIO` (`<= 1 LSB`) | Живий захват `GP0..GP4` на стенді | Не виконувалося без окремої авторизації перепрошивання плати та монтажу дротів `RP2040 PIO`; залишено у відкритій частині [#253](https://github.com/nick-fedchik/kuzmin-machine/issues/253) | Очікує фізичного стенда в #253 |

---

## 5. Відтворення

```bash
# 1. Лінт Verilator та логічний синтез Yosys XC7 (CFG-P та CFG-P-HA)
bash Engineering/hw/scripts/run_open_flow.sh

# 2. Збірка фізичного бітстріму OpenXC7 (Yosys 0.69 + nextpnr-himbaechel + prjxray) для PYNQ-Z1
BUILD_DIR="$PWD/.build_ha_bit" bash Engineering/hw/boards/pynq-z1/build_bram_pipeline_ha.sh

# 3. Повна формальна SMT-верифікація Z3 (база, k-індукція, BMC t=30, Cover C1..C4, мутанти M1..M5)
python3 Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-02/formal/run_cfg_p_ha_formal.py

# 4. Генерація пакета оновлення правила CID=5 (X >= 40) із CRC-8 та транзакцій AXI4-Lite
python3 Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-02/rule_injector.py --cid 5 --threshold-ge 40

# 5. Автоматизований тестовий набір EXP-GPU-02 (інжектор, жива симуляція ядра й топу, мутанти, артефакти SMT/OpenXC7)
python3 -m pytest -v Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-02/tests/test_exp_gpu_02_cfg_p_ha.py
```

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.2.0 | 2026-11-17 | `Part of #253`: створено топовий модуль `kpol_bram_pipeline_pynq_z1_ha_top.v`, XDC `kpol_bram_pipeline_ha.xdc` та скрипт `build_bram_pipeline_ha.sh`; виконано P&R і STA у `OpenXC7` (`5 934` `SLICE_LUTX`, `1 935` `SLICE_FFX`, `2` `RAMB36E1`, `F_max = 28.86 МГц`) і згенеровано бітстрім `kpol_pynq_ha.bit` (`0796dba1...`); додано топ-тестбенч `kpol_bram_pipeline_pynq_z1_ha_top_tb.sv` і `3` мутантні тести пінів `PMOD JB`. |
| 0.1.1 | 2026-11-16 | Доопрацювання за неблокувальними знахідками `N1..N4` рецензії PR #258 ([#259](https://github.com/nick-fedchik/kuzmin-machine/issues/259)): додано мутант `M5_skip_port_a_resync` і властивість `H7_multi_patch_rule_persistence`, cover-ціль `C4_b_we_at_swap` та лічильник симуляції (`4 678 / 10 003`), уточнено docstring глибин SMT і 1-бітний зріз BMC `H3`, задокументовано `DECERR` на `0x03C..0x044` і очікування читання `0x008`/`0x034` під час `sync_busy`. |
| 0.1.0 | 2026-11-16 | Перша редакція звіту Етапів 1–2 за Issue #252: двобанковий RTL `CFG-P-HA`, формальна верифікація `Z3`, синтез `Yosys XC7`, інжектор правил та симуляція `10 000` перемикань. |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| AXI4-Lite | Полегшений синхронний шинний інтерфейс реєстрового доступу ARM AMBA. |
| BMC | Bounded Model Checking — перевірка формальних властивостей моделі на скінченній глибині кроків. |
| BRAM | Block RAM — внутрішньокристальна двопортова синхронна пам'ять ПЛІС (`RAMB36E1`). |
| CFG-P | Базова однобанкова конфігурація програмованого конвеєра дескрипторів за `B4 Варіант 1`. |
| CFG-P-HA | Двобанкова конфігурація високої готовності з тіньовим банком дескрипторів за `B4 Варіант 2`. |
| CME | Concept Micro-Engine — універсальне обчислювальне ядро оцінки предикатів, інваріантів і переходів концепту. |
| CRC-8 | 8-бітна циклічна контрольна сума кадру оновлення правила (`CRC-8/CCITT`, поліном `0x07`). |
| HIL | Hardware-in-the-Loop — натурні випробування на фізичній апаратурі в замкненому контурі. |
| LC | Logic Cell — оцінна логічна комірка сімейства Xilinx 7-series за звітом `Yosys stat -tech xilinx`. |
| SMT | Satisfiability Modulo Theories — розв'язання формул здійсненності в теоріях бітових векторів та масивів. |
| Torn Read | Розірване читання багатослівного 128-бітного дескриптора під час неатомарного оновлення пам'яті. |
| VCD | Value Change Dump — текстовий формат часових діаграм цифрових сигналів. |
