# Інженерія

* **Версія:** 0.1.0
* **Дата:** 2026-11-12
* **Тип WP:** Guide

## Призначення та навігація

Цільовий тракт — compiler + loader + BRAM/CME/gate v2.

| WP / компонент | Основний вхід |
|---|---|
| Requirement | [Реєстр SYS/HW/SW](requirements/requirements.md); статус кожного рядка збережено. |
| Specification | [KPOL](specifications/kpol/README.md), [HW-контракти](specifications/hw/README.md). |
| Design | [Системна межа B1](design/system-boundary-allocation-b1.md), [інтеграція B2](design/bram-pipeline-event-integration.md). |
| Decision | [Карта рішень](decisions/README.md). |
| Solution | [Склад compiler/BRAM-пакета](solutions/compiler-bram-pipeline.md). |
| Source Code | [Референс KPOL](sw/kpol-ref/kpol_reference.py), [RTL](hw/rtl/), [тести](hw/tests/). |
| Configuration | [Карта конфігурацій](configurations/README.md). |
| Hardware | [Профіль PYNQ-Z1](hw/boards/pynq-z1/README.md), [комутація](hw/boards/pynq-z1/hil-bench-wiring-guide.md). |
| Перевірки | [Validation](validation/README.md). |

## Використання та обмеження

Приклади й приймальні сценарії профілю не замінюють реалізації всіх його
вимог. Успішний парсинг не означає коректного lowering у CME.
1024-байтні формати пасивного образу й CME-дескрипторів не взаємозамінні.

Демо-FSM, їхню стару AXI-обгортку й залежні збірки не перенесено.
Результат CFG-R у AV-10/11 залишено як обмежений доказ оригінальної
конфігурації; його не переносять на поточний pipeline.
Фізичний пристрій не є файлом Git; документи описують його ідентичність,
умови, конфігурацію й перевірки.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.1.0 | 2026-11-12 | Вхід до актуальних інженерних WP без PoC-демонстраторів. |

## Абревіатури та глосарій

SYS/HW/SW — системний/апаратний/програмний рівень; CME — Concept Micro-Engine;
BRAM — блокова пам'ять; lowering — перенесення семантики у нижче представлення.
