# Цілі, потреби та зв'язки поточного складу

* **Версія:** 0.3.0
* **Дата:** 2026-11-12
* **Тип WP:** Register
* **Власник:** Микола Федчик; укладач — GitHub Copilot CLI.
* **Джерело ID:** [оригінальний реєстр, §3](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/requirements/traceability/goals-needs-work-items.md#3-цілі-сторони-й-потреби).

## 1. Межі та стани

Поточна карта потрібних результатів, не копія всіх історичних Issues.
ID G/N збережені; нових вимог і числових критеріїв тут не затверджено.
«Наявний результат» не означає виконання всієї потреби.

## 2. Записи та зворотні зв'язки

| Ціль / потреба | Контракт або питання | Поточний WP / перевірка | Стан і межа |
|---|---|---|---|
| G1/N1: визначені правила й працездатність | Які правила авторської машини можна реалізувати без здогадів? | [#76](../../Research/studies/author-semantics/report.md), [джерела](../../Research/sources/README.md). | Повна семантика не отримана; не переносити це автоматично на власний KPOL-контракт. |
| G1/N2: KPOL → об'єкт виконання | B1–B5, KPOL-CME-1, loader і ingress | [Solution](../../Engineering/solutions/compiler-bram-pipeline.md), [вимоги](../../Engineering/requirements/requirements.md), [S4](../../Engineering/validation/experiments/S4-07/report.md). | Поточний цільовий CFG-P; повноту профілю не оголошено. |
| G1/N1–N2: уточнення правил і профільний compiler | [#150](https://github.com/nick-fedchik/kuzmin-machine/issues/150), частина #8; RFC-005–008 | [Source](../../Research/sources/author/rfc-2026-11-12.md) → [Requirement](../../Engineering/requirements/kpol.md) → [B3](../../Engineering/specifications/kpol/kpol-cme-subset-0.1.0.md) → [Report](../../Engineering/validation/kpol-cme/profile-150/report.md). | Strict-path відокремлений від legacy; очікування черги й багатоядерний fallback не реалізовані цим кроком. |
| G1/N1: межі fail-closed | Gate v2 за заданих властивостей і припущень | [S3](../../Engineering/validation/experiments/S3-62/report.md), [RTL](../../Engineering/hw/rtl/core/kpol_txn_gate_v2.sv). | Доказ компонента, не безпечність усієї системи. |
| G1/N1: реактивна затримка | Окремий CFG-R | [AV-10](../../Engineering/validation/experiments/AV-10/report.md), [AV-11](../../Engineering/validation/experiments/AV-11/report.md). | Власник прийняв 100 подій і p99 ≤ 60 нс для перевіреної CFG-R після вимірювання; не попередня реєстрація й не доказ CFG-P. |
| G1/N1: усунення Callback Bottleneck (FPGA + GPU) | Як виконати масив підписок без затримок послідовних шин та host-драйвера GPU? | [Рішення B6](../../Engineering/decisions/b6-gpu-persistent-kernel-subscribers.md) → [Пакет EXP-GPU-01](../../Engineering/validation/experiments/EXP-GPU-01/README.md) ([План](../../Engineering/validation/experiments/EXP-GPU-01/plan.md), [Протокол](../../Engineering/validation/experiments/EXP-GPU-01/protocol.md)). | Архітектурна пропозиція B6 та запланований експеримент HIL (PYNQ-Z1 + Jetson J501 + Pico/PicoScope); статус Proposed / Planned. |
| G2/N3: можливий внесок і новизна | Зіставлення конкретних тверджень | [Prior art](../../Research/studies/prior-art/report.md), [#77](../../Research/studies/turing-construction/report.md). | Обмежені результати; новизну не встановлено. |
| G3/N4: зручність програмування | Користувач, задача, метод спостереження | [Профіль KPOL](../../Engineering/specifications/kpol/README.md), джерельна #120. | Дослідження користувачів не виконано цим перенесенням. |
| G4/N5: походження й керованість | Джерела, авторство, рішення й межі | [Маніфест](migration-manifest.json), [WP](work-products.md), [політика](../policies/layout.md). | Структурне перенесення; не незалежна атестація. |

## 3. Ведення та обмеження

При зміні контракту оновлювати пов'язані Design, код і перевірку.
WI у таблиці належать вихідному GitHub-проєкту; їхній поточний
стан для п'яти поточних рішень перевірено у
[реєстрі відкритих робіт](open-work-items.md): #20 закрито,
#5 відкладено, #8/#120/#115 залишені відкритими.
Це не повторна перевірка всіх історичних WI. Відсутність незалежної рецензії
NG не замінено закриттям старих Issues.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.3.0 | 2026-11-12 | Додано ланцюг ADR B6 → EXP-GPU-01 для розв'язання Callback Bottleneck на GPU. |
| 0.2.0 | 2026-11-12 | Додано двонапрямний ланцюг Source/RFC → вимоги → профільний compiler → перевірки #150. |
| 0.1.0 | 2026-11-12 | Поточні ланцюги без копіювання історичного беклогу. |
| 0.1.1 | 2026-11-12 | Поточні рішення власника щодо ліцензії та відкритих WI. |

## Абревіатури та глосарій

G/N — ціль/потреба з джерельного реєстру; WI — робоча задача;
CFG-P/CFG-R — різні конфігурації, не взаємозамінні докази.
