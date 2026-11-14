# Звіт KPOL-CME-168: усунення 1-тактової гонитви B4 у `kpol_bram_pipeline_axi.sv`, W1C-очищення `0x02C` та модернізація `kpol_bram_pipeline_pynq_z1_top.v`

* **Версія:** 0.1.0
* **Дата:** 2026-11-14
* **Тип WP:** Report
* **Issue:** [#168](https://github.com/nick-fedchik/kuzmin-machine/issues/168).
* **Виконавець:** GitHub Copilot CLI (`gemini-4-carbon`). **Рецензент:** очікується незалежний агент іншої родини моделей (Claude).
* **Коміт, на якому виконано:** `4a3d471` (негативний контроль — `ab48a62`). **Хост / плата:** `AORUS-5-SE` (Linux x86_64, Icarus Verilog 12.0, Verilator 5.032, Yosys 0.52, Python 3.14.4 / pytest 9.0.2; генерація бітстріму та фізичний HIL не охоплюються).
* **Критерії успіху (зафіксовано до виконання):** критерії приймання [#168](https://github.com/nick-fedchik/kuzmin-machine/issues/168).

---

## 1. Що не вдалося і обмеження

1. Верифікація виконана в RTL-симуляції (`iverilog`/`vvp`), статичному аналізі (`verilator --lint-only -Wall`) та логічному синтезі під Xilinx 7-Series (`yosys synth_xilinx` як для `kpol_bram_pipeline_axi`, так і для повного top-level модуля `kpol_bram_pipeline_pynq_z1_top`). Вона **не є** трасуванням у `nextpnr-himbaechel` / Vivado або фізичним запуском бітстріму на платі PYNQ-Z1.
2. Поведінкова перевірка `kpol_bram_pipeline_pynq_z1_top.v` використовує симуляційні моделі примітивів `BUFG` та `PS7` у [`kpol_bram_pipeline_pynq_z1_top_tb.sv`](../../../hw/tests/kpol_bram_pipeline_pynq_z1_top_tb.sv); під час логічного синтезу в Yosys ці елементи синтезуються як штатні апаратні макроси XC7 (`BUFG: 1`, `PS7: 1`, `RAMB36E1: 1`).

## 2. Метод

1. **Негативний контроль до зміни реалізації (`ab48a62` поверх `0d0ff47`):**
   - у [`kpol_bram_pipeline_axi_tb.sv`](../../../hw/tests/kpol_bram_pipeline_axi_tb.sv) додано безперервний монітор фазового інваріанта `!(dut.bram_we && dut.busy)` та два цільові режими `+b4_race_audit` і `+w1c_clear_audit`;
   - створено тестбенч [`kpol_bram_pipeline_pynq_z1_top_tb.sv`](../../../hw/tests/kpol_bram_pipeline_pynq_z1_top_tb.sv) для перевірки параметра зовнішньої події `32'd1`, двоступеневої синхронізації `sw[1:0]`, фільтрації брязкоту `btn[0]` (1,0 мс = 100 000 тактів @ 100 МГц) та незалежності `ja1` при утриманій `btn[0]`;
   - у [`test_kpol_bram_pipeline.py`](../../../hw/tests/test_kpol_bram_pipeline.py) додано 3 тести (`test_axi_b4_load_vs_run_write_race`, `test_axi_overflow_w1c_clear`, `test_pynq_z1_top_cdc_debounce_and_param1`) і записано їхнє падіння на незміненому RTL у [`raw/negative-control-01.log`](raw/negative-control-01.log).
2. **Виправлення (`4a3d471`):**
   - у [`kpol_bram_pipeline_axi.sv`](../../../hw/rtl/bus/kpol_bram_pipeline_axi.sv):
     * введено захисне вікно запису `ext_trigger_blocked = sw_trigger || bram_we || cfg_write_fire`, яке комбінаційно опускає `hw_trigger_ready_o` у `0` та блокує проходження `ext_hw_trigger_valid_i` у секвенсер як на такті `write_fire` у конфігураційні регістри (`0x004`, `0x008`, `0x00C`, `0x02C`), так і на наступному такті фактичного запису `bram_we == 1`, із збереженням обліку B5 для незупинних джерел і очікування без втрат для керованих джерел;
     * додано захист `13'h010` при `bram_we == 1` (`SLVERR`);
     * додано обробку запису W1C у регістр `0x02C`: при `busy == 1` повертається `SLVERR`, а при `busy == 0` запис із `write_data[16] == 1` (`0x0001_0000`) синхронно очищує як AXI-рівневі (`axi_sw_overflow_q`, `axi_sw_dropped_q`), так і секвенсерні (`overflow_latched_q`, `dropped_count_q`) регістри втрат; запис із бітом `16 == 0` є безпечним no-op (`OKAY`);
   - у [`km_autonomous_sequencer.sv`](../../../hw/rtl/core/km_autonomous_sequencer.sv) додано вхід `clear_overflow_i`, активний лише за `!busy_o`;
   - у [`kpol_bram_pipeline_pynq_z1_top.v`](../../../hw/boards/pynq-z1/kpol_bram_pipeline_pynq_z1_top.v):
     * розділено шляхи синхронізації швидкого PMOD-входу `ja1` (2-FF `ASYNC_REG` + детектор фронту без затримки антибрязкоту) та механічної кнопки `btn[0]` (2-FF `ASYNC_REG` + параметризований фільтр антибрязкоту `BTN_DEBOUNCE_CYCLES = 100000` тактів = 1,0 мс @ 100 МГц + детектор фронту);
     * додано 2-FF `ASYNC_REG` синхронізатор для перемикачів `sw[1:0]` перед подачею на `target_cid`;
     * замінено `.ext_hw_trigger_param_i(32'd0)` на `.ext_hw_trigger_param_i(32'd1)` з точним коментарем інженерного призначення;
   - оновлено нормативні специфікації [`kpol-image-loader-pipeline-contract.md`](../../../specifications/hw/kpol-image-loader-pipeline-contract.md) (`v2.2.0`) та [`event-queue-ingress-specification.md`](../../../specifications/hw/event-queue-ingress-specification.md) (`v2.2.0`), а також додано 6 мутаційних контролів `AXI_PYNQ_MUTANTS` у [`test_kpol_bram_pipeline.py`](../../../hw/tests/test_kpol_bram_pipeline.py).
3. **Повна регресійна, синтезна та структурна перевірка:** виконано `python3 -m pytest -q` ([`raw/full-pytest-01.log`](raw/full-pytest-01.log)), `bash Engineering/hw/scripts/run_open_flow.sh` ([`raw/open-flow-01.log`](raw/open-flow-01.log)), окремий логічний синтез XC7 модуля `kpol_bram_pipeline_pynq_z1_top` ([`raw/pynq-top-synth-01.log`](raw/pynq-top-synth-01.log)), а також `check_links.py` і `check_wp_documents.py` ([`raw/structure-01.log`](raw/structure-01.log)).

## 3. Результати

* **Негативний контроль (`ab48a62`, [`raw/negative-control-01.log`](raw/negative-control-01.log)):** усі 3 цільові тести впали на поведінкових інваріантах (`3 failed`, `exit_code=1`):
  - `test_axi_b4_load_vs_run_write_race`: `[FAIL] B4 race: hw_trigger_ready_o remained 1 during write_fire(0x008)`;
  - `test_axi_overflow_w1c_clear`: `write 002c response 3 expected 2` (відсутня підтримка W1C на `0x02C` — повертався `DECERR`);
  - `test_pynq_z1_top_cdc_debounce_and_param1`: `[FAIL] PYNQ top param=1 check failed: cid0_state=10 (exp 11), commits=0 (exp 1)`.
* **Після виправлення (`4a3d471`, [`raw/full-pytest-01.log`](raw/full-pytest-01.log)):** `339 passed, 300 subtests passed` (`exit_code=0`), включно з 3 інтеграційними сценаріями `#168` та всіма 6 мутантами `AXI_PYNQ_MUTANTS`.
* **Відкритий RTL-потік та синтез top-модуля PYNQ-Z1 ([`raw/open-flow-01.log`](raw/open-flow-01.log), [`raw/pynq-top-synth-01.log`](raw/pynq-top-synth-01.log)):** `170 passed` у HW-наборі, Verilator `--lint-only -Wall` без жодних нових попереджень, Yosys `synth_xilinx` успішний як для `kpol_bram_pipeline_axi`, так і для `kpol_bram_pipeline_pynq_z1_top` (`3998` комірок, `RAMB36E1: 1`, `PS7: 1`, `BUFG: 1`, `Found and reported 0 problems`).
* **Структурні перевірки WP та посилань ([`raw/structure-01.log`](raw/structure-01.log)):** `0 broken links`, `errors: []` (`exit_code=0`).

## 4. Перевірка гіпотези / критеріїв

| Критерій (#168) | Очікувано | Отримано | Висновок |
| :--- | :--- | :--- | :--- |
| Ізоляція 1-тактового вікна запису BRAM (`Load vs Run`) | `hw_trigger_ready_o == 0` і блокування запуску секвенсера на тактах `write_fire` та `bram_we == 1`; `!(bram_we && busy)` на кожному такті | Кероване джерело чекає без втрат (`50 -> 51`), незупинний імпульс блокується (`70`, `ovf=1, drop=1`), 2 мутанти перехоплено | Виконано |
| Програмне W1C-очищення `0x02C` | При `busy == 1` — `SLVERR`; при `busy == 0` запис `0x0001_0000` очищує `0x02C[16]` і `0x028`, запис `0` — no-op | `+w1c_clear_audit` PASS + мутант `axi-w1c-ignore-bit16` перехоплено | Виконано |
| PYNQ-Z1 top: CDC `sw[1:0]`, антибрязкіт `btn[0]` та `param = 32'd1` | 2-FF `ASYNC_REG` на `ja1`, `btn[0]`, `sw[1:0]`; антибрязкіт 1 мс на `btn[0]` без маскування `ja1`; `param = 1` | `kpol_bram_pipeline_pynq_z1_top_tb.sv` PASS + 3 мутанти перехоплено + синтез XC7 `0 problems` | Виконано |
| Узгодженість специфікацій B4 та B5 | Описано захист вікна запису Port A та W1C регістру `0x02C` | Оновлено `kpol-image-loader-pipeline-contract.md` (`v2.2.0`) і `event-queue-ingress-specification.md` (`v2.2.0`) | Виконано |

## 5. Відтворення

```bash
python3 -m pytest Engineering/hw/tests/test_kpol_bram_pipeline.py -k "b4_load_vs_run or overflow_w1c or pynq_z1_top or axi_b4_and_pynq_top_mutant" -v
python3 -m pytest -q
bash Engineering/hw/scripts/run_open_flow.sh
yosys -p "read_verilog -sv Engineering/hw/rtl/core/kpol_txn_gate_v2.sv Engineering/hw/rtl/core/km_concept_micro_engine.sv Engineering/hw/rtl/core/km_concept_bram.sv Engineering/hw/rtl/core/km_autonomous_sequencer.sv Engineering/hw/rtl/bus/kpol_bram_pipeline_axi.sv Engineering/hw/boards/pynq-z1/kpol_bram_pipeline_pynq_z1_top.v; synth_xilinx -flatten -abc9 -arch xc7 -top kpol_bram_pipeline_pynq_z1_top; stat; check"
python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
```

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-14 | Перша редакція звіту верифікації виправлень `kpol_bram_pipeline_axi.sv` та `kpol_bram_pipeline_pynq_z1_top.v` (#168). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| CDC | Clock Domain Crossing — перенесення сигналів між асинхронним входом і системним тактовим доменом `clk`. |
| HIL | Hardware-in-the-Loop — перевірка на фізичній апаратній платформі. |
| W1C | Write-1-to-Clear — програмний механізм скидання зафіксованої ознаки записом одиниці у відповідний біт регістру. |
