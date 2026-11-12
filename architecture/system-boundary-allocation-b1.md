# Системна межа та розподіл вимог HW/SW (S2 / B1)

* **Тип Work Product:** `Specification` / `Design` (підтип `Architecture Decision Record & Allocation`)
* **Версія:** 1.0.0
* **Дата:** 2026-11-12
* **Автор:** Antigravity (agy)
* **Статус:** Нормативно зафіксовано (Approved Baseline)
* **ASPICE 4.0 процеси:** `SYS.2` (System Requirements Analysis), `SYS.3` (System Architecture Design), `HWE.1`, `SWE.1`
* **Work Item:** Задача [#136](https://github.com/nick-fedchik/kuzmin-machine/issues/136) (Parent: [#5](https://github.com/nick-fedchik/kuzmin-machine/issues/5))

---

## 1. Контекст, мета та проблема

### 1.1. Проблема визначення об'єкта системи
На етапі S2 постало фундаментальне питання системної інженерії: **що саме є межами цільової системи Машини Кузьміна**, для якої встановлюються, розподіляються та перевіряються системні (`SYS`), апаратні (`HW`) та програмні (`SW`) вимоги.

Історичні матеріали проєкту містили амбівалентність:
1. З одного боку, Машина Кузьміна розглядалася як виключно апаратний процесор подій (PL-обчислювач у ПЛІС/FPGA), для якого трансляція коду KPOL та завантаження образів вважалися зовнішніми допоміжними утилітами. За такого підходу залишався безвідповідальним наскрізний контракт між високорівневою семантикою правил та їхнім відображенням у фізичну пам'ять.
2. З іншого боку, низка вимог висувалася до компілятора та рантайму без чіткого розподілу відповідальності між хостом (PS / ARM Cortex-A9) та програмованою логікою (PL).

### 1.2. Мета роботи
Формалізувати архітектурне рішення **B1** ([`architecture/s2-candidate-system.md`, §7.1](s2-candidate-system.md#71-пять-рішень-для-погодження)), визначити однозначну системну межу, розмежувати внутрішні компоненти від зовнішніх акторів, зафіксувати фазовий життєвий цикл, переглянути статус кандидатних вимог `C-SYS-001/002`, `C-SW-001`, `C-HW-001` та встановити нормативну матрицю розподілу вимог (HW/SW Allocation Matrix) згідно з ASPICE 4.0 SYS.2 / SYS.3.

---

## 2. Архітектурне рішення B1 (Decision / ADR B1)

### 2.1. Альтернативи для вибору

* **Альтернатива 1: Мінімальна межа (Тільки PL-виконавець).**  
  Цільовою системою оголошується виключно цифрова логіка в PL (BRAM, секвенсер, CME, транзакційний шлюз). Компілятор KPOL, завантажувач та драйвер розглядаються як зовнішні інструменти розробника.  
  * *Переваги:* Мінімізація зони відповідальності апаратного ядра.  
  * *Недоліки:* Руйнування наскрізної трасованості. Неможливо довести головну мету `G1` / `N2` (зв'язати KPOL з об'єктом виконання), оскільки помилки трансляції або несумісність форматів образів опиняються поза межами системи.

* **Альтернатива 2: Тріадна система (Compiler + Loader + PL-виконавець) — [ОБРАНО].**  
  Цільова система охоплює повний тракт: **компілятор KPOL (SW) $\to$ завантажувач / драйвер (FW/SW) $\to$ конвеєрний обчислювач BRAM (HW PL)**.  
  Програміст, фізичне джерело подій, зовнішні засоби вимірювання (осцилограф, логічний аналізатор) та незалежний аудитор/верифікатор є **зовнішніми ролями**.  
  * *Обґрунтування:* Досягнення цілі `G1` вимагає верифікованого наскрізного шляху:
    $$\text{Текст програми KPOL} \xrightarrow{\text{Compiler}} \text{1024-байтний образ} \xrightarrow{\text{Loader}} \text{Пам'ять BRAM} \xrightarrow{\text{PL Execution}} \text{Спостережуваний апаратний результат}$$
    Відповідальність за цілісність цього тракту, відповідність форматів дескрипторів та часові межі завантаження закріплюється всередині системи.

### 2.2. Формальне рішення
1. **Затвердити Альтернативу 2** як нормативну системну межу проєкту «Машина Кузьміна» для етапу MVP (TRL 4).
2. Зафіксувати чітке розділення фаз життєвого циклу: підготовка (`PHASE_LOAD`), автономне виконання (`PHASE_RUN`) та неінвазивне спостереження / телеметрія.

```
+--------------------------------------------------------------------------------------------------+
|                                    ЦІЛЬОВА СИСТЕМА (SYSTEM BOUNDARY)                             |
|                                                                                                  |
|   +-----------------------+        +--------------------------+        +---------------------+   |
|   |    Compiler (SW)      |        |   Loader / Driver (SW)   |        |   PL Pipeline (HW)  |   |
|   |                       |        |                          |        |                     |   |
|   | • Parser / AST        | =====> | • Host / PYNQ MMIO       | =====> | • AXI BRAM Intercon |   |
|   | • Semantics Checker   | 1024 B | • Phase Orchestrator     | AXI-4L | • BRAM 64x16 B      |   |
|   | • Image Emitter       |  Image | • Telemetry Collector    |  MMIO  | • Sequencer + FIFO  |   |
|   +-----------------------+        +--------------------------+        | • CME + Gate v2     |   |
|                                                                        +----------+----------+   |
+-----------------------------------------------------------------------------------|--------------+
                                                                                    |
             ^ Зовнішній текст KPOL                                                 | Фізичні сигнали
             |                                                                      v (LED, PMOD)
+-----------------------+                                                +---------------------+
|      Програміст       |                                                |  Зовнішні прилади / |
|   (External Role)     |                                                |  Логічний аналізатор|
+-----------------------+                                                +---------------------+
```

---

## 3. Деталізація ролей, інтерфейсів та життєвого циклу

### 3.1. Внутрішні компоненти системи
1. **KPOL Compiler (SW):** Модуль [`sw/kpol-ref/kpol_reference.py`](../sw/kpol-ref/kpol_reference.py) та утиліти компіляції ([`hw/scripts/compile_kpol_bram_image.py`](../hw/scripts/compile_kpol_bram_image.py)). Відповідає за синтаксичний аналіз підмножини KPOL 0.1.0 ([`specs/kpol/kpol-consolidated-0.1.0.md`](../specs/kpol/kpol-consolidated-0.1.0.md)), видобування предикатів і дій, детерміновану емісію 1024-байтного образу (64 концепти по 16 байтів).
2. **KPOL Image Loader & Driver (FW / SW):** Рантайм хоста на базі Python/C ([`sw/runtime/pynq/`](../sw/runtime/pynq/)). Відповідає за переведення ядра у фазу `PHASE_LOAD`, запис 256 слів дескрипторів через AXI4-Lite у BRAM, ініціацію фази `PHASE_RUN`, а також зчитування телеметрії без порушення детермінізму конвеєра.
3. **PL Pipeline Execution Engine (HW):** Програмована логіка ПЛІС у конфігурації `CFG-P` ([`hw/boards/pynq-z1/kpol_bram_pipeline_pynq_z1_top.v`](../hw/boards/pynq-z1/kpol_bram_pipeline_pynq_z1_top.v) та [`hw/rtl/bus/kpol_bram_pipeline_axi.sv`](../hw/rtl/bus/kpol_bram_pipeline_axi.sv)):
   - AXI4-Lite Slave інтерфейс із захистом від запису при `busy == 1` ([`specs/hw/kpol-image-loader-pipeline-contract.md`](../specs/hw/kpol-image-loader-pipeline-contract.md)).
   - Dual-Port BRAM пам'ять дескрипторів і стану концептів.
   - Вхідна черга FIFO 16 з гібридним арбітражем (підписник над зовнішнім стимулом) та прапорцем переповнення ([`specs/hw/event-queue-ingress-specification.md`](../specs/hw/event-queue-ingress-specification.md)).
   - Concept Micro-Engine (CME) та Transaction Gate v2 з доведеною властивістю fail-closed ([PR #130](https://github.com/nick-fedchik/kuzmin-machine/pull/130)).
   - Модулі CDC 2-FF та Pulse Stretcher для зв'язку з фізичними виводами кристала ([`architecture/bram-pipeline-event-integration.md`](bram-pipeline-event-integration.md)).

### 3.2. Зовнішні ролі (External Actors)
1. **Програміст / Оператор:** Подає вихідні тексти правил KPOL. Знаходиться поза межами цільової системи.
2. **Джерело зовнішніх стимулів:** Фізичні датчики, кнопки, інтерфейси PMOD або генератори тестових імпульсів. Подають асинхронні цифрові сигнали на піни FPGA.
3. **Вимірювальне обладнання:** Осцилографи, логічні аналізатори, тестові фреймворки HIL. Фіксують фізичні імпульси Commit / Reject на пінах `pmodja` та світлодіодах `led`.
4. **Засоби синтезу (EDA Tools):** Vivado Design Suite. Використовуються для створення статичного бітстріму FPGA; динамічне виконання не потребує їхнього повторного виклику.

### 3.3. Фазовий життєвий цикл
* **Фаза підготовки (`PHASE_LOAD`):** Виконується за участю хоста (PS). BRAM відкрита для запису через AXI. Конвеєр перебуває в режимі очікування (`busy = 0`). Будь-яка зовнішня подія ігнорується або блокується через backpressure `hw_trigger_ready_o = 0`.
* **Фаза автономного виконання (`PHASE_RUN`):** Хост переводить модуль у робочий режим. Дозволяється прийом подій чергою FIFO. При обробці події (`busy = 1`) спроби запису в BRAM відхиляються з кодом `AXI_RESP_SLVERR`. Обчислення виконуються суто апаратно за фіксовані 8 тактів ($80\text{ нс}$).
* **Фаза неінвазивної телеметрії:** Дозволяє хосту зчитувати регістри циклів, лічильники оброблених/відхилених подій та статус затримки без жодного впливу на хід конвеєра.

---

## 4. Нормалізація кандидатних вимог (Resolution of C-* Requirements)

На етапі S2 було висунуто чотири кандидатні вимоги (`C-SYS-001`, `C-SYS-002`, `C-SW-001`, `C-HW-001`). За результатами фізичних випробувань на стенді PYNQ-Z1 (S4 / [PR #137](https://github.com/nick-fedchik/kuzmin-machine/pull/137)), консолідації специфікації KPOL ([PR #131](https://github.com/nick-fedchik/kuzmin-machine/pull/131)) та закриття прогалин B2, B4, B5 ([PR #139](https://github.com/nick-fedchik/kuzmin-machine/pull/139), [PR #140](https://github.com/nick-fedchik/kuzmin-machine/pull/140), [PR #141](https://github.com/nick-fedchik/kuzmin-machine/pull/141)), ці вимоги переводяться в нормативний статус:

| Кандидатний ID | Нормативний ID вимоги | Зміст та критерій верифікації | Статус та фізичний доказ |
| :--- | :--- | :--- | :--- |
| `C-SYS-001` + `C-SYS-002` | `REQ-SYS-017` | **End-to-End Behavioral Differentiation & Guard Invariance:** За єдиним наскрізним трактом система зобов'язана виконувати різні програми KPOL (`Increase` та `Decrease`): після валідного імпульсу `Pulse(5)` стан `Counter` змінюється на 11 або 9 відповідно; після невалідного `Pulse(25)` стан залишається 11 або 9 без зміни стану пам'яті (fail-closed guard). | **ПІДТВЕРДЖЕНО ФІЗИЧНО** на платі PYNQ-Z1 в експерименті S4 (Issue [#7](https://github.com/nick-fedchik/kuzmin-machine/issues/7), [PR #137](https://github.com/nick-fedchik/kuzmin-machine/pull/137)). |
| `C-SW-001` | `REQ-SW-013` | **Deterministic 1024-Byte Binary Descriptor Emitter:** Компілятор KPOL зобов'язаний транслювати AST погодженої підмножини мови у бінарний масив рівно 1024 байти (64 концепти по 16 байтів), де кожен дескриптор містить поля `guard_mask`, `action_code`, `param`, `invariant_bound`, `subscriber_cid`. | **ПІДТВЕРДЖЕНО** в юніт-тестах компілятора (`test_kpol_reference.py`) та бінарній збірці образу для S4 ([`hw/scripts/compile_kpol_bram_image.py`](../hw/scripts/compile_kpol_bram_image.py)). |
| `C-HW-001` | `REQ-HW-018` | **Sequential AXI Ingestion of 256 Words into BRAM:** Апаратна обгортка BRAM-конвеєра зобов'язана забезпечувати безпомилковий запис 256 слів (32-бітних) образу через інтерфейс AXI4-Lite з відповідями `AXI_RESP_OKAY` у фазі `PHASE_LOAD`, та блокувати модифікацію під час `busy == 1`. | **ПІДТВЕРДЖЕНО** у симуляції (`kpol_bram_pipeline_axi_tb.sv`) та фізично на стенді PYNQ-Z1 ([`hw/boards/pynq-z1/hil/hil_kpol_bram_pipeline.py`](../hw/boards/pynq-z1/hil/hil_kpol_bram_pipeline.py)). |

---

## 5. Матриця розподілу вимог (HW / SW Allocation Matrix)

Відповідно до процесів ASPICE 4.0 **SYS.2** (Аналіз системних вимог) та **SYS.3** (Проєктування архітектури), всі затверджені системні вимоги розподілено між апаратними (HW) та програмними (SW) компонентами:

```
[System Requirements (SYS.2)]
          |
          +---- Allocated to HW (HWE.1) ---> BRAM, Sequencer, CME, Transaction Gate, CDC
          |
          +---- Allocated to SW (SWE.1) ---> KPOL Compiler, Image Emitter, Host Loader/Driver
```

| ID системної вимоги (SYS.2 / SYS.3) | Розподіл (Allocation) | Реалізуючий модуль / компонент | Підпорядковані вимоги (HWE.1 / SWE.1) |
| :--- | :--- | :--- | :--- |
| `REQ-SYS-001`, `REQ-SYS-006` (Fail-Closed) | **HW** | `hw/rtl/core/kpol_txn_gate_v2.sv` | `REQ-HW-001`, `REQ-HW-006` |
| `REQ-SYS-002`, `REQ-SYS-011` (Autonomous Seq) | **HW** | `hw/rtl/core/km_autonomous_sequencer.sv` | `REQ-HW-002`, `REQ-HW-011` |
| `REQ-SYS-003`, `REQ-SYS-012` (Deterministic Latency) | **HW** | `hw/rtl/core/km_concept_micro_engine.sv` | `REQ-HW-003`, `REQ-HW-012` |
| `REQ-SYS-004`, `REQ-SYS-013`, `REQ-SYS-014` (FIFO & Arb) | **HW** | `hw/rtl/core/km_autonomous_sequencer.sv` | `REQ-HW-004`, `REQ-HW-014`, `REQ-HW-015` |
| `REQ-SYS-005` (Invariant Bound Enforcement) | **HW** | `hw/rtl/core/km_concept_micro_engine.sv` | `REQ-HW-005`, `REQ-HW-016` |
| `REQ-SYS-015`, `REQ-SYS-016` (Lifecycle & Telemetry) | **HW / SW** | `kpol_bram_pipeline_axi.sv` / `hil_runner.py` | `REQ-HW-017`, `REQ-SW-011`, `REQ-SW-012` |
| `REQ-SYS-017` (End-to-End Behavioral Differentiation) | **HW / SW** | Тріада: Compiler + Loader + Pipeline PL | `REQ-SW-013`, `REQ-HW-018` |

---

## 6. Двоспрямоване трасування (Bidirectional Traceability Register)

Цей реєстр демонструє наскрізний зв'язок від верхньорівневих цілей проєкту до конкретних елементів реалізації та протоколів верифікації:

| Ціль / Потреба | Системні вимоги (SYS) | Компонентна вимога (HW/SW) | Артефакт коду | Протокол перевірки / Доказ |
| :--- | :--- | :--- | :--- | :--- |
| **G1 / N1** (Детермінізм та fail-closed) | `REQ-SYS-001`, `REQ-SYS-003`, `REQ-SYS-012` | `REQ-HW-001`, `REQ-HW-012` | `kpol_txn_gate_v2.sv`, `km_concept_micro_engine.sv` | [PR #130](https://github.com/nick-fedchik/kuzmin-machine/pull/130) (BMC формальний доказ), `test_testbenches.py` |
| **G1 / N1** (Черга, арбітраж, захист від переповнення) | `REQ-SYS-004`, `REQ-SYS-013`, `REQ-SYS-014` | `REQ-HW-004`, `REQ-HW-014`, `REQ-HW-015`, `REQ-HW-016` | `km_autonomous_sequencer.sv` | [`specs/hw/event-queue-ingress-specification.md`](../specs/hw/event-queue-ingress-specification.md), [PR #140](https://github.com/nick-fedchik/kuzmin-machine/pull/140) |
| **G1 / N2** (Наскрізний шлях KPOL $\to$ BRAM) | `REQ-SYS-015`, `REQ-SYS-017` | `REQ-SW-013`, `REQ-HW-018` | `kpol_reference.py`, `compile_kpol_bram_image.py`, `kpol_bram_pipeline_axi.sv` | [PR #137](https://github.com/nick-fedchik/kuzmin-machine/pull/137) (Фізичний HIL тест на PYNQ-Z1) |
| **G1 / N2** (Контракт життєвого циклу завантаження) | `REQ-SYS-015`, `REQ-SYS-016` | `REQ-HW-017`, `REQ-SW-011`, `REQ-SW-012` | `kpol_bram_pipeline_axi.sv`, `hil_kpol_bram_pipeline.py` | [`specs/hw/kpol-image-loader-pipeline-contract.md`](../specs/hw/kpol-image-loader-pipeline-contract.md), [PR #141](https://github.com/nick-fedchik/kuzmin-machine/pull/141) |
| **G1 / N1, N2** (Зовнішній апаратний тригер події) | `REQ-SYS-011` | `REQ-HW-011`, `REQ-HW-013` | `kpol_bram_pipeline_pynq_z1_top.v` | [`architecture/bram-pipeline-event-integration.md`](bram-pipeline-event-integration.md), [PR #139](https://github.com/nick-fedchik/kuzmin-machine/pull/139) |

---

## 7. Межі та застереження

1. **Відокремлення конфігурацій `CFG-P` та `CFG-R`:** Ця системна межа визначає конфігурацію конвеєрного обчислювача `CFG-P` на базі BRAM. Реактивний фізичний шлюз `CFG-R` залишається окремим прийнятим результатом етапу S6 (AV-10/AV-11). Результат затримки $p_{99} \le 60\text{ нс}$ із `CFG-R` **не переноситься** на `CFG-P`, оскільки конвеєр BRAM має власну детерміновану латентність 8 тактів ($80\text{ нс}$).
2. **Статус криптографічного Secure Boot та ACL:** Відповідно до рішень щодо #67/#68, апаратна криптографія HMAC-SHA256 та anti-rollback залишаються поза межами поточного скоупу MVP (TRL 4). Дефект програмного тесту [#115](https://github.com/nick-fedchik/kuzmin-machine/issues/115) розглядається окремо як знахідка SUP.9 і не впливає на апаратне виконання конвеєра.

---

## Історія версій

| Версія | Дата | Автор | Зміни |
| :--- | :--- | :--- | :--- |
| 1.0.0 | 2026-11-12 | Antigravity (agy) | Первинна нормативна фіксація системної межі та розподілу HW/SW (Рішення B1, Issue #136). |
