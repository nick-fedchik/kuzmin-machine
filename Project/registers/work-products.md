# Реєстр Work Products NG

* **Версія:** 0.1.1
* **Дата:** 2026-11-12
* **Тип WP:** Register
* **Власник:** Микола Федчик; укладач — GitHub Copilot CLI.
* **База складу:** [маніфест](migration-manifest.json), [карта шляхів](path-map.json).

## 1. Призначення та схема

Тип WP визначає призначення, а напрям — відповідальність і контекст.
Наведені входи є основними; повний файловий [індекс](wp-index.json)
має шлях, тип, напрям і ознаку незмінного входу. Один файл може
реалізувати кілька WP розділами. Відсутність окремої папки не означає
відсутності типу.

## 2. Research

| WP | Основне місце / шаблон | Стан і межа |
|---|---|---|
| Source | [Каталог](../../Research/sources/README.md), [форма](../templates/work-products/source.md) | 4 дописи, презентація у двох форматах і vendor-схема; незмінні копії. |
| Problem | [Q01–Q21](../../Research/studies/concept-assessment/problem.md), постановки в README пакетів; [форма](../templates/work-products/problem.md) | Явну карту верифікованих авторських відповідей ще не створено. |
| Model | [Формальний розбір](../../Research/studies/author-semantics/formal-analysis.md), модель у [#77](../../Research/studies/turing-construction/report.md); [форма](../templates/work-products/model.md) | Похідні моделі, не первинна специфікація автора. |
| Protocol | [Опозиція](../../Research/studies/concept-assessment/protocol.md), методи у звітах; [форма](../templates/work-products/protocol.md) | Для завершених робіт метод вбудований, не нова попередня реєстрація. |
| Report | [П'ять досліджень](../../Research/README.md), [Analysis](../templates/work-products/analysis-report.md) | Результати й невизначене збережено; нового дослідження не заявлено. |
| Data | [Проходи опозиції](../../Research/studies/concept-assessment/data/opposition-passes/), двокоміркова траса у [#77](../../Research/studies/turing-construction/report.md) | Сирі тексти не переформатовано; хеші в маніфесті. Окремого файла для формальної траси немає. |

## 3. Engineering

| WP | Основне місце / шаблон | Стан і межа |
|---|---|---|
| Requirement | [Реєстр](../../Engineering/requirements/requirements.md); [SYS](../templates/work-products/requirement-sys.md), [HW](../templates/work-products/requirement-hw.md), [SW](../templates/work-products/requirement-sw.md) | Ідентифікатори й статуси збережено, нової baseline немає. |
| Specification | [KPOL](../../Engineering/specifications/kpol/README.md), [HW](../../Engineering/specifications/hw/README.md); [форма](../templates/work-products/specification.md) | Цільовий профіль відрізняється від ширшого поточного фронтенду. |
| Design | [B1](../../Engineering/design/system-boundary-allocation-b1.md), [B2](../../Engineering/design/bram-pipeline-event-integration.md); [форма](../templates/work-products/design.md) | Межа й інтеграція, не доказ готовності всього продукту. |
| Decision | [Карта](../../Engineering/decisions/README.md), розділи контрактів; [форма ADR](../templates/work-products/decision.md) | Не створено дубльованих рішень. |
| Solution | [Пакет](../../Engineering/solutions/compiler-bram-pipeline.md); [форма](../templates/work-products/solution.md) | Явний склад, залежності й обмеження. |
| Source Code | [HW](../../Engineering/hw/), [SW](../../Engineering/sw/) | Чинні компоненти й тести; демо-FSM виключено. |
| Configuration | [Карта](../../Engineering/configurations/README.md), файли біля компонентів | CFG-R ≠ CFG-P. |
| Hardware | [Платформа](../../Engineering/hw/boards/pynq-z1/README.md), [стенд](../../Engineering/hw/boards/pynq-z1/hil-bench-wiring-guide.md) | Опис об'єкта; нової фізичної перевірки немає. |

## 4. Project і поперечні типи

| WP | Основне місце / шаблон | Стан і межа |
|---|---|---|
| Plan | [NG](../plans/ng-transition.md); [форма](../templates/work-products/plan.md) | План і фактичний Report — різні WP. |
| Guide | [Навігація](../README.md); [форма](../templates/work-products/guide.md) | README не потребує окремого сховища docs. |
| Policy | [Розміщення](../policies/layout.md), [ліцензійний режим](../policies/licensing.md), [WP](../policies/work-products.md); [форма](../templates/work-products/policy.md) | Межі й повноваження визначає власник. |
| Register | Цей запис, [цілі](goals-needs-work-items.md), [відкриті WI](open-work-items.md), [CI](configuration-items.md); [форма](../templates/work-products/register.md) | Нові актуальні карти, не копії історичних зрізів. |
| Template | [Єдине місце](../templates/README.md), [покриття](../templates/work-products/README.md) | Усі 19 типів, 4 підтипи Report, SYS/HW/SW; placeholder дозволений у формі. |
| Report / Experiment | [Перевірки](../../Engineering/validation/README.md); [форма](../templates/report.md) | Пакети мають різні об'єкти; відсутні sidecar не вигадано. |
| Report / Review | Рецензії біля об'єктів; [форма](../templates/review.md) | Успадковані рецензії оригіналів, не нове прийняття NG. |
| Report / Assessment | [TRL](../assessments/trl/report.md); [форма](../templates/work-products/assessment-report.md) | Самооцінка, не сертифікація. |

## 5. Ведення та контроль

Для нового WP оновлюють основний README й індекс; важливі залежності —
також карту цілей. Типи нетекстових артефактів визначено
[правилами](../templates/README.md#3-wp-для-яких-markdown-форма-не-замінює-сам-артефакт).

`check_wp_documents.py` перевіряє зовнішню структуру Markdown і хеші
перелічених незмінних входів, не науковий зміст чи повну відповідність
кожного розділу шаблону. Змістову відповідність звіряють за питаннями
відповідного шаблону; невідоме позначають, не заповнюють вигадкою.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.1.0 | 2026-11-12 | Поточні WP й місця зберігання, без старого інвентаризаційного зрізу. |
| 0.1.1 | 2026-11-12 | Політика пропрієтарного режиму та реєстр поточних рішень щодо WI. |

## Абревіатури та глосарій

WP — результат роботи; CI — елемент конфігурації; ADR — запис рішення;
sidecar — окремий машиночитаний запис походження.
