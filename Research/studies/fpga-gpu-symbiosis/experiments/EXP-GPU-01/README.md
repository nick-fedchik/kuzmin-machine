# Пакет апаратного HIL-експерименту EXP-GPU-01: Симбіоз ПЛІС та GPU

* **Версія:** 0.4.0
* **Дата:** 2026-11-17
* **Тип WP:** Guide
* **Статус:** Виконано для GPU Фази 3–4 ([#225](https://github.com/nick-fedchik/kuzmin-machine/issues/225), [#229](https://github.com/nick-fedchik/kuzmin-machine/issues/229), [#235](https://github.com/nick-fedchik/kuzmin-machine/issues/235), [#240](https://github.com/nick-fedchik/kuzmin-machine/issues/240)) та для OpenXC7 бітстріму `pipeline_egress.bit` (`101.67 МГц PASS`), живої перевірки на `PYNQ-Z1 + RP2040 PIO` (`340 нс`) і міжплатного контуру `PYNQ-Z1 -> GbE -> Jetson AGX Orin J501` ($R = 5 \times 1\,000$ подій, `Part of` [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226) у [`report-phase1-2-4-crossboard-egress.md`](report-phase1-2-4-crossboard-egress.md)).
* **Власник:** Микола Федчик; автор експерименту — Микола Федчик.

## Призначення та навігація

Цей пакет містить інженерні документи стендового експерименту (Hardware-in-the-Loop, HIL) у межах дослідницького проєкту [fpga-gpu-symbiosis](../../README.md). Експеримент досліджує фізичне стикування плати ПЛІС PYNQ-Z1 (Машина Кузьміна з модулем розширення `PMOD Event Egress`) та обчислювального модуля NVIDIA Jetson AGX Orin 64GB (Seeed Studio reServer Industrial J501) через узгоджений за рівнями цифровий інтерфейс із реєстрацією часових інтервалів цифровим логічним аналізатором Raspberry Pi Pico (`RP2040 PIO`, крок `8 нс` @ 125 МГц).

| Документ | Тип WP | Призначення |
|---|---|---|
| [protocol.md](protocol.md) | Protocol | Нормативний протокол випробувань: вимірювані метрики, часові допуски, покроковий регламент вимірювань, критерії Pass/Fail. |
| [plan.md](plan.md) | Plan | Операційний план підготовки стенду, монтаж з'єднувального шлейфу DuPont, розподіл пінів та календарний графік 4 фаз. |
| [j501-hardware-interface.md](j501-hardware-interface.md) | Specification | Інженерний аналіз несучої плати Seeed Studio reServer Industrial J501 (схемотехніка DI/DO/CAN, оптрони SFH690BT, часовий бюджет). |
| [report-phase3-warp-scaling.md](report-phase3-warp-scaling.md) | Report | Емпіричний звіт Фази 3–4 на Jetson AGX Orin (#225, #229, #235, #240): 128-Б L2 mailbox, декуплінг L2 Read Snoop, декомпозиція `Host RT` та міжпрогонна повторюваність $R=5$ для `32..1024` підписників. |
| [report-phase1-2-4-crossboard-egress.md](report-phase1-2-4-crossboard-egress.md) | Report | Емпіричний звіт Фаз 1–2, 4 (`Part of #226`): фізичний P&R `pipeline_egress.bit` (`101.67 МГц PASS`), захват `LOGICTRACER_PICO_0.5.0` (`340 нс`) на `PYNQ-Z1` та міжплатний контур `PYNQ-Z1 -> GbE -> Jetson AGX Orin J501` ($R = 5 \times 1\,000$ подій, `1 024` підписники) з перевіркою критерію фальсифікації Поппера. |
| [crossboard_frame.py](crossboard_frame.py) | Code | Еталонне пакування/верифікація 64-бітного кадра `km_pmod_event_egress` (`CRC-8 poly 0x07`) та агрегатор статистики міжплатних серій. |
| [crossboard_egress_server.cu](crossboard_egress_server.cu) | Code | Сервер `Jetson AGX Orin J501` із персистентним кернелом GPU (`16×64 = 1 024` підписники у `cudaHostAllocMapped`) та перевіркою `CRC-8`. |
| [crossboard_egress_client.c](crossboard_egress_client.c) | Code | Клієнт `PYNQ-Z1` (`0x40000000` PL + генерація 64-бітного кадра з `CRC-8` + UDP `SO_BUSY_POLL`). |
| [persistent_subscribers.cu](persistent_subscribers.cu) | Code | Реалізація персистентного кернела підписників CUDA (`SM 8.7`) з режимами `partitioned` / `shared_2line` / `shared_1line` та незалежною CPU-моделлю. |
| [summarize_repeatability_240.py](summarize_repeatability_240.py) | Code | Детермінований агрегатор міжпрогонної повторюваності ($R=5$, `ddof=1`, `CV%`, декомпозиція `Host RT`) для набору `repeatability-240`. |
| [Експеримент EXP-GPU-02](../EXP-GPU-02/README.md) | Guide | Наступний HIL-експеримент: динамічне оновлення правил у BRAM на льоту (Zero-Downtime Rule Injection). |
| [Пакет дослідження](../../README.md) | Guide | Загальний дослідницький пакет: постановка проблеми, аналітична модель, загальний протокол та аналітичний звіт. |
| [Рішення B6](../../../../../Engineering/decisions/b6-gpu-persistent-kernel-subscribers.md) | Decision | Архітектурне рішення (ADR B6): концепція Persistent Mega-Kernel для усунення Callback Bottleneck. |

## Огляд чотирьох фаз експерименту

1. **Фаза 1 (Baseline SPI DMA):** Базовий трансфер 64-бітної бітової маски подій на частоті SPI 50 МГц.
2. **Фаза 2 (Parallel Bus):** 8-бітний джерельно-синхронний паралельний інтерфейс зі стробом синхронізації ($T_{\text{bus}} \le 160\text{ нс}$).
3. **Фаза 3 (Persistent Mega-Kernel):** Атомарне `acquire`-опитування когерентного `Event Mailbox` у `L2`-кеші GPU з резидентним утриманням станів підписників у регістрах і `Shared Memory` SM без виклику хост-драйвера на кожну подію.
4. **Фаза 4 (RP2040 PIO Digital Profiling):** Цифрова фіксація часового інтервалу між імпульсом події ПЛІС (`GP0`) та стробом реакції GPU (`GP1`) проти цільового критерію $T_{\text{e2e}} \le 1.0\ \mu\text{с}$, $\sigma \le 50\text{ нс}$.

## Історія версій

| Версія | Дата | Автор | Зміни |
|---|---|---|---|
| 0.4.0 | 2026-11-17 | GitHub Copilot CLI | #226: додано `report-phase1-2-4-crossboard-egress.md`, `crossboard_frame.py`, `crossboard_egress_server.cu` та `crossboard_egress_client.c`. |
| 0.3.1 | 2026-11-16 | GitHub Copilot CLI | #240: оновлено посилання на звіт `0.4.0` (`32..1024`, $R=5$) і додано `summarize_repeatability_240.py`. |
| 0.3.0 | 2026-11-15 | GitHub Copilot CLI (`gemini-4-carbon`) | #225: додано `persistent_subscribers.cu`, тести та звіт Фази 3–4 (`report-phase3-warp-scaling.md`); фізичне замикання з PYNQ-Z1 винесено в #226. |
| 0.2.0 | 2026-11-14 | Микола Федчик, Copilot CLI | #166: уточнено цифровий режим `RP2040 PIO`, передумову `PMOD Event Egress` та ієрархію пам'яті `Event Mailbox + Shared Memory`. |
| 0.1.0 | 2026-11-12 | Микола Федчик | Початкова редакція навігаційного посібника експерименту EXP-GPU-01 у складі Research/studies/fpga-gpu-symbiosis/. |

## Абревіатури та глосарій

* **ADR** (Architecture Decision Record) — запис архітектурного рішення.
* **DMA** (Direct Memory Access) — прямий доступ до пам'яті без участі процесора.
* **HIL** (Hardware-in-the-Loop) — апаратне тестування в замкненому контурі.
* **SPI** (Serial Peripheral Interface) — послідовний синхронний інтерфейс.
