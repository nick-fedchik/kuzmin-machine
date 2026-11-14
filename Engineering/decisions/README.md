# Карта інженерних рішень

* **Версія:** 0.3.0
* **Дата:** 2026-11-14
* **Тип WP:** Guide

## Призначення та навігація

Рішення можуть бути розділами Design або Specification. Тут немає
дублікатів ADR із власним, потенційно суперечливим текстом.

| Рішення | Основний запис і залежності |
|---|---|
| B1: системна межа | [Compiler + loader + PL](../design/system-boundary-allocation-b1.md). |
| B2: вхід події | [Інтеграція фізичного входу](../design/bram-pipeline-event-integration.md). |
| B3-01: KPOL-CME-1 | [Профіль і ABI](../specifications/kpol/kpol-cme-subset-0.1.0.md). |
| B4: образ і loader | [Контракт завантаження](../specifications/hw/kpol-image-loader-pipeline-contract.md). |
| B5: черга та ingress | [Контракт черги](../specifications/hw/event-queue-ingress-specification.md). |
| B6: гетерогенний симбіоз із GPU | [Persistent Mega-Kernel для підписників](b6-gpu-persistent-kernel-subscribers.md). |
| B7 (CR #185): `KPOL-SYS-02` та дескриптор `CME-RAW-2` | [Проєкт 32-байтного слота й біта ініціалізації `state_valid` (`_`)](cme-raw2-kpol-sys02.md) (Proposed). |

## Обмеження

Статуси й рішення належать джерельним документам та власнику;
наявність цієї карти не є повторним затвердженням. Зміни розглядаються
разом із залежними вимогами, кодом і перевірками.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.3.0 | 2026-11-14 | Додано архітектурне рішення B7 / CR [#185](https://github.com/nick-fedchik/kuzmin-machine/issues/185) щодо `KPOL-SYS-02` (`state_valid`) та 32-байтного дескриптора `CME-RAW-2` (Proposed). |
| 0.2.0 | 2026-11-12 | Додано рішення B6 щодо гетерогенного симбіозу з GPU. |
| 0.1.0 | 2026-11-12 | Карта без дублювання нормативного змісту. |

## Абревіатури та глосарій

ADR — Architecture Decision Record; PL — програмована логіка FPGA.
