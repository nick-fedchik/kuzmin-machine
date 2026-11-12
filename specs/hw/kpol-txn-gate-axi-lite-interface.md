# Специфікація апаратного інтерфейсу та карта регістрів AXI4-Lite транзакційного шлюзу (kpol_txn_gate_axi_lite)

* **Версія:** 1.0.0
* **Дата:** 2026-11-12
* **Статус:** Нормативний документ (Approved)
* **ASPICE 4.0 процеси:** `HWE.1` (Hardware Requirements Analysis), `SYS.3` (System Architectural Design)
* **Простежуваність:** `REQ-HW-008`, `REQ-HW-004`, `REQ-HW-005`, Issue #48 (знахідка З1 на PR #44)
* **Цільовий RTL-модуль:** [`hw/rtl/bus/kpol_txn_gate_axi_lite.sv`](../../hw/rtl/bus/kpol_txn_gate_axi_lite.sv)
* **Конфігурація:** `CFG-R` (фізичний транзакційний шлюз, AV-10, AV-11, PYNQ-Z1)

---

## 1. Призначення та межі документа

Цей документ фіксує нормативну специфікацію інтерфейсу шини AXI4-Lite, повну карту регістрів керування та статусу (CSR), простір прямого доступу до BRAM, точні значення всіх регістрів після апаратного скидання (reset values), правила обробки помилок декодування/доступу, а також двоспрямоване трасування до тестових стендів і споживачів (драйверів MCU/PYNQ).

Документ закриває знахідку З1 рецензії agy на PR #44 (Issue #48) та усуває розрив відсутності нормативного джерела для карти регістрів і значень за замовчуванням (зокрема `upper_bound_q = 0x7FFFFFFF`), який призвів до історичної регресії в `drafts@f5c65fc` (#38).

### Межі розрізнення обгорток:
- Ця специфікація регулює **ручну AXI-обгортку** [`kpol_txn_gate_axi_lite.sv`](../../hw/rtl/bus/kpol_txn_gate_axi_lite.sv), яка інстанціює шлюз `kpol_txn_gate` v1, обчислювач предикатів `km_predicate_evaluator`, таблицю `km_concept_bram`, ядро `km_io_trigger_engine` та PoC-рушії в конфігурації `CFG-R`.
- Вона **не підміняє** конвеєрну AXI-обгортку [`kpol_bram_pipeline_axi.sv`](../../hw/rtl/bus/kpol_bram_pipeline_axi.sv) (`CFG-P`), життєвий цикл і завантаження якої регламентуються в межах кроку S2 (задачі #133 / #134).

---

## 2. Параметри шинного інтерфейсу AXI4-Lite

Модуль реалізує інтерфейс підпорядкованого пристрою (AXI4-Lite Slave) згідно зі стандартом **ARM AMBA AXI and ACE Protocol Specification (ARM IHI 0022E)**.

| Параметр | Значення | Опис |
| :--- | :--- | :--- |
| **Протокол** | `AXI4-Lite` (Memory Mapped) | Непідтримувані розширення (bursts, cache, lock, id) не реалізовано. |
| **Базова адреса (Base Address)** | `0x4000_0000` | Стандартний діапазон вікна `M_AXI_GP0` на кристалах Zynq-7000 (PS $\to$ PL). |
| **Розмір апертури (Aperture Size)** | `0x2000` (8 КБ) | Шина адреси 13 біт (`s_axi_awaddr[12:0]`, `s_axi_araddr[12:0]`). |
| **Розрядність даних** | 32 біти | `s_axi_wdata[31:0]`, `s_axi_rdata[31:0]`. |
| **Розрядність стробів байтів** | 4 біти | `s_axi_wstrb[3:0]`. |
| **Тактова частота шини (`s_axi_aclk`)** | 100.0 МГц | Період такту $T_{\text{clk}} = 10.0\text{ нс}$. |
| **Скидання (`s_axi_aresetn`)** | Активний низький рівень (0) | Асинхронний вхід скидання з синхронним зняттям у тактовому домені. |

---

## 3. Правила адресації, вирівнювання та коди відповідей

### 3.1. Вирівнювання (Alignment)
Всі звернення (читання та запис) **повинні бути строго вирівняні по 32-бітних межах слів** (`addr[1:0] == 2'b00`).
- Якщо `addr[1:0] != 2'b00`, модуль повертає відповідь **`AXI_RESP_DECERR`** (`2'b11`) як на каналі запису (`s_axi_bresp`), так і на каналі читання (`s_axi_rresp`). Зміна внутрішнього стану не відбувається.

### 3.2. Адресні підпростори
13-бітна адреса декодується на два дозволені адресні діапазони:
1. **CSR (Control & Status Registers):** `addr[12:8] == 5'b00000` (зсуви `0x0000` .. `0x00FF`). Декодується за молодшими бітами `addr[7:0]`.
2. **BRAM Concepts Table:** `addr[12:10] == 3'b100` (зсуви `0x1000` .. `0x13FF`, 1024 байти = 256 слів).
3. **Незадіяний простір:**
   - Будь-яка адреса в діапазоні `0x0100` .. `0x0FFF` повертає `AXI_RESP_DECERR`.
   - Будь-яка адреса в діапазоні `0x1400` .. `0x1FFF` повертає `AXI_RESP_DECERR`.
   - Незадіяні зсуви всередині CSR (зокрема вирівняний зсув `0x007C`, а також `0x00C4` .. `0x00FF`) повертають `AXI_RESP_DECERR`.

### 3.3. Коди відповідей шини (AXI Responses)
- **`AXI_RESP_OKAY` (`2'b00`):** Нормальне завершення операції читання або запису.
- **`AXI_RESP_DECERR` (`2'b11`):** Помилка адресації (невирівняна адреса `addr[1:0] != 00`, читання/запис неіснуючого регістра, спроба запису в регістр, доступний лише для читання).
- **`AXI_RESP_SLVERR` (`2'b10`):** Помилка підлеглого пристрою у таких випадках:
  - Спроба запису в регістри вхідних даних транзакції (`0x00`..`0x08`) під час активного виконання (`busy_q == 1`).
  - Спроба запису в `REG_COMMAND` (`0x08`) зі сміттям у старших бітах (`write_data[31:1] != 0`).
  - Спроба запуску алгоритмічного ядра, коли воно вже зайняте обчисленням (`euclid_busy`, `bram_core_busy`, `rcfc_busy`, `suite_b_busy`, `stream_busy`, `io_trig_busy`).

---

## 4. Карта регістрів керування та статусу (CSR, 0x0000 .. 0x00FF)

| Зсув (Offset) | Символічне ім'я | Доступ | Значення після скидання (Reset Value) | Опис та бітові поля |
| :---: | :--- | :---: | :---: | :--- |
| `0x00` | `REG_CANDIDATE_VALUE` | R/W | `0x00000000` | Кандидатне значення стану для транзакції. Підтримує побайтові строби `wstrb`. Захищено від запису при `busy_q == 1` (`SLVERR`). |
| `0x04` | `REG_CONDITIONS` | R/W | `0x00000000` | Вектор умов та передумов транзакції (7 біт):<br/>• `[0]` — `candidate_known`<br/>• `[1]` — `assumption_known`<br/>• `[2]` — `assumption_true`<br/>• `[3]` — `invariant_known` (ручний режим)<br/>• `[4]` — `invariant_true` (ручний режим)<br/>• `[5]` — `hazard_known`<br/>• `[6]` — `hazard_true`<br/>• `[31:7]` — зарезервовано (0). Захищено при `busy_q == 1`. |
| `0x08` | `REG_COMMAND` | W (R=0) | `0x00000000` | Запуск апаратної транзакції:<br/>• Запис `0x00000001` (`bit[0]=1`) формує 1-тактовий строб `event_valid_q`, переводить шлюз у стан `busy_q = 1` та обнуляє `status_q`.<br/>• Якщо `write_data[31:1] != 0` або `busy_q == 1` $\to$ повертає `SLVERR`. Читання повертає `0x00000000`. |
| `0x0C` | `REG_STATUS` | R | `0x00000000` | Прапорці статусу транзакційного шлюзу:<br/>• `[0]` — `done` (1 після фіксації результату)<br/>• `[1]` — `committed` (транзакцію зафіксовано)<br/>• `[2]` — `rejected` (транзакцію відхилено)<br/>• `[3]` — `rejected_input` (відхилено за вхідними умовами)<br/>• `[4]` — `rejected_invariant` (відхилено через порушення інваріанта •)<br/>• `[5]` — `changed` (стан зазнав змін)<br/>• `[6]` — `hazard_observed` (виявлено колізію/газард)<br/>• `[7]` — `unknown_hazard` (невідомий газард)<br/>• `[8]` — `busy` (шлюз виконує транзакцію)<br/>• `[31:9]` — зарезервовано (0). Спроба запису повертає `DECERR`. |
| `0x10` | `REG_STATE` | R | `0x00000000` | Поточний зафіксований 32-бітний стан концепту. При порушенні інваріанта зберігає попереднє значення (fail-closed). Спроба запису повертає `DECERR`. |
| `0x14` | `REG_IDENTIFICATION` | R | `0x4B504F4C` | Апаратний ідентифікатор ядра: ASCII `"KPOL"` (`0x4B504F4C`). Спроба запису повертає `DECERR`. |
| `0x18` | `REG_INVARIANT_LOWER_BOUND` | R/W | `0x00000000` | Нижня межа допустимого діапазону стану (знакове 32-бітне ціле `32'sd0`). Підтримує побайтові строби `wstrb`. |
| `0x1C` | `REG_INVARIANT_UPPER_BOUND` | R/W | **`0x7FFFFFFF`** | **Верхня межа допустимого діапазону стану.**<br/>Значення після скидання: `32'sh7FFFFFFF` ($+2\,147\,483\,647$). Забезпечує коректну роботу предикату Range за замовчуванням $[0, 2^{31}-1]$. Підтримує побайтові строби `wstrb`. |
| `0x20` | `REG_INVARIANT_RULE_CFG` | R/W | `0x00000000` | Конфігурація правил апаратного перевізника інваріантів (`rule_cfg_q`):<br/>• `[0]` — `RULE_EVEN` (вимагати парність)<br/>• `[1]` — `RULE_POSITIVE` (вимагати додатність $> 0$)<br/>• `[2]` — `RULE_NON_NULL` (вимагати ненульове значення $\ne 0$)<br/>• `[3]` — `RULE_RANGE` (вимагати `lower <= val <= upper`)<br/>• `[4]` — `RULE_CHANGED` (вимагати зміну стану $\ne \text{state}$)<br/>• `[5]` — `RULE_USE_HW_EVAL` ($1$ = автоматичне підключення апаратного предикатора до входу інваріанта шлюзу замість `conditions[3..4]`)<br/>• `[6]` — `RULE_UNEVEN` (вимагати непарність)<br/>• `[7]` — зарезервовано. |
| `0x24` | `REG_PREDICATE_VECTOR` | R | `0x00000001` (динамічний) | 8-бітний вектор поточних обчислених предикатів кандидата `::`:<br/>• `[0]` — `_` (Absent/Uninit, завжди 1)<br/>• `[1]` — `Null` ($val == 0$)<br/>• `[2]` — `Positive` ($val > 0$)<br/>• `[3]` — `Negative` ($val < 0$)<br/>• `[4]` — `Even` ($val[0] == 0$)<br/>• `[5]` — `Uneven` ($val[0] == 1$)<br/>• `[6]` — `~` / `Changed` ($val \ne \text{state}$)<br/>• `[7]` — `Range` ($lower \le val \le upper$).<br/>Спроба запису повертає `DECERR`. |
| `0x28` | `REG_BIG_DOT_STATUS` | R | `0x00000001` (динамічний) | Апаратний вихід оператора «Велика крапка» (•):<br/>• `[0]` — `hw_big_dot`: $1$ = Commit дозволено (`!`), $0$ = Reject (`¬`, порушення інваріанта).<br/>• `[31:1]` — 0. Спроба запису повертає `DECERR`. |
| `0x2C` | `REG_CYCLE_CNT_LO` | R | `0x00000000` | Молодші 32 біти системного вільного 64-бітного лічильника тактів PL ($100\text{ МГц}$, крок $10.0\text{ нс}$). Спроба запису повертає `DECERR`. |
| `0x30` | `REG_CYCLE_CNT_HI` | R | `0x00000000` | Старші 32 біти вільного 64-бітного лічильника тактів. Спроба запису повертає `DECERR`. |
| `0x34` | `REG_LAST_TXN_CYCLES` | R | `0x00000000` | Тривалість виконання останньої транзакції шлюзу в тактах PL. Спроба запису повертає `DECERR`. |
| `0x38` | `REG_EUCLID_A` | R/W | `0x00000000` | Концепт $A$ алгоритму Евкліда (початкове значення / поточний стан у PL). |
| `0x3C` | `REG_EUCLID_B` | R/W | `0x00000000` | Концепт $B$ алгоритму Евкліда (початкове значення / поточний стан у PL). |
| `0x40` | `REG_EUCLID_CMD` | W (R=0) | `0x00000000` | Запис `bit[0]=1` запускає апаратний цикл Евкліда (`SLVERR`, якщо `euclid_busy`). |
| `0x44` | `REG_EUCLID_STATUS` | R | `0x00000000` | `{8'b0, iterations[15:0], 5'b0, error, done, busy}`. |
| `0x48` | `REG_EUCLID_CYCLES` | R | `0x00000000` | Лічильник тактів виконання алгоритму Евкліда. |
| `0x4C` | `REG_EUCLID_RESULT` | R | `0x00000000` | Апаратний результат $\gcd(A, B)$. |
| `0x50` | `REG_BRAM_CTRL` | R/W | `0x00000000` | Керування ядром BRAM: `[0]` start, `[1]` op, `[13:8]` src CID, `[21:16]` dst CID. |
| `0x54` | `REG_BRAM_STATUS` | R | `0x00000000` | `{29'b0, collision, done, busy}`. |
| `0x58` | `REG_BRAM_CYCLES` | R | `0x00000000` | Лічильник тактів операції BRAM. |
| `0x5C` | `REG_BRAM_PORT_B_ADDR` | R/W | `0x00000000` | `{24'b0, addr[7:0]}` (адреса слова Port B, 0..255). |
| `0x60` | `REG_BRAM_PORT_B_DATA` | R/W | `0x00000000` | Дані слова Port B (читання/запис без блокування Port A). |
| `0x64` | `REG_RCFC_CTRL` | R/W | `0x00000000` | Керування рушієм RCFC: `[2:0]` cmd, `[3]` start, `[15:8]` delay_param. |
| `0x68` | `REG_RCFC_STATUS` | R | `0x00000000` | `{processed[15:0], 4'b0, tc[3:0], drop_err, dlock_err, p4, p3, p2, p1, done, busy}`. |
| `0x6C` | `REG_RCFC_CYCLES` | R | `0x00000000` | Лічильник тактів тесту RCFC. |
| `0x70` | `REG_RCFC_SLOT_STATE` | R/W | `0x00000000` | Запис: `[5:0]` slot_sel; Читання: `{payload[15:0], wait_cycles[7:0], 5'b0, state[2:0]}`. |
| `0x74` | `REG_RCFC_AVALANCHE` | R | `0x00000000` | `{dropped[15:0], enqueued[15:0]}`. |
| `0x78` | `REG_RCFC_RESULT` | R | `0x00000000` | Апаратний результат рандеву. |
| `0x7C` | *Unmapped Gap* | — | — | **Повертає `AXI_RESP_DECERR`.** |
| `0x80` | `REG_SUITE_B_CTRL` | R/W | `0x00000000` | Керування стрес-рушієм каскадів Suite B: `[2:0]` cmd, `[3]` start. |
| `0x84` | `REG_SUITE_B_STATUS` | R | `0x00000000` | `{20'b0, tc[3:0], fail, 1'b0, p8, p7, p6, p5, done, busy}`. |
| `0x88` | `REG_SUITE_B_CYCLES` | R | `0x00000000` | Лічильник тактів Suite B. |
| `0x8C` | `REG_SUITE_B_RES0` | R | `0x00000000` | Апаратний результат Suite B 0. |
| `0x90` | `REG_SUITE_B_RES1` | R | `0x00000000` | Апаратний результат Suite B 1. |
| `0x94` | `REG_STREAM_CTRL` | R/W | `0x00000000` | Керування потоковим конвеєром: `[0]` start, `[2:1]` mode, `[31:16]` count. |
| `0x98` | `REG_STREAM_STATUS` | R | `0x00000000` | `{29'b0, pass, done, busy}`. |
| `0x9C` | `REG_STREAM_CYCLES` | R | `0x00000000` | Лічильник тактів конвеєра. |
| `0xA0` | `REG_STREAM_COUNTS` | R | `0x00000000` | `{clamped[15:0], processed[15:0]}`. |
| `0xA4` | `REG_STREAM_CHECKSUM` | R | `0x00000000` | Контрольна сума актуатора. |
| `0xA8` | `REG_STREAM_LAST_VAL` | R | `0x00000000` | `{actuator[15:0], filtered[15:0]}`. |
| `0xAC` | `REG_IO_TRIGGER_CTRL` | R/W | `0x00000000` | Керування тригером I/O 0p0: `[0]` start, `[1]` clear, `[31:16]` burst. |
| `0xB0` | `REG_IO_TRIGGER_STATUS` | R | `0x00000000` | `{26'b0, reactive_out, ext_pin, 1'b0, pass, done, busy}`. |
| `0xB4` | `REG_IO_TRIGGER_CYCLES` | R | `0x00000000` | `{min_latency[15:0], last_latency[15:0]}`. |
| `0xB8` | `REG_IO_TRIGGER_MAX_CYCLES`| R | `0x00000000` | `{max_latency[15:0], count[15:0]}`. |
| `0xBC` | `REG_IO_TRIGGER_TS_LO` | R | `0x00000000` | Молодші 32 біти таймстампу реактивної події. |
| `0xC0` | `REG_IO_TRIGGER_TS_HI` | R | `0x00000000` | Старші 32 біти таймстампу реактивної події. |
| `0xC4`..`0xFF`| *Unmapped Gap* | — | — | **Повертає `AXI_RESP_DECERR`.** |

---

## 5. Простір таблиці концептів BRAM (0x1000 .. 0x13FF)

Діапазон адрес `0x1000` .. `0x13FF` надає процесору прямий доступ через Port A до апаратної пам'яті концептів [`km_concept_bram.sv`](../../hw/rtl/core/km_concept_bram.sv).

- **Обсяг:** 1024 байти (256 слів по 32 біти).
- **Місткість:** 64 дескриптори концептів (по 16 байтів = 4 слова на концепт).
- **Адресація слова в BRAM:** `bram_a_addr[7:0] = write_address[9:2]` (або `ar_latched_addr_q[9:2]`).
- **Формат 16-байтного дескриптора:**
  - `Слово 0 (+0x0)`: `val_cur` — поточне 32-бітне значення концепту.
  - `Слово 1 (+0x4)`: `val_prev` — попереднє 32-бітне значення концепту.
  - `Слово 2 (+0x8)`: `flags` — бітові прапорці (`[3]` = апаратний захист `KM_FLAG_HW_PROTECTED`).
  - `Слово 3 (+0xC)`: `sub_info` / індекс першої підписки та кількість правил.
- **Підтримка побайтового запису:** Повноцінна апаратна підтримка `s_axi_wstrb[3:0]`.

---

## 6. Двоспрямоване трасування (Traceability Matrix)

| Елемент карти регістрів | Вимоги (HWE.1 / SYS.3) | Реалізація в RTL | Симуляційний тестбенч (HWE.3) | Програмний драйвер / HIL (SYS.4) |
| :--- | :--- | :--- | :--- | :--- |
| **Базова адресація та протокол AXI4-Lite** | `REQ-HW-008`, `SYS.3` | `hw/rtl/bus/kpol_txn_gate_axi_lite.sv:10-45` | `hw/tb/kpol_txn_gate_axi_lite_tb.sv:57-117` | `sw/runtime/pynq/kpol_direct_mmio_driver.py:18-26`, `sw/runtime/mcu/km_mcu_fpga_bridge.c:90-91` |
| **Кандидат і умови (`0x00`, `0x04`)** | `REQ-HW-008`, `SYS.2` | `hw/rtl/bus/kpol_txn_gate_axi_lite.sv:654-661` | `hw/tb/kpol_txn_gate_axi_lite_tb.sv:185-188, 211-213` | `sw/runtime/pynq/kpol_direct_mmio_driver.py:38-46`, `sw/runtime/mcu/km_mcu_fpga_bridge.c:93-94` |
| **Команда і статус (`0x08`, `0x0C`)** | `REQ-HW-008`, `SYS.2` | `hw/rtl/bus/kpol_txn_gate_axi_lite.sv:662-674, 792-806` | `hw/tb/kpol_txn_gate_axi_lite_tb.sv:190-198, 201-204` | `sw/runtime/pynq/kpol_direct_mmio_driver.py:28-36`, `sw/runtime/mcu/km_mcu_fpga_bridge.c:107-113` |
| **Стан і ID (`0x10`, `0x14`)** | `REQ-HW-008`, `SYS.3` | `hw/rtl/bus/kpol_txn_gate_axi_lite.sv:276-277` | `hw/tb/kpol_txn_gate_axi_lite_tb.sv:174-177, 205-208` | `sw/runtime/pynq/kpol_direct_mmio_driver.py:22-25`, `sw/runtime/mcu/km_mcu_fpga_bridge.c:97-98, 105` |
| **Межі інваріанта (`0x18`, `0x1C`)** | `REQ-HW-004`, `REQ-HW-008` | `hw/rtl/bus/kpol_txn_gate_axi_lite.sv:550-551, 675-680` | `hw/tb/kpol_txn_gate_axi_lite_tb.sv:235-243` | `hw/boards/pynq-z1/hil/hil_predicate_eval.py:98`, `sw/runtime/mcu/km_mcu_fpga_bridge.c:157, 167, 179` |
| **Конфігурація правил (`0x20`)** | `REQ-HW-002`, `REQ-HW-004` | `hw/rtl/bus/kpol_txn_gate_axi_lite.sv:681-685` | `hw/tb/kpol_txn_gate_axi_lite_tb.sv:255-257` | `hw/boards/pynq-z1/hil/hil_predicate_eval.py:44-52`, `sw/runtime/mcu/km_mcu_fpga_bridge.c:115-120` |
| **Вектор предикатів і Велика крапка (`0x24`, `0x28`)** | `REQ-HW-002`, `REQ-HW-004` | `hw/rtl/bus/kpol_txn_gate_axi_lite.sv:281-282, 335-347` | `hw/tb/kpol_txn_gate_axi_lite_tb.sv:248-260, 274-279` | `hw/boards/pynq-z1/hil/hil_predicate_eval.py:30-31`, `sw/runtime/mcu/km_mcu_fpga_bridge.c:102-103` |
| **Лічильники тактів (`0x2C`, `0x30`, `0x34`)** | `REQ-HW-008`, `HWE.1` | `hw/rtl/bus/kpol_txn_gate_axi_lite.sv:284-286, 586, 600-602`| `hw/tb/kpol_txn_gate_axi_lite_tb.sv:326-330` | `hw/boards/pynq-z1/hil/hil_manual_mmio.py`, `experiments/AV-10/scripts/` |
| **Прямий доступ BRAM (`0x1000..0x13FF`)** | `REQ-HW-005`, `SYS.3` | `hw/rtl/bus/kpol_txn_gate_axi_lite.sv:250-257, 267-268` | `hw/tests/test_testbenches.py` (`km_concept_bram_tb.sv`) | `hw/boards/pynq-z1/hil/hil_bram_concepts.py:46, 196` |
| **Обробка помилок DECERR / SLVERR** | `HWE.1`, `SYS.3` | `hw/rtl/bus/kpol_txn_gate_axi_lite.sv:264, 327, 644, 651, 672, 784` | `hw/tb/kpol_txn_gate_axi_lite_tb.sv:323-340` | `hw/tests/test_testbenches.py` |

---

## 7. Історія версій

| Версія | Дата | Автор | Зміни |
| :--- | :--- | :--- | :--- |
| **1.0.0** | 2026-11-12 | Antigravity (agy) | Створення нормативної специфікації інтерфейсу та карти регістрів AXI4-Lite для закриття знахідки З1 рецензії PR #44 (Issue #48). Фіксація значень після скидання (`upper_bound_q = 0x7FFFFFFF`), правил вирівнювання, поведінки DECERR/SLVERR та матриці трасування. |
