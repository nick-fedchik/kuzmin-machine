# Звіт KPOL-CME-167: верифікація семантики ядра `km_concept_micro_engine.sv` (каскад на `CID 0`, `state_changed_o`, знакове переповнення, `RANGE`, `action_opcode`)

* **Версія:** 0.1.0
* **Дата:** 2026-11-14
* **Тип WP:** Report
* **Issue:** [#167](https://github.com/nick-fedchik/kuzmin-machine/issues/167).
* **Виконавець:** GitHub Copilot CLI (`gemini-4-carbon`). **Рецензент:** очікується незалежний агент іншої родини моделей (Claude).
* **Коміт, на якому виконано:** `bc3cf27` (негативний контроль — `ffae8ac`). **Хост / плата:** `AORUS-5-SE` (Linux x86_64, Icarus Verilog 12.0, Verilator 5.032, Yosys 0.33, Python 3.14.4 / pytest 9.0.2; апаратний HIL не охоплюється).
* **Критерії успіху (зафіксовано до виконання):** критерії приймання [#167](https://github.com/nick-fedchik/kuzmin-machine/issues/167).

---

## 1. Що не вдалося і обмеження

1. Перевірка є RTL-симуляцією в Icarus Verilog, статичним аналізом у Verilator та логічним синтезом під Xilinx 7-Series у Yosys (`synth_xilinx`). Вона **не є** маршрутизацією у Vivado, генерацією бітстріму або фізичним HIL-запуском на платі PYNQ-Z1.
2. За затвердженим контрактом інваріанта поточного ядра CME (`invariant_true_w = !arith_overflow_w && ($signed(candidate_state_w) >= 0)`) допустима область коміту станів залишається невід'ємною (`0 .. 2147483647`); виправлення усуває обхід цієї межі при знаковому дводоповняльному wrap-around у додатну піввісь.

## 2. Метод

1. **Негативний контроль до зміни реалізації (`ffae8ac`):**
   - розширено [`km_concept_micro_engine_tb.sv`](../../../hw/tb/km_concept_micro_engine_tb.sv) сценаріями 6–10 (каскад на `CID 0` та межа `< 64`, по-концептний `state_changed_o`, знакові переповнення/underflow `SUB/ADD/DEC/INC`, знаковий `RANGE [-10, +10]`, fail-closed відхилення `action_opcode = 0xFF`);
   - додано наскрізний інтеграційний тест секвенсера `test_cme_cascade_to_cid0_end_to_end_in_sequencer` у [`test_kpol_bram_pipeline.py`](../../../hw/tests/test_kpol_bram_pipeline.py) та компіляторний тест `test_v10_cascade_to_cid0_sets_subscriber_enable_guard_flag` у [`test_kpol_reference.py`](../../../sw/kpol-ref/tests/test_kpol_reference.py);
   - виконано прогін проти незміненого RTL та `kpol_reference.py` із записом у [`raw/negative-control-01.log`](raw/negative-control-01.log).
2. **Виправлення (`bc3cf27`):**
   - у [`km_concept_micro_engine.sv`](../../../hw/rtl/core/km_concept_micro_engine.sv):
     * введено явний дозвіл каскаду за `guard_flags_w[4]` (`CME_GUARD_SUBSCRIBER_EN = 0x10`) із перевіркою межі `subscriber_cid_w < 64` та збереженням зворотної сумісності з `KPOL-CME-1` (`guard_flags = 0x03`, `subscriber_cid = 0` → `trigger_subscriber_o = 0`);
     * замінено міжконцептно забруднений `gate_changed` на по-концептне порівняння `gate_committed && (gate_state_out != sampled_state_q)`, де `sampled_state_q` фіксує `current_state_w` на такті `event_valid_i`;
     * додано комбінаційну детекцію знакового дводоповняльного переповнення/underflow `arith_overflow_w` для `INC`, `DEC`, `ADD`, `SUB` та враховано її в `invariant_true_w`;
     * виконано знакове розширення 16-бітних меж `range_lo_w` / `range_hi_w` у компараторі `RANGE` (`8'h05`);
     * подано `action_valid_w` (`action_opcode_w <= 8'h04`) на вхід `candidate_known_i` транзакційного шлюзу `kpol_txn_gate_v2`, забезпечуючи fail-closed відхилення невідомих кодів дій;
   - у [`kpol_reference.py`](../../../sw/kpol-ref/kpol_reference.py) додано `CME_GUARD_SUBSCRIBER_EN = 0x10`, встановлення біта 4 під час компіляції `cascade_map` та відмову `KpolError` на невідомих або позамежних цілях каскаду;
   - у [`kpol-image-loader-pipeline-contract.md`](../../../specifications/hw/kpol-image-loader-pipeline-contract.md) (`v2.1.0`) уточнено призначення біта 4 поля `guard_flags`;
   - у [`test_kpol_bram_pipeline.py`](../../../hw/tests/test_kpol_bram_pipeline.py) додано 6 мутаційних контролів `CME_MUTANTS`, кожен із яких відновлює один конкретний дефект і перевіряє його детерміноване перехоплення тестбенчем.
3. **Повна регресійна, синтезна та структурна перевірка:** виконано `python3 -m pytest -q` ([`raw/full-pytest-01.log`](raw/full-pytest-01.log)), `bash Engineering/hw/scripts/run_open_flow.sh` ([`raw/open-flow-01.log`](raw/open-flow-01.log)), `check_links.py` і `check_wp_documents.py` ([`raw/structure-01.log`](raw/structure-01.log)).

## 3. Результати

* **Негативний контроль (`ffae8ac`, [`raw/negative-control-01.log`](raw/negative-control-01.log)):** усі три цільові перевірки впали (`exit_codes: tb=1 e2e=1 kpol_ref=1`):
  - `km_concept_micro_engine_tb.sv`: `[FAIL] Сценарій 6A провалено: каскад на CID=0 заблоковано! commit=1, state=11, trig=0, sub=0`;
  - наскрізний секвенсер `CID 1 -> CID 0`: `committed=1 (exp 2), cid0_state=10 (exp 11), last_state=21`;
  - компілятор `kpol_reference.py`: `descriptors[1].guard_flags & 0x10 == 0`.
* **Після виправлення (`bc3cf27`, [`raw/full-pytest-01.log`](raw/full-pytest-01.log)):** `330 passed, 300 subtests passed` (`exit_code=0`), включно з усіма 10 сценаріями `km_concept_micro_engine_tb.sv`, наскрізним каскадом `CID 1 -> CID 0` у секвенсері та 6 мутантами `CME_MUTANTS`.
* **Відкритий RTL-потік ([`raw/open-flow-01.log`](raw/open-flow-01.log)):** `161 passed`, Verilator `--lint-only` і Yosys `synth_xilinx -top kpol_bram_pipeline_axi; check` завершилися з `exit_code=0`.
* **Структурні перевірки WP та посилань ([`raw/structure-01.log`](raw/structure-01.log)):** `0 broken links`, `errors: []` (`exit_code=0`).

## 4. Перевірка гіпотези / критеріїв

| Критерій (#167) | Очікувано | Отримано | Висновок |
| :--- | :--- | :--- | :--- |
| Каскад на `CID 0` та сумісність `KPOL-CME-1` | `CID 1 -> CID 0` працює з `guard_flags[4]=1`; без біта 4 `sub_cid=0` не тригерить каскад; `sub_cid >= 64` заблоковано | Сценарії 6A/6B/6C + секвенсер `committed=2, cid0_state=11` + 2 мутанти | Виконано |
| По-концептний `state_changed_o` | Відсутні хибні `1` при `100 -> 100` і пропуски `0` при `0 -> 100` після іншого концепту | Сценарії 7.0/7A/7B PASS + мутант `cross-concept-gate-changed` перехоплено | Виконано |
| Детекція знакового переповнення `INC/DEC/ADD/SUB` | Дводоповняльний wrap-around у додатну область відхиляється (`committed=0, rejected=1`) | Сценарії 8A–8E PASS + мутант `ignore-arith-overflow` перехоплено | Виконано |
| Знаковий компаратор `RANGE` (`0x05`) | Від'ємні й додатні `event_param_i` коректно порівнюються зі знаковими `int16` межами `[-10, +10]` | Сценарії 9A/9B/9C PASS + мутант `unsigned-range-bounds` перехоплено | Виконано |
| Fail-closed на невідомих `action_opcode > 0x04` | Транзакція гарантовано відхиляється (`committed=0, rejected=1`) | Сценарій 10 PASS + мутант `silent-unknown-action-commit` перехоплено | Виконано |
| Негативний контроль + відкритий синтез XC7 | Pre-fix падіння в `raw/`, зелений `pytest`, Verilator і Yosys `synth_xilinx` | `330 passed`, `run_open_flow.sh` PASS | Виконано |

## 5. Відтворення

```bash
python3 -m pytest Engineering/hw/tests/test_testbenches.py -k km_concept_micro_engine_tb -v
python3 -m pytest Engineering/hw/tests/test_kpol_bram_pipeline.py -k "cid0 or cme_core_semantics_mutant" -v
python3 -m pytest -q
bash Engineering/hw/scripts/run_open_flow.sh
python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
```

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-14 | Перша редакція звіту верифікації семантики ядра `km_concept_micro_engine.sv` (#167). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| CID | Concept Identifier — індекс концепту в таблиці BRAM (`0..63`). |
| CME | Concept Micro-Engine — універсальне обчислювальне ядро концепту (`km_concept_micro_engine.sv`). |
| Fail-Closed | Принцип безпечної відмови: будь-яка невизначеність або помилка блокує зміну стану (`committed = 0, rejected = 1`). |
| HIL | Hardware-in-the-Loop — перевірка на реальному кристалі у складі плати. |
