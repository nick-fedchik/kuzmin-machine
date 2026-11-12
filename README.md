# Машина Кузьміна (kuzmin-machine)

* **Версія репозиторію:** див. [`VERSION`](VERSION) (SemVer 2; теги `vX.Y.Z` ставить Lead Engineer за [PROJECT-MANUAL §7.1](process/PROJECT-MANUAL.md#71-тегування))
* **Власник:** Микола Мартинович Федчик
* **Автор концепції:** Михайло Ювеналійович Кузьмін — [первинні джерела](docs/sources/README.md)

Закритий робочий проєкт Машини Кузьміна (МК): дослідження, формальний аналіз, RTL і ПЗ, засоби розробки, верифікація, плани, аналітика, прогнози та комерційні матеріали. Наявність документа тут не означає прийняття його висновків.

**Микола Мартинович Федчик** виконує ролі менеджера проєкту, менеджера продукту й головного архітектора; на відповідних етапах — також маркетингового та комерційного менеджера.

`nick-fedchik/drafts/KuzminMachine` — лише редакційний майданчик статей на перевірених фактах і README з намірами публікацій, зокрема для вичитування Михайлом Кузьміним. Це не архів досліджень. Див. [межу репозиторіїв](docs/PUBLICATION-BOUNDARY.md) та [додаткову міграцію](process/migration/publication-84/report.md).

## Стан

| | |
| :--- | :--- |
| **Рівень готовності** | **TRL 3** за самооцінкою ([паспорт TRL](process/trl/TRL-passport.md)). Незалежним аудитом не підтверджено |
| **Що перевірено** | Властивості шлюзу v1 у моделі AV-04 (Hazard у ній діагностичний); 22/22 мутантів визначеного симуляційного набору AV-07; у STA AV-08 незалежні лінії N = 32 задовольнили 100 МГц, N = 64 — ні. Це не універсальна фізична межа чи доказ усієї МК. [Детальна оцінка, §8](docs/theory/formal-analysis.md#8-підсумкова-оцінка-реконструйованої-моделі) |
| **Що не доведено** | Універсальна машина без задачних FSM; зміна логіки без пересинтезу; автономність від ARM / Linux; ланцюжок KPOL → бітстрім; стандарти безпеки — [план рефакторингу](architecture/refactoring-plan.md) |
| **Ціль** | MVP = TRL 4, кроки S1–S6 — [маршрут](process/PROJECT-MANUAL.md#4-віхи-trl-і-маршрут-до-mvp) |

## Структура

| Каталог | Вміст |
| :--- | :--- |
| [`process/`](process/) | [Настанова проєкту](process/PROJECT-MANUAL.md), [правила рецензування](process/review-rules.md), [методика аудиту ASPICE](process/audit/ASPICE-Audit-Method.md), [реєстр міграції](process/MIGRATION-REGISTER.md), [паспорт TRL](process/trl/TRL-passport.md), шаблони |
| [`requirements/`](requirements/) | Вимоги та трасування |
| [`architecture/`](architecture/) | Архітектура, план рефакторингу |
| [`specs/kpol/`](specs/kpol/README.md) | Специфікації мови KPOL |
| [`docs/`](docs/) | Джерела, теорія, дослідження, стратегія, бізнес/прогнози, докази TRL та незмінні архівні оригінали; [навігація](docs/PUBLICATION-BOUNDARY.md) |
| [Work Items](process/work-items.md) | Види робіт і питань, зв'язки Issue та правила розрізнення |
| [Work Products](docs/governance/work-products.md) | Типи робочих продуктів, призначення каталогів і [шаблони](process/templates/work-products/README.md) |
| [Інвентар Work Products](docs/governance/work-product-inventory.md) | Робоча класифікація документів, пакетів і пов'язаних Issue |
| [Configuration Items](process/configuration-items.md) | Кандидати з результатів і критичних документів для керування конфігурацією |
| [`hw/`](hw/) | RTL (`core`, `bus`, `io`, `poc-demo`), тестбенчі, плата PYNQ-Z1, скрипти |
| [`sw/`](sw/) | Еталонна реалізація KPOL, рантайми PYNQ / MCU, статичний аналізатор |
| [`experiments/`](experiments/) | Експерименти AV-xx: звіт, рецензія, скрипти, сирі дані |
| [`tools/`](tools/) | Перевірки репозиторію |

## Швидкий старт

Потрібні: Python 3.11+, pytest, gcc, Icarus Verilog 12, Verilator 5. Для синтезу — Yosys і nextpnr.

```bash
python3 -m pytest                   # ПЗ, усі тестбенчі, диференційний тест AV-03
python3 tools/check_links.py        # відносні посилання в документах
bash hw/scripts/run_open_flow.sh    # симуляція, лінт, синтез Yosys, проксі-таймінг iCE40
```

## Як працювати

Людям і агентам — спершу [AGENTS.md](AGENTS.md), потім [PROJECT-MANUAL](process/PROJECT-MANUAL.md). Коротко: Issue → гілка `<тип>/<N>-<опис>` → PR з `Closes #N` → Review Report → злиття не автором PR.
