# Цілі, потреби та реєстр двонапрямного трасування

* **Версія:** 0.8.0 (робоча пропозиція)
* **Дата:** 2026-11-12
* **Issues:** [#118](https://github.com/nick-fedchik/kuzmin-machine/issues/118), [#5](https://github.com/nick-fedchik/kuzmin-machine/issues/5)
* **Виконавець:** GitHub Copilot CLI, Auto; конкретна модель середовищем не показана.
* **Рецензент:** ще не призначений.
* **База файлів першого зрізу:** `d99e549edb859bce849f2f95e44e380f1fc5df94`.
* **База продовження:** `82d55c8e4acc0af44672784ef5bd846b858b2723`.
* **База архітектурного уточнення (§14):** `236a251f528e441387f03247c0c5c662a90b9ab7`.

## 1. Межі та результат

Повної матриці S2, погоджених потреб і нової бази MVP поки **немає**.
Документ розширив перший зріз: тепер є відтворюваний огляд усіх Issues
репозиторію на дату продовження (§9), окрема доля 30 успадкованих REQ
(§10) і зворотне трасування вибраних технічних артефактів (§8).
Це все ще робоча пропозиція, а не затверджені вимоги, архітектура чи
рішення щодо статусів. Відкриті та закриті WI не редагувалися.

Історичні `REQ-*` наведено лише як кандидати: їхні `PASS` та заяви про
ASPICE не підтверджують виконання. Для кожного з них уже є
[обмежений огляд #114](../../docs/research/verification/requirements-trace-assessment-114.md).
Жодна таблиця нижче не стверджує, що існування файла або тесту доводить
усю вимогу, інноваційність чи працездатність усієї машини.

## 2. Зріз і спосіб читання

Збережено [знімок відкритих Issues](open-issues-2026-11-12.json),
отриманий 2026-11-12, до 08:28:08 UTC, на хості `AORUS-5-SE`,
`gh 2.46.0`, з репозиторію `nick-fedchik/kuzmin-machine`:

```bash
gh issue list --repo nick-fedchik/kuzmin-machine --state open --limit 250 \
  --json number,title,body,labels,url,updatedAt,state
```

Файл містить отримані назви, тіла, мітки й дату зміни; JSON відформатовано
для читання без зміни даних. SHA-256 збереженого файла:
`eb38c634efc6ca79b60c3feb1dd80de5bbda8cd9eeb79b5623391cedfffb7512`.
Він відтворює **збережений зріз**, а повторний запит може повернути інший
стан. Зріз охоплює 19 Issues, включно з #5 і #118; перевірити можна
розбором JSON. Закриті Issues та PR не є частиною цього зрізу.

`G` — ціль, `N` — кандидатна потреба, `Q` — дослідницьке питання.
Це локальні ідентифікатори аналізу, **не прийняті вимоги**. Потреби
сформульовано як пропозиції для узгодження, а не як установлені запити
майбутніх користувачів. У ланцюгах «не визначено» — видима прогалина,
не дозвіл замінити її припущенням.

## 3. Цілі, сторони й потреби

Власник визначив пріоритет: спочатку перевірити працездатність і
інноваційність Машини, мову KPOL та зручність програмування; галузеві
бізнес-сценарії [архівовано](../../docs/archive/README.md) за цим
рішенням. Цілі зафіксовано також у знімку постановки #5. Вони не
доводять жодної з цих властивостей.

| Ціль | Потреба, яку пропонується уточнити | Для кого / джерело |
|---|---|---|
| G1: перевірити працездатність визначеного об'єкта МК | N1: мати визначені правила, межі й відтворювані сценарії, які можуть показати і відхилення | Власник і виконавець перевірки; [настанова](../../process/PROJECT-MANUAL.md), [аналіз семантики #76](../../docs/research/theory/formal-semantics-76-report.md) |
| G1: зв'язати KPOL з об'єктом виконання | N2: описати підтримувану підмножину мови та відтворюваний шлях від програми до конкретного результату | Власник і розробник реалізації; [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8), [#19](https://github.com/nick-fedchik/kuzmin-machine/issues/19) |
| G2: перевірити зміст можливого внеску й новизни | N3: зіставити конкретне твердження з найближчими попередниками; допустити негативний результат | Власник і дослідник; [prior art](../../docs/trl-evidence/event-languages-prior-art.md), [#82](https://github.com/nick-fedchik/kuzmin-machine/issues/82) |
| G3: оцінити зручність програмування | N4: визначити користувача, типову задачу, інструкції та спосіб спостерігати труднощі й результат без наперед заданого висновку | Власник; потенційний програміст — зацікавлена сторона, потреби якої ще не підтверджено |
| G4: зберегти походження й керованість роботи | N5: мати перевірювані джерела, авторство, рішення, зв'язки та межі використання результатів | Власник і супровід проєкту; [джерела](../../docs/sources/README.md), [WP](../../docs/governance/work-products.md), [WI](../../process/work-items.md) |

М. Ю. Кузьмін — автор концепції та джерело первинних матеріалів;
наведення його тут не означає погодження кожної похідної потреби.
Розробник і незалежний перевіряльник — **ролі**, не призначені особи.
Зовнішнього замовника, промислового користувача чи прийняту систему
якостей у цьому зрізі не встановлено.

## 4. Кандидатні ланцюги

Таблиця навмисно зберігає розриви. Архітектурні файли є кандидатними
рішеннями, а старі вимоги — історичним входом для #5. Тут ланцюги
згруповано за потребами; окремі ланки для кожного WI наведено в §5.
Стан фізичного S6 у цій таблиці належить до першого зрізу;
прийняття AV-10 та пізніші матеріали й закриття #9/#72/#73 наведено
окремо в §12 і §14, без переписування історичного JSON.

| Ціль / потреба | Вимога або питання | Архітектурне рішення | WI | Перевірка | Результат / прогалина |
|---|---|---|---|---|---|
| G1/N1 | Історичні `REQ-SYS-001/006`: реакція на hazard / unknown | Кандидат: [шлюз v2](../../hw/rtl/core/kpol_txn_gate_v2.sv); вибір ядра v1/v2 не погоджено | [#6](https://github.com/nick-fedchik/kuzmin-machine/issues/6), [#18](https://github.com/nick-fedchik/kuzmin-machine/issues/18), [#62](https://github.com/nick-fedchik/kuzmin-machine/issues/62) | [Тестбенч v2](../../hw/tb/kpol_txn_gate_v2_tb.sv) — симуляція; [AV-04](../../experiments/AV-04/report.md) — формальна перевірка **v1** | За [паспортом TRL](../../process/trl/TRL-passport.md) §3 у v1 активний hazard **не блокує** commit: v1 суперечить `REQ-SYS-001` і не є запасним виконанням. Формального доказу v2 немає. |
| G1/N2 | Історичний `REQ-SW-001`: образ BRAM із KPOL | Кандидати: [специфікації](../../specs/kpol/README.md), [компілятор](../../sw/kpol-ref/kpol_reference.py), [план](../../architecture/refactoring-plan.md) | [#7](https://github.com/nick-fedchik/kuzmin-machine/issues/7), [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8), [#19](https://github.com/nick-fedchik/kuzmin-machine/issues/19) | [Інтеграційний тест](../../hw/tests/test_kpol_bram_pipeline.py): два образи на одному RTL, direct і AXI | Лише симуляція: фізичного бітстріму й доказу для довільної програми немає. Консолідованих правил і повної відповідності не встановлено (#19, #60). |
| G1/N1 | Q1: які правила подій і конкурентності можна реалізувати без здогадів? Критерій: незалежний реалізатор застосовує правила до заданих трас, невизначене позначено | **Не визначено**; вхід — [джерела](../../docs/sources/README.md) | [#76](https://github.com/nick-fedchik/kuzmin-machine/issues/76), [#78](https://github.com/nick-fedchik/kuzmin-machine/issues/78) (закриті) | [Звіт #76](../../docs/research/theory/formal-semantics-76-report.md) | Повну семантику з джерел не виведено. #78 закрито [як дубль #76](https://github.com/nick-fedchik/kuzmin-machine/issues/78#issuecomment-6791193803), тож питання лишається відкритим; відкритого WI для нього в зрізі немає. |
| G2/N3 | Q2: які конкретні ознаки МК відрізняються від найближчих попередників? Критерій: твердження зіставлено з указаними джерелами, межі пошуку явні | Непридатне: питання не залежить від архітектурного вибору | [#82](https://github.com/nick-fedchik/kuzmin-machine/issues/82) (закрита) | [Порівняння prior art](../../docs/trl-evidence/event-languages-prior-art.md) | Обмежений порівняльний аналіз, **не доказ глобальної новизни**; #82 закрито як покриту цим матеріалом. |
| G3/N4 | Q3: чи може програміст розв'язати визначену задачу за KPOL-інструкціями і де виникають труднощі? | Входи: [специфікації](../../specs/kpol/README.md), [референс](../../sw/kpol-ref/kpol_reference.py), [посібник розробника](../../docs/research/applications/Kuzmin-Machine-Developers-Guide-UA.md), [аналіз парадигм](../../docs/research/software/Kuzmin-Machine-Innovative-Programming-Paradigms-and-Tooling-UA.md) — неперевірені твердження | На зрізі — відсутній; після §7 — [#120](https://github.com/nick-fedchik/kuzmin-machine/issues/120) | Протокол і критерій висновку — чернетка в #120, власник погоджує **до** запуску | Звіту про користувацьку перевірку немає. |
| G1/N1 | Історичний `REQ-SYS-002`: автономна реакція | Кандидати: [RTL тригера](../../hw/rtl/io/km_io_trigger_engine.sv), [секвенсер](../../hw/rtl/core/km_autonomous_sequencer.sv) | [#9](https://github.com/nick-fedchik/kuzmin-machine/issues/9), [#72](https://github.com/nick-fedchik/kuzmin-machine/issues/72), [#73](https://github.com/nick-fedchik/kuzmin-machine/issues/73) | Фізичне вимірювання заплановане; #73 після §7 — розвідувальне, без порога | Фізичного результату немає. Історичне «< 500 нс» не є погодженим порогом. |
| G1/N1 | Q4: чи потрібні підпис образу, ACL та anti-rollback для вибраного об'єкта? | Історичні `REQ-SYS-007/008`, `REQ-SW-006/007`; програмні кандидати в [KPOL](../../sw/kpol-ref/kpol_reference.py) | [#67](https://github.com/nick-fedchik/kuzmin-machine/issues/67), [#68](https://github.com/nick-fedchik/kuzmin-machine/issues/68), [#115](https://github.com/nick-fedchik/kuzmin-machine/issues/115) | Програмні тести; один assert має відому прогалину #115 | Апаратного Secure Boot не доведено. Після §7 #67 і #68 відкладено: Q4 поза поточними межами, захист не перевірено. |
| G4/N5 | Потреба в походженні та рішеннях; продуктова вимога непридатна | Непридатне: [CI-реєстр](../../process/configuration-items.md), [індекс джерел](../../docs/sources/README.md) | [#5](https://github.com/nick-fedchik/kuzmin-machine/issues/5), [#20](https://github.com/nick-fedchik/kuzmin-machine/issues/20), [#21](https://github.com/nick-fedchik/kuzmin-machine/issues/21) | Джерело й рішення можна простежити та відокремити від похідного | Атрибуцію і ліцензію ще треба вирішити; реєстр не доводить правильності всіх WP. |

Додаткові вибрані закриті роботи:

- [#60](https://github.com/nick-fedchik/kuzmin-machine/issues/60):
  окремі розбіжності специфікації й референсу досліджено, але повної
  відповідності KPOL не доведено.
- [#61](https://github.com/nick-fedchik/kuzmin-machine/issues/61):
  закрита як окрема рутинна задача за рішенням власника; це не означає
  підтвердження трасування без сиріт.
- [#77](https://github.com/nick-fedchik/kuzmin-machine/issues/77):
  [контрприклад](../../docs/research/theory/turing-completeness-77-report.md)
  стосується конкретного авторського ескізу симуляції машини Тюрінга;
  загальну неможливість такої симуляції він не доводить.

Закриті [#79](https://github.com/nick-fedchik/kuzmin-machine/issues/79)
і [#81](https://github.com/nick-fedchik/kuzmin-machine/issues/81) відкладено
власником, а не виконано; [#83](https://github.com/nick-fedchik/kuzmin-machine/issues/83)
закрито як надмірно широкий benchmark. Ці стани не усувають питань Q1–Q3.

## 5. Ревізія відкритих WI на зрізі

Посилання на Issues ведуть до живих записів; їхнє тіло на час перегляду
збережене у [знімку](open-issues-2026-11-12.json). «Пропозиція» адресована
власнику і не змінює статусу. `REQ-*` — лише історичні кандидати з
[реєстру](../requirements.md), не погоджені вимоги. «Непридатна» означає,
що процесній чи керівній роботі продуктова вимога не потрібна;
«відсутня» — прогалина. Для WI з міткою `blocked` причину наведено з
посиланням.

| WI | Ціль / потреба | Вимога або питання | Архітектура / WP | Перевірка → результат, прогалина | Пропозиція |
|---|---|---|---|---|---|
| [#5](https://github.com/nick-fedchik/kuzmin-machine/issues/5) | G1–G4 / N1–N5 | Непридатна: координація | Цей WP; майбутня карта #5 | Частковий результат — цей зріз; повної карти і ревізії закритих WI немає | Залишити; завершувати після ревізії всього корпусу й рішення власника. |
| [#6](https://github.com/nick-fedchik/kuzmin-machine/issues/6) | G1/N1 | Кандидати `REQ-HW-001`, `REQ-SYS-001/006`; вибір ядра v1/v2 не погоджено | [План](../../architecture/refactoring-plan.md), [AV-04](../../experiments/AV-04/report.md) | AV-04 — формально лише v1, а v1 не задовольняє `REQ-SYS-001` (§4); про поріг мутацій див. §6 | Уточнити межу ядра та вимоги; не вилучати PoC із репозиторію без окремого рішення. |
| [#7](https://github.com/nick-fedchik/kuzmin-machine/issues/7) | G1/N2 | Кандидати `REQ-SW-001`, `REQ-HW-005`; критерій S4 у [настанові](../../process/PROJECT-MANUAL.md#4-віхи-trl-і-маршрут-до-mvp) | BRAM-конвеєр: [тест](../../hw/tests/test_kpol_bram_pipeline.py), RTL у `hw/rtl/core/` | Симуляція двох образів на одному RTL; фізичного бітстріму з незмінним SHA-256 немає | Залишити; уточнити об'єкт, образи, метод і фізичний доказ. |
| [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8) | G1/N2 | Кандидати `REQ-SW-001…005`; підтримувана підмножина не погоджена | [KPOL-референс](../../sw/kpol-ref/kpol_reference.py), [специфікації](../../specs/kpol/README.md) | Юніт-тести референсу; довільна трансляція не доведена | Залишити; зв'язати з погодженою підмножиною й перевіркою. |
| [#9](https://github.com/nick-fedchik/kuzmin-machine/issues/9) | G1/N1 | Кандидат `REQ-SYS-002` | [RTL тригера](../../hw/rtl/io/km_io_trigger_engine.sv), [секвенсер](../../hw/rtl/core/km_autonomous_sequencer.sv) | Фізичного результату немає; дочірні #72, #73 | Залишити; визначити системну межу й протокол. |
| [#18](https://github.com/nick-fedchik/kuzmin-machine/issues/18) | G1/N1 | `REQ-SYS-001/006` | [Шлюз v2](../../hw/rtl/core/kpol_txn_gate_v2.sv) | [Тестбенч v2](../../hw/tb/kpol_txn_gate_v2_tb.sv) — симуляція; формального доказу v2 немає | Залишити; узгодити з #6 і #62 після вибору об'єкта. |
| [#19](https://github.com/nick-fedchik/kuzmin-machine/issues/19) | G1/N2 | Q1 і кандидати `REQ-SW-*` | [Специфікації KPOL](../../specs/kpol/README.md) | [#60](https://github.com/nick-fedchik/kuzmin-machine/issues/60) виявив окремі розбіжності; повної відповідності референсу не встановлено | Залишити; зафіксувати підтримувану підмножину й трасування. |
| [#20](https://github.com/nick-fedchik/kuzmin-machine/issues/20) | G4/N5 | Непридатна: потрібне рішення власника | — | — | Залишити на рішення власника; джерела й обсяг прав перевірити окремо. |
| [#21](https://github.com/nick-fedchik/kuzmin-machine/issues/21) | G4/N5 | Непридатна: виправлення джерел | [Індекс джерел](../../docs/sources/README.md) | Зовнішню правку в `drafts` не виконано і не дозволено | Залишити до окремої команди власника; не вважати виправлення нового репо виправленням `drafts`. |
| [#48](https://github.com/nick-fedchik/kuzmin-machine/issues/48) | G1/N1 | Кандидат `REQ-HW-008`; нормативного опису інтерфейсу немає | [Ручна AXI-обгортка](../../hw/rtl/bus/kpol_txn_gate_axi_lite.sv) | Карта регістрів і значення після скидання є лише в коментарях RTL | Залишити; описати інтерфейс і перевірки; це інший об'єкт, ніж згенерована обгортка #64. |
| [#62](https://github.com/nick-fedchik/kuzmin-machine/issues/62) | G1/N1 | `REQ-SYS-001/006` для перелічених у WI об'єктів | Шлюз v2 та об'єкти, названі у WI | Історичні знахідки не перевірено на визначених поточних версіях | Уточнити об'єкти і припущення; звести з #18 без автоматичного закриття. |
| [#64](https://github.com/nick-fedchik/kuzmin-machine/issues/64) | G1/N2 | Кандидат `REQ-HW-008`; гіпотеза #64 про відповідність AXI4-Lite | Згенерована обгортка: `compile_axi_lite_wrapper` у [KPOL-референсі](../../sw/kpol-ref/kpol_reference.py) (~рядок 2324) | Тіло #64: «НЕ ПРОЙДЕНО» за [аудитом F-04](../../specs/kpol/reviews/kpol-0.2-0.9-audit-review.md). [KPOL-FIX](../../experiments/KPOL-FIX/report.md) заявляє виправлення за направленою симуляцією 4 кейсів; `test_v08_compile_axi_lite_wrapper` перевіряє лише текст коду. Метрика #64 вимагає асерцій або VIP — результату немає. Блокування: формулювання критерію потребує узгодження ([коментар](https://github.com/nick-fedchik/kuzmin-machine/issues/64#issuecomment-6751459712)) | Погодити уточнений критерій, потім перевірити поточну версію генератора за ним; не закривати через KPOL-FIX. |
| [#67](https://github.com/nick-fedchik/kuzmin-machine/issues/67) | G1/N1 | Q4; кандидати `REQ-SYS-008`, `REQ-SW-006` | Підпис образу в [KPOL-референсі](../../sw/kpol-ref/kpol_reference.py) | Історичний негативний результат F-06. Блокування: відкладено власником до появи потреби ([коментар](https://github.com/nick-fedchik/kuzmin-machine/issues/67#issuecomment-6804515864)) | Не запускати як універсальний гейт до рішення щодо застосовності та об'єкта. |
| [#68](https://github.com/nick-fedchik/kuzmin-machine/issues/68) | G1/N1 | Q4; кандидати `REQ-SYS-008`, `REQ-SW-006` | Підпис образу в [KPOL-референсі](../../sw/kpol-ref/kpol_reference.py) | Повного перебору не було. Блокування: відкладено власником до потреби й фіксованого формату образу ([коментар](https://github.com/nick-fedchik/kuzmin-machine/issues/68#issuecomment-6804515797)) | Спершу вирішити потребу й об'єкт; не змінювати зафіксований критерій після запуску. |
| [#72](https://github.com/nick-fedchik/kuzmin-machine/issues/72) | G1/N1 | Кандидат `REQ-SYS-002`; питання про участь PS | [RTL тригера](../../hw/rtl/io/km_io_trigger_engine.sv) | Фізичний метод запропоновано; результату немає | Узгодити точки спостереження й залежність від #9. |
| [#73](https://github.com/nick-fedchik/kuzmin-machine/issues/73) | G1/N1 | Кандидат `REQ-SYS-002`; історичне «< 500 нс» не є погодженим порогом | [RTL тригера](../../hw/rtl/io/km_io_trigger_engine.sv) | Блокування: поріг не встановлено ([коментар](https://github.com/nick-fedchik/kuzmin-machine/issues/73#issuecomment-6751462078)); вимірювань немає | Зберегти блокування до рішення власника про поріг і метод. |
| [#80](https://github.com/nick-fedchik/kuzmin-machine/issues/80) | G1/G2 | Відсутні: задачу, базу порівняння й критерій не визначено | — | — | Переглянути необхідність і черговість після перевірки працездатності; не відновлювати бізнес-сценарії. |
| [#115](https://github.com/nick-fedchik/kuzmin-machine/issues/115) | G1/N1 | Q4; кандидат `REQ-SW-006` | [Тест](../../sw/kpol-ref/tests/test_kpol_reference.py), [огляд #114](../../docs/research/verification/requirements-trace-assessment-114.md) | Відомий дефект assert: перевіряється непорожній кортеж | Залишити як конкретну знахідку; перевірити виправлення негативним випадком. |
| [#118](https://github.com/nick-fedchik/kuzmin-machine/issues/118) | G4/N5 | Непридатна: процесна робота | Цей WP і [знімок](open-issues-2026-11-12.json) | Рецензія в PR #119 | Завершити після рецензії; наступним проходом розглянути закриті WI. |

## 6. TRL та подальші рішення

[Паспорт TRL](../../process/trl/TRL-passport.md) містить **самооцінку**
TRL 1–3; для TRL 3 він обмежує підтвердження конкретною критичною
функцією шлюзу v1. TRL 4 є ціллю, а не висновком цього документа.
Формальний доказ, симуляція, mock, синтез/P&R і фізичне вимірювання —
різні типи даних; їх можна зіставляти лише для визначеного об'єкта й
умов. Глобальний поріг мутаційного балу ≥ 95 % скасовано рішенням
власника, записаним у [тілі #6](https://github.com/nick-fedchik/kuzmin-machine/issues/6)
і відображеним в [інвентарі WP](../../docs/governance/work-product-inventory.md).
Проте поріг досі є в [настанові, S3](../../process/PROJECT-MANUAL.md#4-віхи-trl-і-маршрут-до-mvp)
і в таблиці [формального аналізу, §8](../../docs/theory/formal-analysis.md).
Це протиріччя потребує окремого узгодження; карта не відновлює порогу,
не змінює цих документів і не встановлює нових критеріїв виходу.

Для продовження #5 потрібно: узгодити цілі, ролі та потреби; переглянути
всі закриті WI і результати з їхніми причинами закриття; встановити
пов'язані вимоги або дослідницькі питання й рішення щодо сиріт; визначити
контракти, перевірки та зв'язки у зворотному напрямку. Зокрема, для N4
у зрізі немає визначеної задачі чи протоколу користувацької перевірки,
а для Q4 треба рішення про застосовність до MVP.

## 7. Рішення власника після першого зрізу

Таблиця §5 відображає стан на момент знімка. Після рецензії власник
2026-11-12 ухвалив такі рішення; їх записано в самих Issues.

| WI | Рішення | Наслідок для ланцюга |
|---|---|---|
| [#80](https://github.com/nick-fedchik/kuzmin-machine/issues/80) | Закрито як відкладену разом із бізнес-сценаріями | Сценарій не реалізовано; повернутися після перевірки G1–G3 |
| [#67](https://github.com/nick-fedchik/kuzmin-machine/issues/67), [#68](https://github.com/nick-fedchik/kuzmin-machine/issues/68) | Закрито як відкладені до потреби в захищеному завантаженні | Q4 вилучено з поточних меж; захист **не** реалізовано і **не** перевірено, F-06 лишається чинним |
| [#73](https://github.com/nick-fedchik/kuzmin-machine/issues/73) | Порогу немає; вимірювання розвідувальне | Можна отримати розподіл затримки, але висновку «підтверджено / спростовано» немає; мітку `blocked` знято |
| [#64](https://github.com/nick-fedchik/kuzmin-machine/issues/64) | Власник делегував технічне рішення виконавцю; PR #121 прийнято без незалежної рецензії через обмеження квоти Antigravity | Issue закрито разом із PR #121. AXI-64 не спростував гіпотезу лише для перевіреного генератора, параметрів і властивостей; самоперевірка, не HIL і не TRL-гейт. Деталі й обмеження — §8 та [звіт](../../experiments/AXI-64/report.md). |
| [#120](https://github.com/nick-fedchik/kuzmin-machine/issues/120) | Створено дослідження Q3 | Ланцюг G3/N4 → Q3 отримав WI; протокол і критерій висновку чекають погодження власника до запуску |
| [#118](https://github.com/nick-fedchik/kuzmin-machine/issues/118) | Перший зріз прийнято власником через злиття PR #119 | Зріз відображає 19 Issues, а не повний корпус. Епік #5 залишається відкритим. |
| [#122](https://github.com/nick-fedchik/kuzmin-machine/issues/122) | Задачу незалежної рецензії PR #121 закрито за рішенням власника | Рецензії не було; це не Review Report і не незалежне підтвердження AXI-64. |

## 8. Зворотне трасування артефактів

Напрям — від артефакту до обґрунтування. Охоплено всі файли з `git ls-files`
у `hw/rtl`, `hw/tb`, `hw/tests`, `hw/scripts`, `hw/boards`, `sw` і звіти
`experiments/*/report.md`. «Без обґрунтування» означає, що артефакт не
пов'язаний ні з потребою N1–N5, ні з відкритим WI; це сигнал для рішення, а
не вирок. Історичні `REQ-*` наведено лише як найближчий кандидат.

| Артефакти | Вимога / питання | Ціль / потреба | WI | Оцінка / пропозиція |
|---|---|---|---|---|
| [`kpol_txn_gate.sv`](../../hw/rtl/core/kpol_txn_gate.sv), [`kpol_txn_gate_tb.sv`](../../hw/tb/kpol_txn_gate_tb.sv) | `REQ-SYS-001/003` | G1/N1 | [#6](https://github.com/nick-fedchik/kuzmin-machine/issues/6), [#62](https://github.com/nick-fedchik/kuzmin-machine/issues/62) | **Суперечить** `REQ-SYS-001` (hazard не блокує commit); лише TRL 3 самооцінки. Залишати як історичний еталон AV-04, не як кандидат ядра. |
| [`kpol_txn_gate_v2.sv`](../../hw/rtl/core/kpol_txn_gate_v2.sv), [`kpol_txn_gate_v2_tb.sv`](../../hw/tb/kpol_txn_gate_v2_tb.sv) | `REQ-SYS-001/006` | G1/N1 | [#6](https://github.com/nick-fedchik/kuzmin-machine/issues/6), [#18](https://github.com/nick-fedchik/kuzmin-machine/issues/18), [#62](https://github.com/nick-fedchik/kuzmin-machine/issues/62) | Обґрунтовано; формальної перевірки немає. |
| [`kpol_txn_gate_axi_lite.sv`](../../hw/rtl/bus/kpol_txn_gate_axi_lite.sv), [`kpol_txn_gate_axi_lite_tb.sv`](../../hw/tb/kpol_txn_gate_axi_lite_tb.sv), [`kpol_txn_gate_pynq_z1_top.v`](../../hw/boards/pynq-z1/kpol_txn_gate_pynq_z1_top.v), [`pynq_z1.xdc`](../../hw/boards/pynq-z1/pynq_z1.xdc), [`build_openxc7.sh`](../../hw/boards/pynq-z1/build_openxc7.sh), [`hil_manual_mmio.py`](../../hw/boards/pynq-z1/hil/hil_manual_mmio.py) | `REQ-HW-008` | G1/N1 | [#48](https://github.com/nick-fedchik/kuzmin-machine/issues/48) | Частково: обгортка інтегрує v1 і демо-FSM, тобто успадковує прогалини обох; карта регістрів не специфікована (#48). |
| [`km_predicate_evaluator.sv`](../../hw/rtl/core/km_predicate_evaluator.sv), [`km_concept_bram_core.sv`](../../hw/rtl/core/km_concept_bram_core.sv), [`hil_predicate_eval.py`](../../hw/boards/pynq-z1/hil/hil_predicate_eval.py), [`hil_bram_concepts.py`](../../hw/boards/pynq-z1/hil/hil_bram_concepts.py) | `REQ-HW-002/005` (неявно) | G1/N1 |  —  | **Без обґрунтування в поточних WI:** власних тестбенчів немає (лише компіляція в складі AXI-обгортки), HIL-скрипти посилаються на історичні EXP. Пропозиція: або включити в рішення S3 (#6), або вилучити разом із обгорткою v1. |
| [`km_concept_bram.sv`](../../hw/rtl/core/km_concept_bram.sv), [`km_concept_micro_engine.sv`](../../hw/rtl/core/km_concept_micro_engine.sv), [`km_concept_bram_tb.sv`](../../hw/tb/km_concept_bram_tb.sv), [`km_concept_micro_engine_tb.sv`](../../hw/tb/km_concept_micro_engine_tb.sv) | `REQ-HW-001/005/006` | G1/N2 | [#6](https://github.com/nick-fedchik/kuzmin-machine/issues/6), [#7](https://github.com/nick-fedchik/kuzmin-machine/issues/7), [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8), [#19](https://github.com/nick-fedchik/kuzmin-machine/issues/19) | Обґрунтовано як кандидат універсального ядра; повноти не доведено. |
| [`kpol_bram_pipeline_axi.sv`](../../hw/rtl/bus/kpol_bram_pipeline_axi.sv), [`kpol_bram_pipeline_tb.sv`](../../hw/tests/kpol_bram_pipeline_tb.sv), [`kpol_bram_pipeline_axi_tb.sv`](../../hw/tests/kpol_bram_pipeline_axi_tb.sv), [`kpol_bram_pipeline_increase.kpol`](../../hw/tests/kpol_bram_pipeline_increase.kpol), [`kpol_bram_pipeline_decrease.kpol`](../../hw/tests/kpol_bram_pipeline_decrease.kpol), [`test_kpol_bram_pipeline.py`](../../hw/tests/test_kpol_bram_pipeline.py), [`compile_kpol_bram_image.py`](../../hw/scripts/compile_kpol_bram_image.py) | `REQ-SW-001`, `REQ-HW-006` | G1/N2 | [#7](https://github.com/nick-fedchik/kuzmin-machine/issues/7), [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8), [#19](https://github.com/nick-fedchik/kuzmin-machine/issues/19) | Обґрунтовано; лише симуляція. AXI тут ручна, не згенерована — не доказ для #64. |
| [`kpol_bram_pipeline_pynq_z1_top.v`](../../hw/boards/pynq-z1/kpol_bram_pipeline_pynq_z1_top.v), [`kpol_bram_pipeline.xdc`](../../hw/boards/pynq-z1/kpol_bram_pipeline.xdc), [`build_bram_pipeline.sh`](../../hw/boards/pynq-z1/build_bram_pipeline.sh), [`hil_kpol_bram_pipeline.py`](../../hw/boards/pynq-z1/hil/hil_kpol_bram_pipeline.py), [`test_kpol_bram_hil_runner.py`](../../hw/tests/test_kpol_bram_hil_runner.py) | `REQ-SW-001` (фізично) | G1/N2 | [#7](https://github.com/nick-fedchik/kuzmin-machine/issues/7), [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8) | Обґрунтовано; фізичного результату немає. |
| [`km_autonomous_sequencer.sv`](../../hw/rtl/core/km_autonomous_sequencer.sv), [`km_autonomous_sequencer_tb.sv`](../../hw/tb/km_autonomous_sequencer_tb.sv) | `REQ-SYS-002/004`, `REQ-HW-007` | G1/N1 | [#9](https://github.com/nick-fedchik/kuzmin-machine/issues/9), [#72](https://github.com/nick-fedchik/kuzmin-machine/issues/72) | Обґрунтовано; FIFO 16 ≠ 64 у плані рефакторингу. |
| [`km_io_trigger_engine.sv`](../../hw/rtl/io/km_io_trigger_engine.sv), [`km_io_trigger_engine_tb.sv`](../../hw/tb/km_io_trigger_engine_tb.sv), [`hil_io_trigger.py`](../../hw/boards/pynq-z1/hil/hil_io_trigger.py) | `REQ-SYS-002` | G1/N1 | [#9](https://github.com/nick-fedchik/kuzmin-machine/issues/9), [#73](https://github.com/nick-fedchik/kuzmin-machine/issues/73) | Обґрунтовано; #73 розвідувальне. |
| [`poc-demo/README.md`](../../hw/rtl/poc-demo/README.md), [`km_euclid_core.sv`](../../hw/rtl/poc-demo/km_euclid_core.sv), [`km_rcfc_engine.sv`](../../hw/rtl/poc-demo/km_rcfc_engine.sv), [`km_cascade_arbiter_engine.sv`](../../hw/rtl/poc-demo/km_cascade_arbiter_engine.sv), [`km_stream_pipeline_engine.sv`](../../hw/rtl/poc-demo/km_stream_pipeline_engine.sv), [`km_euclid_core_tb.sv`](../../hw/tb/km_euclid_core_tb.sv), [`km_rcfc_engine_tb.sv`](../../hw/tb/km_rcfc_engine_tb.sv), [`km_cascade_arbiter_engine_tb.sv`](../../hw/tb/km_cascade_arbiter_engine_tb.sv), [`km_stream_pipeline_engine_tb.sv`](../../hw/tb/km_stream_pipeline_engine_tb.sv) | Немає (демо патернів) | — | [#6](https://github.com/nick-fedchik/kuzmin-machine/issues/6) (вилучення) | **Без обґрунтування:** не доводять універсальності; лишаються лише як залежність обгортки v1 і об'єкт AV-07/AV-08. |
| [`test_testbenches.py`](../../hw/tests/test_testbenches.py), [`run_open_flow.sh`](../../hw/scripts/run_open_flow.sh) | Інфраструктура перевірки | G1/N1, G4/N5 | — | Обґрунтовано як засіб; сама не дає результату. |
| [`bench-procurement.md`](../../hw/boards/bench-procurement.md), [`radiomag-order-a4.md`](../../hw/boards/radiomag-order-a4.md) | Інфраструктура стенда | G1/N1 | [#9](https://github.com/nick-fedchik/kuzmin-machine/issues/9), [#73](https://github.com/nick-fedchik/kuzmin-machine/issues/73) | Обґрунтовано як передумова фізичних вимірювань. |
| [`kpol_reference.py`](../../sw/kpol-ref/kpol_reference.py), [`test_kpol_reference.py`](../../sw/kpol-ref/tests/test_kpol_reference.py) | `REQ-SW-001…006`, Q3 | G1/N2, G3/N4 | [#7](https://github.com/nick-fedchik/kuzmin-machine/issues/7), [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8), [#19](https://github.com/nick-fedchik/kuzmin-machine/issues/19), [#60](https://github.com/nick-fedchik/kuzmin-machine/issues/60), [#64](https://github.com/nick-fedchik/kuzmin-machine/issues/64), [#115](https://github.com/nick-fedchik/kuzmin-machine/issues/115), [#120](https://github.com/nick-fedchik/kuzmin-machine/issues/120) | Обґрунтовано; частина функцій (HMAC, ACL) — Q4, відкладено в §7. |
| [`km_mcu_fpga_bridge.c`](../../sw/runtime/mcu/km_mcu_fpga_bridge.c), [`test_km_mcu_fpga_bridge.py`](../../sw/runtime/mcu/tests/test_km_mcu_fpga_bridge.py) | `REQ-SW-008` | G1/N1 |  —  | **Без відкритого WI:** тести на mock; цільова платформа заявлена без перевірки. Пропозиція: прив'язати до #6/#9 або позначити архівним. |
| [`kpol_direct_mmio_driver.py`](../../sw/runtime/pynq/kpol_direct_mmio_driver.py), [`test_kpol_direct_mmio.py`](../../sw/runtime/pynq/tests/test_kpol_direct_mmio.py) | `REQ-HW-008` (клієнт) | G1/N1 | [#48](https://github.com/nick-fedchik/kuzmin-machine/issues/48) | Частково: драйвер карти регістрів, яку #48 вважає неспецифікованою. |
| [`static-analyzer/README.md`](../../sw/tools/static-analyzer/README.md), [`design-analysis.md`](../../sw/tools/static-analyzer/design-analysis.md), [`km_static_analyzer.py`](../../sw/tools/static-analyzer/km_static_analyzer.py), [`test_km_static_analyzer.py`](../../sw/tools/static-analyzer/tests/test_km_static_analyzer.py) | Близько до Q1 (гонитви) і `REQ-SYS-003` (WCET) | G1/N1? |  —  | **Без обґрунтування:** жодна потреба не вимагає аналізатора; README сам застерігає щодо WCET. Пропозиція: або WI під Q1, або архів. |
| [`AV-03`](../../experiments/AV-03/report.md) | `REQ-SYS-003` (база порівняння) | G2/N3 | — | Закритий експеримент; порівнює з v1, тож результат не переноситься на v2. |
| [`AV-04`](../../experiments/AV-04/report.md) | `REQ-SYS-005` | G1/N1 | — | Закритий; лише ядро v1. |
| [`AV-07`](../../experiments/AV-07/report.md) | Чутливість тестбенчів | G1/N1 | — | Закритий; більшість мутантів у демо-FSM, які планується вилучити. |
| [`AV-08`](../../experiments/AV-08/report.md) | `REQ-HW-009` | G1/N1 | — | Закритий; масштабування демо, не ядра S3. |
| [`KPOL-FIX`](../../experiments/KPOL-FIX/report.md) | `REQ-SW-001…006` | G1/N2 | [#64](https://github.com/nick-fedchik/kuzmin-machine/issues/64) | Історична заява про виправлення F-04 спиралася на 4 направлені кейси; поточний генератор окремо перевірено у [AXI-64](../../experiments/AXI-64/report.md). Перевірка не охоплює функціональний запуск `dispatch`, PROT чи всі параметри. |
| [`AXI-64`](../../experiments/AXI-64/report.md), [властивості](../../experiments/AXI-64/scripts/axi64_props.sv), [сирі дані](../../experiments/AXI-64/raw/axi64_formal/axi64_results.csv) | Гіпотеза #64, кандидат `REQ-HW-008` | G1/N1 | [#64](https://github.com/nick-fedchik/kuzmin-machine/issues/64), [PR #121](https://github.com/nick-fedchik/kuzmin-machine/pull/121) | P1–P6 доведено ABC PDR для одного згенерованого модуля за припущень master і скидання (звіт, §2); 7/7 cover досягнуто; 4 F-04-мутанти виявлено контрприкладами. Не спростовано в межах методу; незалежної рецензії немає. |

Підсумок: без обґрунтування — демо-FSM `poc-demo`, `km_predicate_evaluator`,
`km_concept_bram_core`, MCU-runtime і статичний аналізатор. Рішення про них
належить до S3 ([#6](https://github.com/nick-fedchik/kuzmin-machine/issues/6))
або окремого WI; цей документ їх не вилучає.

## 9. Ретроспективне трасування всіх Issues

### 9.1. Знімок і правила класифікації

Знімок [`all-issues-2026-11-12.json`](all-issues-2026-11-12.json)
одержано 2026-11-12 через `gh issue list`. Він містить усі 80
Issues, видимих команді `gh issue list --state all --limit 250` на момент
запиту: 65 `CLOSED`, 15 `OPEN`. SHA-256:
`e717fa72468520fb0faab148305c0e4edb7da9374e9e534ca88831db915d6c43`.
Знімок містить номер, назву, тіло, мітки, стани й часові мітки; коментарі
перевірялися окремо. Він є незмінним історичним зрізом, не поточним беклогом.
Рішення власника, що спираються на коментарі закриття (зокрема #64, #65, #122),
наведено за текстом коментарів Issue; знімок їх не містить і в цьому документі
їх не перевірено повторно.

Відтворення:

```bash
gh issue list --repo nick-fedchik/kuzmin-machine --state all --limit 250 \
  --json number,title,body,labels,state,createdAt,updatedAt,closedAt,url
```

Для продуктового WI наведено найближчу ціль/потребу/REQ або питання.
Процесні WI належать до G4/N5; технічне трасування до продукту для них
непридатне. `REQ-*` — лише історичні кандидати (§10). `CLOSED` означає
стан Issue, а не доказ виконання критерію: відкладення, відхилення,
негативний результат і рутинне закриття позначено окремо. Невідомий за
наявними WP результат не домислюється. Таблиця не змінює статуси Issues.

### 9.2. Реєстр

| Issue | Стан | Трасування | Результат / прогалина |
|---|---|---|---|
| [#1](https://github.com/nick-fedchik/kuzmin-machine/issues/1) | CLOSED | G4/N5; [migration register](../../process/MIGRATION-REGISTER.md) | Міграція PoC — організаційний результат; технічні твердження джерела лишаються історичними. |
| [#2](https://github.com/nick-fedchik/kuzmin-machine/issues/2) | CLOSED | G4/N5; [TRL passport §1](../../process/trl/TRL-passport.md) | Аудит TRL 1 перервано через квоту; Audit Report відсутній. |
| [#3](https://github.com/nick-fedchik/kuzmin-machine/issues/3) | CLOSED | G4/N5; [TRL passport §2](../../process/trl/TRL-passport.md) | Спільний аудит TRL 2 перервано через квоту; висновку аудиту немає. |
| [#4](https://github.com/nick-fedchik/kuzmin-machine/issues/4) | CLOSED | G1/N1; [TRL passport §3](../../process/trl/TRL-passport.md), PR #44/#93 | Застарілу постановку закрито; не є новим підтвердженням TRL 3 системи. |
| [#5](https://github.com/nick-fedchik/kuzmin-machine/issues/5) | OPEN | G1–G4/N1–N5; цей WP | Епік не завершено: потрібні рішення про вимоги, архітектури, повну трасу та Review Report. |
| [#6](https://github.com/nick-fedchik/kuzmin-machine/issues/6) | OPEN | G1/N1; [refactoring plan](../../architecture/refactoring-plan.md) | S3: ядро без задачних FSM і вибір об'єкта не завершені; `poc-demo` лишається рішенням власника. |
| [#7](https://github.com/nick-fedchik/kuzmin-machine/issues/7) | OPEN | G1/N2; [BRAM test](../../hw/tests/test_kpol_bram_pipeline.py) | S4: є симуляція двох образів; результат фізичного виконання зафіксованого бітстріму не наведено в цьому WP. |
| [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8) | OPEN | G1/N2; [KPOL reference](../../sw/kpol-ref/kpol_reference.py), #19 | S5: компілятор підтримує обмежений шлях; підмножина KPOL ще не погоджена. |
| [#9](https://github.com/nick-fedchik/kuzmin-machine/issues/9) | OPEN | G1/N1; [I/O RTL](../../hw/rtl/io/km_io_trigger_engine.sv), #72/#73 | На базі продовження `82d55c8` AV-10 ще не був у дереві; пізніше додано [звіт і дані](../../experiments/AV-10/report.md). Порівняння критеріїв — §12. S6 залишається відкритим. |
| [#10](https://github.com/nick-fedchik/kuzmin-machine/issues/10) | CLOSED | G4/N5; [PROJECT-MANUAL](../../process/PROJECT-MANUAL.md) | Закрито як рутинну задачу; не означає виконання S2–S6 чи досягнення TRL 4. |
| [#11](https://github.com/nick-fedchik/kuzmin-machine/issues/11) | CLOSED | G1/N1; [AXI testbench](../../hw/tb/kpol_txn_gate_axi_lite_tb.sv), #38/#42 | Address-width mismatch виправляли пов'язані WI; не є доказом контракту ручної обгортки #48. |
| [#12](https://github.com/nick-fedchik/kuzmin-machine/issues/12) | CLOSED | G4/N5; [Verilator flow](../../hw/scripts/run_open_flow.sh) | Окремий гейт відхилено власником; відсутність попереджень у всіх конфігураціях не доведена. |
| [#13](https://github.com/nick-fedchik/kuzmin-machine/issues/13) | CLOSED | G4/N5; [migration register](../../process/MIGRATION-REGISTER.md) | Навігаційна проблема з посиланням на неіснуючий файл; окремого доказу виправлення у знімку немає. |
| [#14](https://github.com/nick-fedchik/kuzmin-machine/issues/14) | CLOSED | G1/N1; [AV-07](../../experiments/AV-07/report.md), #6 | Окремий coverage gate відхилено; прогалини AV-07 для ядра/BRAM/AXI/top цим не усунені. |
| [#15](https://github.com/nick-fedchik/kuzmin-machine/issues/15) | CLOSED | G4/N5; [AV-07 review](../../experiments/AV-07/review.md) | Рутинну задачу закрито; нової перевірки v2 статус Issue сам по собі не засвідчує. |
| [#16](https://github.com/nick-fedchik/kuzmin-machine/issues/16) | CLOSED | G4/N5; архівні QA/HIL WP | Закрито як рутинну роботу; історичні «Hardware Verified» не стають фізичним доказом. |
| [#17](https://github.com/nick-fedchik/kuzmin-machine/issues/17) | CLOSED | G4/N5; [KPOL-FIX](../../experiments/KPOL-FIX/report.md) | Закрито як рутинну задачу; незалежної рецензії KPOL-FIX це не створює. |
| [#18](https://github.com/nick-fedchik/kuzmin-machine/issues/18) | OPEN | G1/N1; `REQ-SYS-001/006`; [v2 RTL](../../hw/rtl/core/kpol_txn_gate_v2.sv) | Формальної перевірки v2 немає; узгодити об'єкт із #6/#62. |
| [#19](https://github.com/nick-fedchik/kuzmin-machine/issues/19) | OPEN | G1/N2; [KPOL specs](../../specs/kpol/README.md), #60 | Звіт аудиту виявив розбіжності; потрібна консолідована специфікація підтриманої підмножини. |
| [#20](https://github.com/nick-fedchik/kuzmin-machine/issues/20) | OPEN | G4/N5 | Потрібне рішення про ліцензію, авторство та NOTICE; продуктова вимога непридатна. |
| [#21](https://github.com/nick-fedchik/kuzmin-machine/issues/21) | OPEN | G4/N5; зовнішній `drafts` | Потрібне виправлення атрибуції у зовнішньому джерелі; цей репозиторій його не змінює. |
| [#22](https://github.com/nick-fedchik/kuzmin-machine/issues/22) | CLOSED | G4/N5; [AV-03 runner](../../experiments/AV-03/scripts/run_av03.py) | Синтаксичне попередження скрипта; не змінює науковий результат AV-03. |
| [#23](https://github.com/nick-fedchik/kuzmin-machine/issues/23) | CLOSED | G4/N5; [experiment plan](../../experiments/PLAN.md) | Редакційна нумерація плану; не є продуктовою вимогою чи доказом експерименту. |
| [#24](https://github.com/nick-fedchik/kuzmin-machine/issues/24) | CLOSED | G4/N5; [review rules](../../process/review-rules.md) | Адаптація процесної настанови до структури; не підтверджує виконання будь-якого огляду. |
| [#25](https://github.com/nick-fedchik/kuzmin-machine/issues/25) | CLOSED | G4/N5; [migration register](../../process/MIGRATION-REGISTER.md) | Рутинне закриття не доводить створення tag `poc-final` у зовнішньому `drafts`. |
| [#27](https://github.com/nick-fedchik/kuzmin-machine/issues/27) | CLOSED | G4/N5; [PROJECT-MANUAL](../../process/PROJECT-MANUAL.md) | Процедуру злиття з одним обліковим записом уточнено; це процесний контроль. |
| [#28](https://github.com/nick-fedchik/kuzmin-machine/issues/28) | CLOSED | G4/N5; [CI workflow](../../.github/workflows/ci.yml) | Додано Yosys `synth_xilinx` як CI-крок; успіх синтезу не доводить фізичну функціональність. |
| [#29](https://github.com/nick-fedchik/kuzmin-machine/issues/29) | CLOSED | G4/N5; [PROJECT-MANUAL](../../process/PROJECT-MANUAL.md) | Делегування тегування зафіксовано; процесне рішення, не продуктова вимога. |
| [#30](https://github.com/nick-fedchik/kuzmin-machine/issues/30) | CLOSED | G4/N5; [README](../../README.md) | Метадані власника; не є вимогою до МК. |
| [#31](https://github.com/nick-fedchik/kuzmin-machine/issues/31) | CLOSED | G4/N5; [link checker](../../tools/check_links.py) | `file:///` посилання були навігаційним дефектом; не свідчать про помилку runtime. |
| [#33](https://github.com/nick-fedchik/kuzmin-machine/issues/33) | CLOSED | G4/N5; [procurement record](../../hw/boards/bench-procurement.md) | Закупівля — передумова стенда, не підтвердження вимірювань або роботи обладнання. |
| [#35](https://github.com/nick-fedchik/kuzmin-machine/issues/35) | CLOSED | G4/N5; [procurement record](../../hw/boards/bench-procurement.md) | Виправлено твердження про роз'єм PYNQ-Z1; технічні критерії не змінює. |
| [#38](https://github.com/nick-fedchik/kuzmin-machine/issues/38) | CLOSED | G1/N1; [AXI RTL](../../hw/rtl/bus/kpol_txn_gate_axi_lite.sv), #11/#42 | Reset-дефект ручної обгортки виправлявся пов'язаною роботою; AXI-64 не стосується цієї обгортки. |
| [#42](https://github.com/nick-fedchik/kuzmin-machine/issues/42) | CLOSED | G1/N1; [AXI testbench](../../hw/tb/kpol_txn_gate_axi_lite_tb.sv), #11/#38 | Виправлено адресу тесту для лічильника; специфікаційну прогалину #48 це не закриває. |
| [#46](https://github.com/nick-fedchik/kuzmin-machine/issues/46) | CLOSED | G4/N5; [PROJECT-MANUAL](../../process/PROJECT-MANUAL.md) | Власник затвердив WIP/перехресну рецензію в одному PR; процесне рішення. |
| [#47](https://github.com/nick-fedchik/kuzmin-machine/issues/47) | CLOSED | G4/N5; [ASPICE steps](../../process/aspice-steps.md) | Уточнено процесні твердження/шкалу вердиктів; відповідність ASPICE не встановлюється закриттям. |
| [#48](https://github.com/nick-fedchik/kuzmin-machine/issues/48) | OPEN | G1/N1; `REQ-HW-008`; [manual AXI RTL](../../hw/rtl/bus/kpol_txn_gate_axi_lite.sv) | Карта регістрів і reset contract не оформлені як специфікація. AXI-64 тестував інший, згенерований slave. |
| [#51](https://github.com/nick-fedchik/kuzmin-machine/issues/51) | CLOSED | G4/N5; [migration register](../../process/MIGRATION-REGISTER.md) | Виправлено шляхи до drafts; навігаційне виправлення не підтверджує зміст зовнішніх джерел. |
| [#53](https://github.com/nick-fedchik/kuzmin-machine/issues/53) | CLOSED | G4/N5; [PROJECT-MANUAL](../../process/PROJECT-MANUAL.md) | Уточнено класи вердиктів/незалежності Review Report; це процесний результат. |
| [#55](https://github.com/nick-fedchik/kuzmin-machine/issues/55) | CLOSED | G4/N5; [TRL evidence](../../docs/trl-evidence/) | Глосарії створені як супровідні WP; не є технічним доказом. |
| [#59](https://github.com/nick-fedchik/kuzmin-machine/issues/59) | CLOSED | G4/N5; [provenance checker](../../tools/check_report_provenance.py), #75 | Повторний прогін не дав повного збігу; рецензія «Не перевірено». S1 не пройдено в межах заявленого відтворення. |
| [#60](https://github.com/nick-fedchik/kuzmin-machine/issues/60) | CLOSED | G1/N2; [KPOL-FIX](../../experiments/KPOL-FIX/report.md), #19 | Виявлено розбіжності специфікації й референсу; негативний результат лишає #19 відкритою. |
| [#61](https://github.com/nick-fedchik/kuzmin-machine/issues/61) | CLOSED | G4/N5; #5 | Закрито власником як рутинну роботу; не є доказом відсутності сиріт або завершення S2. |
| [#62](https://github.com/nick-fedchik/kuzmin-machine/issues/62) | OPEN | G1/N1; `REQ-SYS-001/006`; [AV-04](../../experiments/AV-04/report.md), #18 | Formal fail-closed для визначеного об'єкта не підтверджено; AV-04 стосується v1. |
| [#63](https://github.com/nick-fedchik/kuzmin-machine/issues/63) | CLOSED | G1/N2; Python/C/RTL parity | Власник відхилив окремий gate; паритет трьох реалізацій цим не доведений. |
| [#64](https://github.com/nick-fedchik/kuzmin-machine/issues/64) | CLOSED | G1/N1; [AXI-64](../../experiments/AXI-64/report.md), [PR #121](https://github.com/nick-fedchik/kuzmin-machine/pull/121) | P1–P6 доведено ABC PDR для одного згенерованого модуля; 7/7 cover, 4 мутанти. Не спростовано в межах методу; незалежної рецензії немає. |
| [#65](https://github.com/nick-fedchik/kuzmin-machine/issues/65) | CLOSED | G1/N1; #14/#6 | Поріг 95 % скасовано власником; це не 95 % результат і не релізний gate. |
| [#66](https://github.com/nick-fedchik/kuzmin-machine/issues/66) | CLOSED | G1/N2; #7 | Власник відхилив окремий експеримент; виконання програм через BRAM без пересинтезу не підтверджене. |
| [#67](https://github.com/nick-fedchik/kuzmin-machine/issues/67) | CLOSED | G1/N1; Q4, #115 | Secure Boot/anti-rollback відкладено; апаратний захист не реалізовано й не перевірено. |
| [#68](https://github.com/nick-fedchik/kuzmin-machine/issues/68) | CLOSED | G1/N1; Q4, #115 | Відкладено; повного перебору бітових інверсій не було, цілісність образу не підтверджена. |
| [#69](https://github.com/nick-fedchik/kuzmin-machine/issues/69) | CLOSED | G1/N2; #8/#19 | Власник відхилив окрему умову; компіляцію без ручного RTL для всіх еталонів не доведено. |
| [#70](https://github.com/nick-fedchik/kuzmin-machine/issues/70) | CLOSED | G1/N2; KPOL triad, #19 | Окремий gate незалежності не планується; коректність доказів цим не підтверджується. |
| [#71](https://github.com/nick-fedchik/kuzmin-machine/issues/71) | CLOSED | G4/N5; mutation gate | 100% mutation score не прийнято як релізний gate; це не доказ такого результату. |
| [#72](https://github.com/nick-fedchik/kuzmin-machine/issues/72) | OPEN | G1/N1; [I/O RTL](../../hw/rtl/io/km_io_trigger_engine.sv) | На базі продовження `82d55c8` дані AV-10 були відсутні; пізніше їх додано. Зв'язок із умовами #72 потребує окремої перевірки. |
| [#73](https://github.com/nick-fedchik/kuzmin-machine/issues/73) | OPEN | G1/N1; #9/#72 | Порога немає; дослідження розвідувальне. Власник повідомив 50 нс (20 нс синхронізатор + 30 нс шлюз); сирі дані тут не зафіксовані. |
| [#74](https://github.com/nick-fedchik/kuzmin-machine/issues/74) | CLOSED | G4/N5; [TRL passport](../../process/trl/TRL-passport.md) | Рутинне закриття не є незалежним аудитом або підтвердженням TRL 4. |
| [#75](https://github.com/nick-fedchik/kuzmin-machine/issues/75) | CLOSED | G4/N5; [baseline report](../../process/validation/75-reproduce-av/baseline-report.md), #59 | Відтворення AV не збіглося повністю; зафіксовано негативний результат для S1. |
| [#76](https://github.com/nick-fedchik/kuzmin-machine/issues/76) | CLOSED | G1/N1; [formal semantics report](../../docs/research/theory/formal-semantics-76-report.md) | Джерела не визначають одну повну операційну семантику; це межа матеріалів, не неможливість формалізації. |
| [#77](https://github.com/nick-fedchik/kuzmin-machine/issues/77) | CLOSED | G2/N3; [Turing report](../../docs/research/theory/turing-completeness-77-report.md), #76 | Контрприклад стосується конкретної конструкції, не є загальним доказом неповноти МК. |
| [#78](https://github.com/nick-fedchik/kuzmin-machine/issues/78) | CLOSED | G1/N1; #76 | Закрито як дубль #76; питання конкуренції, fairness і меж ресурсів лишаються невирішеними. |
| [#79](https://github.com/nick-fedchik/kuzmin-machine/issues/79) | CLOSED | G1/N1; Q1, #76/#78 | Відкладено до визначення правил і експерименту; виконувану еталонну модель не створено. |
| [#80](https://github.com/nick-fedchik/kuzmin-machine/issues/80) | CLOSED | G1/G2; Q2/Q3 | Відкладено; промислова придатність і перевага над baseline не підтверджені. |
| [#81](https://github.com/nick-fedchik/kuzmin-machine/issues/81) | CLOSED | G1/N1; #76/#79 | Відкладено разом із віртуальною моделлю; закриття не створює conformance traces. |
| [#82](https://github.com/nick-fedchik/kuzmin-machine/issues/82) | CLOSED | G2/N3; [prior-art review](../../docs/trl-evidence/event-languages-prior-art.md) | Обмежений огляд задокументовано; глобальна новизна й вичерпність пошуку не доведені. |
| [#83](https://github.com/nick-fedchik/kuzmin-machine/issues/83) | CLOSED | G2/N3; benchmark question | Широкий benchmark закрито; кількісної переваги над обраним baseline не встановлено. |
| [#84](https://github.com/nick-fedchik/kuzmin-machine/issues/84) | CLOSED | G4/N5; [publication boundary](../../docs/PUBLICATION-BOUNDARY.md) | Дослідницькі та редакційні матеріали розділено; сценарії не відновлювати без нового рішення. |
| [#86](https://github.com/nick-fedchik/kuzmin-machine/issues/86) | CLOSED | G4/N5; [procurement](../../hw/boards/bench-procurement.md) | Замовлення зафіксовано як ресурсний факт; закупівля не є HIL-тестом. |
| [#103](https://github.com/nick-fedchik/kuzmin-machine/issues/103) | CLOSED | G4/N5; [WP configuration](../../docs/governance/work-products.md), #104 | Класифікацію WP/маршрутизацію оформили; відповідність ASPICE цим не доведена. |
| [#104](https://github.com/nick-fedchik/kuzmin-machine/issues/104) | CLOSED | G4/N5; [WP catalog](../../docs/governance/work-products.md) | Каталог створено як керівний WP; він не доводить виконання робіт. |
| [#105](https://github.com/nick-fedchik/kuzmin-machine/issues/105) | CLOSED | G4/N5; [templates](../../process/templates/work-products/README.md) | Шаблони створено як засіб оформлення, не як доказ завершення WP. |
| [#106](https://github.com/nick-fedchik/kuzmin-machine/issues/106) | CLOSED | G4/N5; README та окремі WP | Навігаційні README розмежовано із самостійними документами. |
| [#108](https://github.com/nick-fedchik/kuzmin-machine/issues/108) | CLOSED | G4/N5; [WP inventory](../../docs/governance/work-product-inventory.md) | Інвентар WP створено; його класифікація не є доказом коректності кожного WP. |
| [#110](https://github.com/nick-fedchik/kuzmin-machine/issues/110) | CLOSED | G4/N5; [archive](../../docs/archive/README.md) | Бізнес-сценарії й попередні редакції архівовано за рішенням власника. |
| [#112](https://github.com/nick-fedchik/kuzmin-machine/issues/112) | CLOSED | G4/N5; [CI register](../../process/configuration-items.md) | Межі критичних CI/AV визначено; це не доказ виконання вимог виробу. |
| [#114](https://github.com/nick-fedchik/kuzmin-machine/issues/114) | CLOSED | G1/N1, G1/N2; [assessment](../../docs/research/verification/requirements-trace-assessment-114.md) | 30 REQ перевірено як історичні; 15 згаданих шляхів відсутні в базовому дереві. Report не є актуальною RTM чи незалежною рецензією. |
| [#115](https://github.com/nick-fedchik/kuzmin-machine/issues/115) | OPEN | G1/N1; Q4, [test](../../sw/kpol-ref/tests/test_kpol_reference.py) | `assertTrue` перевіряє непорожній кортеж, не bool; потрібне окреме виправлення й негативний тест. |
| [#117](https://github.com/nick-fedchik/kuzmin-machine/issues/117) | CLOSED | G4/N5; [review on PR #116](https://github.com/nick-fedchik/kuzmin-machine/pull/116#issuecomment-6818504443) | Рецензія #114 виконана з обмеженням незалежності; не є незалежною рецензією цього WP. |
| [#118](https://github.com/nick-fedchik/kuzmin-machine/issues/118) | CLOSED | G4/N5; [PR #119](https://github.com/nick-fedchik/kuzmin-machine/pull/119) | Злитий перший зріз 19 відкритих WI; цей реєстр розширює охоплення, але не закриває #5. |
| [#120](https://github.com/nick-fedchik/kuzmin-machine/issues/120) | OPEN | G3/N4; Q3; залежність #19 | Протокол і критерій не погоджено; не запускати дослідження до визначення KPOL subset. |
| [#122](https://github.com/nick-fedchik/kuzmin-machine/issues/122) | CLOSED | G4/N5; PR #121 | Власник закрив задачу без незалежної рецензії через ліміт Antigravity; Review Report відсутній. |

### 9.3. Підсумок

Відкриті WI у знімку: #5–#9, #18–#21, #48, #62, #72–#73, #115 і #120
(15 загалом). Найважливіші незавершені продуктові ланцюги: S3–S6 (#6–#9),
KPOL subset (#19), карта регістрів (#48), формальний gate (#62), тест #115
та Q3 (#120). Ліцензійна й атрибуційна роботи (#20–#21) — процесні
передумови, не продуктові вимоги.

Закриті WI охоплюють виконані процесні/дефектні роботи, негативні
результати (#60, #75, #76), відкладені чи відхилені роботи (#12, #14,
#63, #65–#71, #79–#81) та застарілі/рутинно закриті задачі (#2–#4,
#10, #15–#17, #25, #55, #61, #74). Статус Issue не є verdict вимоги.
Рішення щодо сиріт у коді, актуальної архітектури й MVP лишаються за
власником у межах #5.

## 10. Доля успадкованих вимог REQ

[`requirements.md`](../requirements.md) — перенесений історичний реєстр;
його `PASS`, шляхи та заяви ASPICE не є чинним baseline. Усі 30 рядків
оцінено індивідуально у [звіті #114, §§3–5](../../docs/research/verification/requirements-trace-assessment-114.md).
Тут наведено рішення для трасування: зберегти ID як історичний кандидат,
не затверджувати як вимогу й не називати виконаним. «Критерій/доказ» —
межа підтвердження зі звіту #114, а не приймальний критерій.

| ID | Кандидатний зв'язок | Критерій / доказ за #114 | Рішення та прогалина |
|---|---|---|---|
| `REQ-SYS-001` | G1/N1; #6/#18/#62 | AV-04 v1 допускає commit за hazard; v2 не доведено | Не вважати v1 задоволенням; визначити об'єкт і поведінку в S2/S3. |
| `REQ-SYS-002` | G1/N1; #9/#72/#73 | Симуляції компонентів; історичний поріг <500 нс не перевірений | Поріг не прийнято; #73 — exploratory без порога. |
| `REQ-SYS-003` | G1/N1; #9 | Фіксовані такти й нульовий jitter не доведені; межі виміру не узгоджені | Визначити об'єкт і метод до будь-якого висновку. |
| `REQ-SYS-004` | G1/N1; #6, Q1/#76 | Окремий каскад у симуляції; повна семантика concurrency відсутня | Розвести семантику, чергу й реалізацію. |
| `REQ-SYS-005` | G1/N1; #6 | Кандидатний знак перевірено; усі overflow випадки — ні | Потрібні ширина арифметики й межі. |
| `REQ-SYS-006` | G1/N1; #18/#62 | Симуляція unknown hazard при конкретному параметрі | Не формально перевірено для v2; статус непідтверджений. |
| `REQ-SYS-007` | G1/N1; Q4, #67/#68 | Програмні ACL тести; апаратний access control не доведений | Власник відклав security scope; поточна потреба невстановлена. |
| `REQ-SYS-008` | G1/N1; Q4, #67/#68/#115 | Програмний підпис/verify; Secure Boot не підтверджено; #115 defect | Відкладена; виправлення #115 не означає підтвердження boot security. |
| `REQ-SYS-009` | G1/N2; #19/#70/#76 | Хешування не доводить повноти/правильності proof | Семантика proof та незалежність не узгоджені. |
| `REQ-SYS-010` | G4/N5; #65/#71 | Mutation tests для вибраних наборів | У #71 гейт M < 1.0 не прийнято як релізний; саму вимогу 100 % лишено для рішення у #5 ([#114](../../docs/research/verification/requirements-trace-assessment-114.md)). Mutation testing — засіб, не acceptance gate. |
| `REQ-HW-001` | G1/N1; #6 | Окремі CME дії; універсальність довільних задач не доведена | Визначити immutable core у S3. |
| `REQ-HW-002` | G1/N1; #6/#19 | Opcode гілки є; всі опкоди й межі не тестовано | Вивести з погодженої KPOL підмножини. |
| `REQ-HW-003` | G1/N1; #6/#19 | Окремі арифметичні операції; не всі випадки | Уточнити overflow, ширину й supported subset. |
| `REQ-HW-004` | G1/N1; #19 | RTL перевертає guard; відповідність авторській семантиці не встановлена | Не формулювати нову вимогу без першоджерела/узгодження. |
| `REQ-HW-005` | G1/N2; #7 | BRAM адреси/структура в симуляції; не всі одночасні доступи/фізична BRAM | Потрібні контракт інтерфейсу й окремі перевірки S4. |
| `REQ-HW-006` | G1/N2; #7 | Перевірено 4 послідовні запити; end-to-end контракт не доведено | Визначити значення «4 такти», межі та wait states. |
| `REQ-HW-007` | G1/N1; #6/#76 | RTL FIFO 16; план згадує 64 | Розбіжність 16/64, колізії й переповнення не вирішено. |
| `REQ-HW-008` | G1/N1; #48/#64 | AXI-64 перевірив вибраний генератор; ручний bridge #48 має незадокументовану карту | Розділити два контракти; #64 не закриває #48. |
| `REQ-HW-009` | G1/N2; #7, AV-08 | Оцінки fmax для окремих обгорток; є synthesis-only дані | Не гарантувати частоту для довільної топології. |
| `REQ-HW-010` | G1/N1; #6 | Один simulation сценарій не доводить відсутність latch/glitch у всіх станах | Визначити об'єкт, стани й метод перевірки. |
| `REQ-SW-001` | G1/N2; #8/#19 | Обмежені вирази й правило; довільний AST не покритий | Специфікувати subset і метрики образу; 1024 bytes не приймати автоматично. |
| `REQ-SW-002` | G1/N2; #19 | Вибрані guards, не всі вирази/операнди | Повна граматика/семантичне покриття відсутні. |
| `REQ-SW-003` | G1/N2; #19 | Тести вибраних INC/ADD | Не доведені всі дії, overflow і типи. |
| `REQ-SW-004` | G1/N2; #19 | Окремі шляхи `•`/`not`, не повна еквівалентність | Відповідність синтаксису першоджерелу не встановлена. |
| `REQ-SW-005` | G1/N2; #19 | Приклад передає cascade map явно; автодедукцію не доведено | Не затверджувати автоматичне виведення до уточнення. |
| `REQ-SW-006` | G1/N1; Q4, #67/#68/#115 | HMAC тести програмні; anti-replay залежить від `seen_nonces`; test defect #115 | Security scope відкладено; виправити тест окремо, апаратного boot-proof немає. |
| `REQ-SW-007` | G1/N1; Q4, static analyzer | Окремі ACL перевірки; повнота моделі невідома | Security scope відкладено; обґрунтування аналізатора див. §8. |
| `REQ-SW-008` | G1/N2; MCU runtime | Хостові збірки; STM32/ESP32 target не перевірено | Потреба runtime і цільова плата не встановлені. |
| `REQ-SW-009` | G1/N2; #8/#19, #64 окремо | Тести вибраних генераторів; AXI-64 — один generated slave | Не доводить усі топології чи інтеграцію з ядром. |
| `REQ-SW-010` | G4/N5; #5 | Наявність генератора/текстового тесту не доводить двоспрямовану RTM | Не затверджувати автоматичний compliance synthesis; RTM лишається WP. |

**Висновок щодо REQ.** Жоден із 30 історичних рядків цим продовженням не
стає прийнятою вимогою. Для S2 власник має погодити межі MVP, потреби,
підмножину KPOL і долю надмірних/необґрунтованих тверджень. Локальні
`C-*` у [кандидатній архітектурі](../../architecture/s2-candidate-system.md)
позначають чернетки, не нормативні ID. Після узгодження створювати
нормативні атомарні ID, зберігши зв'язок з історичними ID.

## 11. Що залишилося до S2

Цей документ класифікує історичний знімок Issues і 30 успадкованих REQ;
він не виконує решту #5. Потрібні рішення й артефакти:

1. Погодити межі системи, стейкхолдерів і потреби G/N; нинішні G/N — кандидати.
   Конкретні варіанти й рекомендації для рішення — B1/B2 у
   [кандидатній архітектурі §7.1](../../architecture/s2-candidate-system.md#71-пять-рішень-для-погодження).
2. Визначити KPOL subset на основі #19 (B3); після цього погодити протокол #120.
3. Вирішити прогалини #6/#18/#48/#62 і долю артефактів §8 без обґрунтування.
4. Опрацювати [першу пропозицію системної, HW та SW архітектури](../../architecture/s2-candidate-system.md):
   межі компонентів, інтерфейси й частковий розподіл кандидатних вимог
   потребують погодження та розширення; B4/B5 визначають окремі питання
   доступу loader та приймання подій, не нові погоджені обмеження.
5. Провести незалежну рецензію повного WP; #117 стосувалася PR #116,
   а AXI-64 прийнято власником без незалежної рецензії. Статуси S2, MVP
   і TRL не змінювати без окремого рішення.

## 12. Типи WI та наступний зріз WP

Класифікація нижче — пропозиція за основною метою Issue зі
[знімка §9](all-issues-2026-11-12.json) та
[каталогу WI](../../process/work-items.md), а не автоматичне
переозначення історії. Індивідуальні зв'язки та доля — у §9.2.
Поточні мітки й закриття всіх 80 Issues повторно не звірялися, коментарі
не входять у знімок. Епік означає масштаб, а не додатковий тип.

| Мітка у знімку; кількість | Issue ID | Запропонований тип і підстава |
|---|---|---|
| `type:task`; 31 | #1, #2, #3, #4, #5, #6, #7, #8, #9, #10, #19, #20, #24, #25, #30, #33, #59, #61, #74, #79, #86, #103, #104, #105, #106, #108, #110, #112, #117, #118, #122 | Task: організація, реалізація, аналіз або рецензування визначеної роботи. #5–#9 — широкі WI; їхні результати і перевірки не зводяться до однієї мітки. #59/#61 формулюють гіпотези, але передбачають автоматичну перевірку; можливий Experiment, якщо основним результатом визначать протокол і вимірювання. |
| `type:finding`; 23 | #11, #12, #13, #14, #15, #16, #17, #18, #21, #22, #23, #27, #28, #31, #35, #38, #42, #47, #48, #51, #53, #55, #115 | Finding: зафіксовано дефект, відсутній доказ чи процесну невідповідність. Коригувальна робота може бути Task; закриття знахідки саме по собі не доводить результат. #18 і #62 пов'язані, але мають різні формулювання й не визнані дублями. |
| `type:experiment`; 17 | #60, #62, #63, #64, #65, #66, #67, #68, #69, #70, #71, #72, #73, #75, #80, #81, #83 | Experiment: перевірка гіпотези або вимірювання за визначених умов. Виняток: #81 за основною дією — Task зі створення тестів; їх виконання може бути окремим Experiment. #60 також потребує розбору розбіжностей специфікації через #19. |
| `type:research`; 6 | #76, #77, #78, #82, #114, #120 | Research: дослідити семантику, обґрунтування, попередні роботи, трасування або зручність; негативний чи неповний результат допустимий. #78 закрито як дубль #76, але відкриті питання від цього не розв'язані. |
| `type:change-request`; 3 | #29, #46, #84 | Change Request: зміна процесних правил або меж публікації потребує рішення; реалізацію можна відстежувати окремим Task. |

У знімку кожна Issue має рівно одну `type:*` мітку; `type:risk` не
зустрічається. Рекомендації не змінюють жодної мітки й не перетворюють
дослідницькі питання на вимоги. Для нових WI спочатку визначають мету,
очікуваний WP і рішення щодо меж; #120 не запускати до консолідації #19
та погодження протоколу.

Після історичного знімка [#73](https://github.com/nick-fedchik/kuzmin-machine/issues/73)
закрита з [PR #124](https://github.com/nick-fedchik/kuzmin-machine/pull/124);
[AV-10](../../experiments/AV-10/report.md) і raw є в базі `000aa1ca`.
**Рішення власника 2026-11-12, 13:43–13:44 +02:00.** У цій сесії
власник визначив 100 подій у серії достатніми для AV-10 з огляду на
мету й обмеження обладнання та прийняв результат як підтвердження S6
у перевіреній конфігурації, включно з критерієм `p99 ≤ 60 нс`.
Власник повідомив, що виконано кілька серій по 100 подій з однаковими
результатами. Джерело — повідомлення власника в сесії Copilot
`8533854a-7756-4530-afda-d6ff033f53b0`, а не незалежний аналіз raw.

Це рішення замінює для AV-10 попередню умову `N ≥ 1000` і розвідувальний
статус без порога з [коментаря #73](https://github.com/nick-fedchik/kuzmin-machine/issues/73#issuecomment-6820268498).
Зауваження щодо недостатності 100 подій та непогодженого критерію
знято. Прийняття зафіксовано після вимірювань: це не твердження про
попередню реєстрацію критерію. Історичний коментар, знімки й raw не
переписано. Незалежної перевірки вимірювань або всіх повторних серій у
межах цієї ревізії не виконано. Прийняття власником не є незалежною
рецензією та не переносить результат на інші конфігурації, S2, MVP чи TRL.
Стан і результати паралельних #9/#62/#72 ця ревізія не змінює.
Класифікація нових WP і додаткові межі — в
[інвентарі WP §7](../../docs/governance/work-product-inventory.md#7-нові-wp-після-базового-інвентаря).

## 13. Звіт про ревізію WI/WP

**Обмеження.** Повного змістового аудиту всіх WP, актуальних міток усіх
Issues або незалежної рецензії цього доповнення немає. Прийняття
власником результату AV-10 для S6 у перевіреній конфігурації — у §12;
ця ревізія не виконує власного експериментального підтвердження S6.
Виконавець — Copilot CLI Auto; рецензента ще не призначено. Апаратні
прогони й зміни Issues не виконувалися.

**Метод і результат.** На базі `000aa1ca5896620d03d8bab9e5a5d508aa0cc38b`
зіставлено мітки 80 історичних Issues з §12; Python-перевірка встановила
80 унікальних ID та збіг п'яти груп із JSON. Перелік змінених шляхів і
групування WP — в інвентарі §7. Зіставлено текст звіту AV-10 з
попереднім рішенням у #73 та зафіксовано нове рішення власника в цій
сесії; raw і відтворення фізичного вимірювання не оцінювалися.

**Відтворення перевірок проєкту:**

```bash
python3 -m pytest -q
python3 tools/check_links.py
```

Для цього доповнення: 185 тестів і 172 subtests пройшли; локальних
битих посилань немає, але 31 посилання на зовнішній `drafts` не
перевірено через відсутній `KM_DRAFTS_REPO`. Це не рецензія й не
прийняття вимог, архітектури, MVP або TRL.

## 14. Конфігурації S2 та рішення про системну межу

Це уточнення на базі `236a251f528e441387f03247c0c5c662a90b9ab7`, а не
нова база вимог. [Архітектура v0.2.0](../../architecture/s2-candidate-system.md)
розділяє compiler/BRAM-конвеєр (`CFG-P`), фізичний реактивний gate-шлях
(`CFG-R`) та окремий I/O trigger (`CFG-I`). Позначення локальні,
не прийняті ID конфігурацій. Опис з'єднань перевірено за RTL і тестом;
нових фізичних прогонів та незалежної рецензії не виконано.

| Ціль / потреба → об'єкт | Вимога або предмет рішення | Design / WI | Перевірка → результат і межа |
|---|---|---|---|
| G1/N2 → CFG-P | `C-SYS-001/002`, `C-SW-001`, `C-HW-001` (нормалізовано в `REQ-SYS-017`, `REQ-SW-013`, `REQ-HW-018`); B1/B3/B4 | [Архітектура §§2–5](../../architecture/s2-candidate-system.md#2-системна-межа-для-обговорення), [системна межа](../../architecture/system-boundary-allocation-b1.md); #7/#8/#19, [#136](https://github.com/nick-fedchik/kuzmin-machine/issues/136) | [Інтеграційний тест](../../hw/tests/test_kpol_bram_pipeline.py) та [HIL S4](../../experiments/S4-07/report.md) (PR #137) — фізичне виконання двох програм на одному бітстрімі доведено. Рішення B1, B2, B4, B5 формалізовано. |
| G1/N1 → CFG-R | Прийнятий власником результат AV-10 (§12); питання інтеграції B2 | [PYNQ-Z1 top](../../hw/boards/pynq-z1/kpol_txn_gate_pynq_z1_top.v), [ручна обгортка](../../hw/rtl/bus/kpol_txn_gate_axi_lite.sv); #9/#72/#73 | [AV-10](../../experiments/AV-10/report.md), [AV-11](../../experiments/AV-11/report.md), [підсумковий S6 Report](../../process/trl/reviews/review-gate-s6-autonomy.md). Gate v1 і PL-генератор, не sequencer/CME/gate v2; результат не переноситься на CFG-P. |
| G1/N1 → CFG-I | Контракт зовнішнього входу, не результат компіляції KPOL | [I/O trigger](../../hw/rtl/io/km_io_trigger_engine.sv), B2 | [Тестбенч](../../hw/tb/km_io_trigger_engine_tb.sv) — симуляція окремого блока. Його вхід `ext_pin_i` не ототожнюється з виходом монітора JA1 у CFG-R. |
| G1/N1 → черга CFG-P | B5: навантаження, одночасність, відмова/втрата при переповненні | [Sequencer](../../hw/rtl/core/km_autonomous_sequencer.sv), #6/#7 | RTL містить FIFO 16, план — 64. Ні одне число не обрано новою вимогою; спочатку потрібні погоджені сценарій і поведінка. |

На read-only перевірці GitHub 2026-11-12 #9/#72/#73 мають стан `CLOSED`;
#9 закрита 11:52:22 UTC після [PR #127](https://github.com/nick-fedchik/kuzmin-machine/pull/127)
з [рецензіями AV-10](../../experiments/AV-10/review.md) та
[AV-11](../../experiments/AV-11/review.md). Їхню наявність більше не
позначаємо як майбутню роботу. Незалежність рецензента й усі твердження
цих WP тут не переоцінюються; статус Issue сам собою не є новим доказом.
Історичні 65 CLOSED / 15 OPEN у §9 залишаються незмінними.

Безпосередній наступний крок власника — вибрати варіанти
[B1–B5](../../architecture/s2-candidate-system.md#71-пять-рішень-для-погодження)
із причинами й межами. До цього нормативні ID, єдину інтегровану
конфігурацію та числові ресурсні обмеження не затверджено. Роботу #62
залишено Antigravity; тут не змінено її критерії чи результат.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.1.0 | 2026-11-12 | Цілі, кандидатні потреби, перші ланцюги й ревізія відкритих WI (#118). |
| 0.2.0 | 2026-11-12 | За рецензією PR #119: окремі ланки ланцюга в таблиці WI; докази й причини блокування #64/#67/#68/#73; суперечність v1 і `REQ-SYS-001`; джерела й місця порога 95 %; входи для Q3; причина закриття #78. |
| 0.3.0 | 2026-11-12 | §7: рішення власника щодо #64, #67, #68, #73, #80 і нове дослідження Q3 (#120). |
| 0.4.0 | 2026-11-12 | §4 розділено на окремі ланки; додано §8 зворотного трасування артефактів. |
| 0.5.0 | 2026-11-12 | Після злиття #119/#121: враховано результат AXI-64, знімок усіх 80 Issues, індивідуальну класифікацію 30 успадкованих REQ, відкриті прогалини й наступні рішення для #5. |
| 0.6.0 | 2026-11-12 | Додано посилання на першу кандидатну системну/HW/SW архітектуру та обмежені чернетки вимог. |
| 0.7.0 | 2026-11-12 | Типи всіх WI з історичного знімка, винятки, нові WP і розбіжність критеріїв AV-10. |
| 0.7.1 | 2026-11-12 | Зафіксовано прийняття власником AV-10: 100 подій достатньо, результат прийнято для S6 у перевіреній конфігурації; попереднє зауваження знято. |
| 0.8.0 | 2026-11-12 | Додано трасування конфігурацій CFG-P/R/I, джерела пізніших результатів S6 і п'ять конкретних рішень власника щодо меж та контрактів S2. |

## Абревіатури та глосарій

| Термін | Значення |
|---|---|
| WP / WI | Робочий продукт / робота або питання для відстеження |
| TRL | Рівень технологічної готовності; у цьому документі — самооцінка чи ціль |
| RTL / FPGA | Опис цифрової логіки / програмована логічна інтегральна схема |
| BRAM | Блокова пам'ять FPGA |
| PS / HIL | Процесорна система / випробування з фізичним обладнанням у контурі |
| ACL / P&R | Список повноважень / розміщення та трасування FPGA |
| MVP | Мінімальний продукт проєкту, межі й база якого ще не прийняті |
