# Звіт #216: Пілот Q3 на ізольованих LLM-агентах без контексту проєкту

* **Версія:** 0.1.0
* **Дата:** 2026-11-15
* **Тип WP:** Experiment
* **Issue:** [#216](https://github.com/nick-fedchik/kuzmin-machine/issues/216) (sub-issue [#120](https://github.com/nick-fedchik/kuzmin-machine/issues/120)). **PR:** у поточному PR з гілки `exp/216-q3-llm-pilot`.
* **Виконавець:** GitHub Copilot CLI (`gemini-4-hydrogen`). **Рецензент:** незалежна рецензія не проведена.
* **Коміт, на якому виконано:** `56c9abd50f70dcb8318f66bfa26e7e73f4597e5b`. **Хост / плата:** `AORUS-5-SE` (програмна симуляція / компіляція без FPGA/HIL). **Бітстрім (SHA-256):** не використовувався.
* **Критерії успіху (зафіксовано до виконання):** [Issue #216](https://github.com/nick-fedchik/kuzmin-machine/issues/216) та заморожені приймальні тести [`tasks_and_tests.py`](data/q3-pilot-216/tasks_and_tests.py).

---

## 1. Що не вдалося і обмеження

1. **Застереження про межу щодо людей (обов'язкова межа експерименту):**
   **Пілот на LLM не дає жодного висновку про зручність, зрозумілість або ергономіку KPOL для програмістів-людей.** LLM-учасники не замінюють людських програмістів, і батьківська Issue [#120](https://github.com/nick-fedchik/kuzmin-machine/issues/120) залишається відкритою для окремого людського етапу Q3.
2. **Обмеження охоплення:**
   - Перевірено 3 цільові задачі (`KPOL-CME-1` та `KPOL-CME-2`) на 3 моделях різних родин (`gemini-4-hydrogen`, `claude-sonnet-5.5`, `gpt-5.3-codex`) в одноразовому режимі (zero-shot, без ітеративного виправлення за помилками компілятора).
   - У межах пілота не перевірялися апаратна симуляція RTL (`iverilog`/Verilator) і запуск на платі PYNQ-Z1 (HIL); перевірка обмежується парсингом, профільним компілятором `compile_concept_microcode_bram_image`, CLI `compile_kpol_bram_image.py`, дизасемблюванням `CME-RAW-1` та еталонним `Interpreter` (`kpol_reference.py`).
   - Ізольованість учасників забезпечувалася явною інструкцією заборони виклику будь-яких інструментів; усі 3 сесії повернули текстові відповіді без викликів інструментів читання файлів чи bash.

## 2. Метод

1. **Заморожування задач і приймальних тестів (до запуску сесій):**
   - Зафіксовано 3 задачі (`TASKS_PROMPT`) та незалежні приймальні перевірки (`check_task1`, `check_task2`, `check_task3`) у [`tasks_and_tests.py`](data/q3-pilot-216/tasks_and_tests.py) і [`test_q3_acceptance.py`](data/q3-pilot-216/tests/test_q3_acceptance.py).
   - Проведено негативний контроль: підтверджено, що тести падають на хибних розв'язках (непідтримуваний оператор `<=` в `KPOL-CME-1`, хибна межа охоронця, відсутній `Proof`, `CME2-OPERAND-COLLISION`, активний на старті каскад `CME2-CASCADE`). Сирий лог заморожування й негативного контролю: [`raw/freeze-and-negative-control-01.log`](data/q3-pilot-216/raw/freeze-and-negative-control-01.log).
2. **Ізольовані сесії LLM-агентів:**
   - Запущено 3 незалежні сесії `general-purpose` із суворою забороною доступу до репозиторію та інструментів.
   - У промпт кожної сесії передано виключно дослівний текст [`kpol-cme-subset-0.1.0.md`](../../../Engineering/specifications/kpol/kpol-cme-subset-0.1.0.md), [`kpol-cme2-profile-0.1.0.md`](../../../Engineering/specifications/kpol/kpol-cme2-profile-0.1.0.md) та розділів §2–4 [`kpol-consolidated-0.1.0.md`](../../../Engineering/specifications/kpol/kpol-consolidated-0.1.0.md), а також формулювання 3 задач.
   - Незмінні сирі відповіді збережено в `Research/studies/author-semantics/data/q3-pilot-216/raw/`.
3. **Приймальне тестування:**
   - Усі 9 згенерованих програм (3 сесії × 3 задачі) прогнано через заморожений `pytest` (`test_pilot_sessions_acceptance`), що викликає `Parser`, `compile_concept_microcode_bram_image`, CLI `compile_kpol_bram_image.py`, `verify_module`, `disassemble_concept_microcode` та `Interpreter`. Сирий лог прогону: [`raw/pilot-acceptance-01.log`](data/q3-pilot-216/raw/pilot-acceptance-01.log).

## 3. Результати

### 3.1. Зведена таблиця прогону ізольованих сесій

| Сесія | Модель | Сирий файл | Задача 1 (`KPOL-CME-1`) | Задача 2 (`KPOL-CME-2`) | Задача 3 (`KPOL-CME-2`) | Усього |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | `gemini-4-hydrogen` | [`session-01-gemini-4-hydrogen.md`](data/q3-pilot-216/raw/session-01-gemini-4-hydrogen.md) | PASS | PASS | PASS | 3 / 3 |
| 02 | `claude-sonnet-5.5` | [`session-02-claude-sonnet-5.5.md`](data/q3-pilot-216/raw/session-02-claude-sonnet-5.5.md) | PASS | PASS | PASS | 3 / 3 |
| 03 | `gpt-5.3-codex` | [`session-03-gpt-5.3-codex.md`](data/q3-pilot-216/raw/session-03-gpt-5.3-codex.md) | PASS | PASS | PASS | 3 / 3 |

Загалом у [`raw/pilot-acceptance-01.log`](data/q3-pilot-216/raw/pilot-acceptance-01.log) пройдено 7/7 тестів (`4` тести еталону й негативного контролю + `3` параметризовані сесійні приймальні прогони, 9/9 програм).

### 3.2. Класифікований реєстр виявлених дефектів та неоднозначностей

У процесі підготовки приймальних тестів і аналізу відповідей ізольованих сесій виявлено такі дефекти та неоднозначності специфікацій і діагностики (самі специфікації та `kpol_reference.py` у цьому PR не змінювалися згідно з обмеженнями Issue):

| ID | Клас | Джерело | Опис дефекту / неоднозначності | Спостережений прояв |
| :--- | :--- | :--- | :--- | :--- |
| Q3-DEF-01 | Специфікація / синтаксис профілю | [`kpol-cme2-profile-0.1.0.md`](../../../Engineering/specifications/kpol/kpol-cme2-profile-0.1.0.md) §2 п. 4 | У тексті наведено псевдосинтаксис `rule R on Ev(p) when G { ... }`, хоча граматика фронтенду (`kpol-consolidated-0.1.0.md` §2.1) **не допускає** `(p)` після імені події в `rule` (`rule NAME on EVENT [when expression]`). | Учасники проігнорували `(p)` завдяки перехресному читанню прикладу з `kpol-consolidated-0.1.0.md`, але буквальне слідування `KPOL-CME-2` призвело б до `CME2-SYNTAX`. |
| Q3-DEF-02 | Специфікація / синтаксис профілю | [`kpol-cme2-profile-0.1.0.md`](../../../Engineering/specifications/kpol/kpol-cme2-profile-0.1.0.md) §2 п. 2 | Запис `State_i: Int32 = Init_i;` подано з великої літери `State`, хоча лексика чутлива до регістру і парсер вимагає `state` у нижньому регістрі. | Сесія 02 явно зафіксувала відсутність повної граматики в специфікації `KPOL-CME-2` і змушена була брати ключові слова з `kpol-consolidated-0.1.0.md`. |
| Q3-DEF-03 | Специфікація / повнота | [`kpol-cme2-profile-0.1.0.md`](../../../Engineering/specifications/kpol/kpol-cme2-profile-0.1.0.md) §2, §5 | Не наведено повної EBNF-граматики для `KPOL-CME-2` (включно з форматом `Proof` і обов'язковістю іменованих міток `NAME :` в `Invariants`). | Зауважено сесією 02 (`claude-sonnet-5.5`): довелося виводити синтаксис інваріантів і `step E(P = ...)` з `kpol-consolidated-0.1.0.md`. |
| Q3-DEF-04 | Діагностика / модель виконання | `kpol_reference.py` (`Interpreter.run` vs `kpol-cme-subset-0.1.0.md` §3) | Порушення інваріанта `S >= 0` у `Interpreter.run()` записується в `RunResult.diagnostics` (`"InvariantViolation:..."`), а **не** в `RunResult.rejected` (куди потрапляють `RejectedInput` і `RejectedHazard`), тоді як у RTL (`kpol_txn_gate_v2.sv`) це `rejected_o` (`rejected_invariant_o`). | Виявлено під час першого прогону приймального тесту Задачі 2 (`tasks_and_tests.py`), коли перевірка `r2.rejected` впала, бо `r2.rejected == []` при `InvariantViolation` у `diagnostics`. |

## 4. Перевірка гіпотези / критеріїв

| Критерій | Очікувано | Отримано | Висновок |
| :--- | :--- | :--- | :--- |
| Заморожені задачі й тести до запуску сесій | Фіксація в Git до старту прогонів і доказ падіння на негативних прикладах | `4 passed` у `raw/freeze-and-negative-control-01.log` (золотий еталон + 3 негативні контролі) | Виконано |
| $\ge 3$ ізольовані сесії LLM без доступу до репо | $\ge 3$ сирі файли з різних моделей із моделлю, датою й SHA | 3 сесії (`gemini-4-hydrogen`, `claude-sonnet-5.5`, `gpt-5.3-codex`) без викликів інструментів | Виконано |
| Перевірка програм замороженими тестами | Усі результати задокументовано у `raw/` | 7/7 тестів (`9/9` програм) пройшли в `raw/pilot-acceptance-01.log` | Виконано |
| Класифікований реєстр дефектів і межа щодо людей | Наявний реєстр та явне застереження про непридатність висновку щодо людей | Зафіксовано 4 дефекти/неоднозначності (`Q3-DEF-01..04`) і явне застереження в §1 | Виконано |

## 5. Відтворення

```bash
python3 -m pytest -v Research/studies/author-semantics/data/q3-pilot-216/tests/test_q3_acceptance.py
python3 -m pytest -q
KM_DRAFTS_REPO=/home/mfedchyk/GitHub/nick-fedchik/drafts python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
git diff --check
```

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-15 | Перша редакція звіту пілота Q3 на ізольованих LLM-агентах (#216). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| WP | Work Product, результат роботи з визначеним призначенням. |
| CME | Concept Micro-Engine (`km_concept_micro_engine.sv`). |
| `CME-RAW-1` | 16-байтний формат дескриптора концепту в BRAM ($64 \times 16$ байтів). |
| EBNF | Розширена форма Бекуса — Наура. |
| HIL | Hardware-in-the-Loop, перевірка на фізичному обладнанні. |
