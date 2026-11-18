# Машина Кузьміна

* **Версія:** 0.4.1
* **Дата:** 2026-11-18
* **Тип WP:** Guide
* **Укладач:** GitHub Copilot CLI, Auto.
* **Підстава:** команди Миколи Федчика підготувати актуальне дерево без legacy та перенести його до Git; [#148](https://github.com/nick-fedchik/kuzmin-machine/issues/148), [#270](https://github.com/nick-fedchik/kuzmin-machine/issues/270), [#274](https://github.com/nick-fedchik/kuzmin-machine/issues/274), [#276](https://github.com/nick-fedchik/kuzmin-machine/issues/276).

## Призначення

Робоче дерево досліджень та апаратно-програмної реалізації.
Автор концепції — Михайло Ювеналійович Кузьмін; інженерні специфікації,
код і похідні аналізи не приписуються йому автоматично.

**Пропрієтарний проєкт, не open source:** [LICENSE](LICENSE),
[AUTHORS](AUTHORS.md), [NOTICE](NOTICE).
Сторонні Source зберігають власні права й умови.

## Навігація

| Напрям | Зміст |
|---|---|
| [Research](Research/README.md) | Джерела, питання, моделі, методи та дослідницькі висновки. |
| [Engineering](Engineering/README.md) | Вимоги, контракти, рішення, compiler/loader/BRAM/CME та перевірки. |
| [Project](Project/README.md) | Правила, плани, реєстри, оцінювання й шаблони WP. |

Поточний цільовий тракт: текст KPOL → CME-образ (`--emit-c99` / `--emit-z3-cert`) → loader → BRAM (`CFG-P` / `CFG-P-HA`) →
sequencer/CME/gate v2, детермінований C99-автомат безпеки або двомодовий Go-емулятор **VMK** і 4-панельний TUI-дебагер ([`Engineering/sw/vmk-go/`](Engineering/sw/vmk-go/README.md), [Посібник користувача VMK `1.0.0`](Engineering/guides/vmk-users-guide.md), [специфікація `vmk-go` `0.1.0`](Engineering/specifications/sw/vmk-go-emulator-and-tui-debugger-0.1.0.md)). Опис складу — у
[Solution](Engineering/solutions/compiler-bram-pipeline.md), а підсумковий інженерно-комерційний висновок проєкту — у
[Commercialization & Final Conclusions](Research/studies/commercialization-and-final-conclusions.md).
Реалізований фронтенд ширший за погоджений цільовий профіль KPOL-CME-1.

## Використання

Команди виконуються з цієї папки:

```bash
(cd Engineering/sw/vmk-go && go test -v ./...)
python3 -m pytest -q
python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
bash Engineering/hw/scripts/run_open_flow.sh
```

Для програмних тестів потрібні Python 3, pytest і GCC; для RTL —
Icarus Verilog, Verilator та Yosys; для формальних тестів також
Z3, yosys-smtbmc й yosys-abc. Фізичний HIL запускають окремо за
[правилами агента](AGENTS.md); перелічені перевірки не програмують плату.

## Обмеження

Це не нова доказова baseline, не реліз і не підтвердження TRL.
Міграція продовжує історію наявного репозиторію через окрему гілку
та PR; злиття до main потребує рішення власника. Походження кожного
скопійованого файла й причини
виключення інших — у [реєстрі перенесення](Project/registers/migration.md).
Виконання в Git — у [Report](Project/assessments/structure-migration/report.md);
попередню локальну підготовку обліковано окремо.

Не перенесено архіви, старі дельти KPOL, демо-FSM, бізнес-чернетки,
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
| 0.3.0 | 2026-11-17 | #270: додано навігацію на підсумковий інженерно-комерційний висновок `Research/studies/commercialization-and-final-conclusions.md` та бекенд `--emit-c99` + Z3. |
| 0.4.0 | 2026-11-18 | #274: додано навігацію на двомодовий Go-емулятор VMK та 4-панельний TUI-дебагер (`Engineering/sw/vmk-go/`, `Engineering/specifications/sw/vmk-go-emulator-and-tui-debugger-0.1.0.md`). |
| 0.4.1 | 2026-11-18 | #276: додано посилання на Посібник користувача VMK (`Engineering/guides/vmk-users-guide.md`) та `Engineering/sw/vmk-go/README.md`. |

## Абревіатури та глосарій

WP — Work Product; CME — Concept Micro-Engine; BRAM — блокова пам'ять FPGA;
RTL — опис цифрової логіки; HIL — перевірка з фізичним обладнанням;
NG — нова структура, не нова атестація результатів.
