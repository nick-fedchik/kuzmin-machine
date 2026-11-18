# Звіт #216: Пілот Q3 на ізольованих LLM-агентах без контексту проєкту

* **Версія:** 0.1.1
* **Дата:** 2026-11-15
* **Тип WP:** Experiment
* **Issue:** [#216](https://github.com/nick-fedchik/kuzmin-machine/issues/216) (sub-issue [#120](https://github.com/nick-fedchik/kuzmin-machine/issues/120)). **PR:** у поточному PR з гілки `exp/216-q3-llm-pilot`.
* **Виконавець:** GitHub Copilot CLI (`gemini-4-hydrogen`; редакція `0.1.0`), доопрацювання `0.1.1` за рецензією PR #223 — `claude-sonnet-5.5`. **Рецензент:** `claude-sonnet-5.5` (вердикт «Доопрацювати» щодо `0.1.0`, [коментар](https://github.com/nick-fedchik/kuzmin-machine/pull/223#issuecomment-6900552057)); повторна рецензія `0.1.1` очікується від моделі родини Gemini. **Конфлікт інтересів:** `claude-sonnet-5.5` водночас є досліджуваним учасником (сесія 02).
* **Коміт, на якому виконано:** `56c9abd50f70dcb8318f66bfa26e7e73f4597e5b`. **Хост / плата:** `AORUS-5-SE` (програмна симуляція / компіляція без FPGA/HIL). **Бітстрім (SHA-256):** не використовувався.
* **Критерії успіху (зафіксовано до виконання):** [Issue #216](https://github.com/nick-fedchik/kuzmin-machine/issues/216) та заморожені приймальні тести [`tasks_and_tests.py`](data/q3-pilot-216/tasks_and_tests.py).

---

## 1. Що не вдалося і обмеження

1. **Застереження про межу щодо людей (обов'язкова межа експерименту):**
   **Пілот на LLM не дає жодного висновку про зручність, зрозумілість або ергономіку KPOL для програмістів-людей.** LLM-учасники не замінюють людських програмістів, і батьківська Issue [#120](https://github.com/nick-fedchik/kuzmin-machine/issues/120) залишається відкритою для окремого людського етапу Q3.
2. **Обмеження охоплення:**
   - Перевірено 3 цільові задачі (`KPOL-CME-1` та `KPOL-CME-2`) на 3 моделях різних родин (`gemini-4-hydrogen`, `claude-sonnet-5.5`, `gpt-5.3-codex`) в одноразовому режимі (zero-shot, без ітеративного виправлення за помилками компілятора).
   - У межах пілота не перевірялися апаратна симуляція RTL (`iverilog`/Verilator) і запуск на платі PYNQ-Z1 (HIL); перевірка обмежується парсингом, профільним компілятором `compile_concept_microcode_bram_image`, CLI `compile_kpol_bram_image.py`, дизасемблюванням `CME-RAW-1` та еталонним `Interpreter` (`kpol_reference.py`).
   - Ізольованість учасників і відсутність у них викликів інструментів **спираються лише на самозвіт виконавця** `0.1.0`: дослівні промпти, час запуску сесій та ідентифікатори/логи викликів не збережено (R-02). У [`raw/prompt-inputs-snapshot.md`](data/q3-pilot-216/raw/prompt-inputs-snapshot.md) наведено лише відновлені входи (SHA-256 трьох специфікацій на `56c9abd`, SHA-256 `TASKS_PROMPT`).
3. **Відхилення від методу: заморожування не засвідчено Git (R-01, `AGENTS.md §3`).** Задачі, приймальні тести та відповіді сесій потрапили в Git **одним комітом** `5584f1f` (`2026-11-15T22:06:58+02:00`); окремого попереднього коміту із замороженням немає. Дотримання порядку «тести → сесії» засвідчують лише мітки часу в самих логах (`2026-11-15T22:00:58+02:00` у `freeze-and-negative-control-01.log`, `2026-11-15T22:05:44+02:00` у `pilot-acceptance-01.log`) і самозвіт виконавця; незалежно перевірити це за Git неможливо. Нового коміту заднім числом це не виправляє.
4. **Обмеження вибірки (R-05):**
   - Негативні контролі перевіряють лише мутанти **золотих розв'язків** (`<=` у `KPOL-CME-1`, межі `p < 9` та `p <= 99`, відсутній `Proof`, колізія операндів, каскад на старті), а не відповіді LLM.
   - Усі 9 програм (3 сесії × 3 задачі) пройшли (9/9): **стельовий ефект** — вибірка не розрізняє складність задач і моделей, і відсутність відмов не доводить, що специфікації однозначні.
   - Задача 1 перевіряє значення `Proof` лише опосередковано (через `verify_module` та `Interpreter`).

## 2. Метод

1. **Заморожування задач і приймальних тестів (до запуску сесій; за заявою виконавця, див. відхилення в §1 п. 3):**
   - Зафіксовано 3 задачі (`TASKS_PROMPT`) та незалежні приймальні перевірки (`check_task1`, `check_task2`, `check_task3`) у [`tasks_and_tests.py`](data/q3-pilot-216/tasks_and_tests.py) і [`test_q3_acceptance.py`](data/q3-pilot-216/tests/test_q3_acceptance.py).
   - Проведено негативний контроль: підтверджено, що тести падають на хибних розв'язках (непідтримуваний оператор `<=` в `KPOL-CME-1`, хибна межа охоронця, відсутній `Proof`, `CME2-OPERAND-COLLISION`, активний на старті каскад `CME2-CASCADE`). Сирий лог заморожування й негативного контролю: [`raw/freeze-and-negative-control-01.log`](data/q3-pilot-216/raw/freeze-and-negative-control-01.log).
2. **Ізольовані сесії LLM-агентів:**
   - Запущено 3 незалежні сесії `general-purpose` із суворою забороною доступу до репозиторію та інструментів.
   - У промпт кожної сесії передано виключно дослівний текст [`kpol-cme-subset.md`](../../../Engineering/specifications/kpol/kpol-cme-subset.md), [`kpol-cme2-profile.md`](../../../Engineering/specifications/kpol/kpol-cme2-profile.md) та розділів §2–4 [`kpol-consolidated.md`](../../../Engineering/specifications/kpol/kpol-consolidated.md), а також формулювання 3 задач.
   - Незмінні сирі відповіді збережено в `Research/studies/author-semantics/data/q3-pilot-216/raw/`; відновлені входи — у [`raw/prompt-inputs-snapshot.md`](data/q3-pilot-216/raw/prompt-inputs-snapshot.md) (дослівні промпти не збережено, див. §1).
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
| Q3-DEF-01 | Специфікація / синтаксис профілю | [`kpol-cme2-profile.md`](../../../Engineering/specifications/kpol/kpol-cme2-profile.md) §2 п. 4 | У тексті наведено псевдосинтаксис `rule R on Ev(p) when G { ... }`, хоча граматика фронтенду (`kpol-consolidated.md` §2.1) **не допускає** `(p)` після імені події в `rule` (`rule NAME on EVENT [when expression]`). | **Перевірено:** буквальна форма `rule R on Ev(p) when ...` відхиляється `Parser` (`KpolError: 7:17: expected '{', got '('`), форма без `(p)` компілюється ([`raw/repro-def01-def04-01.log`](data/q3-pilot-216/raw/repro-def01-def04-01.log)). **Не перевірено:** що це саме код `CME2-SYNTAX` у CLI (CLI на буквальній формі не запускався) і що учасники свідомо «проігнорували» `(p)` — сирі відповіді сесій цього не коментують. |
| Q3-DEF-02 | Специфікація / синтаксис профілю | [`kpol-cme2-profile.md`](../../../Engineering/specifications/kpol/kpol-cme2-profile.md) §2 п. 2 | Запис `State_i: Int32 = Init_i;` подано з великої літери `State`, хоча лексика чутлива до регістру і парсер вимагає `state` у нижньому регістрі. | Сесія 02 явно зафіксувала відсутність повної граматики в специфікації `KPOL-CME-2` і змушена була брати ключові слова з `kpol-consolidated.md`. |
| Q3-DEF-03 | Специфікація / повнота | [`kpol-cme2-profile.md`](../../../Engineering/specifications/kpol/kpol-cme2-profile.md) §2, §5 | Не наведено повної EBNF-граматики для `KPOL-CME-2` (включно з форматом `Proof` і обов'язковістю іменованих міток `NAME :` в `Invariants`). | Зауважено сесією 02 (`claude-sonnet-5.5`): довелося виводити синтаксис інваріантів і `step E(P = ...)` з `kpol-consolidated.md`. |
| Q3-DEF-04 | Діагностика / модель виконання | `kpol_reference.py` (`Interpreter.run` vs `kpol-cme-subset.md` §3) | Порушення інваріанта `S >= 0` у `Interpreter.run()` записується в `RunResult.diagnostics` (`"InvariantViolation:..."`), а **не** в `RunResult.rejected` (куди потрапляють `RejectedInput` і `RejectedHazard`), тоді як у RTL (`kpol_txn_gate_v2.sv`) це `rejected_o` (`rejected_invariant_o`). | Спостереження виконавця під час написання приймального тесту, **не результат LLM-сесій** і не порівняння зі специфікацією §3 дослівно. Поведінку відтворено: `rejected=[]`, `diagnostics=['InvariantViolation:NonNeg']` ([`raw/repro-def01-def04-01.log`](data/q3-pilot-216/raw/repro-def01-def04-01.log), скрипт [`repro_def01_def04.py`](data/q3-pilot-216/repro_def01_def04.py)). Чи це розбіжність зі специфікацією, а не прийнятий дизайн, не встановлено. |

## 4. Перевірка гіпотези / критеріїв

| Критерій | Очікувано | Отримано | Висновок |
| :--- | :--- | :--- | :--- |
| Заморожені задачі й тести до запуску сесій | Фіксація в Git до старту прогонів і доказ падіння на негативних прикладах | `4 passed` у `raw/freeze-and-negative-control-01.log` (золотий еталон + 3 негативні контролі); окремої Git-фіксації до сесій немає (відхилення, §1 п. 3) | Негативні контролі — виконано; порядок «замороження → сесії» — не підтверджено Git |
| $\ge 3$ ізольовані сесії LLM без доступу до репо | $\ge 3$ сирі файли з різних моделей із моделлю, датою й SHA | 3 сесії (`gemini-4-hydrogen`, `claude-sonnet-5.5`, `gpt-5.3-codex`); відсутність викликів інструментів — за самозвітом | Сирі файли — виконано; ізоляція — не підтверджена незалежно |
| Перевірка програм замороженими тестами | Усі результати задокументовано у `raw/` | 7/7 тестів (`9/9` програм) пройшли в `raw/pilot-acceptance-01.log` | Виконано |
| Класифікований реєстр дефектів і межа щодо людей | Наявний реєстр та явне застереження про непридатність висновку щодо людей | Зафіксовано 4 дефекти/неоднозначності (`Q3-DEF-01..04`; 01 і 04 відтворено, решта — за сирими відповідями сесії 02 та специфікаціями) і явне застереження в §1 | Виконано із зазначеними межами |

## 5. Відтворення

```bash
python3 -m pytest -v Research/studies/author-semantics/data/q3-pilot-216/tests/test_q3_acceptance.py
PYTHONPATH=Engineering/sw/kpol-ref python3 Research/studies/author-semantics/data/q3-pilot-216/repro_def01_def04.py
python3 -m pytest -q
KM_DRAFTS_REPO=/home/mfedchyk/GitHub/nick-fedchik/drafts python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
git diff --check origin/main..HEAD
```

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-15 | Перша редакція звіту пілота Q3 на ізольованих LLM-агентах (#216). |
| 0.1.1 | 2026-11-15 | Доопрацювання за рецензією PR #223 (R-01..R-05): відхилення щодо Git-замороження, ізоляція — за самозвітом, знімок входів, відтворення Q3-DEF-01/04, обмеження вибірки; прибрано зайвий порожній рядок у тесті. |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| WP | Work Product, результат роботи з визначеним призначенням. |
| CME | Concept Micro-Engine (`km_concept_micro_engine.sv`). |
| `CME-RAW-1` | 16-байтний формат дескриптора концепту в BRAM ($64 \times 16$ байтів). |
| EBNF | Розширена форма Бекуса — Наура. |
| HIL | Hardware-in-the-Loop, перевірка на фізичному обладнанні. |
