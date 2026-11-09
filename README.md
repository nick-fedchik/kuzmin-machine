# Машина Кузьміна (kuzmin-machine)

* **Версія репозиторію:** див. [`VERSION`](VERSION) (SemVer 2; теги `vX.Y.Z` ставить власник)
* **Власник:** Микола Мартинович Федчик
* **Автор концепції:** Михайло Ювеналійович Кузьмін — [первинні джерела](docs/sources/README.md)

Інженерний репозиторій Машини Кузьміна (МК). Це обчислювальна модель, де стан концептів змінюють події-предикати й підписки, а не потік інструкцій. Тут розробляють RTL-ядро на FPGA, мову KPOL та її еталонну реалізацію, а також засоби верифікації. Публікації, бізнес-модель і наукова опозиція лишаються в `nick-fedchik/drafts`.

## Стан

| | |
| :--- | :--- |
| **Рівень готовності** | **TRL 3** за самооцінкою ([паспорт TRL](process/trl/TRL-passport.md)). Незалежним аудитом не підтверджено |
| **Що доведено** | Транзакційний fail-closed шлюз `kpol_txn_gate` приймає або відхиляє зміну стану за 1 такт: формально (AV-04), мутаційно (AV-07, 22/22), на Zynq-7020 до N ≤ 32 (AV-08) |
| **Що не доведено** | Універсальна машина без задачних FSM; зміна логіки без пересинтезу; автономність від ARM / Linux; ланцюжок KPOL → бітстрім; стандарти безпеки — [план рефакторингу](architecture/refactoring-plan.md) |
| **Ціль** | MVP = TRL 4, кроки S1–S6 — [маршрут](process/PROJECT-MANUAL.md#4-віхи-trl-і-маршрут-до-mvp) |

## Структура

| Каталог | Вміст |
| :--- | :--- |
| [`process/`](process/) | [Настанова проєкту](process/PROJECT-MANUAL.md), [правила рецензування](process/review-rules.md), [методика аудиту ASPICE](process/audit/ASPICE-Audit-Method.md), [реєстр міграції](process/MIGRATION-REGISTER.md), [паспорт TRL](process/trl/TRL-passport.md), шаблони |
| [`requirements/`](requirements/) | Вимоги та трасування |
| [`architecture/`](architecture/) | Архітектура, план рефакторингу |
| [`specs/kpol/`](specs/kpol/README.md) | Специфікації мови KPOL |
| [`docs/`](docs/) | Первинні джерела автора, похідна теорія, докази TRL, інструменти |
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
