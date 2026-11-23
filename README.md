# Машина Кузьміна

* **Версія:** 0.8.0
* **Дата:** 2026-11-23
* **Тип WP:** Guide
* **Укладач:** GitHub Copilot CLI, Auto.
* **Підстава:** команди Миколи Федчика підготувати актуальне дерево без legacy та перенести його до Git; [#148](https://github.com/nick-fedchik/kuzmin-machine/issues/148), [#270](https://github.com/nick-fedchik/kuzmin-machine/issues/270), [#274](https://github.com/nick-fedchik/kuzmin-machine/issues/274), [#276](https://github.com/nick-fedchik/kuzmin-machine/issues/276), [#278](https://github.com/nick-fedchik/kuzmin-machine/issues/278), [#280](https://github.com/nick-fedchik/kuzmin-machine/issues/280), [#282](https://github.com/nick-fedchik/kuzmin-machine/issues/282), [#284](https://github.com/nick-fedchik/kuzmin-machine/issues/284).

## Призначення

Цей репозиторій — інженерно-дослідницьке робоче дерево Машини Кузьміна (МК).
Воно об'єднує матеріали про концепцію, дослідницькі питання та джерела,
специфікації, програмні й апаратні прототипи, перевірки та проєктну
простежуваність.

Автор концепції — Михайло Ювеналійович Кузьмін. Інженерні специфікації,
реалізації та похідні аналізи не приписуються йому автоматично; межі
авторства й походження матеріалів описані в [AUTHORS](AUTHORS.md) та
[NOTICE](NOTICE).

**Проєкт пропрієтарний, не open source.** Умови використання визначає
[LICENSE](LICENSE); включені сторонні матеріали зберігають власні права
та умови.

## Навігація

| Розділ | Що знайдете |
|---|---|
| [Articles](Articles/README.md) | Огляд концепції, порівняльні матеріали та статті про МК, KPOL/EKPOL і реалізації. |
| [Research](Research/README.md) | Карта дослідницьких питань, джерел, моделей, аналізів та їхніх обмежень. |
| [Engineering](Engineering/README.md) | Вимоги, специфікації, проєктні рішення, програмна й апаратна реалізація та валідація. |
| [Project](Project/README.md) | Правила роботи, політики, реєстри, простежуваність, оцінювання та шаблони. |
| [AUTHORS](AUTHORS.md) · [LICENSE](LICENSE) · [NOTICE](NOTICE) | Авторство, умови використання та походження сторонніх матеріалів. |

### З чого почати

* **Огляд і матеріали про концепцію:** [Articles](Articles/README.md).
* **Дослідницький стан і відкриті питання:** [Research](Research/README.md).
* **Технічний контекст і контракти:** [Engineering](Engineering/README.md).
* **Мова KPOL/EKPOL:** [посібник](Engineering/guides/kpol-ekpol-language-guide.md),
  [специфікація EKPOL](Engineering/specifications/kpol/ekpol-specification.md)
  та [Go-компілятор `kpolc`](Engineering/sw/kpol-go/README.md).
* **Емуляція та налагодження:** [VMK](Engineering/sw/vmk-go/README.md) і
  [посібник користувача](Engineering/guides/vmk-users-guide.md).
* **Перевірка на апаратурі:** [інженерна валідація](Engineering/validation/README.md)
  та [HIL runbook](Engineering/hw/RUNBOOK.md).
* **Організація робіт і походження перенесених матеріалів:** [Project](Project/README.md)
  та [реєстр міграції](Project/registers/migration.md).

Один із цільових трактів — KPOL/EKPOL → Go-компілятор `kpolc` → CME/BRAM-образ
або підтримані виходи C99 і Z3-сертифіката → емулятор VMK чи апаратний loader.
Реалізований фронтенд ширший за погоджений профіль KPOL-CME-1; склад,
контракти й докази для окремих компонентів наведені в документах
[Engineering](Engineering/README.md), а не узагальнюються як підтвердження
властивостей усієї системи.

## Використання

Команди виконуються з цієї папки:

```bash
(cd Engineering/sw/vmk-go && go test -v ./...)
(cd Engineering/sw/kpol-go && go test ./...)
python3 -m pytest -q
python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
bash Engineering/hw/scripts/run_open_flow.sh
```

Для програмних тестів потрібні Python 3, pytest і GCC; для RTL —
Icarus Verilog, Verilator та Yosys; для формальних тестів також
Z3, yosys-smtbmc й yosys-abc. Фізичний HIL запускають окремо за
[RUNBOOK](Engineering/hw/RUNBOOK.md); перелічені перевірки не програмують плату.

## Обмеження

Це не нова доказова baseline, не реліз і не підтвердження TRL.
Міграція продовжує історію наявного репозиторію через окрему гілку
та PR; злиття до main потребує рішення власника. Походження кожного
скопійованого файла й причини
виключення інших — у [реєстрі перенесення](Project/registers/migration.md);
виконання #148 та попередню локальну підготовку там зведено в один чинний запис.

Не перенесено архіви, старі дельти KPOL, демо-FSM,
попередні міграційні пакети й стару базу повтору AV-03/04/07/08.
Незмінні приклади компілятора та записи вимірювань збережено як потрібні
входи перевірок, а не як чинні старі специфікації чи реалізації.

AV-10/11 стосуються попередньої CFG-R. Їхні дані не доводять затримку
або автономність поточного CFG-P. Успадковані рецензії стосуються
оригіналів; ця локальна редакція ще не має незалежної рецензії.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.1.0 | 2026-11-12 | Три напрями та вибіркове перенесення актуальних артефактів. |
| 0.1.1 | 2026-11-12 | Пропрієтарний режим і записи атрибуції за рішенням власника #20. |
| 0.2.0 | 2026-11-12 | Перехід від локальної підготовки до Git-гілки міграції #148 зі збереженням історії. |
| 0.3.0 | 2026-11-17 | #270: додано навігацію на бекенд `--emit-c99` + Z3 (`Engineering/validation/kpol-cme/c99-emitter-270/report.md`). |
| 0.4.0 | 2026-11-18 | #274: додано навігацію на двомодовий Go-емулятор VMK та 4-панельний TUI-дебагер (`Engineering/sw/vmk-go/`, `Engineering/specifications/sw/vmk-go-emulator-and-tui-debugger.md`). |
| 0.4.1 | 2026-11-18 | #276: додано посилання на Посібник користувача VMK (`Engineering/guides/vmk-users-guide.md`) та `Engineering/sw/vmk-go/README.md`. |
| 0.5.0 | 2026-11-18 | #278: додано навігацію на специфікацію мови `EKPOL 0.1.0` (`Engineering/specifications/kpol/ekpol-specification.md`) та оновлено версію `VMK v0.2.0`. |
| 0.6.0 | 2026-11-18 | #284: додано навігацію на Керівництво користувача та чистий код мов KPOL і EKPOL (`Engineering/guides/kpol-ekpol-language-guide.md`), каталог посібників (`Engineering/guides/README.md`) та оновлено версію `VMK v0.3.0`. |
| 0.7.0 | 2026-11-20 | Додано навігацію на компілятори й трансляцію KPOL, EKPOL та KPOL-AUTH на Go (`Engineering/sw/kpol-go/`) і команду перевірки `go test` модуля. |
| 0.8.0 | 2026-11-23 | Переписано опис призначення, додано карту основних розділів і маршрути входу до досліджень, реалізацій та перевірок. |

## Абревіатури та глосарій

WP — Work Product; CME — Concept Micro-Engine; BRAM — блокова пам'ять FPGA;
RTL — опис цифрової логіки; HIL — перевірка з фізичним обладнанням;
NG — нова структура, не нова атестація результатів.
