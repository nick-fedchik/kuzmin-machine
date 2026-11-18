# Контракти KPOL

* **Версія:** 1.0.0
* **Дата:** 2026-11-18
* **Тип WP:** Guide

## Призначення

Актуальні робочі входи специфікації KPOL (не послідовність дев'яти старих дельт):

| Документ | Призначення та стан |
|---|---|
| [KPOL-CME-1 / CME-RAW-1](kpol-cme-subset.md) | Цільовий початковий профіль B3 (`Decision B3-01`); типовий профіль CLI (`--profile KPOL-CME-1`). |
| [KPOL-CME-2 / CME-RAW-1](kpol-cme2-profile.md) | Багатоконцептний профіль (#184) на незмінному `CME-RAW-1`: до 64 станів, ациклічні каскади `on change(...)` (включно з `CID 0`), `ADD/SUB/ASSIGN`, `>=`/`<=`/`int16` `RANGE` та детектор `CME2-OPERAND-COLLISION`. |
| [EKPOL (Ergonomic KPOL 0.1.0)](ekpol-specification.md) | Ергономічна концептно-орієнтована мова програмування МК у чистому 7-бітному ASCII (`.ekpol`, `--profile EKPOL`, #278): підтримує символьну (`<-`, `->`, `~`, `::`, `=>`, `.`) та ключову (`on write`, `on read`, `on change`, `when`, `commit`, `after`) нотації, двосторонню трансляцію `EKPOL <-> KPOL` і 100% побітову ідентичність образів `CME-RAW-1`. |
| [KPOL-AUTH (підмножинний фронтенд і lowering)](kpol-auth-subset.md) | Похідна специфікація ізольованого прототипу [`Engineering/sw/kpol-auth/`](../../sw/kpol-auth/__init__.py) (#245, частина #186 і #8): CST з UTF-8 `Span`, гейти `KPOL-AUTH-U01..U12`, розмежування `•` та lowering у `Do/Go` + `CME-RAW-1` (`KPOL-LOWER-CYCLE`); #186 лишається відкритою до відповідей на `RFC-016` / `RFC-017` п. 3. |
| [Консолідований контракт](kpol-consolidated.md) | Опис наявного ширшого фронтенду та інтерпретатора; містить відомі прогалини безпрофільного CME-lowering. |
| [VMK (Virtual Machine of Kuzmin) та TUI-дебагер на Go](../sw/vmk-go-emulator-and-tui-debugger.md) | Специфікація двомодового емулятора МК (`--mode bram64` та `--mode conceptual`), протоколу `PRE-LOAD -> POST-LOAD`, потокового `STDIO`, транспайлера `EKPOL` і повноекранного TUI-дебагера [`Engineering/sw/vmk-go/`](../../sw/vmk-go/go.mod) (`v0.3.0`, #274, #278, #280). |
| [Керівництво користувача та чистий код мов KPOL і EKPOL](../../guides/kpol-ekpol-language-guide.md) | Фундаментальний практичний посібник користувача та стандарт чистого кодування за принципами Кернігана, Рітчі (*K&R*) та Мартіна (*Clean Code*) ([каталог `Engineering/guides/`](../../guides/README.md), #284). |

Референс — [kpol_reference.py](../../sw/kpol-ref/kpol_reference.py).
Поточні тести — [tests](../../sw/kpol-ref/tests/).
Вхідні уточнення — [Requirement KPOL](../../requirements/kpol.md),
переданий [Source відповідей](../../../Research/sources/author/rfc-2026-11-12.md).
Результат #150 — [Report профільної компіляції](../../validation/kpol-cme/profile-150/report.md).
Приклади трьох раніших програм збережено незмінно як тестову fixture,
не як чинний стандарт v0.1.
Новий [авторський Source #155](../../../Research/sources/author/introduction-2026-11-13.md)
має інший native синтаксис і адресну структуру.
[Impact/Q-AUTH](../../../Research/studies/author-semantics/kpol-syntax-155-report.md)
та кандидати AUTH у Requirement відділені від двох нинішніх контрактів.
`•` у Source — результат/метаподія, а не реалізований alias `not`;
Def/Class, Group, Name/Help та адресні групи не оголошуються підтриманими.
Подальша [редакція #157](../../../Research/studies/author-semantics/kpol-syntax-157-report.md)
уточнює Static й виконувану роль дужок; AUTH-08 / Q-AUTH-07 відділені
від чинної граматики. [Відповіді 2026-11-13](../../../Research/sources/author/clarifications-2026-11-13.md)
не є погодженням MMIO, native ABI або реалізації циклів/паралелізму.
[Фрагмент #159](../../../Research/studies/author-semantics/kpol-syntax-159-report.md)
уточнює Token → Min/Max для індексів груп; це Proposed AUTH-03,
не новий контракт поточного Parser. Q-AUTH-01 лишається частково відкритим.

## Обмеження

Перенесення не створює KPOL v1.0 або нової baseline. Успіх парсера
не означає підтримки CME-бекендом. `compile_bram_image` і
`compile_concept_microcode_bram_image` створюють різні формати.
CLI підтримує явні профілі `--profile KPOL-CME-1` (типовий) і `--profile KPOL-CME-2`
([Report #184](../../validation/kpol-cme/cme2-profile-184/report.md)): строгий whitelist,
незалежність від імен і обов'язковий pre-emission Proof gate. Виклик API без
`profile` зберігає сумісне експериментальне lowering: у [#183](https://github.com/nick-fedchik/kuzmin-machine/issues/183)
в ньому виправлено інверсію за іменем правила та трансляцію `>=`/`<=`/двостороннього `int16` `RANGE`
([Report #183](../../validation/kpol-cme/verifier-lowering-183/report.md)), але структурні межі
спільного `operand_val`, константного `ASSIGN` і `state-guard` залишаються чинними (деталізовано для `CME-RAW-2` у [#185](https://github.com/nick-fedchik/kuzmin-machine/issues/185)).
У межах [#151](https://github.com/nick-fedchik/kuzmin-machine/issues/151)
в RTL черги та AXI-обгортки реалізовано тактовий контракт очікування без втрат
[B5 v2.1](../hw/event-queue-ingress-specification.md) для керованих джерел;
фізично незупинний edge-вхід і HIL залишаються окремими межами.
Старі специфікації, навігаційні tombstone-файли та історичний аудит
залишені тільки у вихідному Git, не скопійовані в NG.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 1.0.0 | 2026-11-18 | #282, #284: уніфіковано імена файлів специфікацій без суфіксів версій та додано навігацію на Керівництво користувача з мов KPOL і EKPOL (`../../guides/kpol-ekpol-language-guide.md`) і каталог посібників (`../../guides/README.md`). |
| 0.9.0 | 2026-11-18 | #278: додано навігацію до специфікації ергономічної мови `EKPOL 0.1.0` (`ekpol-specification.md`) та оновлено версію `VMK v0.2.0`. |
| 0.8.0 | 2026-11-18 | #274: додано навігацію до специфікації двомодового Go-емулятора VMK та 4-панельного TUI-дебагера (`../sw/vmk-go-emulator-and-tui-debugger.md`, `Engineering/sw/vmk-go/`). |
| 0.7.0 | 2026-11-16 | #245 (частина #186, #8): додано навігацію до специфікації ізольованого підмножинного фронтенду та lowering `KPOL-AUTH` (`kpol-auth-subset.md`) і пакета `Engineering/sw/kpol-auth/` зі збереженням відкритого статусу #186. |
| 0.6.0 | 2026-11-14 | #184: додано навігацію до специфікації багатоконцептного профілю `KPOL-CME-2` (`kpol-cme2-profile.md`) і звіту перевірки `cme2-profile-184/report.md`. |
| 0.5.2 | 2026-11-14 | #183: уточнено стан виправлень верифікатора та експериментального CME-lowering і збережені структурні межі `CME-RAW-1`. |
| 0.5.1 | 2026-11-13 | #151: оновлено примітку про стан RTL черги за B5 v2.1 та межу незупинного джерела. |
| 0.5.0 | 2026-11-13 | #159: типізовані межі груп, AUTH-03/Q-AUTH-01 та незмінність current контрактів. |
| 0.4.0 | 2026-11-13 | #157: навігація до редакції Static, окремих відповідей і AUTH-08/Q-AUTH-07. |
| 0.3.0 | 2026-11-13 | #155: навігація й межа native авторського матеріалу та current DSL/CME. |
| 0.2.0 | 2026-11-12 | #150: вимоги за RFC, явний профільний шлях і межі legacy API та черги. |
| 0.1.0 | 2026-11-12 | Єдиний вхід до двох актуальних контрактів. |

## Абревіатури та глосарій

KPOL — Kuzmin Problem-Oriented Language; CME — Concept Micro-Engine;
ABI — контракт двійкового представлення.
