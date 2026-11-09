# Реєстр міграції PoC → MVP (`drafts/KuzminMachine` → `kuzmin-machine`)

* **Версія:** 0.3.3 (чернетка; потребує затвердження власником)
* **Дата:** 2026-11-09
* **Укладач:** Copilot (роль: Виконавець). Затверджує: Власник.
* **База:** план v0.2 укладено на `drafts@ecdc049`. **Фактичне перенесення — з `drafts@a4738bc`** (після завершення робіт Gemini). Тег `poc-final` у `drafts` не створено (зовнішня дія, рішення власника); посилання на неперенесене ведуть на `drafts@a4738bc`.
* **Обсяг:** 211 файлів без `raw/` і 298 файлів `raw/`.
* **Цільова структура:** фактична — [PROJECT-MANUAL §5.1](PROJECT-MANUAL.md#51-структура-репозиторію). Каталогу `verification/` немає: перевірка — у `hw/tb`, `hw/tests`, `sw/*/tests`, `experiments/`.
* **Мета MVP** (прийнято власником 2026-11-09): рефакторинг у три кроки та усунення п'яти прогалин PoC:
  1. незмінне ядро;
  2. взаємодія концептів без FSM, жорстко закодованих у RTL;
  3. справжній компілятор KPOL.

## 0. Виконання (v0.3.0, 2026-11-09)

Перенесення виконав [скрипт](migration/migrate_from_drafts.py) за словником `MAP` — він і є авторитетним переліком перенесеного (86 файлів + 298 сирих, разом 384). Ручні правки після скрипта — окремими комітами.

### 0.1. Відхилення від плану v0.2 (§3)

| Що | План v0.2 | Фактично | Чому |
| :--- | :--- | :--- | :--- |
| Демо-FSM `euclid`, `rcfc`, `cascade_arbiter`, `stream_pipeline` + tb | А | П\* → `hw/rtl/poc-demo/` | Їх інстанціює AXI-обгортка; без них не збираються бітстрім і AV-07/AV-08. Вилучити на S3 ([README](../hw/rtl/poc-demo/README.md)) |
| `km_io_trigger_engine` + tb + HIL | Р2 | П\* → `hw/rtl/io/`, `hw/boards/pynq-z1/hil/` | Р2 за рекомендацією: кандидат для прогалини 3 |
| `kpol_txn_gate_v2` + tb | Р3 (рекомендація — А) | П\* → `hw/rtl/core/` | F2 застарів: v2 тепер використовують `km_concept_micro_engine` і `kpol_reference.compile_verilog_interconnect`. Формально не верифіковано |
| `km_concept_micro_engine`, `km_autonomous_sequencer` + tb (Gemini, `1c2f3b7`) | — (з'явились після v0.2) | П\* → `hw/rtl/core/` | Кандидати для S3/S4. Формальної верифікації й AV-07 немає; Verilator `-Wall` — попередження (F13) |
| Gemini-обгортки `test_km_concept_micro_engine.py`, `test_km_autonomous_sequencer.py` | — | Не перенесено | Замінено загальним [`hw/tests/test_testbenches.py`](../hw/tests/test_testbenches.py) для всіх 11 тестбенчів |
| `build_pynq_z1_openxc7.sh`, `run_open_flow.sh`, Runbook | `hw/build/` | `hw/boards/pynq-z1/build_openxc7.sh`, `hw/scripts/run_open_flow.sh`, `hw/RUNBOOK.md` | Збірка прив'язана до плати |
| KPOL v0.1–v0.9 | Р6 (рекомендація — консолідувати, дельти в архів) | П\* → `specs/kpol/kpol-0.N.0.md` + [індекс](../specs/kpol/README.md) | Консолідація — Issue кроку S5; до неї дельти потрібні як вхід |
| `TRL-Assessment-Matrix` | П → `process/trl/matrix.md` (§3.8) і А (§3.10) — суперечність | А | Замінено [паспортом TRL](trl/TRL-passport.md) |
| Мемо застосувань v1.2, звіт наукової опозиції | П\* → `docs/trl-evidence/` | Так само | Докази TRL 2 |
| Копії топіків DOU | П (Р7) | [`docs/sources/author/dou/`](../docs/sources/author/dou/) | Лише текст автора; скрипт `docs/sources/fetch_dou.py` |
| `requirements.md`, `refactoring-plan.md` (Gemini, після v0.2) | — | П\* → `requirements/`, `architecture/` | Без Review Report. Перевірка — S2 |
| `VERSION` | — (версії тегами) | `VERSION` = `0.4.0` + теги `vX.Y.Z` | SemVer 2 (PROJECT-MANUAL §7) |

### 0.2. Що змінено вручну після скрипта

- Шляхи в скриптах AV-03/04/07/08, тестах `sw/`, `build_openxc7.sh`, `run_open_flow.sh`. Скрипти AV пишуть результати в каталог із змінної `AV0x_OUT_DIR`, тож повторний прогін не перезаписує прийняті звіти й сирі дані.
- `run_open_flow.sh`: симуляція через pytest; строгий лінт ядра; інформаційний лінт `poc-demo` і CME (F13).
- F11 виправлено в `docs/theory/formal-analysis.md` (версія 0.1.1). У `drafts` — не виправлено (Р8, потрібна команда власника).
- Шапки звітів AV: посилання на Review Report → `review.md`.

### 0.3. Повторні прогони в новому репо

| Перевірка | Результат | Збіг з `raw/` |
| :--- | :--- | :--- |
| `python3 -m pytest` | 76 пройдено, 1 очікуваний провал (F12); після PR #44 — без очікуваних провалів | — |
| AV-04 (`AV04_OUT_DIR=/tmp/…`), Z3 | `AV-04 OVERALL: PASS`; усі мутанти спростовано | Так (вердикти) |
| AV-07 (`AV07_OUT_DIR=/tmp/…`) | 22/22, mutation score 100 % | Так: стадія вбивства кожного мутанта збігається |
| AV-08 `analyze_av08.py` на перенесених сирих даних | Зведення ідентичне | Так, побайтно |
| AV-08 синтез nextpnr | Не запускали (години) | — |
| AV-03 вимірювання | Не запускали (потрібні jetson і pynq2); диференційний тест C ↔ Python пройдено | — |
| `bash hw/scripts/run_open_flow.sh` | Код виходу 0 | — |
| `python3 tools/check_links.py` | 0 битих посилань | — |

### 0.4. Нові знахідки

| # | Факт | Доказ |
| :--- | :--- | :--- |
| F2′ | Поправка до F2: `kpol_txn_gate_v2.sv` уже не «сирота». Його використовують `km_concept_micro_engine.sv`, `kpol_reference.compile_verilog_interconnect` і тест `test_v05_real_iverilog_interconnect_with_gate_v2`. Висновок F2 щодо доказовості лишається: AV-04 доводить лише v1 | grep; `drafts@1c2f3b7` |
| F12 | `kpol_txn_gate_axi_lite_tb.sv` падає: `upper bound default mismatch: 0x00000000` (рядок 242). Встановлено три причини: 1) регресія скидання `upper_bound_q` у `drafts@f5c65fc` (було `0x7FFFFFFF` у `7c904aa`); 2) застаріла перевірка DECERR на `0x2C`, де тепер REG_CYCLE_CNT_LO; 3) 6-бітні адреси в задачах тестбенча (не спричиняли цей провал, бо 13-бітне читання `0x1C` теж давало 0, але обрізали б адреси понад `0x3F`). Провал існував ще в `drafts@a4738bc`: старий `run_open_flow.sh` цей тестбенч не запускав. Виправлено в PR #44 | `#38`, `#42`, `#11`, PR #44; `iverilog` на знімку `drafts`; `xfail(strict=True)` у `hw/tests` (знято в PR #44) |
| F13 | Verilator `-Wall`: CME + секвенсер — 16 попереджень (порожні піни, урізання розрядності `%`), AXI-обгортка + `poc-demo` — 19. Ядро v1, v2, предикатор, BRAM — без попереджень | `run_open_flow.sh`, крок 3 |
| F14 | Мемо застосувань посилається на `reports/Подієві мови та пріоритет.md`, якого немає в `drafts@a4738bc`. Виправлено в PR (#13): звіт перенесено в `docs/trl-evidence/event-languages-prior-art.md` | `git ls-tree` |
| F15 | Твердження §6 п. 3 «жодного посилання `file:///` — **так**» хибне: лишилися 4 посилання `file:///home/mfedchyk/...` — `docs/toolchain/xc7.md` (рядки 227–229) і `architecture/refactoring-plan.md` (рядок 64). Цілі поза репозиторієм, тож скрипт міграції їх не переписав, а `check_links.py` пропускав будь-яку схему | grep; Issue #31 |

## 1. Критерії та статуси

| Статус | Значення | Критерій |
| :--- | :--- | :--- |
| **П** | Перенести | Актуальна остання версія, яку використовує збірка або експеримент. Звіт має незалежний Review Report. Тест має вміти впасти |
| **П\*** | Перенести з умовою | Потрібне, але з відомою вадою. Умова записується як Issue в новому репо |
| **А** | Архів PoC | Лишається в `drafts`. Новий репо посилається на `drafts@a4738bc`. Застаріле, замінене, без рецензії або бутафорія |
| **Д** | Лишити в `drafts` | Публікації, бізнес, опозиція — не розробка |
| **Р** | Рішення власника | Обидва варіанти мають підстави |

Загальні правила перенесення:

* лише поточний стан файла, без історії `drafts`;
* абсолютні посилання `file:///home/...` замінити відносними;
* посилання на архівні документи вести на `drafts@a4738bc` (тег `poc-final` — за рішенням власника).

## 2. Ключові факти, перевірені під час укладання

| # | Факт | Доказ |
| :--- | :--- | :--- |
| F1 | Бітстрім збирають з 11 файлів RTL. Верхній модуль — `kpol_txn_gate_pynq_z1_top` | `build_pynq_z1_openxc7.sh`, рядки 33–44 |
| F2 | `kpol_txn_gate_v2.sv` — «сирота»: його немає ні у збірці, ні в AV-04, AV-07 чи AV-08. Твердження «доведено для v2» неправдиве | grep по `*.py`, `*.sv`, `*.sh` |
| F3 | AV-07 покриває 7 модулів: gate, bram, euclid, io_trigger, rcfc, arbiter, pipeline. **Не покриває:** `km_predicate_evaluator`, `km_concept_bram_core`, `kpol_txn_gate_axi_lite`, top | `run_av07_mutation.py`, поле `rtl_file` |
| F4 | AV-07 v2.0 відтворено: 22/22. Але вердикт «Прийнято» в Review Report дописав автор виправлення, тобто це самоприйняття. Незалежної рецензії v2.0 немає | повторний прогін 2026-11-09; коміт `ecdc049` |
| F5 | 6 тестів `test_km_{bram_concepts,cascade_arbiter,euclid_hw,io_trigger,rcfc_stress,stream_pipeline}.py` лише читають закомічені JSON. Впасти вони не можуть: це **бутафорія** за AGENTS §4 | код тестів; 129 тестів проходять за 0,78 с |
| F6 | Специфікації KPOL v0.2–v0.9 — **дельти** (кожна додає можливості), консолідованої немає. `kpol_reference.py` у заголовку — «v0.1 draft», реалізує частини v0.5–v0.8 | заголовки файлів |
| F7 | Звіти QA v1.0–v1.3 і протокол фізичного стенда не мають Review Report. Статус «Hardware Verified» автори присвоїли собі самі | заголовки звітів |
| F8 | `KPOL_Verification_Program_Report` посилається на аудит як на свій Review Report. Але аудит **передував** звіту, тож рецензії самого звіту немає | заголовок звіту |
| F9 | `kuzmin_sva_checker.sv` має фіктивні порти й ні до чого не підключений | AV-04, Review Report |
| F10 | H4 (84 мкс) виміряно з Python через `pynq.MMIO`, тобто це не затримка шини | `benchmark_h4_latency_jitter.py` |
| F11 | **Хибна атрибуція.** Три документи посилаються на «Авторську технічну специфікацію М. Ю. Кузьміна (Київ / Харків, 2026)». Такого документа не існує. Матеріал, на який вони спираються, реконструював Микола Федчик з публікацій М. Ю. Кузьміна на DOU та з особистих розмов із ним (підтвердив власник 2026-11-09). Документи: `Formal-Analysis` (рядки 12, 24, 80, 167, 355), `Dossier` (рядок 1356), `High-Level-Language-Specification` (рядки 243, 899) | grep; свідчення власника |

## 3. Реєстр

### 3.1. Корінь і процес

| Файл | Статус | Куди | Підстава |
| :--- | :--- | :--- | :--- |
| `Kuzmin-Machine-Document-Review-and-Audit-Rules-UA.md` | П\* | `process/review-rules.md` | Чинні правила Report ↔ Review Report. Адаптувати шляхи до `experiments/AV-xx/` |
| `Kuzmin-Machine-Safety-and-Security-Standards-Position-UA.md` | П | `process/standards-position.md` | Чинна позиція |
| `Kuzmin-Machine-ASPICE4-Improvement-Steps-UA.md` | П\* | `process/aspice-steps.md` | Кроки К1–К9 частково реалізує `PROJECT-MANUAL`. Об'єднати й позначити виконане |
| `README.md` | А | — | Описує структуру PoC. Новий README пишеться заново |
| `MOVED.md` | — | — | Несанкціонований артефакт `b1d7981`. Не переносити |
| `pytest.ini` | — | — | Новий, з новими `testpaths` |
| `.github/skills/paperjury/**` (37) | Д | — | Скіл рецензування публікацій |

### 3.2. `01-concepts-and-theory`

| Файл | Статус | Куди | Підстава |
| :--- | :--- | :--- | :--- |
| `Kuzmin-Machine-ASN-Specification-UA.md` | Р1 | `docs/theory/asn.md` | Теоретична основа. Довідкова, не нормативна |
| `Kuzmin-Machine-Formal-Analysis-UA.md` | Р1 | `docs/theory/formal-analysis.md` | Те саме |
| `Kuzmin-Machine-Scientific-and-Engineering-Dossier-UA.md` | Д | — | Публікаційний документ на 170 КБ |
| `MEMO_CONTRIBUTIONS_AND_PARTICIPANTS_STATUS_UA.md` | Д | — | Організаційне. *Але:* внески й авторство можуть знадобитися для ліцензії → Р5 |
| `MEMO_KPOL_SOVEREIGN_STRATEGY_AND_EXTENDED_ROADMAP_UA.md` | Д | — | Стратегія, не інженерія |
| `MEMO_SCIENTIFIC_ROLE_FEDCHYK_AND_TURING_LANDSCAPE_UA.md` | Д | — | Публікаційне |

### 3.3. `02-engineering-hardware`: RTL і тестбенчі

| Файл | Статус | Куди | Підстава |
| :--- | :--- | :--- | :--- |
| `rtl/kpol_txn_gate.sv` + `tb/kpol_txn_gate_tb.sv` | **П** | `hw/rtl/core/`, `hw/tb/` | Ядро MVP. Покрите AV-04 (k-індукція), AV-07 і AV-08 |
| `rtl/km_predicate_evaluator.sv` | П\* | `hw/rtl/core/` | Ядро (лінія AV-08). Немає власного тестбенча і покриття AV-07 (F3) → Issue |
| `rtl/km_concept_bram.sv` + `tb/km_concept_bram_tb.sv` | П | `hw/rtl/core/`, `hw/tb/` | Пам'ять концептів (крок 1). AV-07 |
| `rtl/km_concept_bram_core.sv` | П\* | `hw/rtl/core/` | Немає покриття AV-07 (F3) → Issue |
| `rtl/kpol_txn_gate_axi_lite.sv` + tb | П\* | `hw/rtl/bus/`, `hw/tb/` | Потрібен для зв'язку з PS. Інстанціює 5 демо-FSM → прибрати їх під час кроку 1. Немає покриття AV-07 |
| `rtl/kpol_txn_gate_pynq_z1_top.v` | П\* | `hw/boards/pynq-z1/` | Верхній модуль бітстріму. Список модулів зміниться разом з AXI-обгорткою |
| `rtl/km_euclid_core.sv` + tb | **А** | — | Демо-FSM, жорстко закодоване під задачу (прогалина 1). Відтворюється з `poc-final` |
| `rtl/km_rcfc_engine.sv` + tb | **А** | — | Те саме. AV-08: `NUM_SLOTS` не впливає на ресурси |
| `rtl/km_cascade_arbiter_engine.sv` + tb | **А** | — | Те саме |
| `rtl/km_stream_pipeline_engine.sv` + tb | **А** | — | Те саме |
| `rtl/km_io_trigger_engine.sv` + tb | Р2 | `hw/rtl/io/` або А | Пін → рішення. Може стати основою для прогалини 3 (незалежність від PS) |
| `rtl/kpol_txn_gate_v2.sv` + tb | Р3 | — | «Сирота» (F2). Перенести як кандидата на ядро, лише якщо крок 1 базується на v2. Інакше — А |

### 3.4. `02-engineering-hardware`: збірка, плата, скрипти

| Файл | Статус | Куди | Підстава |
| :--- | :--- | :--- | :--- |
| `build_pynq_z1_openxc7.sh` | П\* | `hw/build/` | Відтворюваний маршрут openXC7. Оновити список RTL |
| `run_open_flow.sh` | П | `hw/build/` → основа для `ci.yml` | Лінтинг, симуляція й синтез без плати |
| `pynq_z1.xdc` | П | `hw/boards/pynq-z1/` | Обмеження плати |
| `VERSION` | — | — | Версії ведуться тегами |
| `deploy/kpol_direct_mmio_driver.py` + `04/test_kpol_direct_mmio.py` | П\* | `sw/runtime/pynq/` | Драйвер живий. Тест на mock — позначити як mock (AGENTS §4) |
| `pynq_z1_hw_predicate_eval_test.py`, `pynq_z1_bram_concepts_test.py`, `pynq_z1_manual_mmio_test.py` | П\* | `hw/boards/pynq-z1/hil/` | HIL для частин ядра. Переписати під нову карту регістрів |
| `pynq_z1_{euclid_hw,rcfc_stress,cascade_arbiter,stream_pipeline}_test.py` | А | — | HIL для демо-FSM |
| `pynq_z1_io_trigger_test.py` | Р2 | разом з `km_io_trigger_engine` | |
| `pynq_z1_led_interactive_demo.py`, `deploy/benchmark_kuzmin_machine_physical.py` | А | — | Демо |
| `benchmark_h4_latency_jitter.py` | А | — | Вимірює Python + MMIO (F10). Для прогалини 3 потрібна нова методика: пін → пін, логічний аналізатор |

### 3.5. `02-engineering-hardware`: документи

| Файл | Статус | Куди | Підстава |
| :--- | :--- | :--- | :--- |
| `Kuzmin-Machine-Open-Source-XC7-Toolchain-Architecture-UA.md` | П | `docs/toolchain/xc7.md` | Чинний опис інструментів |
| `Kuzmin-Machine-Open-Source-Verification-and-Synthesis-Runbook-UA.md` | П\* | `hw/build/RUNBOOK.md` | Звірити з фактичними скриптами |
| `Hardware_Procurement.md` | П\* | `hw/boards/bench-procurement.md` | Стенд «пін → рішення → пін» = прогалина 3 |
| `Kuzmin-Machine-FPGA-PYNQ-Z1-Architecture-UA.md` | Р4 | `architecture/hardware/` або А | 71 КБ про PoC з демо-FSM. Рекомендація: А, а архітектуру MVP писати заново |
| `Kuzmin-Machine-FPGA-Launch-Plan-UA.md` | А | — | План виконано |
| `MEMO-FPGA-KuzminMachine-openXC7-HIL-Execution.md`, `MEMO-FPGA-KuzminMachine-FirstAttempt-log.txt` | А | — | Історія |
| `Reports/Kuzmin-Machine-FPGA-Physical-Benchmark-Report-UA.md` | А | — | Без Review Report (F7) |
| `README.md`, `Reports/README.md`, `Review_Reports/README.md` | — | — | Індекси PoC |

### 3.6. `03-engineering-software`

| Файл | Статус | Куди | Підстава |
| :--- | :--- | :--- | :--- |
| `kpol_reference.py` + `test_kpol_reference.py` | П\* | `sw/kpol-ref/`, `sw/kpol-ref/tests/` | 44 справжні тести (gcc, iverilog). Звіт про виправлення без власної рецензії (F8). Основа для кроку 3 |
| `km_mcu_fpga_bridge.c` + `04/test_km_mcu_fpga_bridge.py` | П\* | `sw/runtime/mcu/` | Тест справді компілює й запускає. Потрібен для прогалини 3 (MCU замість PS) |
| `Kuzmin-Machine-KPOL-Language-v0.2…v0.9-Specification-UA.md` (8) | **Р6** | — | Дельти (F6). Див. Р6 |
| `Kuzmin-Machine-KPOL-Language-Draft-UA.md` | Р6 | — | База v0.1 |
| `Kuzmin-Machine-Compiler-and-Assembler-Architecture-UA.md` | П\* | `architecture/software/compiler.md` (вхід) | Прямий вхід для кроку 3. Позначити, що реалізовано, а що ні |
| `Kuzmin-Machine-Problem-Oriented-Language-Specification-UA.md`, `Kuzmin-Machine-High-Level-Language-Specification-UA.md` | А | — | Бачення, не реалізоване. Вхід для Р6 |
| `Kuzmin-Machine-Embedded-MCU-Runtime-Architecture-UA.md` | Р4 | `architecture/software/` або А | Стосується прогалини 3 |
| `Kuzmin-Machine-Reference-VM-and-Cycle-Accurate-Simulator-UA.md`, `Kuzmin-Machine-Live-Environment-and-Debugger-Protocol-UA.md`, `Kuzmin-Machine-Innovative-Programming-Paradigms-and-Tooling-UA.md` | А | — | Бачення поза MVP |
| `KPOL-Language-Evolution-and-Roadmap-Plan-UA.md`, `KPOL-Theoretical-Foundations-and-Canon-Pillars-UA.md` | А | — | Замінює Project Plan і Issues. Теорія — довідка в `poc-final` |
| `AUDITOR_PROMPT_KPOL_COMPILER_UA.md` | А | — | Замінює `ASPICE-Audit-Method` і skill `km-review` |
| `Reports/README.md`, `Review_Reports/README.md` | — | — | Індекси |

### 3.7. `04-verification-and-qa`: експерименти AV

| Файл | Статус | Куди | Підстава |
| :--- | :--- | :--- | :--- |
| `Reports/AV-03_SW_Gate_Decision_Report_UA.md` + Review | П | `experiments/AV-03/report.md`, `review.md` | Є незалежна рецензія |
| `benchmarks/av03_sw_gate/*` (5) + `raw/av03_*` (6) | П\* | `experiments/AV-03/scripts/`, `raw/` | Виправити SyntaxWarning `\,` у `run_av03.py` |
| `Reports/AV-04_Formal_Verification_Report_UA.md` + Review | П | `experiments/AV-04/` | Незалежна рецензія Gemini (не автор) |
| `benchmarks/av04_formal/*` (2) + `raw/av04_*` (131) | П | `experiments/AV-04/scripts/`, `raw/` | Сирі дані прийнятого звіту |
| `Reports/AV-08_Scaling_Report_UA.md` + Review | П | `experiments/AV-08/` | Незалежна рецензія Gemini |
| `benchmarks/av08_scaling/*` (2) + `raw/av08_*` (160) | П | `experiments/AV-08/scripts/`, `raw/` | |
| `Reports/AV-07_Mutation_Testing_Report_UA.md` + Review + `run_av07_mutation.py` + `raw/av07_mutation_results.json` | **П\*** | `experiments/AV-07/` | Потрібна незалежна рецензія v2.0 (F4). Після кроку 1 набір мутантів зміниться: 4 демо-FSM ідуть в архів |
| `Reports/KPOL_Verification_Program_Report_UA.md` | П\* | `experiments/KPOL-FIX/report.md` | Потрібен власний Review Report (F8) |
| `Review_Reports/KPOL-v0.2-v0.9_Audit_Review_Report_UA.md` | П | `specs/kpol/reviews/` | Незалежний аудит. Вхід для Р6 |

Шляхи в скриптах (`02-engineering-hardware/rtl`) після перенесення треба виправити. Результати перевіряються повторним прогоном у новому репо: це критерій Done для Issue міграції.

### 3.8. `04-verification-and-qa`: решта

| Файл | Статус | Куди | Підстава |
| :--- | :--- | :--- | :--- |
| `Reports/KUZMIN_MACHINE_QA_AND_VERIFICATION_TEST_REPORT_UA_v1.0…v1.3.md` (4) | А | — | Без рецензій (F7). v1.0 відкликано. Абсолютні посилання |
| `Reports/*_results.json` (7) | А | — | Немає хешу бітстріму й коміту. Не прив'язані до прийнятого звіту |
| `test_km_{bram_concepts,cascade_arbiter,euclid_hw,io_trigger,rcfc_stress,stream_pipeline}.py` (6) | **А, не переносити як тести** | — | Бутафорія (F5) |
| `test_km_domain_efficacy.py` | Д | — | Тестує `06/tco_calculator.py` |
| `km_static_analyzer.py` + `test_km_static_analyzer.py` | П\* | `sw/tools/static-analyzer/` | Справжні юніт-тести. Зв'язок з KPOL уточнити на кроці 3 |
| `Kuzmin-Machine-Static-Analysis-and-Termination-Checker-UA.md` | П\* | `sw/tools/static-analyzer/README.md` | Звірити з кодом |
| `kuzmin_sva_checker.sv` | А | — | Фіктивні порти (F9) |
| `Kuzmin-Machine-Experiment-Plan-Available-Hardware-UA.md` | П\* | `experiments/PLAN.md` | Чинний план AV. Виправити два розділи «6.1» |
| `Kuzmin-Machine-TRL-Assessment-Matrix-UA.md` | П | `process/trl/matrix.md` | Шкала TRL (ISO 16290, Brave1, NASA) |
| `KUZMIN_MACHINE_TRL_ASSESSMENT_MEMO_UA_v1.0.md` | А | — | Замінюється паспортом TRL на віхах |
| `Kuzmin-Machine-FPGA-Experiment-Backlog-UA.md` | А | → Issues | Відкриті пункти перетворити на Issues, документ не переносити |
| `Kuzmin-Machine-Verification-and-Benchmark-Suite-UA.md` | А | — | Перекрито планом AV |
| `Kuzmin-Machine-Domain-Efficacy-Verification-Plan-UA.md` | Д | — | Галузеве (06) |
| `AUDITOR_PROMPT_AV_EXPERIMENTS_UA.md` | А | — | Замінює `ASPICE-Audit-Method` |
| `README.md`, `TEST_REPORT.md`, `Reports/README.md`, `Review_Reports/README.md` | — | — | Індекси PoC |

### 3.9. `05`, `06`, `07`

| Файл | Статус | Підстава |
| :--- | :--- | :--- |
| `05/Kuzmin-Machine-Developers-Guide-UA.md` | А | Описує PoC. Для MVP — новий `docs/developers-guide.md` після кроку 1 |
| `05/Kuzmin-Machine-Expert-Systems-and-Knowledge-Engineering-UA.md` | Д | Застосування |
| `06-economic-model/**` (15) | Д | Бізнес |
| `07-scientific-opposition/**` (14) | Д | Опозиція й публікації |

### 3.10. Докази віх TRL 1 і TRL 2 (ISO 16290)

Чинні `TRL-Assessment-Matrix` і `TRL memo v1.0` оголошують TRL 1–3 «Завершено (100 %)» без жодного Review Report. Для доказів TRL 1 бере лише документ ASN, хоча це наша реконструкція, а не первинне джерело. Для TRL 2 — специфікацію HLL, тобто бачення.

Пропозиція: паспорт `process/trl/TRL-passport.md`, по одному розділу на рівень. Для кожного рівня в розділі:
- критерій ISO 16290;
- первинні докази;
- наші похідні документи;
- обмеження;
- незалежна рецензія.

| Рівень | Критерій ISO 16290 | Доказ | Тип | Статус | Куди |
| :--- | :--- | :--- | :--- | :--- | :--- |
| TRL 1 | Базові принципи спостережено й описано | Публікації М. Ю. Кузьміна на DOU (2020–2023): топіки 35914, 36556, 38994, 43177 | Первинне, зовнішнє | П: локальна копія (Markdown або PDF) + URL + дата доступу (Р7 вирішено) | `docs/sources/author/dou/` |
| TRL 1 | те саме | `07/Пример для АН.pptx` і `.pdf` (автор — Кузьмин Михаил Ювенальевич, 2024-05-21, 16 слайдів) | Первинне, авторське | П (Р7 вирішено) | `docs/sources/author/` |
| TRL 1 | те саме | Записи особистих розмов з автором (якщо є) | Первинне, усне | Р7: зафіксувати як «особисте спілкування, дата» | `docs/sources/author/` |
| TRL 1 | те саме | `01/Kuzmin-Machine-Formal-Analysis-UA.md` | Похідне (реконструкція М. Федчика) | Р1 → П **після виправлення F11** | `docs/theory/` |
| TRL 2 | Концепцію й застосування сформульовано | `01/Kuzmin-Machine-ASN-Specification-UA.md` | Похідне (формалізація концепції М. Федчиком) | Р1 → П | `docs/theory/` |
| TRL 2 | те саме | `03/Kuzmin-Machine-KPOL-Language-Draft-UA.md` (KPOL v0.1) | Похідне (концепція мови) | Р6 | `specs/kpol/` або `poc-final` |
| TRL 2 | Сформульовано застосування | `07/KUZMIN_MACHINE_APPLICATION_PROSPECTS_MEMO_UA_v1.2.md` | Похідне (застосування) | П\* (лише як доказ TRL 2; решта 07 — Д) | `docs/trl-evidence/` |
| TRL 2 | Критичний розгляд | `07/SCIENTIFIC_OPPOSITION_REPORT_UA.md` | Незалежна опозиція | П\* (як доказ, що концепцію критично розглянуто) | `docs/trl-evidence/` |
| TRL 1–3 | — | `04/Kuzmin-Machine-TRL-Assessment-Matrix-UA.md`, `KUZMIN_MACHINE_TRL_ASSESSMENT_MEMO_UA_v1.0.md` | Самооцінка | А; шкалу з Matrix перенести в паспорт | `process/trl/` |

Р7 вирішено 2026-11-09: авторські матеріали **зберігати** в репо (`docs/sources/author/`, лише для читання, із зазначенням джерела). Окремої авторської специфікації 2026 року немає (див. F11). Отже, джерела TRL 1 — лише публікації на DOU, `Пример для АН` і особисте спілкування з автором. Усе інше — похідні документи М. Федчика, і в паспорті їх так і треба позначати.

Помилка, яку виявлено під час перевірки: у тексті Gemini про PoC вказано «Сергій Кузьмін». За первинними джерелами автор — Михайло Ювенальевич Кузьмін (М. Ю. Кузьмін).

## 4. Підсумок

| Статус | Файлів (без `raw/`) | `raw/` |
| :--- | ---: | ---: |
| П | ≈ 16 | 297 (AV-03/04/08) |
| П\* | ≈ 30 | 1 (AV-07) |
| А | ≈ 75 | — |
| Д | ≈ 75 | — |
| Р | 18 | — |
| Індекси, не переносяться | ≈ 12 | — |

Отже, з 211 файлів переноситься ≈ 46. Ще 18 залежать від рішень власника.

## 5. Рішення власника

| # | Питання | Рекомендація |
| :--- | :--- | :--- |
| Р1 | Теорія ASN і формальний аналіз — у новий репо як довідка чи лише посилання на `poc-final`? | **Виконано за рекомендацією:** `docs/theory/` |
| Р2 | `km_io_trigger_engine` — основа для автономності від PS (прогалина 3) чи архів? | **Виконано за рекомендацією:** `hw/rtl/io/`; Issue на S6 |
| Р3 | Ядро кроку 1 будувати на `kpol_txn_gate.sv` (верифікований) чи на `v2` (не верифікований)? | Ядро — `kpol_txn_gate.sv`. **Змінено:** `v2` перенесено як кандидата (F2′); Issue на формальну верифікацію v2. Остаточно — рішення власника на S3 |
| Р4 | Великі архітектурні документи PoC (PYNQ-Z1 Architecture, MCU Runtime) — переносити чи писати MVP-архітектуру заново? | **Виконано за рекомендацією:** не перенесено; архітектура MVP — S2 |
| Р5 | Ліцензія та авторство нового репо: чи потрібен `MEMO_CONTRIBUTIONS` як основа `AUTHORS`/`NOTICE`? | Відкрито: окреме Issue |
| Р6 | KPOL: перенести 9 дельта-специфікацій чи консолідувати в одну `specs/kpol/kpol-v1.0-draft.md`? | **Змінено:** дельти перенесено як `kpol-0.N.0.md`; консолідація — Issue кроку S5 |
| Р7 | Первинні матеріали автора: копії чи посилання? | **Вирішено (2026-11-09):** зберігати копії в `docs/sources/author/`. Специфікації 2026 немає: це реконструкція М. Федчика (F11) |
| Р8 | Виправлення F11: у `drafts` (окремий коміт) чи лише в перенесених копіях? | **У новому репо виконано** (`formal-analysis.md` 0.1.1). У `drafts` — чекає команди власника. Рекомендація: в обох місцях. Замінити джерело на «Реконструкція М. Федчика з публікацій М. Ю. Кузьміна на DOU та особистого спілкування, 2026». Твердження «вийти за межі гіпотетичних реконструкцій» (`Formal-Analysis`, рядок 12) прибрати |

## 6. Порядок виконання

1. ~~Тег `poc-final`~~ — не створено; база — `drafts@a4738bc`. Рішення власника.
2. Issue «S1: Міграція PoC → структура MVP» → гілка `chore/<N>-migrate-poc` → PR з `Closes #<N>`.
3. Done для PR міграції (§0.3):
   - `run_open_flow.sh` зелений — **так**;
   - повторні прогони AV-04, AV-07 і AV-08 збігаються з `raw/` — **так** (синтез AV-08 не повторювали);
   - жодного посилання `file:///` і битих відносних посилань — **ні** — 4 посилання, виправлено в #31;
   - CI зелений — перевіряється в PR.
4. Окремі Issues на всі П\*, відкриті Р і знахідки F3, F4, F7, F8, F12 (виправлено, #44), F13, F14 (виправлено, #13).

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-09 | Перша редакція (Copilot). На підставі `drafts@ecdc049`, повторного прогону AV-07 і прогону `pytest` |
| 0.2.0 | 2026-11-09 | Додано розділ 3.10 (докази TRL 1 і 2), F11 (хибна атрибуція «специфікації 2026»), Р7 вирішено, Р8 відкрито |
| 0.3.0 | 2026-11-09 | Розділ 0: фактичне виконання з `drafts@a4738bc`, відхилення від плану, ручні правки, повторні прогони, знахідки F2′, F12–F14. Р1, Р2, Р4 виконано; Р3, Р6 змінено; Р8 виконано в новому репо |
| 0.3.1 | 2026-11-09 | §6 п. 3: хибне твердження про відсутність `file:///` виправлено; §0.4 — знахідка F15 (#31) |
| 0.3.2 | 2026-11-09 | §0.4 F12: замінено спростовану гіпотезу про адреси на три встановлені причини; статус виправлено в PR #44 (#38, #42, #11); §0.3 і §6 п. 4 позначено (#38) |
| 0.3.3 | 2026-11-09 | §0.4 F14: звіт перенесено в `docs/trl-evidence/event-languages-prior-art.md`; §6 п. 4 позначено (#13) |
