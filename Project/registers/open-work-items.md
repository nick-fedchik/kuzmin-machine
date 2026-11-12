# Відкриті роботи та рішення власника

* **Версія:** 0.2.0
* **Дата:** 2026-11-12
* **Тип WP:** Register
* **Власник рішень:** Микола Федчик.
* **База:** [знімок GitHub після оновлення](../assessments/ng-migration/raw/owner-status-decisions-20261112.json).
* **Повторна перевірка з #148:** [фактичні стани під час міграції](../assessments/structure-migration/raw/execution-results.json).

## Межі та схема

Початковий запис п'яти розглянутих Issues доповнено окремою міграцією
[#148](https://github.com/nick-fedchik/kuzmin-machine/issues/148); це не повторний аудит всього
беклогу. GitHub Issue має стан Open/Closed; окреме поле Project має
Todo/In progress/Postponed/Done. Відкладення не є виконанням чи закриттям.

## Рішення та записи

| Issue | GitHub | Project | Рішення та залишок |
|---|---|---|---|
| [#20 — ліцензія й авторство](https://github.com/nick-fedchik/kuzmin-machine/issues/20) | Closed, completed | Done | Власник визначив пропрієтарний, не відкритий режим і доручив закриття. LICENSE/AUTHORS/NOTICE включені до гілки міграції; злиття ще попереду. |
| [#5 — S2](https://github.com/nick-fedchik/kuzmin-machine/issues/5) | Open | Postponed | Відкладено власником, не завершено. Історію, критерії та завершені B1–B5 збережено. |
| [#8 — компілятор](https://github.com/nick-fedchik/kuzmin-machine/issues/8) | Open | Todo | Погоджений KPOL-CME-1 не є доказом реалізації; lowering, відмови й перевірки залишаються роботою. |
| [#120 — зручність KPOL](https://github.com/nick-fedchik/kuzmin-machine/issues/120) | Open | Todo | Потрібне погодження протоколу до дослідження. Залежність #19 закрита, але дослідження не виконане. |
| [#115 — assert підпису](https://github.com/nick-fedchik/kuzmin-machine/issues/115) | Open | Todo | Відомий дефект тесту не виправляється цим статусним кроком. |
| [#148 — структура Research/Engineering/Project](https://github.com/nick-fedchik/kuzmin-machine/issues/148) | Open | In progress | Виконання прямої команди власника у власному worktree; один PR, без злиття до main. |

Джерела рішень:
[пропрієтарний режим](https://github.com/nick-fedchik/kuzmin-machine/issues/20#issuecomment-6829699920),
[відкладення S2 та відкритий беклог](https://github.com/nick-fedchik/kuzmin-machine/issues/5#issuecomment-6829701768).

## Ведення й обмеження

При новому рішенні оновлюють GitHub і цей запис, не переписуючи
первинний знімок. Новий знімок зберігають окремо.
Заміна структури не повинна автоматично закривати #5/#8/#120/#115.
Нове розміщення у GitHub-посиланнях вводять після появи файлів у main;
старі посилання на конкретні коміти не змінюють.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.1.0 | 2026-11-12 | Рішення власника про #20, Postponed для #5 та відкриті #8/#120/#115. |
| 0.2.0 | 2026-11-12 | Окрема міграція #148 без поновлення S2 чи закриття compiler/usability/finding. |

## Абревіатури та глосарій

WI — робоча задача; Project — GitHub Projects із власним полем Status;
S2 — вимоги, архітектура та трасування; Todo — беклог, не почате виконання.
