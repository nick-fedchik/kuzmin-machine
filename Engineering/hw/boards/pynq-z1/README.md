# Платформа PYNQ-Z1: поточний CFG-P

* **Версія:** 0.2.0
* **Дата:** 2026-11-12
* **Тип WP:** Guide
* **Походження:** [індекс 0.1.0](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/hw/boards/pynq-z1/README.md).

## Призначення й ідентичність

Поточний апаратний цільовий тракт — BRAM/CME на Digilent PYNQ-Z1,
XC7Z020. Серійний номер і фактичний стан конкретної плати цим
перенесенням не перевірялися.

Офіційний [Reference Manual](https://digilent.com/reference/programmable-logic/pynq-z1/reference-manual),
локальна [схема](../../../../Research/sources/vendor/pynq-z1-sch-f0.pdf)
та [картка Source](../../../../Research/sources/README.md) — різні
входи; схема не є доказом фактичної комутації.

## Поточні артефакти та використання

| Об'єкт | Локатор |
|---|---|
| Реалізація CFG-P | [Top](kpol_bram_pipeline_pynq_z1_top.v), [XDC](kpol_bram_pipeline.xdc). |
| Збірка | [build_bram_pipeline.sh](build_bram_pipeline.sh), новий `BUILD_DIR`. |
| Loader / HIL | [Runner](hil/hil_kpol_bram_pipeline.py); [контракт](../../../specifications/hw/kpol-image-loader-pipeline-contract.md). |
| Стенд | [Комутування](hil-bench-wiring-guide.md), [Pico](pico/). |
| Локальні перевірки | [Runbook](../../RUNBOOK.md). |

Для CFG-P `sw[1:0]` вибирає CID 0–3. LD0/LD1 показують commit/reject,
LD2 — busy, LD3 — overflow згідно з поточним top. Старе призначення
перемикачів як invariant/assumption та RGB-індикація CFG-R тут не діють.
Авторитет для портів — конкретні top/XDC, не загальна таблиця старого PoC.

## Межі та безпека

Лінії Pmod працюють на 3,3 В і не є 5V-толерантними. Не застосовувати
таблицю іншого top як інструкцію підключення. Для фізичної роботи
потрібні перевірена комутація та lock за [AGENTS](../../../../AGENTS.md).
Ця міграція не змінювала плату й не створювала нового бітстріму.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.2.0 | 2026-11-12 | Поточні CFG-P шляхи й призначення замість legacy CFG-R. |

## Абревіатури та глосарій

CFG-P — compiler/BRAM pipeline; CID — ідентифікатор концепту;
XDC — обмеження FPGA; HIL — апаратний прогін.
