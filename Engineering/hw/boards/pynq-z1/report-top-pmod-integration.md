# Звіт про реалізацію та синтез інтегрованого BRAM-конвеєра з фізичним тригером (CFG-P)

* **Тип Work Product:** `Report` (підтип `Analysis Report`)
* **Версія:** 1.0.1
* **Дата:** 2026-11-12
* **Автор:** Antigravity (agy, Lead Systems & Hardware Engineer)
* **ASPICE 4.0 процеси:** `SYS.3` (System Architectural Design), `HWE.1` (Hardware Requirements Analysis), `HWE.2` (Hardware Design), `HWE.3` (Hardware Verification)
* **Пов'язані рішення та задачі:**
  - Задача [#134](https://github.com/nick-fedchik/kuzmin-machine/issues/134) (Рішення B2, [`Engineering/design/bram-pipeline-event-integration.md`](../../../design/bram-pipeline-event-integration.md))
  - Задача [#135](https://github.com/nick-fedchik/kuzmin-machine/issues/135) (Рішення B5, [`Engineering/specifications/hw/event-queue-ingress-specification.md`](../../../specifications/hw/event-queue-ingress-specification.md))
  - Задача [#136](https://github.com/nick-fedchik/kuzmin-machine/issues/136) (Рішення B1, [`Engineering/design/system-boundary-allocation-b1.md`](../../../design/system-boundary-allocation-b1.md))
  - Монтажна схема стенда: [`Engineering/hw/boards/pynq-z1/hil-bench-wiring-guide.md`](hil-bench-wiring-guide.md)
* **Ціль / Потреби:** G1 (Автономний реактивний виконавець без PS) / N1 (Детермінізм реакції), N2 (Гнучкість KPOL через BRAM)

---


* **Тип WP редакції NG:** Report
* **Укладач редакції NG:** GitHub Copilot CLI, Auto; конкретна модель не атестована.
* **Підстава редакції NG:** команда власника від 2026-11-12; локальне перенесення без legacy.
* **Походження:** [оригінал 1.0.0](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/hw/boards/pynq-z1/report-top-pmod-integration.md), `707fdba697d92ef9874c9013eb6f4f3cb2796d70`.
* **Стан редакції NG:** адаптовано до нової структури; незалежна рецензія не проведена.

> **Межі редакції NG.** Перенесення й оформлення не є новим експериментом,
> повторною науковою перевіркою або затвердженням baseline. Авторство,
> рішення, числа й рецензії нижче стосуються зазначених оригінальних
> об'єктів та версій, а не автоматично цієї локальної копії.

## 1. Мета та контекст

Цей звіт фіксує результати інженерної реалізації наскрізного фізичного тракту для конфігурації `CFG-P` (програмований BRAM-конвеєр KPOL) на платформі Digilent PYNQ-Z1 (Xilinx Zynq-7020).

До цієї модифікації конвеєр `CFG-P` міг ініціювати виконання концептів **виключно через програмний регістр MMIO** (`0x010`), а вхідні/вихідні фізичні лінії залишалися непідключеними. Крім того, вхідна черга секвенсера мовчазно відкидала події при переповненні (silent drop).

У цій роботі виконано:
1. Повну інтеграцію фізичного тригера події та реактивних виходів у топ-модуль `kpol_bram_pipeline_pynq_z1_top.v` та файл обмежень `kpol_bram_pipeline.xdc` (рішення B2);
2. Реалізацію нормативної політики черги FIFO із сигналом зворотного тиску (backpressure) та немовчазним обліком втрат у `km_autonomous_sequencer.sv` (рішення B5);
3. Доопрацювання шинної обгортки `kpol_bram_pipeline_axi.sv` для мультиплексування тригерів і виведення нових регістрів CSR (`0x028`, `0x02C`);
4. Повну верифікацію на рівні RTL-тестбенчів та перевірку синтезу Yosys для кристала XC7Z020.

---

## 2. Реалізовані зміни в RTL та XDC

### 2.1. Топ-модуль `kpol_bram_pipeline_pynq_z1_top.v`
- **Зовнішні інтерфейси:**
  - PMOD JA: `ja1` (Pin 1 / `Y18`, вхідний стимул), `ja2` (Pin 2 / `Y19`, вихід Commit), `ja3` (Pin 3 / `Y16`, вихід Reject), `ja4` (Pin 4 / `Y17`, вихід Busy).
  - Користувацькі кнопки: `btn[0]` (Pin `D19`, ручний апаратний тригер).
  - Користувацькі перемикачі: `sw[1:0]` (Pins `M20`, `M19`, вибір цільового концепту CID 0..3).
  - Світлодіоди: `led[0]` (Commit), `led[1]` (Reject), `led[2]` (Busy), `led[3]` (FIFO Overflow).
- **Синхронізація (CDC, REQ-HW-011):** 2-ступеневий тригерний синхронізатор на тактовій частоті $100\text{ МГц}$ та детектор переднього фронту (`posedge`) формують 1-тактовий строб тригера тривалістю $10\text{ нс}$.
- **Формувачі імпульсів (Pulse Stretchers):**
  - Для виходів PMOD JA (`ja2`, `ja3`): розтягування на 10 тактів ($100\text{ нс}$), що забезпечує надійну реєстрацію логічним аналізатором на Raspberry Pi Pico (період дискретизації $8\text{ нс}$, ~12 відліків на імпульс).
  - Для світлодіодів `led[0]`, `led[1]`: розтягування на $2^{22}$ тактів (~$41.9\text{ мс}$) для чіткої візуальної фіксації людським оком.

### 2.2. Автономний диспетчер `km_autonomous_sequencer.sv`
- **Параметризація:** введено параметр `QUEUE_DEPTH = 16` (REQ-HW-016).
- **Зворотний тиск (Backpressure, REQ-HW-014):** формування сигналу `hw_trigger_ready_o = (fifo_count_q < QUEUE_DEPTH)` та `fifo_full_o = (fifo_count_q == QUEUE_DEPTH)`.
- **Немовчазне переповнення (REQ-SYS-013, REQ-HW-015):** при надходженні події в заповнену чергу активується прапорець `fifo_overflow_o`, інкрементується лічильник `events_dropped_count_o`, а пам'ять дескрипторів BRAM і вже прийняті події залишаються цілісними.
- **Пріоритет каскаду (REQ-SYS-014):** внутрішні події підписників CME мають пріоритет над зовнішніми тригерами при колізіях на одному такті.
- **Однотактові строби рішень:** виведено строби `commit_pulse_o` та `reject_pulse_o` на такті `ST_EVAL_GATE`.

### 2.3. AXI-обгортка `kpol_bram_pipeline_axi.sv`
- **Арбітраж стимулів:** об'єднання програмного тригера MMIO (`write 0x010`) та зовнішнього апаратного тригера `ext_hw_trigger_valid_i`.
- **Нові регістри CSR:**
  - `0x028` (`R`): `events_dropped_count_o` (32-бітний лічильник відкинутих подій);
  - `0x02C` (`R`): статус черги `{15'b0, fifo_overflow_o, 8'b0, hw_trigger_ready_o, 7'b0}`.

### 2.4. Файл фізичних обмежень `kpol_bram_pipeline.xdc`
- Додано повні обмеження розміщення (`LOC`) та стандарту сигналів (`IOSTANDARD LVCMOS33`) для всіх задіяних пінів PMOD JA, кнопок, перемикачів і світлодіодів згідно зі схемою стенда.

---

## 3. Результати верифікації та синтезу

### 3.1. Синтез OpenXC7 / Yosys (`synth_xilinx`)
Синтез виконано командою:
```bash
yosys -p "read_verilog -sv \
  hw/rtl/core/kpol_txn_gate_v2.sv \
  hw/rtl/core/km_concept_micro_engine.sv \
  hw/rtl/core/km_concept_bram.sv \
  hw/rtl/core/km_autonomous_sequencer.sv \
  hw/rtl/bus/kpol_bram_pipeline_axi.sv \
  hw/boards/pynq-z1/kpol_bram_pipeline_pynq_z1_top.v; \
  synth_xilinx -flatten -abc9 -arch xc7 -top kpol_bram_pipeline_pynq_z1_top; \
  stat; check"
```

**Результати звіту синтезу:**
- Статус перевірки: `Checking module kpol_bram_pipeline_pynq_z1_top... Found and reported 0 problems.`
- Використання ресурсів:
  - RAMB36E1: 1 (двопортовий BRAM концептів)
  - PS7: 1 (інтерфейс Zynq-7000 Processing System)
  - BUFG: 1 (буфер тактового дерева 100 МГц)
  - CARRY4: 114
  - Тригери (FDCE / FDRE): 1247
  - Таблиці перекодування (LUT2..LUT6): 1771
  - Оціночна кількість логічних осередків (LC): 1597 (менше 3% від 53 200 LC кристала XC7Z020).

### 3.2. RTL-моделювання та стрес-тести
1. **`km_autonomous_sequencer_tb.sv`:**
   - Штатне виконання двох послідовних транзакцій з каскадом: стан 10 $\to$ 11, каскад 50 $\to$ 55 (успішно).
   - Відхилення за інваріантом (Fail-Closed Reject): транзакція відхилена, стан у BRAM зберігся ($20$).
   - Стрес-тест переповнення черги: пачка з 25 подій підряд перевірила досягнення `fifo_full`, блокування прийому, виставлення `fifo_overflow = 1`, фіксацію `events_dropped_count > 0` та відновлення `hw_trigger_ready = 1` після вичитки.
2. **`kpol_bram_pipeline_axi_tb.sv`:**
   - Верифіковано роботу як через AXI MMIO, так і через фізичний апаратний тригер `send_hw_trigger(cid=0, val=5)`.
   - Зміна стану $11 \to 12$ підтвердила працездатність тракту апаратного запуску.
   - Перевірено регістри `0x028` та `0x02C`.
3. **Загальний тестовий набір:**
   - Усі 193 тести `pytest` пройдено успішно (`193 passed in 9.18s`).
   - Перевірка посилань: `python3 tools/check_links.py` — 0 битих посилань.

---

## 4. Висновок та статус відповідності вимогам

| Вимога | Зміст | Статус | Доказ |
| :--- | :--- | :---: | :--- |
| `REQ-SYS-011` | Зовнішній апаратний тригер конвеєра | **Реалізовано** | `kpol_bram_pipeline_pynq_z1_top.v:51-64`, `kpol_bram_pipeline_axi_tb.sv:156` |
| `REQ-SYS-012` | Фізична індикація Fail-Closed | **Реалізовано** | `kpol_bram_pipeline_pynq_z1_top.v:114-142`, `km_autonomous_sequencer_tb.sv:217` |
| `REQ-SYS-013` | Немовчазне відкидання подій (Non-Silent Drop) | **Реалізовано** | `km_autonomous_sequencer.sv:198-204`, `km_autonomous_sequencer_tb.sv:239-269` |
| `REQ-SYS-014` | Пріоритет внутрішнього каскаду над стимулом | **Реалізовано** | `km_autonomous_sequencer.sv:155-188` |
| `REQ-HW-011` | CDC синхронізатор (2-FF, MTBF $> 10^9$ год) | **Реалізовано** | `kpol_bram_pipeline_pynq_z1_top.v:51-64` |
| `REQ-HW-012` | Детермінований цикл виконання 8 тактів (80 нс) | **Підтверджено** | `km_autonomous_sequencer.sv:214-279` |
| `REQ-HW-014` | Сигналізація зворотного тиску `ready_o` | **Реалізовано** | `km_autonomous_sequencer.sv:138`, `km_autonomous_sequencer_tb.sv:263` |
| `REQ-HW-015` | Ізоляція пам'яті BRAM при переповненні | **Підтверджено** | `km_autonomous_sequencer.sv:198-204` |
| `REQ-HW-016` | Параметризація глибини черги `QUEUE_DEPTH` | **Реалізовано** | `km_autonomous_sequencer.sv:10` |

Апаратний тракт повністю готовий до збирання бітстріму та фізичного підключення стенда з Raspberry Pi Pico.

---

## Історія версій

| Версія | Дата | Автор | Зміни |
| :--- | :--- | :--- | :--- |
| 1.0.1 | 2026-11-12 | Редакція NG: структура, навігація та оформлення WP; нових результатів не заявлено. |
| **1.0.0** | 2026-11-12 | Antigravity (agy) | Початковий звіт про реалізацію та синтез BRAM-конвеєра з фізичним тригером (B2/B5/HWE.1..HWE.3). |

## Абревіатури та глосарій

| Термін | Значення |
|---|---|
| WP | Work Product, результат роботи з визначеним призначенням. |
| NG | Нова структура локальної робочої копії; не нова доказова baseline. |
| SHA | Ідентифікатор Git-коміту або контрольна сума з указаним алгоритмом. |

## Контроль редакції NG

Метод цієї редакції — структурне перенесення, перевірка навігації та залежностей;
не повторний апаратний прогін. Точний склад і початкові хеші наведено в
[маніфесті](../../../../Project/registers/migration-manifest.json).
Рецензії оригіналу не є рецензіями цієї редакції. Для нового вимірювання потрібні
новий протокол/прогін та новий незмінний набір даних; невідоме походження не домислюється.
