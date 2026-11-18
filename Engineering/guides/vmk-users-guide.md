# Посібник користувача VMK (Virtual Machine of Kuzmin) та 4-панельного TUI-дебагера (`Engineering/sw/vmk-go`, SemVer `0.1.0`)

* **Версія:** 1.0.1
* **Дата:** 2026-11-18
* **Тип WP:** Guide
* **Статус:** Чинний практичний посібник користувача
* **Issue:** `Closes` [#276](https://github.com/nick-fedchik/kuzmin-machine/issues/276); пов'язані задачі [#274](https://github.com/nick-fedchik/kuzmin-machine/issues/274), [#272](https://github.com/nick-fedchik/kuzmin-machine/issues/272), [#270](https://github.com/nick-fedchik/kuzmin-machine/issues/270), [#252](https://github.com/nick-fedchik/kuzmin-machine/issues/252), [#253](https://github.com/nick-fedchik/kuzmin-machine/issues/253), [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186).
* **Відповідальний:** власник Микола Федчик; укладач — GitHub Copilot CLI (Lead Engineer / Documentation Engineer).
* **Цільовий модуль ПЗ:** [`Engineering/sw/vmk-go/`](../sw/vmk-go/README.md) ([`cmd/vmk/main.go`](../sw/vmk-go/cmd/vmk/main.go), [`internal/vmk/`](../sw/vmk-go/internal/vmk/cli.go), `go 1.22`+, `std` only).
* **Нормативна специфікація та звіт верифікації:** [`Engineering/specifications/sw/vmk-go-emulator-and-tui-debugger-0.1.0.md`](../specifications/sw/vmk-go-emulator-and-tui-debugger-0.1.0.md) (`1.0.1`), [`Engineering/validation/kpol-cme/vmk-go-274/report.md`](../validation/kpol-cme/vmk-go-274/report.md) (`1.0.1`).

---

## Призначення

Цей посібник призначений для системних, апаратних (FPGA/RTL) та вбудованих (C99/Go/Python) інженерів, дослідників реактивних обчислень та верифікаторів проєкту **Машини Кузьміна** (`nick-fedchik/kuzmin-machine`). Документ покроково пояснює, як збирати та використовувати виконуваний бінарник **`vmk` (`VMK — Virtual Machine of Kuzmin v0.1.0`)**, розташований у [`Engineering/sw/vmk-go/`](../sw/vmk-go/README.md).

### Що таке VMK і яку задачу він вирішує

На відміну від класичних процесорів фон Неймана, у Машині Кузьміна (автор концепції — **Михайло Ювеналійович Кузьмін**, первинні матеріали в [`Research/sources/`](../../Research/sources/README.md)) **немає глобального лічильника команд (`Program Counter, PC`)** і немає послідовного потоку інструкцій. Одиницею стану, захисту та реакції є **концепт (`Concept`)**, а виконання програми відбувається як поширення **хвилі подій (`Event Cascade Wave`)** за графом підписок між концептами:

$$\text{External Event } (cid_0, \text{param}, \text{valid}) \longrightarrow C_0 \xrightarrow{\text{COMMIT}} C_1 \xrightarrow{\text{COMMIT}} \dots \xrightarrow{\text{COMMIT}} C_k$$

Через відсутність `PC` традиційні дебагери на кшталт `gdb` або `lldb` (побудовані навколо точок зупинки за адресою інструкції та стека викликів) не придатні для діагностики програм МК. Коли каскад зупиняється або видає неочікуваний стан, інженер має бачити:
1. Скільки концептів було завантажено в машину **до** програмування (`PRE-LOAD State`) і як змінилася топологія слотів **після** завантаження (`POST-LOAD State & Diff`);
2. Яку саме з **10 внутрішніх фаз оцінки концепту** не пройшла подія на глибині каскаду `Depth = d`: чи спрацював вхідний предикат припущення `::` (`Predicate`), яке значення-кандидат обчислила дія (`Action`), чи пропустив його пост-умовний вентиль інваріанта Великої Крапки `•` (`Invariant Gate`), чи подія була заблокована через стан невизначеності `_` (`REJECT_FAULT`);
3. Як події проходять крізь стандартні потоки UNIX (`STDIN` $\to$ `STDOUT` для `COMMIT`/`READ` та `STDERR` для `REJECT_*`).

Саме для цього в модулі [`Engineering/sw/vmk-go/`](../sw/vmk-go/go.mod) створено самодостатній двомодовий емулятор і 4-панельний TUI-дебагер `vmk` на мові Go (виключно стандартна бібліотека `std`, без жодної зовнішньої залежності), який поєднує два виконавчі режими:
* **`--mode conceptual`** — навчально-концептуальна віртуальна машина за первинними джерелами та відповідями Автора (`RFC-001..018`: типізовані концепти `?`, `Int32`, `U64`, `Float`, стан невизначеності `_`, 4 види адресації `←`, `→`, `|`, `:`, пост-адресний бар'єр Великої Крапки `•` після читання `→ •`, одноразовий захист від самозбудження `Busy`, колекції `{ ... }` «І», масиви вибору `[ ... ]` «АБО» та `Exit`);
* **`--mode bram64`** — побітово точна 64-слотова модель апаратного конвеєра дескрипторів `CME-RAW-1` (`1024 B`, однобанковий `CFG-P` та двобанковий `CFG-P-HA` з контрольною сумою `CRC-8-CCITT` і вхідною чергою `FIFO 16`), яка підтримує як локальну симуляцію (`--target sim`), так і пряме підключення по SSH/MMIO до фізичної плати ПЛІС **`Digilent PYNQ-Z1`** (`--target pynq1 | pynq2`).

---

## Навігація чи використання

### 2.1. Встановлення, збірка та швидкий старт за 30 секунд

Модуль [`Engineering/sw/vmk-go/`](../sw/vmk-go/go.mod) потребує лише стандартного компілятора Go версії **`go >= 1.22`** (перевірено на `go 1.22` в Ubuntu 24.04 GitHub Actions CI та локальному `go1.27.1 linux/amd64`) і не завантажує жодних пакетів із мережі (`0` директив `require` у `go.mod`).

#### Крок 1. Перевірка компілятора Go та запуск модульних тестів

```bash
cd Engineering/sw/vmk-go
go version
go test -v ./...
```

Очікуваний вивід модульних тестів (`< 0.05 с`):

```text
=== RUN   TestBRAM64PredicatesActionsInvariantsAndUncertainties
--- PASS: TestBRAM64PredicatesActionsInvariantsAndUncertainties (0.00s)
=== RUN   TestBRAM64OverflowFIFO16AndDualBankCRC8
--- PASS: TestBRAM64OverflowFIFO16AndDualBankCRC8 (0.00s)
=== RUN   TestBMSSafetyCascadeAndPrePostLoadDiff
--- PASS: TestBMSSafetyCascadeAndPrePostLoadDiff (0.00s)
=== RUN   TestConceptualModeAllSixExamples
--- PASS: TestConceptualModeAllSixExamples (0.00s)
=== RUN   TestCLIStdioFailOnRejectTUIAndUnreachableTarget
--- PASS: TestCLIStdioFailOnRejectTUIAndUnreachableTarget (0.01s)
=== RUN   TestAllPredicatesActionsSelfSuppressAndExamplesAll
--- PASS: TestAllPredicatesActionsSelfSuppressAndExamplesAll (0.00s)
PASS
ok  	github.com/nick-fedchik/kuzmin-machine/Engineering/sw/vmk-go/internal/vmk	0.017s
```

#### Крок 2. Збірка виконуваного бінарника `vmk` та перевірка версії

> **Примітка щодо робочого дерева:** щоб не залишати невідстежуваний бінарник у робочому дереві Git після роботи, видаляйте зібраний `./vmk` після перевірки або використовуйте `go run ./cmd/vmk`.

```bash
cd Engineering/sw/vmk-go
go build -o vmk ./cmd/vmk
./vmk --version
```

Вивід:

```text
VMK (Virtual Machine of Kuzmin) v0.1.0
```

#### Крок 3. Миттєвий демонстраційний прогін обох режимів

```bash
# Навчально-концептуальний режим: реактивний НСД Евкліда Nod(120, 6) = 6
go run ./cmd/vmk --example nod

# Апаратно-точний 64-слотовий BRAM-режим: 4-рівневий каскад безпеки BMS
go run ./cmd/vmk --example bms
```

---

### 2.2. Два режими роботи VMK (`conceptual` проти `bram64`)

VMK підтримує два взаємодоповнювальні режими виконання, які обираються прапорцем `--mode conceptual` або `--mode bram64` (якщо `--mode` не вказано явно, VMK автоматично обирає `conceptual` для прикладів `if`, `sum`, `nod`, `factorial`, `tachometer` та `bram64` для `bms`, `increase`, `decrease`, `cascade`, `auth` і зовнішніх файлів `--program`).

| Характеристика | `--mode conceptual` ([`internal/vmk/conceptual.go`](../sw/vmk-go/internal/vmk/conceptual.go)) | `--mode bram64` ([`internal/vmk/bram64.go`](../sw/vmk-go/internal/vmk/bram64.go)) |
| :--- | :--- | :--- |
| **Призначення** | Навчально-концептуальна модель та візуалізація авторської семантики МК (`RFC-001..018`) на канонічних прикладах зі статей і презентацій М. Ю. Кузьміна. | Побітово точна емуляція та покрокове трасування 64-слотового апаратного конвеєра дескрипторів `CME-RAW-1` (`CFG-P` / `CFG-P-HA`), сумісна такт-у-такт з RTL `kpol_bram_pipeline_axi.sv` та C99 (`--emit-c99`). |
| **Формат пам'яті концептів** | До 64 типізованих слотів `ConceptualSlot` + 3 вбудовані потокові концепти `STDIN`, `STDOUT`, `STDERR` (`Pre-load: 3 / 64`). | 64 апаратні слоти по 16 байтів (`W0..W3`, little-endian, сумарно `1024 B` BRAM) у двох банках `Bank 0` та `Bank 1`. |
| **Типи даних** | `?` (`Bool`: `!` True, `¬` False, `_` Undefined), `Int32`, `U64`, `Float` (`float64`), `Class`, `Stream`. | Знаковий `Int32` у доповняльному коді (`W0` — поточний стан, `W1` — 32-бітний операнд або пара `int16` меж `[lo, hi]`). |
| **Стан невизначеності `_`** | Повноцінне значення кожного концепту (`Valid = false`, відображається як `_`); підтримує перехід із `_` (наприклад, у `? If _`: `_ -> !`) та відсікання невалідних вхідних даних (`REJECT_FAULT`). | 64-бітна маска визначеності `ValidMask` у VMK + вхідна ознака `param_valid`; при `!param_valid` або невалідному слоті концепту генерує `REJECT_FAULT` і зберігає `W0` незмінним (`KPOL-SYS-02`). |
| **Види адресації** | Усі 4 авторські види адресації: `←` (запис / подія), `→` (читання), `|` (виконання / виклик алгоритму), `:` (ініціалізація / екземпляр). | Подієвий запис `Event(cid, param, valid)` у вхідну чергу `FIFO 16` або безпосередньо в слот `CID 0..63`. |
| **Роль Великої Крапки `•`** | Як інваріантний бар'єр **і** як пост-адресний бар'єр порядку виконання за [`RFC-013`](../../Research/sources/author/rfc-2026-11-12.md): у `→ • Sum = 0` спочатку повертається поточне значення у `STDOUT` (`35`), і строго після цього виконується підписка `Sum = 0`. | Апаратний пост-умовний вентиль інваріанта `EvalInvariantGate`: перевіряє `GuardInvariantEn`, відсутність 32-бітного переповнення (`!ovf32`), невід'ємність кандидата (`cand >= 0`) та поріг `HazardLimit`. |
| **Топологія каскадів і цикли** | Підтримує реактивні цикли з природним згасанням хвилі (`Nod(120, 6) = 6`), рекурсію з масивом вибору `[ 0 1 ] { ... Exit }` (`Factorial(5) = 120`) та одноразовий прапорець `Busy` проти самозациклення (`RFC-001` в `If`). | Суворо ациклічний орієнтований граф підписок (`DAG`, теорема Ляпунова `P1_dag_lyapunov_acyclicity`, максимум 64 кроки на подію) + апаратне придушення самопідписки (`subscriber_cid == cid` $\to$ `SUPPRESSED_SELF`). |
| **Підключення до фізичної ПЛІС** | Локальна симуляція (`Target: SIM (RFC-001..018)`). | Локальна симуляція (`--target sim`) або жива ПЛІС `Digilent PYNQ-Z1` (`--target pynq1 | pynq2`). |

> **Прозора сумісність дескрипторних прикладів із `--mode conceptual`:** якщо запустити дескрипторний приклад (`bms`, `cascade`, `increase`, `decrease`, `auth`) із прапорцем `--mode conceptual` (зокрема у потоковому режимі `--stdio`), VMK автоматично виконає його на дескрипторному ядрі та позначить режим у шапці TUI як `Mode: conceptual (descriptor-backed)`.

---

### 2.3. Життєвий цикл підключення до машини (`PRE-LOAD -> POST-LOAD -> RUNNING`) та інспекція кількості концептів

Коли інженер підключається до машини Кузьміна (фізичної плати `PYNQ-Z1` або симулятора `sim`), критично знати: **чи була машина порожньою до нашого підключення, чи в її BRAM уже працювала попередня програма, і які саме слоти змінилися після запису нового образу**. Для цього модуль [`internal/vmk/snapshot.go`](../sw/vmk-go/internal/vmk/snapshot.go) реалізує трифазний протокол `PRE-LOAD -> POST-LOAD -> RUNNING`:

```mermaid
sequenceDiagram
    participant User as Інженер (CLI / TUI)
    participant VMK as Go VMK (snapshot.go)
    participant Target as Ціль (SIM або PYNQ-Z1 0x40000000)

    User->>VMK: vmk --mode bram64 --program bms.kpol --target pynq2
    VMK->>Target: 1. Read REG_ID, HW Counters & 256 BRAM words (1024 B)
    Target-->>VMK: Знімок PRE-LOAD (M / 64 active concepts, SHA-256)
    VMK->>Target: 2. Write 256 words of new program + Full Readback (256/256 words)
    Target-->>VMK: Знімок POST-LOAD (K / 64 active concepts, Readback OK)
    VMK->>VMK: ComputePrePostLoadDiff (порівняння W0, W1, W2, W3 кожного з 64 слотів)
    VMK->>Target: 3. Подача стимулів (RUNNING) та зчитування POST-RUN
    Target-->>User: Звіт PRE-LOAD vs POST-LOAD + 4-панельний TUI + траса хвилі
```

Розглянемо реальний вивід інспекції підключення на прикладі 4-рівневого каскаду захисту батареї BMS (`go run ./cmd/vmk --example bms` або підключення до фізичної плати `pynq2` з [`raw/pynq2_live_vmk_session.log`](../validation/kpol-cme/vmk-go-274/raw/pynq2_live_vmk_session.log)):

```text
=== MACHINE CONNECTION & PROGRAMMING SNAPSHOT (PYNQ2 | HW_ID=0x4B504D43 'KPMC') ===
  Capacity          : 64 concept slots (1024 B CME-RAW-1 BRAM)
  PRE-LOAD State    : 1 / 64 active concepts (free=63, SHA-256=ef5e343eb743d5e4...) | HW Counters: events=112, commits=78, rejects=34, dropped=0
  POST-LOAD State   : 4 / 64 active concepts (entry=[0], internal=[1 2], leaf=[3], free=60, SHA-256=de03442454424b5c...)
  Readback & Diff   : 256/256 words OK (verified=true); 4 slot(s) modified during programming
+-----+----------------------+---------+-------------+--------------+-------------------------------------------------------------------------------------------------------------------------+------------------------------------------+
| CID | Name                 | Changed | Pre-Load W0 | Post-Load W0 | Pre-Load Rule -> Post-Load Rule                                                                                         | Pre-Sub -> Post-Sub (W3)                 |
+-----+----------------------+---------+-------------+--------------+-------------------------------------------------------------------------------------------------------------------------+------------------------------------------+
| C00 | Cell_Delta_mV        | YES     | 11          | 0            | ::(param < 20) | W0' := W0 + 1 | •(cand>=0 && !ovf) => ::(50 <= param <= 5000) | W0' := W0 + 1 | •(cand>=0 && !ovf) | None (0) => -> C1 (Module_Thermal_Guard) |
| C01 | Module_Thermal_Guard | YES     | _ (empty)   | 0            | EMPTY => ::(!(param < 1) [>= 1]) | W0' := W0 + 1 | •(cand>=0 && !ovf)                                                 | None => -> C2 (Pack_Fault_Latch)         |
| C02 | Pack_Fault_Latch     | YES     | _ (empty)   | 2            | EMPTY => ::(!(param < 1) [>= 1]) | W0' := W0 - 1 | •(cand>=0 && !ovf)                                                 | None => -> C3 (Contactor_Interlock)      |
| C03 | Contactor_Interlock  | YES     | _ (empty)   | 10           | EMPTY => ::(!(param == 2) [!= 2]) | W0' := param | •(cand>=0 && !ovf)                                                 | None => None (0)                         |
+-----+----------------------+---------+-------------+--------------+-------------------------------------------------------------------------------------------------------------------------+------------------------------------------+
```

#### 1. Як читати знімок ДО програмування (`PRE-LOAD State`)
* `Capacity: 64 concept slots (1024 B CME-RAW-1 BRAM)` — загальна апаратна місткість банку дескрипторів конвеєра `CFG-P` (`64` слоти по `16 Б`).
* `PRE-LOAD State: 1 / 64 active concepts (free=63, SHA-256=ef5e343eb743d5e4...)` — до нашого запису в BRAM машини був активний лише **1 концепт із 64** (одноконцептна програма `Increase.kpol` у слоті `C00` з накопиченим станом `Pre-Load W0 = 11`, тоді як слоти `C01..C63` були порожніми `_ (empty)`).
* `HW Counters: events=112, commits=78, rejects=34, dropped=0` — значення апаратних регістрів телеметрії ПЛІС (`0x018..0x028`) на момент підключення.
* **Особливість початкового стану `PRE-LOAD` у локальному симуляторі (`--target sim`):**
  - при запуску `--example bms` симулятор навмисно передініціалізується образом 1-концептної програми `Increase.kpol` (`Pre-load: 1 / 64`, `Pre-Load W0 = 10`), щоб інженер бачив повноцінну картину перезапису існуючого слота `C00` та додавання нових слотів `C01..C03` без потреби у фізичній платі;
  - при запуску інших BRAM-прикладів (`increase`, `decrease`, `cascade`, `auth`) або зовнішнього файлу `--program <file.kpol>` симулятор стартує з чистої нульової BRAM (`Pre-load: 0 / 64`);
  - у чисто концептуальному режимі (`if`, `sum`, `nod`, `factorial`, `tachometer`) до завантаження користувацької програми в машині вже присутні **`3 / 64`** системні потокові концепти (`STDIN`, `STDOUT`, `STDERR`).

#### 2. Як читати знімок ПІСЛЯ внесення програми (`POST-LOAD State & Diff`)
* `POST-LOAD State: 4 / 64 active concepts (entry=[0], internal=[1 2], leaf=[3], free=60, SHA-256=de03442454424b5c...)` — після завантаження `BmsSafetyCascade` активними стали **4 концепти з 64**, а **60 слотів** залишилися вільними (`free=60`). Автоматичний аналізатор топології [`AnalyzeConceptTopology`](../sw/vmk-go/internal/vmk/snapshot.go) класифікував активні концепти за їхньою роллю в каскаді:
  - **`entry=[0]` (вхідні кореневі концепти):** слоти з нульовим вхідним степенем підписок (`inDeg == 0`), які приймають зовнішні події (тут `C00 Cell_Delta_mV`, а також ізольовані концепти без підписок);
  - **`internal=[1 2]` (внутрішні каскадні вузли):** слоти, які мають і вхідну підписку (`inDeg > 0`), і вихідну підписку (`outEdge`, тут `C01 Module_Thermal_Guard` та `C02 Pack_Fault_Latch`);
  - **`leaf=[3]` (вихідні листкові концепти):** термінальні слоти каскаду (`inDeg > 0`, без вихідної підписки, тут `C03 Contactor_Interlock`), на яких хвиля подій завершується.
* `Readback & Diff: 256/256 words OK (verified=true); 4 slot(s) modified during programming` — підтвердження того, що всі 256 32-бітних слів, вичитаних назад із BRAM після програмування, побітово збіглися із записаним образом, а функція `ComputePrePostLoadDiff` перевірила кожне з 4 слів (`W0`, `W1`, `W2`, `W3`) кожного слота і зафіксувала зміну 4 слотів (`Changed = YES`), включно зі зміною правила `Pre-Load Rule -> Post-Load Rule` та адреси підписника `Pre-Sub -> Post-Sub (W3)`.

#### 3. Як читати дескрипторну таблицю концептів (`--dump-concepts`)

Щоб вивести лише розшифровану таблицю 16-байтних дескрипторів `CME-RAW-1` без запуску хвилі подій, виконайте:

```bash
cd Engineering/sw/vmk-go
go run ./cmd/vmk --mode bram64 \
  --program ../../validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol \
  --profile KPOL-CME-2 --dump-concepts
```

Вивід Блоку 2 (`BRAM DESCRIPTOR TABLE`):

```text
=== [BLOCK 2] BRAM DESCRIPTOR TABLE (--dump-concepts, 4 active of 64 slots) ===
+-----+----------------------+-----------------+-----------+------------------------+-----------------------------------------------------------------------------+----------------------------------+
| CID | Name                 | W0 (Init State) | Valid (_) | W1 (Operand)           | W2 (Hex & Decoded: Predicate ::, Action, Invariant •)                     | W3 (Subscriber -> CID)           |
+-----+----------------------+-----------------+-----------+------------------------+-----------------------------------------------------------------------------+----------------------------------+
| C00 | Cell_Delta_mV        | 0 (0x00000000)  | 1 (valid) | 327680050 (0x13880032) | 0x01001305 [::(50 <= param <= 5000) | W0' := W0 + 1 | •(cand>=0 && !ovf)] | 1 (-> C1 (Module_Thermal_Guard)) |
| C01 | Module_Thermal_Guard | 0 (0x00000000)  | 1 (valid) | 1 (0x00000001)         | 0x01001B04 [::(!(param < 1) [>= 1]) | W0' := W0 + 1 | •(cand>=0 && !ovf)] | 2 (-> C2 (Pack_Fault_Latch))     |
| C02 | Pack_Fault_Latch     | 2 (0x00000002)  | 1 (valid) | 1 (0x00000001)         | 0x02001B04 [::(!(param < 1) [>= 1]) | W0' := W0 - 1 | •(cand>=0 && !ovf)] | 3 (-> C3 (Contactor_Interlock))  |
| C03 | Contactor_Interlock  | 10 (0x0000000A) | 1 (valid) | 2 (0x00000002)         | 0x00000B01 [::(!(param == 2) [!= 2]) | W0' := param | •(cand>=0 && !ovf)] | 0 (None (0))                     |
+-----+----------------------+-----------------+-----------+------------------------+-----------------------------------------------------------------------------+----------------------------------+
```

Значення колонок дескриптора `CME-RAW-1` (`16 Б = 4 × 32 біти`):
* **`W0 (Init State)`** (`байти 0..3`): початковий 32-бітний знаковий стан концепту в доповняльному коді (наприклад, для `C02 Pack_Fault_Latch` `W0 = 2`, для `C03 Contactor_Interlock` `W0 = 10`).
* **`Valid (_)`**: поточний стан біта визначеності концепту (`1 (valid)` — визначений стан; `_ (invalid)` — концепт перебуває у стані невизначеності `_` за `RFC-005` / `KPOL-SYS-02`).
* **`W1 (Operand)`** (`байти 4..7`): константний операнд правила. Для звичайних предикатів це знакове `int32`, а для діапазонного предиката `PredRANGE (0x05)` у слоті `C00` слово `0x13880032` містить дві упаковані знакові `int16`-межі: молодші 16 біт `0x0032 = 50` (`lo`), старші 16 біт `0x1388 = 5000` (`hi`).
* **`W2 (Hex & Decoded: Predicate ::, Action, Invariant •)`** (`байти 8..11`): упаковане керуюче слово `[action_op:8 | hazard_limit:8 | guard_flags:8 | pred_op:8]` та його людиночитана формула:
  - `pred_op` (`біти 7:0`): `0x00` `NOP` (`true`), `0x01` `EQ` (`==`), `0x02` `NEQ` (`!=`), `0x03` `GT` (`>`), `0x04` `LT` (`<`), `0x05` `RANGE` (`lo <= param <= hi`), `0x06` `BITMASK` (`(param & W1) != 0`), `0x07` `UGT` (`u32(param) > u32(W1)`);
  - `guard_flags` (`біти 15:8`): бітова маска `0x01` (`GuardAssumptionEn` — увімкнено `::`), `0x02` (`GuardInvariantEn` — увімкнено вентиль Великої Крапки `•`), `0x04` (`GuardHazardEn` — перевірка `HazardLimit`), `0x08` (`GuardInvertAssumption` — логічна інверсія `::`, наприклад `!(param < 1)` для `>= 1`), `0x10` (`GuardSubscriberEn` — дозвіл каскадного переходу на підписника, зокрема на `CID 0`);
  - `action_op` (`біти 31:24`): `0x00` `ASSIGN` (`W0' := param`), `0x01` `INC` (`W0 + 1`), `0x02` `DEC` (`W0 - 1`), `0x03` `ADD` (`W0 + W1`), `0x04` `SUB` (`W0 - W1`), `0x05` `NOP` (`W0' := W0`).
* **`W3 (Subscriber -> CID)`** (`байти 12..15`): індекс концепту-підписника (`0..63`), якому передається нове значення `W0'` як вхідний параметр `param` каскадної події у разі успішного `COMMIT`.

---

### 2.4. Покрокове налагодження в 4-панельному TUI-дебагері (`--tui` та `--render-tui-frame`)

TUI-дебагер VMK ([`internal/vmk/tui.go`](../sw/vmk-go/internal/vmk/tui.go)) має два режими відображення:
1. **Детермінований 4-панельний ASCII-кадр (`--render-tui-frame`):** виводить повний знімок усіх 4 панелей у `stdout` без керівних послідовностей очищення екрана (ідеально підходить для CI-логів, звітів, `grep`/`diff` та перенаправлення у файл);
2. **Інтерактивний покроковий термінальний режим (`--tui` або підкоманда `vmk tui`):** коли `stdin` і `stdout` є інтерактивним терміналом (`TTY`), запускає цикл живого покрокового керування хвилею подій.

#### Команда запуску 4-панельного TUI-кадру

```bash
cd Engineering/sw/vmk-go
printf "Cell_Delta_mV 15\nCell_Delta_mV _\nCell_Delta_mV 120\nCell_Delta_mV 180\nCell_Delta_mV 250\n" | \
  go run ./cmd/vmk --mode bram64 \
    --program ../../validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol \
    --stdio --watch-cid 2,3 --break-on-reject --render-tui-frame
```

#### Анатомія 4 панелей екрана TUI (реальний вивід)

```text
======================================================================================================================
 VMK (Virtual Machine of Kuzmin) v0.1.0 | Target: SIM (0x4B504D43 'KPMC') | Mode: bram64 | State: PRE-LOAD -> POST-LOAD -> RUNNING
 Concepts: Active: 4 / 64 (Pre-load: 0 / 64, Changed on load: 4, Free: 60) | Entry: [0] Internal: [1 2] Leaf: [3]
 Counters: Events=13 | Commits=10 | Rejects=3 | Faults(_)=1 | Dropped=0 | Bank=0 | LastState=3
======================================================================================================================
 [PANEL 1: CONCEPT TABLE (PRE-LOAD vs POST-LOAD vs CURRENT STATE)]
+-----+----------------------+-------+-------------+--------------+-----------------+----------+----------------------+---------------+---------------------+------------------------------+
| CID | Name                 | Type  | Pre-Load W0 | Post-Load W0 | Current W0 (Δ) | Valid(_) | Predicate ::         | Action        | Gate •            | Subscriber                   |
+-----+----------------------+-------+-------------+--------------+-----------------+----------+----------------------+---------------+---------------------+------------------------------+
| C00 | Cell_Delta_mV        | Int32 | _ (empty)   | 0            | 3 (+3)          | 1        | 50 <= param <= 5000  | W0' := W0 + 1 | cand >= 0 && !ovf32 | -> C1 (Module_Thermal_Guard) |
| C01 | Module_Thermal_Guard | Int32 | _ (empty)   | 0            | 3 (+3)          | 1        | !(param < 1) [>= 1]  | W0' := W0 + 1 | cand >= 0 && !ovf32 | -> C2 (Pack_Fault_Latch)     |
| C02 | Pack_Fault_Latch     | Int32 | _ (empty)   | 2            | 0 (-2)          | 1        | !(param < 1) [>= 1]  | W0' := W0 - 1 | cand >= 0 && !ovf32 | -> C3 (Contactor_Interlock)  |
| C03 | Contactor_Interlock  | Int32 | _ (empty)   | 10           | 0 (-10)         | 1        | !(param == 2) [!= 2] | W0' := param  | cand >= 0 && !ovf32 | None (0)                     |
+-----+----------------------+-------+-------------+--------------+-----------------+----------+----------------------+---------------+---------------------+------------------------------+
----------------------------------------------------------------------------------------------------------------------
 [PANEL 2: PROGRAM SOURCE CODE & LIVE STDIO STREAMS (STDIN / STDOUT / STDERR)]
   SRC 01 | Problem BmsSafetyCascade {
   SRC 02 |     Invariants {
   SRC 03 |         inv_cell_delta: Cell_Delta_mV >= 0;
   SRC 04 |         inv_mod_thermal: Module_Thermal_Guard >= 0;
   SRC 05 |         inv_pack_latch: Pack_Fault_Latch >= 0;
   SRC 06 |         inv_contactor: Contactor_Interlock >= 0;
   SRC 07 |     }
   SRC 08 | }
   SRC 09 |
   SRC 10 | Solution BmsSafetyCascade {
   SRC 11 |     state Cell_Delta_mV: Int32 = 0;
   SRC 12 |     state Module_Thermal_Guard: Int32 = 0;
   STDIN  (5 events) : (C0:15,valid=1), (C0:0,valid=_), (C0:120,valid=1), (C0:180,valid=1), (C0:250,valid=1)
   STDOUT -> COMMIT: Cell_Delta_mV[cid=0] = 1 (pre=0, depth=0, param=120, valid=1)
   STDOUT -> COMMIT: Module_Thermal_Guard[cid=1] = 1 (pre=0, depth=1, param=1, valid=1)
   STDOUT -> COMMIT: Pack_Fault_Latch[cid=2] = 1 (pre=2, depth=2, param=1, valid=1)
   STDOUT -> COMMIT: Contactor_Interlock[cid=3] = 1 (pre=10, depth=3, param=1, valid=1)
   STDOUT -> COMMIT: Cell_Delta_mV[cid=0] = 2 (pre=1, depth=0, param=180, valid=1)
   STDOUT -> COMMIT: Module_Thermal_Guard[cid=1] = 2 (pre=1, depth=1, param=2, valid=1)
   STDOUT -> COMMIT: Pack_Fault_Latch[cid=2] = 0 (pre=1, depth=2, param=2, valid=1)
   STDOUT -> COMMIT: Contactor_Interlock[cid=3] = 0 (pre=1, depth=3, param=0, valid=1)
   STDOUT -> COMMIT: Cell_Delta_mV[cid=0] = 3 (pre=2, depth=0, param=250, valid=1)
   STDOUT -> COMMIT: Module_Thermal_Guard[cid=1] = 3 (pre=2, depth=1, param=3, valid=1)
   STDERR -> REJECT_GUARD: Cell_Delta_mV[cid=0] kept W0=0 (depth=0, param=15, valid=1, pred=(50 <= param <= 5000)=>false, cand=1, gate=(cand >= 0 && !ovf32)=>true)
   STDERR -> REJECT_FAULT: Cell_Delta_mV[cid=0] kept W0=0 (depth=0, param=0, valid=_, pred=(50 <= param <= 5000)=>false, cand=1, gate=(cand >= 0 && !ovf32)=>false)
   STDERR -> REJECT_INVARIANT: Pack_Fault_Latch[cid=2] kept W0=0 (depth=2, param=3, valid=1, pred=(!(param < 1) [>= 1])=>true, cand=-1, gate=(cand >= 0 && !ovf32)=>false)
----------------------------------------------------------------------------------------------------------------------
 [PANEL 3: CASCADE WAVE STEP TRACE]
=== [BLOCK 3] STEP-BY-STEP EVENT & CASCADE TRACE (--trace-events, 13 steps) ===
+------------+-------+----------------------------+---------------------+----------------+------------------------------+---------------------+------------------------------+------------------------------------------------------------------------------------+---------------+----------------------------+
| Step       | Depth | CID (Name)                 | Event(param, valid) | Pre-State      | Predicate ::                 | Candidate           | Gate •                     | Verdict                                                                            | Post-State    | Next Subscriber            |
+------------+-------+----------------------------+---------------------+----------------+------------------------------+---------------------+------------------------------+------------------------------------------------------------------------------------+---------------+----------------------------+
| E0.0 (#0)  | 0     | C00 (Cell_Delta_mV)        | param=15, valid=1   | W0=0, valid=1  | 50 <= param <= 5000 => false | W0' := W0 + 1 => 1  | cand >= 0 && !ovf32 => true  | REJECT_GUARD *BREAK_ON_REJECT(REJECT_GUARD)                                        | W0=0, valid=1 | None                       |
| E1.0 (#1)  | 0     | C00 (Cell_Delta_mV)        | param=0, valid=_    | W0=0, valid=1  | 50 <= param <= 5000 => false | W0' := W0 + 1 => 1  | cand >= 0 && !ovf32 => false | REJECT_FAULT *BREAK_ON_REJECT(REJECT_FAULT)                                        | W0=0, valid=1 | None                       |
| E2.0 (#2)  | 0     | C00 (Cell_Delta_mV)        | param=120, valid=1  | W0=0, valid=1  | 50 <= param <= 5000 => true  | W0' := W0 + 1 => 1  | cand >= 0 && !ovf32 => true  | COMMIT *STATE_CHANGE(0->1)                                                         | W0=1, valid=1 | C01 (Module_Thermal_Guard) |
| E2.1 (#3)  | 1     | C01 (Module_Thermal_Guard) | param=1, valid=1    | W0=0, valid=1  | !(param < 1) [>= 1] => true  | W0' := W0 + 1 => 1  | cand >= 0 && !ovf32 => true  | COMMIT *STATE_CHANGE(0->1)                                                         | W0=1, valid=1 | C02 (Pack_Fault_Latch)     |
| E2.2 (#4)  | 2     | C02 (Pack_Fault_Latch)     | param=1, valid=1    | W0=2, valid=1  | !(param < 1) [>= 1] => true  | W0' := W0 - 1 => 1  | cand >= 0 && !ovf32 => true  | COMMIT *WATCH_CID(C2:Pack_Fault_Latch),STATE_CHANGE(2->1)                          | W0=1, valid=1 | C03 (Contactor_Interlock)  |
| E2.3 (#5)  | 3     | C03 (Contactor_Interlock)  | param=1, valid=1    | W0=10, valid=1 | !(param == 2) [!= 2] => true | W0' := param => 1   | cand >= 0 && !ovf32 => true  | COMMIT *WATCH_CID(C3:Contactor_Interlock),STATE_CHANGE(10->1)                      | W0=1, valid=1 | None                       |
| E3.0 (#6)  | 0     | C00 (Cell_Delta_mV)        | param=180, valid=1  | W0=1, valid=1  | 50 <= param <= 5000 => true  | W0' := W0 + 1 => 2  | cand >= 0 && !ovf32 => true  | COMMIT *STATE_CHANGE(1->2)                                                         | W0=2, valid=1 | C01 (Module_Thermal_Guard) |
| E3.1 (#7)  | 1     | C01 (Module_Thermal_Guard) | param=2, valid=1    | W0=1, valid=1  | !(param < 1) [>= 1] => true  | W0' := W0 + 1 => 2  | cand >= 0 && !ovf32 => true  | COMMIT *STATE_CHANGE(1->2)                                                         | W0=2, valid=1 | C02 (Pack_Fault_Latch)     |
| E3.2 (#8)  | 2     | C02 (Pack_Fault_Latch)     | param=2, valid=1    | W0=1, valid=1  | !(param < 1) [>= 1] => true  | W0' := W0 - 1 => 0  | cand >= 0 && !ovf32 => true  | COMMIT *WATCH_CID(C2:Pack_Fault_Latch),STATE_CHANGE(1->0)                          | W0=0, valid=1 | C03 (Contactor_Interlock)  |
| E3.3 (#9)  | 3     | C03 (Contactor_Interlock)  | param=0, valid=1    | W0=1, valid=1  | !(param == 2) [!= 2] => true | W0' := param => 0   | cand >= 0 && !ovf32 => true  | COMMIT *WATCH_CID(C3:Contactor_Interlock),STATE_CHANGE(1->0)                       | W0=0, valid=1 | None                       |
| E4.0 (#10) | 0     | C00 (Cell_Delta_mV)        | param=250, valid=1  | W0=2, valid=1  | 50 <= param <= 5000 => true  | W0' := W0 + 1 => 3  | cand >= 0 && !ovf32 => true  | COMMIT *STATE_CHANGE(2->3)                                                         | W0=3, valid=1 | C01 (Module_Thermal_Guard) |
| E4.1 (#11) | 1     | C01 (Module_Thermal_Guard) | param=3, valid=1    | W0=2, valid=1  | !(param < 1) [>= 1] => true  | W0' := W0 + 1 => 3  | cand >= 0 && !ovf32 => true  | COMMIT *STATE_CHANGE(2->3)                                                         | W0=3, valid=1 | C02 (Pack_Fault_Latch)     |
| E4.2 (#12) | 2     | C02 (Pack_Fault_Latch)     | param=3, valid=1    | W0=0, valid=1  | !(param < 1) [>= 1] => true  | W0' := W0 - 1 => -1 | cand >= 0 && !ovf32 => false | REJECT_INVARIANT *WATCH_CID(C2:Pack_Fault_Latch),BREAK_ON_REJECT(REJECT_INVARIANT) | W0=0, valid=1 | None                       |
+------------+-------+----------------------------+---------------------+----------------+------------------------------+---------------------+------------------------------+------------------------------------------------------------------------------------+---------------+----------------------------+
======================================================================================================================
 KEYS: [s] Step Next Event | [i] Input STDIN | [f] Inject Fault (_) | [r] Reload BRAM | [q] Quit
======================================================================================================================
```

1. **Верхній статус-бар машини та лічильників:**
   - Показує ціль (`Target: SIM` або `PYNQ2 (0x4B504D43 'KPMC')`), режим (`bram64` / `conceptual`), поточну фазу (`PRE-LOAD -> POST-LOAD -> RUNNING | INTERACTIVE | COMPLETED`);
   - Виводить баланс слотів концептів: `Active: 4 / 64 (Pre-load: 0 / 64, Changed on load: 4, Free: 60) | Entry: [0] Internal: [1 2] Leaf: [3]`;
   - Виводить лічильники виконання: `Events=13 | Commits=10 | Rejects=3 | Faults(_)=1 | Dropped=0 | Bank=0 | LastState=3`.
2. **Панель 1 (`[PANEL 1: CONCEPT TABLE]`):**
   - Одночасно показує для кожного активного концепту **три стани**: `Pre-Load W0` (що було в слоті до програмування), `Post-Load W0` (початковий стан після завантаження програми) та `Current W0 (Δ)` (поточний стан разом із приростом відносно `Post-Load`, наприклад `3 (+3)` або `0 (-10)`), а також біт `Valid(_)`, умову `Predicate ::`, дію `Action`, інваріант `Gate •` і підписника `Subscriber`.
3. **Панель 2 (`[PANEL 2: PROGRAM SOURCE CODE & LIVE STDIO STREAMS]`):**
   - Відображає пронумеровані рядки вихідної програми `.kpol` і живу стрічку трьох потоків: `STDIN` (подані зовнішні події), `STDOUT` (підтверджені `COMMIT` / `READ`) та `STDERR` (відхилені кроки `REJECT_GUARD`, `REJECT_INVARIANT`, `REJECT_FAULT`).
4. **Панель 3 (`[PANEL 3: CASCADE WAVE STEP TRACE]`):**
   - Містить 10-колонкову таблицю покрокового проходження хвилі подій:
     * `Step` — ідентифікатор `E<НомерЗовнішньоїПодії>.<КрокУсерединіХвилі> (#<ГлобальнийІндекс>)`;
     * `Depth` — глибина каскаду (`0` для зовнішньої події, `1, 2, 3...` для внутрішніх переходів `on change(...)`);
     * `CID (Name)` — слот і назва концепту;
     * `Event(param, valid)` — параметр події та його визначеність (`1` або `_`);
     * `Pre-State` — стан `W0` та `valid` до оцінки кроку;
     * `Predicate ::` — формула вхідного охоронця та булевий результат (`=> true` або `=> false`);
     * `Candidate` — формула дії та обчислене значення-кандидат `W0'` (із позначкою `[OVF!]` у разі знакового 32-бітного переповнення);
     * `Gate •` — формула вентиля інваріанта Великої Крапки та результат перевірки (`=> true` або `=> false`);
     * `Verdict` — підсумковий вердикт (`COMMIT`, `SUPPRESSED_SELF`, `REJECT_GUARD`, `REJECT_INVARIANT`, `REJECT_FAULT`) і маркери спрацьованих точок спостереження (`*WATCH_CID(...)`, `*BREAK_ON_REJECT(...)`, `*STATE_CHANGE(...)`);
     * `Post-State` та `Next Subscriber` — підсумковий стан концепту і наступний концепт, поставлений у чергу каскаду (`None`, якщо хвиля загасла або була відхилена).

#### Гарячі клавіші інтерактивного режиму (`--tui`)

Під час запуску в інтерактивному терміналі (`./vmk --mode bram64 --example bms --trace-events "0:15,0:120,0:180" --tui`) у нижньому рядку працює командний запит `vmk-tui [s/i/f/r/q]>`:

| Клавіша / команда | Дія в інтерактивному TUI-дебагері |
| :--- | :--- |
| **`s`** або **`Enter`** | Виконати наступну подію з черги `--trace-events` і перемалювати всі 4 панелі каскаду. |
| **`i <подія>`** | Ввести нову подію в `STDIN` вручну (наприклад, `i 120`, `i Cell_Delta_mV 180`, `i 0:250` або `i _`). |
| **`f`** | Інжектувати апаратну помилку датчика / стан невизначеності `_` (`param_valid = false`) у кореневий концепт і перевірити спрацювання `REJECT_FAULT`. |
| **`r`** | Перезавантажити (`Reset`) стани `W0`, маску `ValidMask` і обидва банки `Bank 0 / Bank 1` до чистого стану `POST-LOAD` та відновити початкову чергу подій. |
| **`q`** | Завершити інтерактивну сесію та вивести фінальний знімок `COMPLETED`. |

#### Точки спостереження та зупинки (`Watchpoints & Breakpoints`)

* `--watch-cid 0,2,3` — відстежує всі звернення до перелічених слотів `CID` і позначає їх у колонці `Verdict` маркером `*WATCH_CID(C2:Pack_Fault_Latch)` та в підсумковому списку `Watchpoints / Breakpoints Triggered`.
* `--break-on-reject` — генерує спрацювання точки зупинки `*BREAK_ON_REJECT(<Verdict>)` щоразу, коли будь-який концепт відхиляє подію (`REJECT_GUARD`, `REJECT_INVARIANT` або `REJECT_FAULT`).
* `--stop-on-breakpoint` — негайно зупиняє подальше просування хвилі каскаду на першому ж кроці, де спрацював `Watchpoint` або `Breakpoint` (`HaltedOnBreakpoint = true`).

---

### 2.5. Потокове введення-виведення `STDIO` (`stdin` / `stdout` / `stderr`), прагми `# @stdin` / `# @stdout` та автотестування

Прапорець `--stdio` ([`internal/vmk/stdio.go`](../sw/vmk-go/internal/vmk/stdio.go)) перетворює `vmk` на стандартний UNIX-фільтр, який приймає вхідні події або команди з потоку `stdin` і строго розділяє вихідні потоки:
* **`stdout`** отримує виключно підтверджені переходи станів (`COMMIT: ...`) та операції читання (`READ: ...`);
* **`stderr`** отримує виключно діагностику відмов (`REJECT_GUARD: ...`, `REJECT_INVARIANT: ...`, `REJECT_FAULT: ...`) та помилки CLI/I/O.

#### 1. Формати вхідних рядків `stdin` у режимі `--mode bram64 --stdio`

У режимі `bram64` парсер `ParseStdioInputLine` підтримує 5 зручних форматів (порожні рядки та коментарі `# ...` або `// ...` ігноруються):

| Формат рядка `stdin` | Приклад | Як інтерпретується у `bram64` |
| :--- | :--- | :--- |
| Число (`<param>`) | `120` | Подія у вхідний концепт за замовчуванням (`# @stdin` або перший активний слот) із `param = 120, valid = 1`. |
| Невизначеність (`_`) | `_` або `invalid` / `fault` | Подія у вхідний концепт за замовчуванням із невалідним станом (`param = 0, valid = _`) $\to$ викликає `REJECT_FAULT`. |
| `<Concept> <param>` | `Cell_Delta_mV 180` або `write C0 180` | Подія у вказаний концепт (за назвою, `C0`, `C00`, `cid0` або номером `0`) із параметром `180`. |
| `<CID>:<param>[:<valid>]` | `0:120` або `C0:0:_` | Компактна нотація траси (сумісна з `--trace-events`). |
| Рядок `JSONL` | `{"concept":"Cell_Delta_mV","param":120,"valid":true}` | Машиночитаний JSON-об'єкт для інтеграції з зовнішніми сервісами та тестовими генераторами. |

Приклад запуску через UNIX-пайп із розділенням `stdout` і `stderr`:

```bash
cd Engineering/sw/vmk-go
printf "15\n_\n120\n180\n250\n" | \
  go run ./cmd/vmk --mode bram64 --example bms --stdio --fail-on-reject \
  >stdout_commits.log 2>stderr_rejects.log ; echo "Exit code: $?"
```

Вміст `stdout_commits.log` (лише успішні переходи `COMMIT`):

```text
COMMIT: Cell_Delta_mV[cid=0] = 1 (pre=0, depth=0, param=120, valid=1)
COMMIT: Module_Thermal_Guard[cid=1] = 1 (pre=0, depth=1, param=1, valid=1)
COMMIT: Pack_Fault_Latch[cid=2] = 1 (pre=2, depth=2, param=1, valid=1)
COMMIT: Contactor_Interlock[cid=3] = 1 (pre=10, depth=3, param=1, valid=1)
COMMIT: Cell_Delta_mV[cid=0] = 2 (pre=1, depth=0, param=180, valid=1)
COMMIT: Module_Thermal_Guard[cid=1] = 2 (pre=1, depth=1, param=2, valid=1)
COMMIT: Pack_Fault_Latch[cid=2] = 0 (pre=1, depth=2, param=2, valid=1)
COMMIT: Contactor_Interlock[cid=3] = 0 (pre=1, depth=3, param=0, valid=1)
COMMIT: Cell_Delta_mV[cid=0] = 3 (pre=2, depth=0, param=250, valid=1)
COMMIT: Module_Thermal_Guard[cid=1] = 3 (pre=2, depth=1, param=3, valid=1)
```

Вміст `stderr_rejects.log` (лише заблоковані події `REJECT_*`, код виходу `1` завдяки `--fail-on-reject`):

```text
REJECT_GUARD: Cell_Delta_mV[cid=0] kept W0=0 (depth=0, param=15, valid=1, pred=(50 <= param <= 5000)=>false, cand=1, gate=(cand >= 0 && !ovf32)=>true)
REJECT_FAULT: Cell_Delta_mV[cid=0] kept W0=0 (depth=0, param=0, valid=_, pred=(50 <= param <= 5000)=>false, cand=1, gate=(cand >= 0 && !ovf32)=>false)
REJECT_INVARIANT: Pack_Fault_Latch[cid=2] kept W0=0 (depth=2, param=3, valid=1, pred=(!(param < 1) [>= 1])=>true, cand=-1, gate=(cand >= 0 && !ovf32)=>false)
```

#### 2. Прагми `# @stdin` та `# @stdout` у файлах `.kpol`

У верхніх коментарях файлу `.kpol` можна явно задати вхідний концепт за замовчуванням та відфільтрувати, які саме концепти каскаду мають друкуватися у `stdout` (наприклад, лише термінальний листок каскаду `Contactor_Interlock`):

```text
# @stdin Cell_Delta_mV
# @stdout Contactor_Interlock
```

* Якщо прагма `# @stdin <Concept>` задана, то рядки `stdin`, які містять лише число (`120`) або `_`, автоматично спрямовуються у слот `<Concept>`.
* Якщо прагма `# @stdout <Concept1, Concept2>` задана, у потік `stdout` виводяться повідомлення `COMMIT:` лише для вказаних вихідних концептів (проміжні внутрішні кроки каскаду виконуються, але не засмічують вихідний потік споживача). Якщо `# @stdout` не вказано, у `stdout` виводяться всі активні концепти.

#### 3. Команди `stdin` у концептуальному режимі (`--mode conceptual --stdio`)

У режимі `--mode conceptual --stdio` вхідний потік приймає символьні команди адресації концептів (`write`, `toggle`, `read`, `call`):

```bash
# Приклад 1: Акумулятор Sum із пост-адресним скиданням при читанні (RFC-013) та відсіканням '_'
cd Engineering/sw/vmk-go
printf "write Sum 10\nwrite Sum 25\nwrite Sum _\nread Sum\nread Sum\n" | \
  go run ./cmd/vmk --mode conceptual --example sum --stdio 2>stderr.log
```

Вивід потоку `stdout` (підтверджені записи `COMMIT` та читання `READ`):

```text
COMMIT: Sum[cid=0] = 10 (pre=0, ← += 10)
COMMIT: Sum[cid=0] = 35 (pre=10, ← += 25)
READ: Sum = 35 (post-dot → • reset Sum = 0)
READ: Sum = 0 (post-dot → • reset Sum = 0)
```

Вивід потоку `stderr` (вміст `stderr.log` — відсікання невалідного запису `write Sum _`; якщо не перенаправляти `2>stderr.log`, у терміналі `vmk` спочатку друкує буфер `stdout`, а слідом за ним — `stderr`):

```text
REJECT_FAULT: Sum[cid=0] kept 35 (input valid=_)
```

Зверніть увагу: перша команда `read Sum` повертає накопичену суму `35`, після чого пост-адресний бар'єр Великої Крапки `→ • Sum = 0` скидає акумулятор у `0`, тому друга команда `read Sum` повертає вже `0`.

```bash
# Приклад 2: Перемикання T-тригера If (write If 1 або toggle If)
printf "toggle If\ntoggle If\ntoggle If\n" | \
  go run ./cmd/vmk --mode conceptual --example if --stdio

# Приклад 3: Виклик реактивного НСД Евкліда Nod(120, 6) та рекурсивного Factorial(5)
printf "call Nod 120 6\n" | go run ./cmd/vmk --mode conceptual --example nod --stdio
printf "call Factorial 5\n" | go run ./cmd/vmk --mode conceptual --example factorial --stdio
```

---

### 2.6. Каталог і приклади запуску всіх 10 вбудованих програм (`--example ...`)

У бінарник `vmk` вбудовано **10 еталонних програм** ([`internal/vmk/examples.go`](../sw/vmk-go/internal/vmk/examples.go)): 5 чисто концептуальних прикладів за матеріалами Автора (`if`, `sum`, `nod`, `factorial`, `tachometer`) та 5 дескрипторних прикладів (`bms`, `increase`, `decrease`, `cascade`, `auth`), а також мета-режим `--example all`, який послідовно виконує всі 10 програм.

| Назва (`--example`) | Режим за замовчуванням | Профіль / джерело | Команда запуску | Що саме демонструє та очікуваний результат (`./vmk --example all`) |
| :--- | :---: | :--- | :--- | :--- |
| **`if`** | `conceptual` | `RFC-001` (`? If _`) | `vmk --example if` | T-тригер, що стартує зі стану невизначеності `_`. За 3 імпульси запису (`Events=3, Commits=3`) проходить траєкторію **`_ -> ! -> ¬ -> !`** (фінальний стан `If = !`). Прапорець `Busy` блокує нескінченне самозбудження (`SUPPRESSED_SELF`). |
| **`sum`** | `conceptual` | `RFC-013` (`Float Sum 0`) | `vmk --example sum` | Накопичення `0 + 10 + 25 = 35` (`Events=3, Commits=3`). Під час читання `→ • Sum = 0` спочатку повертає **`35`** у `STDOUT` (`read_returned_value = 35`), а потім пост-адресно скидає стан `Sum` у **`0`** (`post_read_state = 0`). |
| **`nod`** | `conceptual` | Алгоритм Евкліда (`Nod(120, 6)`) | `vmk --example nod` | Реактивна хвиля взаємного віднімання `a -= b` між двома концептами (`a=120, b=6`). У концептуальній віртуальній машині VMK виконує **`19` реактивних кроків віднімання** (`20` кроків оцінки хвилі `E0.0..E19.0`, де на кроці `#19` при `a == b == 6` хвиля природно згасає і фіксує **`Nod = 6`**, фінальні стани слотів `[a=6, b=6, Nod=6]`). Окреме спеціалізоване апаратне RTL-ядро `km_euclid_core.sv` ([`kpol_debugger.py`](../sw/kpol-ref/kpol_debugger.py)) у симуляції `iverilog` виконує цю саму задачу за **`58` тактів** (`19 × 3 + 1`, `result = 6`). |
| **`factorial`** | `conceptual` | Масив вибору `[ 0 1 ]` + `Exit` | `vmk --example factorial` | Рекурсивне обчислення `Factorial(5)` (`Events=9, Commits=9`): 4 кроки спуску (`5 -> 4 -> 3 -> 2 -> 1`), 1 крок спрацювання базового масиву `[ 0 1 ] { Factorial = 1 Exit }` та 4 кроки зворотного множення до **`120`** (фінальні стани слотів `[n=1, Factorial=120]`). |
| **`tachometer`** | `conceptual` | Клас `Tachometer` (`Tick`, `_Tick`) | `vmk --example tachometer` | 3 імпульси колеса `Tick` накопичують `Revolutions = 3`, `Distance = 6`; імпульс таймера `_Tick(dt=1s)` за правилом `→ •` (`Events=7, Commits=7`) обчислює **`Speed = 6`** і скидає `Revolutions = 0` (фінальні стани `[Revolutions=0, Distance=6, Speed=6]`). |
| **`bms`** | `bram64` | `KPOL-CME-2` (`4` концепти) | `vmk --example bms` | 4-рівневий каскад захисту батареї (`Cell_Delta_mV -> Module_Thermal_Guard -> Pack_Fault_Latch -> Contactor_Interlock`). На 6 демо-стимулах (`15, 5500, _, 120, 180, 250`; `Events=14, Commits=10, Rejects=4, Faults(_)=1`) демонструє всі 4 види вердиктів: `REJECT_GUARD`, `REJECT_FAULT`, `COMMIT` по всій глибині `Depth 0..3` (розмикання контактора `10 -> 1 -> 0`) та `REJECT_INVARIANT` при спробі декременту защіпки `0 -> -1` (фінальні стани **`[3, 3, 0, 0]`**; на 9 стимулах стендового HIL-тесту — **`[4, 4, 0, 0]`**). |
| **`increase`** | `bram64` | `KPOL-CME-1` (`1` концепт) | `vmk --example increase` | Базовий одноконцептний лічильник `Counter = 10` з умовою `param < 20`: на стимулах `5, 25, _` (`Events=3, Commits=1, Rejects=2, Faults(_)=1`) демонструє `COMMIT` (`10 -> 11`), `REJECT_GUARD` (`param=25`) та `REJECT_FAULT` (`param=_`), фінальний стан **`[11]`**. |
| **`decrease`** | `bram64` | `KPOL-CME-1` (`1` концепт) | `vmk --example decrease` | Лічильник `Counter = 1` із декрементом `Counter - 1` та інваріантом `Counter >= 0`: на стимулах `5, 5, 25` (`Events=3, Commits=1, Rejects=2, Faults(_)=0`) демонструє `COMMIT` (`1 -> 0`), блокування `0 -> -1` вентилем Великої Крапки `•` (`REJECT_INVARIANT`) та `REJECT_GUARD`, фінальний стан **`[0]`**. |
| **`cascade`** | `bram64` | `KPOL-CME-2` (`4` концепти) | `vmk --example cascade` | Канонічний 4-концептний каскад `C0 -> C1 -> C2 -> C3` на стимулах `10, 100, 10, 10` (`Events=12, Commits=10, Rejects=2, Faults(_)=0`, фінальні стани **`[13, 3, 0, 0]`**). |
| **`auth`** | `bram64` | `KPOL-AUTH` (`Do/Go` + BRAM) | `vmk --example auth` | Компіляція авторського запису `Concept(Counter, 10, ...) / Counter • Assign(Mirror, Counter + 1)` у 5 слів 32-бітного байткоду `Do/Go` (`0x12000000..0x50000000`) та каскад дескрипторів `Counter -> Mirror` на стимулах `-5, 25, _` (`Events=4, Commits=2, Rejects=2, Faults(_)=1`, фінальні стани **`[25, 1]`**). |

Щоб виконати всі 10 прикладів одним запуском і зберегти повний машиночитаний звіт у JSON:

```bash
cd Engineering/sw/vmk-go
go run ./cmd/vmk --example all --json-out vmk_all_examples.json
```

---

### 2.7. Двобанкове гаряче оновлення правил (`CFG-P-HA` у `bram64`) та робота з фізичною платою `PYNQ-Z1` (`--target pynq1 | pynq2`)

#### 1. Двобанкове гаряче оновлення дескрипторів (`Bank 0 / Bank 1` та `CRC-8-CCITT`)

У режимі `bram64` ([`internal/vmk/bram64.go`](../sw/vmk-go/internal/vmk/bram64.go)) реалізовано програмну модель двобанкової пам'яті дескрипторів `CFG-P-HA` за контрактом [B4 v2.4.0](../specifications/hw/kpol-image-loader-pipeline-contract.md):
* Рушій `BRAM64Engine` підтримує два банки по 64 дескриптори (`Bank0` і `Bank1`) та індикатор активного банку `ActiveBank` (відображається в шапці TUI як `Bank=0` або `Bank=1`).
* Метод `HotUpdateShadowSlot(cid, packet16, expectedCRC8, overrideW0)` приймає 16-байтний пакет нового дескриптора, обчислює контрольну суму **`CRC-8-CCITT`** (поліном `0x07`, початкове значення `0x00`) і у разі розбіжності CRC відхиляє пакет за принципом `fail-closed` (`VMK-HA-CRC8`), не змінюючи тіньовий банк.
* При валідному `CRC-8` оновлення записується в неактивний тіньовий банк (`ShadowDescriptors`), виставляється прапорець `SwapPending = true`, а виклик `SwapBanksAtIdleBoundary()` атомарно перемикає активний банк між хвилями подій (на межі `ST_IDLE`), зберігаючи живий накопичений стан `W0` для всіх слотів, де не було замовлено явного перезапису `overrideW0`.

#### 2. Підключення `vmk` до фізичної плати `Digilent PYNQ-Z1` (`--target pynq1 | pynq2`)

Коли в прапорці `--target` (або `--connect`) вказано апаратну ціль `pynq1`, `pynq2` чи явну адресу `user@host`, метод [`ExecutePYNQSession`](../sw/vmk-go/internal/vmk/pynq.go) (разом зі структурою знімків у [`internal/vmk/snapshot.go`](../sw/vmk-go/internal/vmk/snapshot.go)):
1. Автоматично бере ексклюзивне системне блокування **`syscall.Flock` на файлі `/tmp/km-bench.lock`** із таймаутом очікування до `120 с` (відповідно до правила `AGENTS.md §2.3`, щоб унеможливити одночасний доступ кількох агентів або тестів до `/dev/mem` плати). При запуску зовнішніх оболонок або батч-скриптів також можна обгортати команду у `flock -w 120 /tmp/km-bench.lock`;
2. Підключається по SSH до плати, компілює та виконує C99 MMIO-зонд за базовою фізичною адресою **`0x40000000`** (`HW_ID = 0x4B504D43` `"KPMC"` для `CFG-P` або `0x4B504841` `"KPHA"` для `CFG-P-HA`), передаючи `PYNQ_SUDO_PASS` через `stdin` (`sudo -S -p ''`) без підстановки пароля в рядок команди оболонки (або викликаючи `sudo -n`, якщо `PYNQ_SUDO_PASS` не задано);
3. Знімає повний апаратний знімок **`PRE-LOAD`** (`256` слів BRAM + апаратні лічильники `REG_EVENTS`, `REG_COMMITS`, `REG_REJECTS`, `REG_LAST_STATE`, `REG_DROPPED`), записує 256 слів нової програми, виконує зворотну перевірку **`POST-LOAD` (`256/256 words OK`)**, подає валідні стимули через `REG_EVENT_PARAM (0x00C)` та `REG_SW_TRIGGER (0x010)` і зчитує фінальний апаратний знімок **`POST-RUN`**.

Приклад команди для роботи з фізичною платою `pynq2`:

```bash
cd Engineering/sw/vmk-go
printf "Cell_Delta_mV 15\nCell_Delta_mV 5500\nCell_Delta_mV _\nCell_Delta_mV 120\nCell_Delta_mV 49\nCell_Delta_mV 180\nCell_Delta_mV 250\nCell_Delta_mV 5000\nCell_Delta_mV -10\n" | \
  PYNQ_SUDO_PASS='<ваш_пароль_sudo>' \
  flock -w 120 /tmp/km-bench.lock \
  go run ./cmd/vmk --mode bram64 \
    --program ../../validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol \
    --profile KPOL-CME-2 --stdio --render-tui-frame --target pynq2
```

#### 3. Змінні оточення та коди виходу процесу `vmk`

| Змінна оточення / Код виходу | Значення за замовчуванням | Призначення |
| :--- | :--- | :--- |
| `KM_PYNQ1_HOST` | `xilinx@192.168.68.81` (локальний стенд) | SSH-адреса першої стендової плати `PYNQ-Z1` при виборі `--target pynq1` (перевизначається змінною оточення). |
| `KM_PYNQ2_HOST` | `xilinx@192.168.68.69` (локальний стенд) | SSH-адреса другої стендової плати `PYNQ-Z1` при виборі `--target pynq2` (перевизначається змінною оточення). |
| `PYNQ_SUDO_PASS` | `<ваш_пароль_sudo>` (за замовчуванням порожній `""` $\to$ `sudo -n`) | Пароль `sudo` користувача на платі `PYNQ-Z1` для доступу C99 MMIO-зонда до `/dev/mem` (передається безпечно через `stdin` у `sudo -S -p ''` без інтерполяції в оболонку). |
| **Код виходу `0`** | Успішне виконання | Програма скомпільована і виконана успішно (навіть якщо були `REJECT_*`, коли прапорець `--fail-on-reject` не вказано). |
| **Код виходу `1`** | Відмова події при `--fail-on-reject` | Увімкнено `--fail-on-reject` (або `--exit-on-reject`) і під час сесії трапився принаймні один `REJECT_GUARD`, `REJECT_INVARIANT` або `REJECT_FAULT`. |
| **Код виходу `2`** | Помилка CLI / компіляції / цілі (`VMK-TARGET-IO`) | Некоректні прапорці CLI, помилка синтаксису `.kpol` або недосяжність апаратної цілі по SSH/MMIO (повертається діагностика `VMK-TARGET-IO: ...` у `stderr`). |

---

### 2.8. Повний довідник прапорців командного рядка (`CLI Reference`)

Виконуваний файл `vmk` підтримує опціональні позиційні підкоманди (`vmk run`, `vmk trace`, `vmk tui`, `vmk version`) та прапорці стандартного пакета `flag` ([`internal/vmk/cli.go`](../sw/vmk-go/internal/vmk/cli.go)):

| Прапорець / підкоманда | Аргумент / тип | Значення за замовчуванням | Опис |
| :--- | :--- | :--- | :--- |
| `--mode` | `bram64 \| conceptual` | Автовибір за `--example` або `bram64` | Вибір виконавчого режиму: апаратно-точний 64-слотовий BRAM (`bram64`) або навчально-концептуальний (`conceptual`). |
| `--example` | `if \| sum \| nod \| factorial \| tachometer \| bms \| increase \| decrease \| cascade \| auth \| all` | `""` | Запуск одного з 10 вбудованих канонічних прикладів або всіх 10 прикладів поспіль (`all`). |
| `--program` | `<шлях до .kpol або .bin>` | `""` | Шлях до вхідного файлу програми `.kpol` або готового 1024-байтного двійкового образу BRAM `.bin`. |
| `--profile` | `KPOL-CME-1 \| KPOL-CME-2 \| KPOL-AUTH` | `KPOL-CME-2` | Профіль вбудованого компілятора KPOL під час компіляції текстового файлу `--program <file.kpol>`. |
| `--target` (аліас `--connect`) | `sim \| pynq1 \| pynq2 \| user@host` | `sim` | Цільова машина: локальний симулятор (`sim`) або фізична плата `PYNQ-Z1` по SSH/MMIO (`pynq1`, `pynq2`, `user@host`). |
| `--trace-events` | `<spec>` (наприклад, `"0:10,0:100,0:_"`) | `""` | Перелік подій через кому або крапку з комою у форматі `<CID_або_Назва>:<param>[:<valid>]` для пакетного трасування. |
| `--dump-concepts` | Булевий прапорець | `false` | Вивести розшифровану таблицю дескрипторів BRAM (`W0`, `Valid(_)`, `W1`, `W2`, `W3`) для активних концептів. |
| `--stdio` | Булевий прапорець | `false` | Читати події/команди з `stdin`, направляти `COMMIT`/`READ` у `stdout`, а всі `REJECT_*` — у `stderr`. |
| `--fail-on-reject` (аліас `--exit-on-reject`) | Булевий прапорець | `false` | Завершувати процес із кодом виходу `1`, якщо під час виконання відбувся хоча б один `REJECT_*` (для CI/CD). |
| `--tui` (або підкоманда `tui`) | Булевий прапорець | `false` | Запустити 4-панельний TUI-дебагер (інтерактивний цикл `s/i/f/r/q`, якщо підключено до `TTY`, або детермінований кадр). |
| `--render-tui-frame` | Булевий прапорець | `false` | Примусово вивести детермінований 4-панельний ASCII-кадр TUI у `stdout` без інтерактивного очікування клавіш. |
| `--watch-cid` | `<cids>` (наприклад, `"0,2,3"`) | `""` | Список слотів `CID` через кому, на яких встановлюються точки спостереження (`*WATCH_CID`). |
| `--break-on-reject` | Булевий прапорець | `false` | Встановити точку спрацювання (`*BREAK_ON_REJECT`) на будь-яку відмову охоронця, інваріанта чи невизначеності. |
| `--stop-on-breakpoint` | Булевий прапорець | `false` | Негайно зупиняти виконання хвилі подій при першому спрацюванні `Watchpoint` або `Breakpoint`. |
| `--json-out` | `<шлях до .json>` | `""` | Записати повний структурований звіт сесії (`pre_load`, `post_load`, `load_diffs`, `telemetry`, `steps`, `stdio`, `pynq_hw_report`) у JSON-файл. |
| `--version` (або `-v`, `version`) | Булевий прапорець | `false` | Вивести версію `VMK (Virtual Machine of Kuzmin) v0.1.0` та завершити роботу з кодом `0`. |

---

## Обмеження

1. **Атрибуція та розмежування з первинними авторськими джерелами (`AGENTS.md §6.1`):**
   * Автор концепції Машини Кузьміна — **Михайло Ювеналійович Кузьмін** (первинні матеріали у [`Research/sources/`](../../Research/sources/README.md)). Програмний модуль [`Engineering/sw/vmk-go/`](../sw/vmk-go/go.mod), специфікація [`vmk-go-emulator-and-tui-debugger-0.1.0.md`](../specifications/sw/vmk-go-emulator-and-tui-debugger-0.1.0.md) та цей посібник є похідними інженерними напрацюваннями проєкту (М. Федчик, інженерні агенти) і не приписуються Автору концепції.
2. **Межа між концептуальним режимом (`--mode conceptual`) та апаратним конвеєром `CME-RAW-1` (`--mode bram64`):**
   * Апаратний конвеєр `CFG-P` (`kpol_bram_pipeline_axi.sv`) та його двобанкова версія `CFG-P-HA` (`kpol_bram_pipeline_axi_ha.sv`) оперують 16-байтними дескрипторами `CME-RAW-1` над 32-бітними цілими `Int32` та вимагають ациклічності графа підписок (`DAG`).
   * Рекурсивні й циклічні конструкції (`Nod(120, 6)`, `Factorial(5)`), тип `Float64`, пост-адресне скидання після читання (`→ • Sum = 0`) та клас `Tachometer` виконуються у концептуальній віртуальній машині `--mode conceptual` і не транслюються в 16-байтний слот `CME-RAW-1`.
   * Наявність `--mode conceptual` не закриває 12 відкритих питань авторської граматики `KPOL-AUTH-U01..U12` (`RFC-009, 015–018`), які залишаються заблокованими за принципом `fail-closed` у [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186).
3. **Особливості роботи з фізичною платою `PYNQ-Z1` (`--target pynq1 | pynq2`):**
   * Усі звернення до фізичних плат виконуються виключно під міжпроцесним блокуванням `/tmp/km-bench.lock` (`AGENTS.md §2.3`).
   * Оскільки регістр `REG_EVENT_PARAM (0x00C)` у поточному RTL `CFG-P` (`CME-RAW-1`) приймає 32-бітне слово без окремого апаратного біта `state_valid` (який спроєктовано для 32-байтного дескриптора `CME-RAW-2` в [`ADR B7`](../decisions/cme-raw2-kpol-sys02.md)), події зі станом невизначеності `_` (`param_valid = false`) під час сесії `--target pynq2` відсікаються шлюзом визначеності `BRAM64Engine` (`REJECT_FAULT`), а валідні 32-бітні події виконуються безпосередньо в ПЛІС `Zynq-7020`.
4. **Позиція щодо стандартів (`Project/policies/standards-position.md`):**
   * Орієнтація на процеси ASPICE 4.0 у документації та трасуванні є внутрішнім інженерним орієнтиром проєкту; жодна сертифікація чи відповідність стандартам функціональної безпеки (ISO 26262, IEC 61508 тощо) не заявляється.

---

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 1.0.1 | 2026-11-18 | Ураховано всі 5 зауважень незалежної рецензії `claude-sonnet-5.5` у PR #277 (`F1..F5`): виправлено відносні шляхи `../../validation/...` у командах запуску з `Engineering/sw/vmk-go` (`F1`); винесено PYNQ-драйвер у `internal/vmk/pynq.go` з безпечною передачею `PYNQ_SUDO_PASS` через `stdin` (`sudo -S -p ''`) або `sudo -n` без інтерполяції в оболонку та замінено пароль на плейсхолдер `<ваш_пароль_sudo>` (`F2, F4`); показано роздільний вивід потоків `stdout` і `stderr` у прикладі `sum --stdio` (`F3`); уточнено атрибуцію `19` реактивних віднімань у VMK проти `58` тактів спеціалізованого RTL-ядра `km_euclid_core.sv` у симуляції `iverilog` і звірено всі фінальні стани таблиці §2.6 із `vmk --example all` (`F5`). |
| 1.0.0 | 2026-11-18 | Перша редакція практичного Посібника користувача VMK (`Virtual Machine of Kuzmin v0.1.0`) та 4-панельного TUI-дебагера на Go (`Engineering/sw/vmk-go/`) за Issue #276. |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| **VMK** | Virtual Machine of Kuzmin — двомодовий емулятор, потоковий фільтр `STDIO` та 4-панельний TUI-дебагер Машини Кузьміна на мові Go (`Engineering/sw/vmk-go/`). |
| **Концепт (`Concept`)** | Базова комірка стану, припущення `::`, дії, інваріанта Великої Крапки `•` та підписки в Машині Кузьміна (`CID 0..63` у `bram64`). |
| **Велика Крапка (`•` / Big Dot)** | Пост-умовний бар'єр інваріанта та порядку виконання: у `bram64` — вентиль `EvalInvariantGate` (`cand >= 0 && !ovf32`), який блокує порушення інваріанта до зміни стану `W0`; у `conceptual` (`RFC-013`) — також пост-адресний бар'єр після читання `→ •`. |
| **Стан невизначеності (`_`)** | Явно виділений стан відсутності валідного значення концепту або пошкодження вхідного сигналу датчика (`Valid = false`, `RFC-005` / `KPOL-SYS-02`). |
| **`CME-RAW-1`** | 16-байтний (`W0..W3`, little-endian) двійковий формат дескриптора концепту в 64-слотовій BRAM (`1024 B`). |
| **`CFG-P` / `CFG-P-HA`** | Однобанкова (`1 × RAMB36E1`, `HW_ID = 0x4B504D43`) та двобанкова (`2 × RAMB36E1`, беззупинне гаряче оновлення правил із `CRC-8`, `HW_ID = 0x4B504841`) конфігурації апаратного BRAM-конвеєра МК. |
| **`PRE-LOAD` / `POST-LOAD`** | Фази інспекції стану машини: знімок 64 слотів BRAM і апаратних лічильників **до** запису нової програми (`PRE-LOAD`) та верифікований знімок і послотна таблиця змін **після** програмування (`POST-LOAD`). |
| **`TUI`** | Text-based User Interface — 4-панельний текстовий інтерфейс покрокового налагодження каскадів подій (`--tui`, `--render-tui-frame`). |
| **`STDIO`** | Потоковий режим роботи через стандартні потоки UNIX (`stdin` — вхідні події/команди, `stdout` — `COMMIT`/`READ`, `stderr` — `REJECT_*`). |
| **`HIL`** | Hardware-in-the-Loop — верифікація за участю фізичної плати ПЛІС `Digilent PYNQ-Z1` (`Zynq-7020`). |
