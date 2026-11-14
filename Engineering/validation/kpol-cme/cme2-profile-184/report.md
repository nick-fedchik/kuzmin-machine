# Звіт #184: багатоконцептний профіль компіляції `KPOL-CME-2` та його побітова еквівалентність з AXI RTL на `CME-RAW-1`

* **Версія:** 0.1.1
* **Дата:** 2026-11-14
* **Тип WP:** Report / Analysis
* **Issue:** [#184](https://github.com/nick-fedchik/kuzmin-machine/issues/184) (sub-issue [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8)). **PR:** у гілці `feat/184-kpol-cme2-profile`.
* **Виконавець:** GitHub Copilot CLI (Gemini 4 Carbon, `gemini-4-carbon`). **Рецензент:** незалежна рецензія не проведена.
* **Коміт бази (Шар 1 стеку, PR #187):** `33a9974d9006bea8eb6d261a903c210ceac50b9c`. **Хост / плата:** Linux x86_64 (`AORUS-5-SE`); фізична плата FPGA не залучалася. **Бітстрім (SHA-256):** не генерувався.
* **Критерії успіху (зафіксовано до виконання):** критерії приймання в описі [#184](https://github.com/nick-fedchik/kuzmin-machine/issues/184) та зауваження незалежної рецензії [PR #187](https://github.com/nick-fedchik/kuzmin-machine/pull/187#issuecomment-6881195250) (явне відхилення невідомих/неконстантних правих операндів і строгих меж `RANGE` на краях `int16`).

---

## 1. Що не вдалося і обмеження

* Усі перевірки у цьому пакеті виконані в хостовому інтерпретаторі Python та в RTL-симуляції повного конвеєра `kpol_bram_pipeline_axi.sv` (`iverilog -g2012` + `vvp`, `verilator`, логічний синтез `yosys`) із кінцевою звіркою стану всіх 64 слотів `W0..W3` після траси; фізичний запуск HIL на платі PYNQ-Z1 не виконувався.
* Профіль `KPOL-CME-1` (`_compile_cme1_profile`, типовий прапорець `--profile KPOL-CME-1`), 16-байтний формат слота `CME-RAW-1` та RTL-файли конфігурації `CFG-P` не змінювалися.
* Через структурні межі 16-байтного дескриптора `CME-RAW-1` у профілі `KPOL-CME-2` навмисно відхиляються (`fail-closed`):
  1. поєднання літерального/діапазонного охоронця та дії `ADD`/`SUB` із кроком $K \ge 2$ (`CME2-OPERAND-COLLISION`, спільне поле `W1 = operand_val`);
  2. присвоєння константи `set S := K`, порівняння власного стану концепту в охоронці (`state-guard`), неініціалізований стан `_` (`KPOL-SYS-02`) та `Hazards` (`CME2-HAZARD`) — перенесені до проєкту системного контракту `CME-RAW-2` у [#185](https://github.com/nick-fedchik/kuzmin-machine/issues/185);
  3. розгалуження каскаду `fan-out > 1` з одного концепту-видавця, цикли підписок, істинний на старті охоронець `on change(S_src)` або видавець без монотонного кроку (`CME2-CASCADE`);
  4. лексеми `•` / `(*)` та конструкції авторського діалекту `Concept`/`Define`/`Group` (`CME2-GUARD` / `CME2-SYNTAX`) — перенесені до [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186).

## 2. Метод

1. **До-імплементаційний негативний контроль ([`raw/negative-control-pre-impl-01.log`](raw/negative-control-pre-impl-01.log)):** на незміненому коді бази `33a9974d9006bea8eb6d261a903c210ceac50b9c` додано клас `KpolCme2ProfileTests` у [`test_kpol_reference.py`](../../../sw/kpol-ref/tests/test_kpol_reference.py) (5 тестових методів і 22 підтести) та запущено `pytest -k KpolCme2ProfileTests`: усі 5 тестів завершилися відмовою (`exit_code=1`, `KpolError: B3-PROFILE: unsupported profile KPOL-CME-2`).
2. **Реалізація профілю `KPOL-CME-2`:**
   * у [`kpol_reference.py`](../../../sw/kpol-ref/kpol_reference.py) додано ознаку `Module.phase_aliases_used` для виявлення лексем `•`/`(*)`, реалізовано `_compile_cme2_profile` з підтримкою $1..64$ станів `Int32`, 3-кольоровою DFS-перевіркою ациклічності та `fan-out <= 1` для `on change(...)`, виставленням `CME_GUARD_SUBSCRIBER_EN = 0x10` для каскаду в будь-який слот включно з `CID 0`, перевіркою стартової хибності охоронця каскаду й монотонності видавця, предикатами `true`/`false`/`not`/`==`/`!=`/`<`/`>`/`>=`/`<=`/`int16` `RANGE`, діями `INC`/`DEC`/`ADD`/`SUB`/`ASSIGN`, детектором `CME2-OPERAND-COLLISION` і обов'язковим невакуумним гейтом `Proof`;
   * у [`compile_kpol_bram_image.py`](../../../hw/scripts/compile_kpol_bram_image.py) додано опцію `--profile {KPOL-CME-1,KPOL-CME-2}` зі збереженням типового `KPOL-CME-1` і коректним пробросом кодів `B3-*` / `CME2-*`.
3. **Кінцева звірка стану після траси `Interpreter` проти повного AXI RTL `kpol_bram_pipeline_axi.sv`:**
   * багатоконцептний модуль `MultiPipeline` (6 активних концептів `CID 0..5` і 58 нульових слотів `CID 6..63`): двоходовий каскад `Ingest (CID 2, +5) -> StageMid (CID 1, +1) -> AlertDigest (CID 0, ASSIGN StageMid)` із каскадним записом у `CID 0`, віднімання `SubBudget (CID 3, -25)` із відкатом за інваріантом `SubBudget >= 0`, діапазонний охоронець `not (x >= -10 and x <= 20)` на екстремумах `Int32` (`-2147483648`, `2147483647`) для `OutOfBandCount (CID 4, +1)`, та `MirrorParam (CID 5, ASSIGN v)` із `v <= 1000`;
   * граничний 64-концептний модуль `Full64` (`CID 0..63`): пряма MMIO-подія в `S0 (CID 0, +1)` з діапазоном `[-32768, 32767]` (перевірено `p0 = -32768` та відхилення `p0 = 40000`) і каскад із верхнього слота `S63 (CID 63, +10) -> S1 (CID 1, ASSIGN S63)` за умови `S63 >= 70`;
   * таблична матриця `охоронець × дія` (`==`, `!=`, `<`, `>`, `>=`, `<=` × `INC`/`DEC`/`ASSIGN`) та 3-кроковий каскад довжини 3 `S3 -> S2 -> S1 -> S0` із ціллю `CID 0` (`test_cme2_guard_action_matrix_and_chain3_rtl_equivalence`).
4. **Специфікація та структурна валідація:** створено [`kpol-cme2-profile-0.1.0.md`](../../../specifications/kpol/kpol-cme2-profile-0.1.0.md), синхронізовано реєстри й індекс `wp-index.json`, виконано `run_open_flow.sh`, `check_links.py`, `check_wp_documents.py`, `inspect_math_formatting.py` та повний `pytest`.

## 3. Результати

* **До-імплементаційний негативний контроль ([`raw/negative-control-pre-impl-01.log`](raw/negative-control-pre-impl-01.log)):** `5 failed` на базі `33a9974d9006bea8eb6d261a903c210ceac50b9c`, `exit_code=1`.
* **Цільовий прогін тестів профілю `KPOL-CME-2` ([`raw/cme2-tests-02.log`](raw/cme2-tests-02.log), попередній прогін [`raw/cme2-tests-01.log`](raw/cme2-tests-01.log)):** `6 passed, 31 subtests passed in 0.91s`, `exit_code=0`:
  * у `MultiPipeline` після 12 зовнішніх AXI-транзакцій (та 1 відхиленого звернення на неактивний слот `CID 63`) побітово збіглися всі 64 слоти стану `W0` між `Interpreter` і `kpol_bram_pipeline_axi.sv` (`AlertDigest = 16`, `StageMid = 16`, `Ingest = 15`, `SubBudget = 15`, `OutOfBandCount = 5`, `MirrorParam = 420`), а всі конфігураційні слова `W1..W3` залишилися незмінними;
  * у `Full64` підтверджено роботу повних 64 слотів (`S0 = 1`, `S1 = 73`, `S63 = 73`, решта слотів незмінні);
  * у матричному тесті `охоронець × дія` підтверджено RTL-еквівалентність для `==`, `!=`, `<`, `>`, `>=`, `<=` і дій `INC`/`DEC`/`ASSIGN`, а у тесті `Chain3` підтверджено 3-кроковий каскад `S3 -> S2 -> S1 -> S0` (`[1, 1, 2, 3]`);
  * підтверджено відмову з усіма 13 точними кодами таблиці §5 специфікації: `CME2-OPERAND-COLLISION`, `CME2-CASCADE` (самопідписка, 2-цикл, 3-цикл, `fan-out = 2`, істинний на старті guard каскаду, `ASSIGN` у видавці каскаду, передача `cascade_map`), `CME2-RANGE` (зокрема строгі `p > 32767` і `p < -32768`), `CME2-GUARD` (`•`, state-guard, `or`), `CME2-ACTION` (константний `ASSIGN`, `+ 0`, `- 0`, `+ -2`), `CME2-HAZARD`, `CME2-INVARIANT` (`Init < 0`, відсутній інваріант, секція `Goals`), `CME2-SHAPE` (65 станів, `Unknown`), `CME2-TYPE` (`Bool`-параметр), `CME2-PROOF`, `CME2-ACL` (`acl_table` без `CAP_WRITE`), `CME2-SYNTAX` та `CME2-IO` (у CLI), а також байт-ідентичність виходу CLI без `--profile` та з `--profile KPOL-CME-1`.
* **Відкритий апаратний потік ([`raw/open-flow-01.log`](raw/open-flow-01.log)):** `bash Engineering/hw/scripts/run_open_flow.sh` — `170 passed in 13.94s`, `verilator` lint та синтез XC7 у `yosys` завершилися з `exit_code=0`.
* **Проміжні контролі форматування формул ([`raw/final-verification-01.log`](raw/final-verification-01.log), [`raw/final-verification-02.log`](raw/final-verification-02.log)):** `inspect_math_formatting.py` виявив незахищений підрядковий індекс у лінійній формулі в `kpol-cme2-profile-0.1.0.md` (`ERR-MATH-09`) та цитування формули в кодових лапках у звіті (`ERR-MATH-01`), після чого обидва місця приведено до захищеного синтаксису GitHub MathJax `` $`S_{src} \pm K \ne S_{src}`$ ``.
* **Фінальна наскрізна перевірка пакета ([`raw/final-verification-04.log`](raw/final-verification-04.log)):** `check_links.py` (включно з 17 посиланнями на `drafts`), `check_wp_documents.py` (`errors: []`), `run_open_flow.sh`, `git diff --check` та повний `python3 -m pytest -q` (`350 passed, 337 subtests passed`) завершилися з `exit_code=0`.

## 4. Перевірка критеріїв приймання

| Критерій (`#184`) | Очікувано | Отримано | Висновок |
| :--- | :--- | :--- | :--- |
| Специфікація та реалізація `profile="KPOL-CME-2"` і `--profile KPOL-CME-2` без зміни `KPOL-CME-1` | Нова специфікація; старі тести `KPOL-CME-1` і типовий режим CLI проходять без змін | Створено `kpol-cme2-profile-0.1.0.md`; байт-ідентичність CLI у режимі за замовчуванням перевірена тестом (`exit_code=0`) | Виконано |
| До 64 концептів і DAG-перевірка каскадів `on change(...)` | Прийняття 1..64 станів та ациклічних ланцюгів (включно з `CID 0`); відмова на циклах і `fan-out > 1` | Перевірено `MultiPipeline` (2-ходовий каскад у `CID 0`), `Full64` (`CID 63 -> CID 1`) та всі негативні тести `CME2-CASCADE` | Виконано |
| Розширені предикати, дії та детектор колізії `operand_val` | Підтримка `>=`, `<=`, `int16` `RANGE`, `INC/DEC/ADD/SUB/ASSIGN`; явний `CME2-OPERAND-COLLISION` і `CME2-RANGE` на межах `int16` | Побітова збіжність у RTL і точні коди відмов на всіх негативних контролях | Виконано |
| Еквівалентність `Interpreter` та RTL-симуляції (`iverilog`) | Співпадіння вектора 64 станів `W0` і незмінність `W1..W3` після багатоходової траси з каскадами та відмовами інваріанта | Усі 64 слоти `W0..W3` у `kpol_bram_pipeline_axi.sv` побітово збіглися з еталоном ([`raw/cme2-tests-02.log`](raw/cme2-tests-02.log)) | Виконано |

## 5. Відтворення

```bash
python3 -m pytest Engineering/sw/kpol-ref/tests/test_kpol_reference.py -k KpolCme2ProfileTests -v
python3 -m pytest -q
bash Engineering/hw/scripts/run_open_flow.sh
KM_DRAFTS_REPO=/home/mfedchyk/GitHub/nick-fedchik/drafts python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
```

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-14 | Перша редакція звіту реалізації та RTL-еквівалентності багатоконцептного профілю `KPOL-CME-2` ([#184](https://github.com/nick-fedchik/kuzmin-machine/issues/184)). |
| 0.1.1 | 2026-11-14 | Виправлення за рецензією PR #188 (B-1, B-2, N-1..N-3): приведено числа й сценарії до фактичних тестів, додано матрицю `охоронець × дія`, ланцюг довжини 3 та повне покриття 13 кодів `CME2-*`. |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| AXI-Lite | Програмна шина керування й завантаження BRAM у `kpol_bram_pipeline_axi.sv` |
| CID | Індекс слота концепту в таблиці BRAM (`0..63`) |
| `CME-RAW-1` | Чинний 16-байтний двійковий дескриптор концепту ядра CME |
| DAG | Спрямований ациклічний граф підписок `on change(...)` |
| HIL | Hardware-in-the-Loop (фізична плата FPGA; у цьому звіті не залучалася) |
| `KPOL-CME-2` | Багатоконцептний профіль компіляції KPOL у формат `CME-RAW-1` |
