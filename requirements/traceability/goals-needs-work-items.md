# Цілі, потреби і перший зріз трасування

* **Версія:** 0.4.0 (робоча пропозиція)
* **Дата:** 2026-11-12
* **Issue:** [#118](https://github.com/nick-fedchik/kuzmin-machine/issues/118), у складі [#5](https://github.com/nick-fedchik/kuzmin-machine/issues/5)
* **Виконавець:** GitHub Copilot CLI, Auto; конкретна модель середовищем не показана.
* **Рецензент:** ще не призначений.
* **База файлів:** `d99e549edb859bce849f2f95e44e380f1fc5df94`.

## 1. Межі та результат

Повної матриці S2, погоджених потреб і нової бази MVP поки **немає**.
Цей документ починає трасування: пропонує цілі та потреби, показує
кандидатні ланцюги і переглядає **відкриті** WI на зафіксованому зрізі.
Вибрані закриті WI використано як контекст; повна ревізія закритих WI
залишається в [#5](https://github.com/nick-fedchik/kuzmin-machine/issues/5).
Це не незалежна рецензія і не зміна пріоритетів або статусів Issues.

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

## 7. Рішення власника після зрізу

Таблиця §5 відображає стан на момент знімка. Після рецензії власник
2026-11-12 ухвалив такі рішення; їх записано в самих Issues.

| WI | Рішення | Наслідок для ланцюга |
|---|---|---|
| [#80](https://github.com/nick-fedchik/kuzmin-machine/issues/80) | Закрито як відкладену разом із бізнес-сценаріями | Сценарій не реалізовано; повернутися після перевірки G1–G3 |
| [#67](https://github.com/nick-fedchik/kuzmin-machine/issues/67), [#68](https://github.com/nick-fedchik/kuzmin-machine/issues/68) | Закрито як відкладені до потреби в захищеному завантаженні | Q4 вилучено з поточних меж; захист **не** реалізовано і **не** перевірено, F-06 лишається чинним |
| [#73](https://github.com/nick-fedchik/kuzmin-machine/issues/73) | Порогу немає; вимірювання розвідувальне | Можна отримати розподіл затримки, але висновку «підтверджено / спростовано» немає; мітку `blocked` знято |
| [#64](https://github.com/nick-fedchik/kuzmin-machine/issues/64) | Власник не має експертизи для погодження критерію | Корекцію критерію за специфікацією AXI має підтвердити незалежний технічний рецензент; задача лишається `blocked` |
| [#120](https://github.com/nick-fedchik/kuzmin-machine/issues/120) | Створено дослідження Q3 | Ланцюг G3/N4 → Q3 отримав WI; протокол і критерій висновку чекають погодження власника до запуску |

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
| [`KPOL-FIX`](../../experiments/KPOL-FIX/report.md) | `REQ-SW-001…006` | G1/N2 | [#64](https://github.com/nick-fedchik/kuzmin-machine/issues/64) | Заява про виправлення F-04 спирається на 4 направлені кейси; див. #64. |

Підсумок: без обґрунтування — демо-FSM `poc-demo`, `km_predicate_evaluator`,
`km_concept_bram_core`, MCU-runtime і статичний аналізатор. Рішення про них
належить до S3 ([#6](https://github.com/nick-fedchik/kuzmin-machine/issues/6))
або окремого WI; цей документ їх не вилучає.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.1.0 | 2026-11-12 | Цілі, кандидатні потреби, перші ланцюги й ревізія відкритих WI (#118). |
| 0.2.0 | 2026-11-12 | За рецензією PR #119: окремі ланки ланцюга в таблиці WI; докази й причини блокування #64/#67/#68/#73; суперечність v1 і `REQ-SYS-001`; джерела й місця порога 95 %; входи для Q3; причина закриття #78. |
| 0.3.0 | 2026-11-12 | §7: рішення власника щодо #64, #67, #68, #73, #80 і нове дослідження Q3 (#120). |
| 0.4.0 | 2026-11-12 | §4 розділено на окремі ланки; додано §8 зворотного трасування артефактів. |

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
