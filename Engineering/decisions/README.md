# Карта інженерних рішень

* **Версія:** 0.4.0
* **Дата:** 2026-11-17
* **Тип WP:** Guide

## Призначення та навігація

Рішення можуть бути розділами Design або Specification. Тут немає
дублікатів ADR із власним, потенційно суперечливим текстом.

| Рішення | Основний запис і залежності |
|---|---|
| B1: системна межа | [Compiler + loader + PL](../design/system-boundary-allocation-b1.md). |
| B2: вхід події | [Інтеграція фізичного входу](../design/bram-pipeline-event-integration.md). |
| B3-01 / B3-02: KPOL-CME-1 та KPOL-CME-2 | [Профіль `KPOL-CME-1`](../specifications/kpol/kpol-cme-subset-0.1.0.md) та [багатоконцептний профіль `KPOL-CME-2`](../specifications/kpol/kpol-cme2-profile-0.1.0.md) на `CME-RAW-1`. |
| B4: образ і loader (`CFG-P` та `CFG-P-HA`) | [Контракт завантаження v2.3.0](../specifications/hw/kpol-image-loader-pipeline-contract.md) (Варіант 1 `CFG-P` + двобанковий Варіант 2 `CFG-P-HA` у [#252](https://github.com/nick-fedchik/kuzmin-machine/issues/252)). |
| B5: черга та ingress | [Контракт черги](../specifications/hw/event-queue-ingress-specification.md). |
| B6: гетерогенний симбіоз із GPU | [Persistent Mega-Kernel для підписників v0.4.0](b6-gpu-persistent-kernel-subscribers.md) (верифіковано на GPU до `1024` підписників у `EXP-GPU-01` і `EXP-GPU-03`). |
| B7 (CR #185): `KPOL-SYS-02` та дескриптор `CME-RAW-2` | [Проєкт 32-байтного слота й біта ініціалізації `state_valid` (`_`)](cme-raw2-kpol-sys02.md) (прийнято власником за Варіантом А; RTL `CFG-P2` відкладено до відповіді на `RFC-017`). |

## Обмеження

Статуси й рішення належать джерельним документам та власнику;
наявність цієї карти не є повторним затвердженням. Зміни розглядаються
разом із залежними вимогами, кодом і перевірками.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.4.0 | 2026-11-17 | #8: актуалізовано посилання й статуси B3 (`KPOL-CME-2`), B4 v2.3.0 (`CFG-P-HA`, #252), B6 v0.4.0 (`EXP-GPU-01` v0.4.0 та `EXP-GPU-03` #256) і B7 v0.2.0 (#215). |
| 0.3.0 | 2026-11-14 | Додано архітектурне рішення B7 / CR [#185](https://github.com/nick-fedchik/kuzmin-machine/issues/185) щодо `KPOL-SYS-02` (`state_valid`) та 32-байтного дескриптора `CME-RAW-2` (Proposed). |
| 0.2.0 | 2026-11-12 | Додано рішення B6 щодо гетерогенного симбіозу з GPU. |
| 0.1.0 | 2026-11-12 | Карта без дублювання нормативного змісту. |

## Абревіатури та глосарій

ADR — Architecture Decision Record; PL — програмована логіка FPGA.
