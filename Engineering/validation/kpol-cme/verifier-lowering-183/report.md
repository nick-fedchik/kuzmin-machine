# Звіт #183: виправлення інкрементного `change()`, анти-вакуумного `verify_module`, базового CME-lowering та синхронізація `RFC-010`

* **Версія:** 0.1.0
* **Дата:** 2026-11-14
* **Тип WP:** Report / Analysis
* **Issue:** [#183](https://github.com/nick-fedchik/kuzmin-machine/issues/183) (sub-issue [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8)). **PR:** у гілці `fix/183-kpol-verifier-lowering-rfc010`.
* **Виконавець:** GitHub Copilot CLI (Gemini 4 Carbon, `gemini-4-carbon`). **Рецензент:** незалежна рецензія не проведена.
* **Коміт бази (до виправлення):** `134f1095ef674a20312172eaa8dbfd314dba9cb0`. **Хост / плата:** Linux x86_64 (`AORUS-5-SE`); фізична плата FPGA не залучалася. **Бітстрім (SHA-256):** не генерувався.
* **Критерії успіху (зафіксовано до виконання):** критерії приймання в описі [#183](https://github.com/nick-fedchik/kuzmin-machine/issues/183).

---

## 1. Що не вдалося і обмеження

* Усі перевірки у цьому пакеті виконані на хості в інтерпретаторі Python та в RTL-симуляції (`iverilog` + `vvp`, `verilator`, логічний синтез `yosys`); фізичний HIL на платі PYNQ-Z1 не виконувався.
* Профіль `KPOL-CME-1` (`_compile_cme1_profile`) та двійковий формат 16-байтного слота `CME-RAW-1` навмисно не змінювалися (рішення власника B3-01).
* У безпрофільному `compile_concept_microcode_bram_image` зберігаються структурні межі формату `CME-RAW-1`: спільне 32-бітне поле `operand_val` для предиката й `ADD/SUB`, кодування `CME_ACT_ASSIGN` із `event_param` (а не константи), відсутність збереження `when false` без профільної перевірки, відсутність порівняння стану (`state-guard`) та відсутність прапорця ініціалізації стану `_`. Ці обмеження винесені в окремі задачі [#184](https://github.com/nick-fedchik/kuzmin-machine/issues/184) та [#185](https://github.com/nick-fedchik/kuzmin-machine/issues/185).
* Відповідь М. Ю. Кузьміна на `RFC-010` (`drafts@c92001c69f7417ca35f743c0e3c6942783eb29a7`) частково уточнює `Q-AUTH-02` (вилучення окремого `Size` на користь безіменного атрибута розміру `Token` і визначення `Def` як 8-бітної маски присутності елементів концепту), але не встановлює порядок 8 бітів у `Def`, коди `Class` для `Token`/`Byte` чи розмежування порожнього присутнього елемента й його відсутності; native-діалект `KPOL-AUTH` залишається предметом [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186).

## 2. Метод

1. **Попередній негативний контроль на незміненому коді (`134f109`):** до редагування `Engineering/sw/kpol-ref/kpol_reference.py` у `Engineering/sw/kpol-ref/tests/test_kpol_reference.py` додано клас `KpolIssue183LanguageAndLoweringTests` (5 тестових методів, включно з компіляцією та симуляцією реального RTL `km_concept_micro_engine.sv` + `kpol_txn_gate_v2.sv` у `iverilog -g2012` / `vvp`) і зафіксовано падіння на незміненому `kpol_reference.py` у [`raw/negative-control-pre-fix-01.log`](raw/negative-control-pre-fix-01.log).
2. **Виправлення коду в [`kpol_reference.py`](../../../sw/kpol-ref/kpol_reference.py):**
   * `Interpreter`: прапорець `_initial_changes_pending` обмежує початкову постановку `change_watches` першим викликом `run()` екземпляра, усуваючи хибне повторне спрацьовування незмінених підписок між кроками багатоходових сценаріїв `Proof` та інкрементних викликів `run()`.
   * `verify_module`: додано облік активованих охоронців `activated_asserts`; оголошений `AssertPropertyDecl`, чия передумова `when` жодного разу не набула `True` в жодному сценарії, а також непорожній `Proof` із `total_checks == 0` переводять звіт у стан відмови (`report.passed == False`), тоді як явно порожній `Proof {}` зберігає `total_checks == 0` для відсікання мутаційним гейтом і профільним компілятором.
   * `compile_concept_microcode_bram_image`: видалено евристику інверсії охоронця за підрядками імені правила (`not`, `negat`, `•`); додано послідовне згортання вкладених унарних заперечень `not`/`!`, двосторонній знаковий інтервал `Binary("and", ...)` у `CME_PRED_RANGE` з перевіркою діапазону `int16` (`[-32768, 32767]`) і `lo <= hi` (поза межами — `KpolError`), а також точне перенесення `>=` як `INVERT + CME_PRED_LT` і `<=` як `INVERT + CME_PRED_GT` на всьому діапазоні `Int32`.
3. **Синхронізація джерел і документації:** оновлено [`Research/sources/author/clarifications-2026-11-13.md`](../../../../Research/sources/author/clarifications-2026-11-13.md) (`v0.2.0`), [`Research/sources/README.md`](../../../../Research/sources/README.md) (`v0.5.1`), [`Engineering/requirements/kpol.md`](../../../requirements/kpol.md) (`v0.5.2`), [`Engineering/design/software/compiler.md`](../../../design/software/compiler.md) (`v0.5.1`), [`Engineering/specifications/kpol/kpol-consolidated-0.1.0.md`](../../../specifications/kpol/kpol-consolidated-0.1.0.md) (`v0.6.0`), [`Engineering/specifications/kpol/README.md`](../../../specifications/kpol/README.md) (`v0.5.2`), [`Project/registers/open-work-items.md`](../../../../Project/registers/open-work-items.md) (`v0.4.0`), [`Project/registers/work-products.md`](../../../../Project/registers/work-products.md) (`v0.5.1`), [`Project/registers/goals-needs-work-items.md`](../../../../Project/registers/goals-needs-work-items.md) (`v0.9.1`), [`Engineering/validation/README.md`](../../README.md) (`v0.5.5`) і [`Project/registers/wp-index.json`](../../../../Project/registers/wp-index.json) (`v0.11.0`).
4. **Повна регресія та структурна валідація:** запущено повний набір `pytest`, відкритий апаратний потік `run_open_flow.sh`, перевірку посилань `check_links.py`, конвертів WP `check_wp_documents.py`, форматування формул і повноти `wp-index.json`.

## 3. Результати

* **До-фіксовий негативний контроль ([`raw/negative-control-pre-fix-01.log`](raw/negative-control-pre-fix-01.log)):** на базі `134f1095ef674a20312172eaa8dbfd314dba9cb0` команда `python3 -m pytest Engineering/sw/kpol-ref/tests/test_kpol_reference.py -k KpolIssue183LanguageAndLoweringTests -v` завершилася з `exit_code=1` (усі 5 тестових методів зафіксували дефекти: `AssertionError: 8 != 0` для імен `NotifyOperator`/`AnnotateEvent`/`NegativeSlopeStep`; розходження станів RTL `km_concept_micro_engine.sv` `[10, 13, 23, 10]` проти еталонних `[15, 15, 19, 14]` на 13 знакових векторах `[-2147483648..2147483647]`; відсутність `KpolError` для інтервалів поза `int16` і `20..10`; хибне `Marker == True` при незміненому `C`; проходження вакуумних `Proof`).
* **Негативний контроль посилань під час проміжних прогонів ([`raw/pytest-full-01.log`](raw/pytest-full-01.log), [`raw/pytest-full-02.log`](raw/pytest-full-02.log), [`raw/structure-checks-01.log`](raw/structure-checks-01.log), [`raw/final-verification-01.log`](raw/final-verification-01.log), [`raw/final-verification-02.log`](raw/final-verification-02.log), [`raw/final-verification-03.log`](raw/final-verification-03.log), [`raw/final-verification-04.log`](raw/final-verification-04.log)):** проміжні запуски зафіксували спрацьовування `check_links.py` на ще не створений цільовий звіт/лог, корекцію імені файла `RFC-010` у картці джерела (`RFC-010-concept-layout-and-size.md` у `drafts@c92001c`) та уточнення перевірки індексу `wp-index.json` для нових файлів пакета.
* **Фінальний наскрізний прогін тестів, посилань та індексу ([`raw/final-verification-05.log`](raw/final-verification-05.log)):** `check_links.py` (з перевіркою 17 посилань на `drafts`) — `0` битих посилань; `check_wp_documents.py` — `errors: []`; `inspect_math_formatting.py` — `0` зауважень; усі записи `Project/registers/wp-index.json` існують на диску й охоплюють усі нові файли пакета `#183`; `git diff --check` — `exit_code=0`; `python3 -m pytest -q` — `344 passed, 306 subtests passed`, `exit_code=0`. В RTL-симуляції `km_concept_micro_engine.sv` фінальні стани 4 концептів (`>= 5`, `<= -3`, `[-10, 20]`, `not [-10, 20]`) збіглися з `Interpreter`: `[15, 15, 19, 14]`.
* **Відкритий апаратний потік ([`raw/open-flow-01.log`](raw/open-flow-01.log)):** `bash Engineering/hw/scripts/run_open_flow.sh` завершився з `exit_code=0` (симуляція RTL тестбенчів, `verilator` lint та логічний синтез XC7 без помилок).

## 4. Перевірка гіпотези / критеріїв

| Критерій (`#183`) | Очікувано | Отримано | Висновок |
| :--- | :--- | :--- | :--- |
| Одноразовий початковий `change(...)` у `Interpreter` | `Marker == False` на кроці 2 без зміни `C`; `verify_module.passed == True` | `Marker == False`, `A == 2`, `report.passed == True` ([`raw/final-verification-05.log`](raw/final-verification-05.log)) | Виконано |
| Відхилення вакуумних елементів `Proof` у `verify_module` | `report.passed == False` для `assert` без сценарію, неактивованого `when` та сценарію без перевірок; збереження контракту порожнього `Proof {}` для мутаційного гейта | Усі 3 вакуумні випадки дають `passed == False`; `test_v07_popperian_falsification_score_and_gate_failure` проходить ([`raw/final-verification-05.log`](raw/final-verification-05.log)) | Виконано |
| Відсутність інверсії охоронця за іменем правила | `guard_flags & 0x08 == 0` для `NotifyOperator`, `AnnotateEvent`, `NegativeSlopeStep` | `guard_flags & 0x08 == 0` для всіх трьох імен | Виконано |
| Точне lowering `>=`, `<=` та двостороннього `int16` `RANGE` у RTL `km_concept_micro_engine.sv` | Збіг станів RTL і `Interpreter` на 13 векторах включно з `-2147483648` і `2147483647`; `KpolError` поза `int16` або при `lo > hi` | Стани `[15, 15, 19, 14] == [15, 15, 19, 14]`; поза `int16` і `20..10` піднімається `KpolError` | Виконано |
| Синхронізація `RFC-010`, специфікацій KPOL і реєстрів | `check_links.py`, `check_wp_documents.py`, `wp-index.json` і `run_open_flow.sh` без помилок | `0 broken links`, `errors: []`, `exit_code=0` ([`raw/final-verification-05.log`](raw/final-verification-05.log), [`raw/open-flow-01.log`](raw/open-flow-01.log)) | Виконано |

## 5. Відтворення

```bash
python3 -m pytest -q
bash Engineering/hw/scripts/run_open_flow.sh
KM_DRAFTS_REPO=/home/mfedchyk/GitHub/nick-fedchik/drafts python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
```

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-14 | Перша редакція звіту перевірки виправлень `#183` у `kpol_reference.py` та синхронізації документації мови KPOL. |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| CME | Concept Micro-Engine (`km_concept_micro_engine.sv`) |
| `CME-RAW-1` | 16-байтний двійковий дескриптор концепту для BRAM ядра CME |
| HIL | Hardware-in-the-Loop (перевірка на фізичній платі FPGA; у цьому звіті не виконувалася) |
| Vacuous Proof | Формально непорожній блок доведення, у якому жодна перевірка не виконалася або передумова `when` жодного разу не стала істинною |
| WP | Work Product (робочий продукт за структурою NG) |
