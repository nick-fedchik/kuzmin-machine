# Інвентар Work Products

* **Версія:** 0.3.0 (робоча класифікація)
* **Дата:** 2026-11-12
* **Issue:** [#108](https://github.com/nick-fedchik/kuzmin-machine/issues/108)
* **База:** `5ab7a6b297cb0762f402265f6a9e4a89231cee94`, гілка #108; вихідний `main` після PR #107 — `898552ebb7b01e7836e8e1a657fb267b72604bfb`.

## Межі

За `git ls-files` на зазначеній базі відстежувалося 1153 файли, з них
146 Markdown-файлів. Каталог нижче охоплює їх як окремі документи або
явно перелічені групи, а інші матеріали — як пакети за призначенням.
Для класифікації переглянуто заголовки, структуру й вибраний зміст;
вибрані критичні документи й зв'язки розглянуто детальніше. Це **не**
посторінкова рецензія всіх тверджень, перевірка кожної редакції або
пофайлова класифікація 1007 файлів інших форматів. Сирі файли
розглянуто на рівні пакетів і маніфестів, не по одному.

Наявність файла у Git або в таблиці не означає прийняття його змісту.
Пропозиції нижче не є дозволом на видалення чи переміщення. Статус
відображає джерело та наявні застереження, а не незалежну атестацію.

## 1. Вибрані результати

| WP або пакет | Основний тип | Стан і призначення | Пропозиція |
|---|---|---|---|
| Копії публікацій автора: [35914](../sources/author/dou/dou-35914.md), [36556](../sources/author/dou/dou-36556.md), [38994](../sources/author/dou/dou-38994.md), [43177](../sources/author/dou/dou-43177.md) | Source | Первинні джерела; походження й авторство описано в [індексі](../sources/README.md) | Зберегти для читання; не приписувати похідні висновки автору |
| [Авторська презентація](../sources/author/kuzmin-2024-example-for-AN.pptx) та її [PDF](../sources/author/kuzmin-2024-example-for-AN.pdf) | Source | Одне джерело у двох форматах; дата й обмеження метаданих — в індексі джерел | Зберегти обидва формати й походження |
| [Формальний розбір](../theory/formal-analysis.md) | Report / Analysis | Похідний аналіз; у [навігації досліджень](../research/README.md) позначений як чинна редакція | Залишити як аналіз, не ототожнювати з первинною специфікацією автора |
| [Звіт про семантику #76](../research/theory/formal-semantics-76-report.md) | Report / Analysis | Нове похідне дослідження; повної семантики не виведено, незалежної рецензії за шапкою немає | Залишити як окремий результат; CI-12; не називати повною специфікацією |
| [Звіт про ескіз машини Тьюринга #77](../research/theory/turing-completeness-77-report.md) | Report / Analysis | Нове похідне дослідження; висновок обмежений конкретним авторським ескізом, незалежної рецензії за шапкою немає | Залишити разом із посиланнями на джерела; не поширювати висновок на всі можливі моделі |
| [Реєстр вимог](../../requirements/requirements.md) | Register | Перенесений матеріал зі старими шляхами і неперевіреними статусами | Зберегти як вхід для перегляду #5; CI-01 |
| [KPOL v0.1](../../specs/kpol/kpol-0.1.0.md) | Specification | Проєктна пропозиція з обмеженою виконуваною підмножиною | Зберегти; врахувати при консолідації #19; CI-02 |
| Дельти KPOL: [v0.2](../../specs/kpol/kpol-0.2.0.md), [v0.3](../../specs/kpol/kpol-0.3.0.md), [v0.4](../../specs/kpol/kpol-0.4.0.md), [v0.5](../../specs/kpol/kpol-0.5.0.md), [v0.6](../../specs/kpol/kpol-0.6.0.md), [v0.7](../../specs/kpol/kpol-0.7.0.md), [v0.8](../../specs/kpol/kpol-0.8.0.md), [v0.9](../../specs/kpol/kpol-0.9.0.md) | Specification | Вісім окремих взаємопов'язаних специфікацій із різними темами; консолідованої редакції немає | Зберегти до рішення #19; не вважати самопозначення «нормативна» підтвердженням повноти чи реалізації; CI-03 |
| [План архітектурного рефакторингу](../../architecture/refactoring-plan.md) | Plan | У документі зазначено затверджений робочий план; актуальність і реалізацію треба оцінювати окремо | Залишити; перегляд охоплено #5; CI-04 |
| [Опис архітектури компілятора](../../architecture/software/compiler.md) | Design | Похідний інженерний опис; відповідність поточній реалізації не встановлено | Залишити як вхід для проєктування та зіставити з кодом; CI-05 |
| [Референсна реалізація KPOL](../../sw/kpol-ref/kpol_reference.py) | Source Code | Дослідна реалізація, а не повний компілятор МК | Залишити; CI-06; оцінювати разом зі специфікацією та тестами |
| [Тести референсної реалізації](../../sw/kpol-ref/tests/test_kpol_reference.py) | Source Code | Перевірки реалізації; сам факт наявності тестів не встановлює повного покриття | Залишити; CI-07; співвіднести з вимогами в межах #5 та #19 |
| [RTL шлюзу v1](../../hw/rtl/core/kpol_txn_gate.sv) | Source Code | Об'єкт формальної перевірки AV-04 у межах зазначених там умов | Залишити з його доказами; CI-08 |
| [RTL шлюзу v2](../../hw/rtl/core/kpol_txn_gate_v2.sv) | Source Code | Інший варіант; AV-04 не є автоматично доказом для v2 | Залишити; CI-09; питання верифікації або відмови від v2 — #18 |
| PYNQ-Z1 BRAM pipeline: [збірка](../../hw/boards/pynq-z1/build_bram_pipeline.sh), [top](../../hw/boards/pynq-z1/kpol_bram_pipeline_pynq_z1_top.v), [XDC](../../hw/boards/pynq-z1/kpol_bram_pipeline.xdc) | Configuration | Три конкретні входи збірки; інші залежності та обладнання потребують ідентифікації для відтворення | Залишити; CI-10; визначати повний склад для конкретної бази |
| [Звіт AV-04](../../experiments/AV-04/report.md) і [рецензія](../../experiments/AV-04/review.md) | Report | Звіт і окрема рецензія на перевірку RTL v1; метод та обмеження — у звіті | Зберегти з пов'язаними сирими даними; CI-11 стосується звіту |
| [Нова база відтворення AV #75](../../process/validation/75-reproduce-av/baseline-report.md) | Report | Описує окрему базу AV за рішенням власника; не підтверджує старий запуск і не є базою MVP | Зберегти з [протоколом](../../process/validation/75-reproduce-av/baseline-protocol.md) та [маніфестом](../../process/validation/75-reproduce-av/baseline-20261111/manifest.json) |
| [Паспорт TRL](../../process/trl/TRL-passport.md) | Report / Assessment | Самооцінка; обмеження незалежності рецензії наведено в документі | Залишити як самооцінку; CI-13 |
| [Економічний аналіз](../business/economic-analysis.md) | Report / Analysis | Історичний текст, винесений з README; прогнози та шляхи потребують перевірки | Залишити як історичний аналіз; не подавати прогнози як встановлені факти |
| [Проєктний опис статичного аналізатора](../../sw/tools/static-analyzer/design-analysis.md) | Design | Похідний математичний і проєктний опис, винесений з README | Залишити з [навігацією](../../sw/tools/static-analyzer/README.md); окремо перевіряти заявлені можливості |
| Історичні QA-звіти: [v1.0](../archive/verification/Reports/KUZMIN_MACHINE_QA_AND_VERIFICATION_TEST_REPORT_UA_v1.0.md), [v1.1](../archive/verification/Reports/KUZMIN_MACHINE_QA_AND_VERIFICATION_TEST_REPORT_UA_v1.1.md), [v1.2](../archive/verification/Reports/KUZMIN_MACHINE_QA_AND_VERIFICATION_TEST_REPORT_UA_v1.2.md), [v1.3](../research/verification/Reports/KUZMIN_MACHINE_QA_AND_VERIFICATION_TEST_REPORT_UA_v1.3.md) | Report | Історичні редакції; їхні самопозначення не підтверджені міграцією | v1.0–v1.2 перенесено до архіву, v1.3 залишено в дослідженнях; не зводити редакції автоматично (#110) |
| Мемо перспектив: [v1.0](../archive/opposition/KUZMIN_MACHINE_APPLICATION_PROSPECTS_MEMO_UA_v1.0.md), [v1.1](../archive/opposition/KUZMIN_MACHINE_APPLICATION_PROSPECTS_MEMO_UA_v1.1.md), [v1.2.1](../trl-evidence/application-prospects-memo.md) | Report / Analysis | Пов'язані редакції; v1.2.1 перенесено з файла v1.2 | v1.0–v1.1 перенесено до архіву, v1.2.1 залишено на місці; не вважати їх дублікатами (#110) |

CI-01…CI-13 — посилання на записи реєстру CI, а не твердження про
затверджену базову конфігурацію або призначення відповідальних.

## 2. Інші документи за призначенням

У групових рядках кожне посилання — окремий документ; спільна пропозиція
стосується кожного з них. «Історичний» нижче означає походження та час
матеріалу, а не рішення перемістити його в архів.

### 2.1. Навігація, правила та шаблони

| Документи | Основний тип | Стан і пропозиція |
|---|---|---|
| [Кореневий README](../../README.md), [джерела](../sources/README.md), [дослідження](../research/README.md), [бізнес](../business/README.md), [KPOL](../../specs/kpol/README.md), [PoC RTL](../../hw/rtl/poc-demo/README.md), [аналізатор](../../sw/tools/static-analyzer/README.md), [шаблони WP](../../process/templates/work-products/README.md) | Guide | Навігаційні входи; зберегти біля відповідних матеріалів і підтримувати посилання |
| [CLAUDE.md](../../CLAUDE.md), [GEMINI.md](../../GEMINI.md) | Guide | Перенаправляють до спільних правил агентів; залишити без дублювання правил |
| [AGENTS.md](../../AGENTS.md), [настанова](../../process/PROJECT-MANUAL.md), [правила рецензування](../../process/review-rules.md), [позиція щодо стандартів](../../process/standards-position.md), [межа репозиторіїв](../PUBLICATION-BOUNDARY.md) | Policy | Правила й межі проєкту; застосовувати з урахуванням власника та зазначеної версії; розбіжність S3 — §5 |
| [Конфігурація WP](work-products.md), [каталог WI](../../process/work-items.md) | Policy | Проєктні угоди про види й розміщення; не вважати самі угоди доказом виконання |
| [Реєстр CI](../../process/configuration-items.md), [реєстр міграції](../../process/MIGRATION-REGISTER.md), [цей інвентар](work-product-inventory.md) | Register | Реєстри різних сутностей: обрані кандидати CI, походження міграції та класифікація WP; не зливати в один |
| [Шаблон PR](../../.github/pull_request_template.md), [шаблон звіту](../../process/templates/report.md), [шаблон рецензії](../../process/templates/review.md) | Template | Форми робочого процесу; зберегти як шаблони, а не приклади виконаної роботи |
| Шаблони WP: [аналіз](../../process/templates/work-products/analysis-report.md), [рішення](../../process/templates/work-products/decision.md), [дизайн](../../process/templates/work-products/design.md), [посібник](../../process/templates/work-products/guide.md), [модель](../../process/templates/work-products/model.md), [план](../../process/templates/work-products/plan.md), [питання](../../process/templates/work-products/problem.md), [протокол](../../process/templates/work-products/protocol.md), [вимога](../../process/templates/work-products/requirement.md), [специфікація](../../process/templates/work-products/specification.md) | Template | Допоміжні форми; не створювати продукти лише для заповнення форми |
| [Кроки ASPICE](../../process/aspice-steps.md) | Plan | Історичний план за PAM 4.0; не переписувати як оцінку 4.1 без окремої перевірки |
| [Метод аудиту](../../process/audit/ASPICE-Audit-Method.md) | Protocol | Методика для PAM 4.0 та TRL; зберегти з версією моделі |
| [Аудит v0.5.1](../../process/audit/reports/Audit-2026-11-11-v0.5.1.md), [рецензія TRL](../../process/trl/reviews/review-trl-passport-s1-s2.md), [рецензія міграції](../../process/migration/review.md) | Report / Review | Результати для конкретних зрізів; зберегти об'єкт, дату й обмеження рецензії |
| [Звіт міграції #84](../../process/migration/publication-84/report.md), [звіт походження #59](../../process/validation/59-report-provenance/report.md) | Report | Результати конкретних робіт; негативні висновки та межі не переписувати |

### 2.2. Дослідження і історичні матеріали

У перенесених читабельних копіях попередження про міграцію не підтверджує
заявлених там статусів. Оригінали й походження — у
[маніфесті](../../process/migration/publication-84/manifest.json) та
[архіві](../archive/drafts-774d575-kuzminmachine.tar.gz).

| Документи | Основний тип | Стан і пропозиція |
|---|---|---|
| [Досьє](../research/theory/Kuzmin-Machine-Scientific-and-Engineering-Dossier-UA.md), [споріднені машини](../research/theory/Similar_Machines_to_KM.md), [роль і науковий ландшафт](../research/theory/MEMO_SCIENTIFIC_ROLE_FEDCHYK_AND_TURING_LANDSCAPE_UA.md), [попередники подієвих мов](../trl-evidence/event-languages-prior-art.md), [зведена наукова опозиція](../trl-evidence/scientific-opposition-report.md) | Report / Analysis | Похідні аналітичні роботи; залишити окремо від джерел, перевіряти сильні твердження |
| [Переклад праці про концепт-орієнтоване програмування](../research/theory/Concepts_And_Concept-Oriented_Programming_UA.md) | Source | Сторонній авторський матеріал у перекладі; зберегти авторство й перевірити права та походження окремо |
| [ASN-опис](../theory/asn.md) | Specification | Похідна пропозиція нотації й протоколу; не ототожнювати з авторським першоджерелом |
| [Запитання до автора](../research/opposition/SCIENTIFIC_OPPOSITION_QUESTIONS_TO_AUTHOR_UA_v1.0.md) | Problem | Проєкт питань для уточнення; наявність файла не означає, що автор відповів |
| [Протокол наукової опозиції](../research/opposition/SCIENTIFIC_OPPOSITION_PROMPT_UA.md), [промпт аудиту KPOL](../research/software/AUDITOR_PROMPT_KPOL_COMPILER_UA.md), [промпт аудиту AV](../research/verification/AUDITOR_PROMPT_AV_EXPERIMENTS_UA.md) | Protocol | Історичні інструкції перевірки; актуальність корпусу й інструментів оцінювати до повторного використання |
| Опозиція: [прохід 1 Opus](../research/opposition/opposition-passes/pass1-opus.md), [прохід 1 Sol](../research/opposition/opposition-passes/pass1-sol.md), [прохід 2 Opus](../research/opposition/opposition-passes/pass2-opus.md), [прохід 2 Sol](../research/opposition/opposition-passes/pass2-sol.md) | Report / Review | Окремі проходи й взаємні рецензії; зберегти відмінності, авторство та зв'язок зі зведенням |
| [Посібник розробника](../research/applications/Kuzmin-Machine-Developers-Guide-UA.md) | Guide | Історичний опис запропонованої мови; не інструкція гарантовано реалізованих можливостей |
| [Експертні системи](../research/applications/Kuzmin-Machine-Expert-Systems-and-Knowledge-Engineering-UA.md), [програмні парадигми](../research/software/Kuzmin-Machine-Innovative-Programming-Paradigms-and-Tooling-UA.md), [основи KPOL](../research/software/KPOL-Theoretical-Foundations-and-Canon-Pillars-UA.md) | Report / Analysis | Історичні дослідницькі судження; відокремити гіпотези від підтверджених реалізацій |
| [План запуску FPGA](../research/hardware/Kuzmin-Machine-FPGA-Launch-Plan-UA.md), [план еволюції KPOL](../research/software/KPOL-Language-Evolution-and-Roadmap-Plan-UA.md), [стратегія KPOL](../strategy/MEMO_KPOL_SOVEREIGN_STRATEGY_AND_EXTENDED_ROADMAP_UA.md) | Plan | Історичні плани й рішення у текстах; звірити з актуальними Issue, не вважати автоматично чинною дорожньою картою |
| [FPGA-архітектура](../research/hardware/Kuzmin-Machine-FPGA-PYNQ-Z1-Architecture-UA.md), [MCU runtime](../research/software/Kuzmin-Machine-Embedded-MCU-Runtime-Architecture-UA.md), [середовище й налагоджувач](../research/software/Kuzmin-Machine-Live-Environment-and-Debugger-Protocol-UA.md) | Design | Історичні проєктні пропозиції; реалізацію та актуальність перевіряти окремо |
| [Високорівнева мова](../research/software/Kuzmin-Machine-High-Level-Language-Specification-UA.md), [проблемно-орієнтована мова](../research/software/Kuzmin-Machine-Problem-Oriented-Language-Specification-UA.md), [еталонна VM](../research/software/Kuzmin-Machine-Reference-VM-and-Cycle-Accurate-Simulator-UA.md) | Specification | Історичні похідні проєкти; не вважати автоматично авторською або консолідованою специфікацією |
| [HIL-мемо](../research/hardware/MEMO-FPGA-KuzminMachine-openXC7-HIL-Execution.md), [звіт стенда](../research/hardware/Reports/Kuzmin-Machine-FPGA-Physical-Benchmark-Report-UA.md), [мемо TRL](../research/verification/KUZMIN_MACHINE_TRL_ASSESSMENT_MEMO_UA_v1.0.md), [матриця TRL](../research/verification/Kuzmin-Machine-TRL-Assessment-Matrix-UA.md) | Report | Історичні описи й оцінки; твердження і межі звіряти із сирими даними та поточним паспортом |
| [Програма доменної ефективності](../research/verification/Kuzmin-Machine-Domain-Efficacy-Verification-Plan-UA.md), [беклог FPGA](../research/verification/Kuzmin-Machine-FPGA-Experiment-Backlog-UA.md), [набір верифікації](../research/verification/Kuzmin-Machine-Verification-and-Benchmark-Suite-UA.md) | Plan | Історичні плани з твердженнями про виконання; не сприймати як поточний стан експериментів без перевірки |
| [Індекс історичних QA-звітів](../research/verification/TEST_REPORT.md) | Guide | Навігація до v1.0–v1.3 без висновку про поточний стан; історичний оригінал збережено в архіві (#110) |

### 2.3. Бізнес, обладнання і засоби

| Документи | Основний тип | Стан і пропозиція |
|---|---|---|
| [План бізнесу](../business/Business_Development_Plan.md) | Plan | Історичний сценарій; не підтверджує здійснення заходів |
| [Обґрунтування бізнесу](../business/Business_Feasibility_Study.md), [патентування та комерціалізація](../business/commercialization-models-and-patent-strategy.md) | Report / Analysis | Історичні економічні припущення та альтернативи; перевірити перед використанням у рішеннях |
| [Автомобільна сфера](../archive/business/automotive-safety-cybersecurity.md), [авіоніка](../archive/business/avionics-safety-critical.md), [медицина](../archive/business/medicine-biomedical-devices.md), [маркетинг](../archive/business/martech-realtime-bidding.md), [логістика](../archive/business/logistics-warehouse-coldchain.md), [оборонна сфера](../archive/business/miltech-defense-aerospace.md), [гральна індустрія](../archive/business/gambling-fairness-rng-integrity.md), [ризики ставок](../archive/business/sports-betting-realtime-risk.md) | Report / Analysis | Галузеві сценарії архівовано за рішенням власника (#110); це не підтвердження переваги чи відповідності стандартам |
| [Гранти та звітність](../business/ukrainian-grants-funding-and-reporting-guide.md) | Guide | Історичний довідник; умови програм потрібно звіряти з офіційними джерелами |
| [Внески та учасники](MEMO_CONTRIBUTIONS_AND_PARTICIPANTS_STATUS_UA.md) | Report / Analysis | Матеріал про атрибуцію; рішення про ліцензію та авторство — #20 |
| [Інструкція XC7](../toolchain/xc7.md), [апаратний runbook](../../hw/RUNBOOK.md) | Guide | Інструкції до інструментів; перед виконанням звірити команди й версії середовища |
| [Комплектація стенда](../../hw/boards/bench-procurement.md), [аркуш замовлення](../../hw/boards/radiomag-order-a4.md) | Plan | Закупівельні документи на визначену дату; перед використанням звірити фактичну наявність, ціни та статус |

### 2.4. Перевірки, протоколи й результати

| Документи | Основний тип | Стан і пропозиція |
|---|---|---|
| [План AV](../../experiments/PLAN.md) | Plan | План із попередньою реєстрацією; не підміняти результати планом |
| [AV-03 звіт](../../experiments/AV-03/report.md), [AV-03 рецензія](../../experiments/AV-03/review.md) | Report | Рецензія обмежує прийняття частини вимірювань; читати разом із сирими даними |
| [AV-07 звіт](../../experiments/AV-07/report.md), [рецензія](../../experiments/AV-07/review.md), [AV-08 звіт](../../experiments/AV-08/report.md), [рецензія](../../experiments/AV-08/review.md) | Report | Окремі результати й рецензії; зберегти джерельні дані, методи та невдалі випадки |
| [KPOL-FIX](../../experiments/KPOL-FIX/report.md), [аудит дельт KPOL](../../specs/kpol/reviews/kpol-0.2-0.9-audit-review.md) | Report | Історія виправлень та окремий аудит; не замінюють консолідовану специфікацію #19 |
| #60 Hazard: [протокол](../../process/validation/60-fail-closed/protocol.md), [звіт](../../process/validation/60-fail-closed/report.md); U32: [протокол](../../process/validation/60-spec-conformance/u32-protocol.md), [звіт](../../process/validation/60-spec-conformance/u32-report.md); imports: [протокол](../../process/validation/60-spec-conformance/namespace-import-protocol.md), [звіт](../../process/validation/60-spec-conformance/namespace-import-report.md) | Protocol і Report | Кожна пара має власні межі; зберегти разом із відповідними `raw` |
| #75 перший повтор: [протокол](../../process/validation/75-reproduce-av/protocol.md), [звіт](../../process/validation/75-reproduce-av/report.md); RCFC: [протокол](../../process/validation/75-reproduce-av/rcfc-source-match-protocol.md), [звіт](../../process/validation/75-reproduce-av/rcfc-source-match-report.md) | Protocol і Report | Історичний повтор з розбіжністю та окрема перевірка джерела; не переписувати після створення нової бази |

### 2.5. Пакети коду, конфігурацій і даних

| Пакет | Типи WP і призначення | Пропозиція |
|---|---|---|
| [`hw/rtl/core/`](../../hw/rtl/core/), [`bus/`](../../hw/rtl/bus/), [`io/`](../../hw/rtl/io/), [`poc-demo/`](../../hw/rtl/poc-demo/README.md) | Source Code: компоненти ядра, шинні обгортки, ввід/вивід та задачні FSM | Зберегти зв'язки модулів; долю PoC визначає #6 після перевірки залежностей |
| [`hw/tb/`](../../hw/tb/), [`hw/tests/`](../../hw/tests/) | Source Code: тестбенчі, тестові програми й перевірки | Зберегти разом із предметом тестів; наявність тесту не доводить потрібного покриття |
| [`hw/boards/pynq-z1/`](../../hw/boards/pynq-z1/), [`hw/scripts/`](../../hw/scripts/) | Configuration / Source Code: конфігурації, top, обмеження, збірка та HIL-скрипти | При відтворенні фіксувати потрібні RTL, інструменти, бітстрім і обладнання |
| [`sw/kpol-ref/`](../../sw/kpol-ref/), [`sw/runtime/`](../../sw/runtime/), [`sw/tools/static-analyzer/`](../../sw/tools/static-analyzer/README.md) | Source Code: референс, драйвери, інструмент і тести | Зберегти як різні компоненти; їхня наявність не підтверджує повного компілятора |
| [`docs/business/tco_calculator.py`](../business/tco_calculator.py) і [тести](../business/test_tco_calculator.py) | Source Code: сценарний калькулятор та перевірки | Зберегти з економічними припущеннями; формула не підтверджує вхідних даних |
| [`tools/`](../../tools/), [міграційні скрипти](../../process/migration/) | Source Code: перевірки, тестування та перенесення | Зберегти з тестами й описом контракту [походження звітів](../../tools/report-provenance.md) |
| [Автоматизація GitHub](../../.github/), [конфігурація pytest](../../pytest.ini), [виключення Git](../../.gitignore), [VERSION](../../VERSION) | Configuration / Template: CI, форми Issue, налаштування тестів, правила Git та версія | Зберегти; оцінювати вплив перед зміною, а не класифікувати як дослідницькі результати |
| [`experiments/AV-03/`](../../experiments/AV-03/), [`AV-04/`](../../experiments/AV-04/), [`AV-07/`](../../experiments/AV-07/), [`AV-08/`](../../experiments/AV-08/) | Report / Protocol / Source Code / Data: звіти, рецензії, скрипти й сирі дані конкретних перевірок | Зберегти пакети й походження; не прибирати негативні результати чи однакові файли лише за хешем |
| [`process/validation/`](../../process/validation/) | Protocol / Report / Source Code / Data: окремі перевірки #59, #60, #75 і їхні журнали | Зберегти разом протоколи, скрипти, маніфести та конкретні `raw` кожного запуску |
| [Архів міграції](../archive/drafts-774d575-kuzminmachine.tar.gz) і [маніфест](../../process/migration/publication-84/manifest.json) | Data / Register: історичний знімок та пофайлове походження | Зберегти як пару; архів не є автоматично робочою версією кожного файла |

## 3. Відкриті Work Items

Перевірено назви, описи, мітки та Project усіх 18 відкритих Issue
2026-11-12. Наведені стани — знімок, а не поточний реєстр. Зміст
технічних тверджень у кожній Issue повторно не відтворювався.

| Issue | Вид і стан Project | Результат / пропозиція |
|---|---|---|
| [#108](https://github.com/nick-fedchik/kuzmin-machine/issues/108) | Task, In progress | Цей інвентар і погоджені уточнення; залишити однією задачею |
| [#5](https://github.com/nick-fedchik/kuzmin-machine/issues/5) | Task, Postponed | Вимоги й архітектура MVP; використовувати наявну задачу |
| [#6](https://github.com/nick-fedchik/kuzmin-machine/issues/6) | Task, Postponed | Незмінне ядро і перевірки; питання критерію S3 — у §5 |
| [#7](https://github.com/nick-fedchik/kuzmin-machine/issues/7) | Task, Postponed | Дві програми на одному бітстрімі; зберегти як окремий результат S4 |
| [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8) | Task, Postponed | Компілятор в образ BRAM; пов'язаний із консолідацією #19 |
| [#9](https://github.com/nick-fedchik/kuzmin-machine/issues/9) | Task, Postponed | Автономність від PS і апаратні вимірювання S6 |
| [#19](https://github.com/nick-fedchik/kuzmin-machine/issues/19) | Task, Postponed | Консолідація специфікації KPOL; не створювати дубль |
| [#20](https://github.com/nick-fedchik/kuzmin-machine/issues/20) | Task, Postponed | Ліцензія та авторство; рішення власника за наявним питанням, не висновок із самого мемо |
| [#18](https://github.com/nick-fedchik/kuzmin-machine/issues/18) | Finding, Postponed | Верифікація v2 або відмова від нього в MVP; не переносити на нього доказ v1 |
| [#21](https://github.com/nick-fedchik/kuzmin-machine/issues/21) | Finding, Todo | Атрибуція у `drafts`; коміт в іншому репозиторії лише за окремою командою власника |
| [#48](https://github.com/nick-fedchik/kuzmin-machine/issues/48) | Finding, Postponed | Потрібна специфікація карти регістрів з трасуванням на тести й драйвери |
| [#62](https://github.com/nick-fedchik/kuzmin-machine/issues/62) | Experiment, Postponed | Fail-closed: конкретна формальна перевірка; у тексті пов'язано з #6 і #18 |
| [#64](https://github.com/nick-fedchik/kuzmin-machine/issues/64) | Experiment, Postponed; мітка `blocked` | Перевірка AXI4-Lite; у тексті зазначено #6 |
| [#67](https://github.com/nick-fedchik/kuzmin-machine/issues/67) | Experiment, Todo; мітка `blocked` | Anti-rollback; у тексті зазначено #7 і попередній негативний результат |
| [#68](https://github.com/nick-fedchik/kuzmin-machine/issues/68) | Experiment, Todo; мітка `blocked` | Перебір однобітових змін образу; у тексті зазначено #7 |
| [#72](https://github.com/nick-fedchik/kuzmin-machine/issues/72) | Experiment, Postponed | Фізична перевірка шляху без PS; у тексті зазначено #9 |
| [#73](https://github.com/nick-fedchik/kuzmin-machine/issues/73) | Experiment, Postponed; мітка `blocked` | Латентність пін→пін; поріг має визначити власник до запуску, у тексті зазначено #9 |
| [#80](https://github.com/nick-fedchik/kuzmin-machine/issues/80) | Experiment, Todo | Широка мета промислової перевірки; конкретний сценарій і критерії визначають до порівняння |

У перевірених описах #62, #64, #67, #68, #72 і #73 є текстове
«Батько», але API GitHub на дату огляду не повертає їм Parent Issue;
списки Sub-Issues #6, #7 і #9 порожні. Це не доказ відсутності
змістовної залежності. За потреби власник може оформити існуючі зв'язки
в GitHub; нові Issue для цього не потрібні. Мітка `blocked` і стан Project
`Todo` / `Postponed` — різні поля, не автоматична суперечність.
Мітки, зв'язки й статуси цим оглядом не змінено.

## 4. CI та межі відтворюваних баз

| Питання | Практична пропозиція / відкрите рішення |
|---|---|
| Склад CI-01…CI-13 | Поки це кандидати; власнику переглянути необхідність кожного, область впливу та зв'язки, не затверджувати всі за замовчуванням. Відповідальних за супровід у реєстрі ще немає. |
| База AV #75 | Є окрема відтворювана база з [маніфестом](../../process/validation/75-reproduce-av/baseline-20261111/manifest.json), вхідними хешами, еталонами й [протоколом](../../process/validation/75-reproduce-av/baseline-protocol.md). Пропозиція: розглянути маніфест і його зафіксовані еталони як конкретну групу для контролю; це не затвердження бази MVP і не доведення ідентичності історичного запуску. |
| Майбутня база MVP | Після рішень #5, #6, #8 і #19 визначити точні вимоги, специфікацію, обрані RTL/ПЗ, тести та конфігурацію збірки; залежності, інструменти, бітстрім і плату ідентифікувати окремо. Склад фіксувати комітом або тегом, не назвою рухомої гілки. |
| Відповідальність | Власник затверджує склад і зміну бази; супровід кожного CI призначається явним рішенням. Не записувати агента або людину відповідальним без такого рішення. |

## 5. Неоднозначності та кандидати на прибирання

| Знахідка і підстава | Пропозиція |
|---|---|
| У [настанові, S3](../../process/PROJECT-MANUAL.md#4-віхи-trl-і-маршрут-до-mvp) наведено поріг мутаційного бала 95 %, тоді як #6 повідомляє про скасування порогу власником і вимагає тестів, що виявляють конкретні дефекти. | Не застосовувати поріг автоматично. Узгодити текст настанови з рішенням власника за її §10; цим інвентарем правила не змінено. |
| [Історичний QA-індекс](../research/verification/TEST_REPORT.md) раніше називав v1.1 останньою чинною, хоча існують і v1.2–v1.3. | У #110 замінено на навігаційний індекс без тверджень про поточний статус; оригінал збережено у знімку. |
| Бізнес-аналіз, галузеві звіти й плани частково перетинаються; [аналіз](../business/economic-analysis.md) та історичні TRL-матеріали залишаються доступними. | Вісім галузевих сценаріїв перенесено до [архіву](../archive/README.md#галузеві-бізнес-сценарії) за рішенням власника (#110); інші матеріали не видалено. |
| [PoC RTL](../../hw/rtl/poc-demo/README.md) позначений до вилучення в S3, але використовується обгорткою та експериментами AV-07/08. | Не вилучати в #108; виконувати #6 після перевірки збірки, тестів і відтворення. |
| На базі інвентаря 146 Markdown-файлів не мають однакових Git-blob ідентифікаторів. Серед усіх файлів є 136 груп однакових blob, що охоплюють 413 шляхів; зокрема експериментальні дані можуть повторюватися у різних запусках. | Це технічна ознака байтової тотожності, не рішення про непотрібність: перевірити маніфести, посилання, походження й вимоги відтворення до будь-якого прибирання. |
| `docs/research/` змішує історичну міграцію та нові звіти; `docs/trl-evidence/` містить не лише TRL, а й опозицію та попередній рівень техніки; `process/validation/` і `experiments/` обидва містять перевірки. | Залишити наявні пакети й уточнені індекси; перенесення має сенс лише за конкретної потреби з оновленням посилань та збереженням походження. |

## 6. Що лишається перевірити

Потрібні рішення власника щодо CI, відповідальних і решти кандидатів на
прибирання, а також змістовне зіставлення історичних редакцій за потреби.
Повноту залежностей коду й зв'язків усіх сирих файлів не
доведено. Перед переміщенням або вилученням окремо перевіряють первинні
джерела, посилання, архів, маніфести та відтворюваність.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.1.0 | 2026-11-12 | Перша черга інвентаризації та зв'язків із наявними Issue. |
| 0.2.0 | 2026-11-12 | Додано огляд усіх Markdown-документів, пакетів даних і коду, відкритих WI, меж CI та кандидатів на окремий перегляд. |
| 0.3.0 | 2026-11-12 | Відображено рішення про архівування та оновлення QA-індексу (#110). |

## Абревіатури та глосарій

| Термін | Значення |
|---|---|
| WP | Work Product, робочий продукт |
| CI | Configuration Item, елемент конфігурації |
| WI | Work Item, відстежувана робота або питання |
| TRL | Technology Readiness Level, рівень готовності технології |
| RTL | Register Transfer Level, опис апаратної логіки |
