# Звіт DEBUGGER-TRACE-272: Покроковий дебагер-трасувальник каскадів МК (`--trace-events`, `--stdio`, `--tui`), підключення до `PYNQ-Z1` (`PRE-LOAD` / `POST-LOAD`) та верифікація прикладів програм зі статей (Issue #272)

* **Версія:** 1.0.0
* **Дата:** 2026-11-18
* **Тип WP редакції NG:** Report
* **Issue:** `Closes` [#272](https://github.com/nick-fedchik/kuzmin-machine/issues/272). **PR:** [#273](https://github.com/nick-fedchik/kuzmin-machine/pull/273) у гілці `feat/272-step-debugger-and-example-traces`.
* **Виконавець:** GitHub Copilot CLI (Lead Engineer / Architect). **Рецензент:** очікується незалежна рецензія (`claude-sonnet-5.5` за правилом `PROJECT-MANUAL §2.1`).
* **Коміт бази, на якому виконано:** `6c234bcf513734e8f024024b27379e08a13a35cb` (`origin/main`).
* **Хост верифікації:** `Linux 7.0.0-42-generic x86_64` (`GCC 15.2.0`, `Python 3.14.4`, `pytest 9.0.2`, `z3-solver 5.4.1`, `/usr/bin/z3 4.13.3`, `Icarus Verilog 12.0`).
* **Фізична плата HIL (`pynq2`, під `flock -w 120 /tmp/km-bench.lock`):** `Digilent PYNQ-Z1` (`xilinx@192.168.68.69`, двоядерний `ARM Cortex-A9 @ 650 МГц` + кристал `Xilinx Zynq-7020 XC7Z020-1CLG400C` @ `100.0 МГц`, активний конвеєр `CFG-P` `HW_ID = 0x4B504D43` `"KPMC"`).
* **Критерії успіху (зафіксовано до виконання в Issue #272 та командах власника):**
  1. Покроковий трасувальник-дебагер [`Engineering/sw/kpol-ref/kpol_debugger.py`](../../../sw/kpol-ref/kpol_debugger.py) та прапорці `--dump-concepts` і `--trace-events` у [`Engineering/hw/scripts/compile_kpol_bram_image.py`](../../../hw/scripts/compile_kpol_bram_image.py), що виводять 4 наочні блоки (`Source Code`, `BRAM Descriptors`, `Step-by-Step Cascade Trace`, `State Diff & Telemetry`);
  2. Підтримка `STDIO` (`stdin` / `stdout` / `stderr`, прагми `# @stdin` / `# @stdout`, прапорець `--stdio`) для потокового тестування програм МК через стандартні UNIX-пайпи;
  3. Підключення TUI-дебагера (`--tui` / `--render-tui-frame`, `--target <sim|pynq1|pynq2>`) до реальної машини зі зняттям та порівнянням стану **ДО програмування (`PRE-LOAD`)** і **ПІСЛЯ внесення програми (`POST-LOAD`)**, підрахунком кількості активних концептів (`Active: K / 64`, вхідні, внутрішні каскадні, листові та вільні слоти) і readback-верифікацією 256 слів BRAM;
  4. Покрокова верифікація 5 груп показових програм зі статей та слайдів Автора (`Increase/Decrease`, `4-Concept Cascade`, `BMS 4-Stage Safety Cascade`, `Author Native Counter Subset`, та слайдові `If`, `Sum`, `Nod(120, 6) = 6` зі звіркою проти `km_euclid_core.sv` у `Icarus Verilog`);
  5. Походження всіх чисел у `raw/*.log` із заголовками `# cmd:`, `# timestamp:`, `# git_commit:`, `# host:` та щонайменше 4 негативні мутантні тести за `AGENTS.md §4.1` у [`Engineering/sw/tests/test_kpol_debugger_272.py`](../../../sw/tests/test_kpol_debugger_272.py).

---

## 1. Що не вдалося і обмеження

1. **Межа апаратного `STDIO` та біта невизначеності `_` у чинному `CME-RAW-1` (`CFG-P`):**
   * У фізичному конвеєрі `kpol_bram_pipeline_axi.sv` (`CFG-P`, 16-байтний слот `W0..W3` формату `CME-RAW-1`) апаратні регістри `REG_EVENT_PARAM (0x00C)` та `REG_SW_TRIGGER (0x010)` передають 32-бітне значення `param` на `CID 0`, а окремий біт `state_valid` (`_`) запланований у 32-байтному дескрипторі `CME-RAW-2` за прийнятим [`ADR B7`](../../../decisions/cme-raw2-kpol-sys02.md).
   * Тому при роботі дебагера з фізичною платою `PYNQ-Z1` (`--target pynq2`) валідні події траси виконуються безпосередньо в кремнії `Zynq-7020 PL` (де апаратні лічильники `REG_EVENTS = +18`, `REG_COMMITS = +12`, `REG_REJECTS = +6` і кінцеві стани `W0 = [4, 4, 0, 0]` 100% збігаються з дебагером), тоді як події зі станом невизначеності `_` (`param_valid = False`) відпрацьовуються на рівні C99-модуля безпеки (`valid_mask`) і покрокового трасувальника `KpolCascadeDebugger` (`REJECT_FAULT`).
2. **Розмежування ациклічних каскадів `CFG-P` та циклічного `Nod(120, 6) = 6`:**
   * Як строго доведено в теоремі Ляпунова `P1_dag_lyapunov_acyclicity` ([звіт `#227`](../cme2-formal-227/report.md) та [`c99_emitter.py`](../../../sw/kpol-ref/c99_emitter.py)), апаратний конвеєр безпеки `CFG-P` і генератор `--emit-c99` навмисно вимагають строго ациклічного графа підписок `W3` (`DAG`), щоб гарантувати скінченний найгірший час відгуку `WCET = O(K)` без зависання в нескінченних циклах.
   * Через це циклічний алгоритм Евкліда зі слайда 3 презентації М. Ю. Кузьміна (`Nod(120, 6) = 6`, де `a` та `b` взаємно зменшують одне одного 19 разів поспіль) не завантажується в ациклічну таблицю `CFG-P`, а верифікується у `kpol_debugger.py` двома незалежними шляхами: (а) покроковим трасувальником реактивної моделі переходів Автора (`trace_author_euclid_nod_example`) та (б) такт-у-такт симуляцією апаратного RTL-ядра `km_euclid_core.sv` у `Icarus Verilog 12.0` (`58` тактів = `19 * 3 + 1`, результат `6`).
3. **Незакриті авторські ескізи зі слайдів (`RFC-009, 015–018`, Issue `#186`):**
   * Слайдові ескізи `Factorial`, `Tachometer / Електролічильник` та `Static(OpenBracket, ..., CloseBracked)` покладаються на конструкції, для яких у первинних матеріалах Автора відсутня повна операційна семантика (`KPOL-AUTH-U01..U12`). У компіляторі `KPOL-AUTH` вони детерміновано блокуються за принципом `fail-closed` і не подаються як «працюючі програми».

---

## 2. Метод: 4-рівнева архітектура налагодження Машини Кузьміна

Оскільки в Машині Кузьміна немає глобального лічильника команд (`PC`), класичний покроковий дебагінг інструкцій `STEP INTO / STEP OVER` за адресою `PC` замінюється **пофазовим трасуванням хвилі події та каскаду (`Event & Cascade Step Debugging`)** на чотирьох рівнях:

1. **Рівень 1 — Інспекція стану машини `PRE-LOAD` vs `POST-LOAD` (`MachineDebugConnection`):**
   * Дебагер підключається до цільової машини (`--target sim` або `--target pynq2` під `flock -w 120 /tmp/km-bench.lock`), зчитує апаратний ідентифікатор `REG_ID (0x000)` (`0x4B504D43 "KPMC"` або `0x4B504841 "KPHA"`), лічильники `REG_EVENTS`, `REG_COMMITS`, `REG_REJECTS` та всі `256` 32-бітних слів BRAM (`64` слоти по `16 Б`) **до** запису нової програми (`PRE-LOAD`).
   * Після запису 256 слів нової програми дебагер виконує повне зворотне вичитування (`POST-LOAD readback`), класифікує всі 64 слоти (`Active: K / 64`, `Entry`, `Internal Cascade`, `Leaf`, `Free: 64 - K`) і будує таблицю `PRE-LOAD vs POST-LOAD DIFF`.
2. **Рівень 2 — Стандартні потоки `STDIO` (`stdin` / `stdout` / `stderr`):**
   * Будь-яка програма KPOL може містити директиви прив'язки потоків `# @stdin <Concept>` та `# @stdout <Concept1, Concept2, ...>` і запускатися в потоковому режимі `--stdio`.
   * Кожен рядок `stdin` (`<param>`, `<cid_or_name> <param>`, `<cid_or_name> _` або JSONL) запускає хвилю каскаду: усі успішні зміни станів (`COMMIT`) миттєво пишуться у `stdout`, а всі відмови охоронців чи інваріантів (`REJECT_GUARD`, `REJECT_INVARIANT`, `REJECT_FAULT`) з повною формулою причини відмови — у `stderr`.
3. **Рівень 3 — Десятифазна таблиця покрокового трасування (`--trace-events`) та Watchpoints:**
   * Для кожного кроку хвилі (`E<event_id>.<cascade_step>`, глибина `depth`) дебагер обчислює і виводить: `CID (Name)`, `Event(param, valid)`, `Pre-State (W0, valid)`, `Predicate :: (formula => bool)`, `Candidate (formula => val)`, `Gate • (formula => bool)`, `Verdict (COMMIT / REJECT_GUARD / REJECT_INVARIANT / REJECT_FAULT / SUPPRESSED_SELF)`, `Post-State (W0, valid)` та `Next Subscriber`.
   * Якщо вентиль Великої Крапки `•` блокує перехід (`REJECT_INVARIANT`), функція `diagnose_invariant_counterexample_z3` викликає SMT-солвер `Z3` (`QF_BV BitVec32`) і пред'являє точний контрприклад `(witness_cur_state, witness_ev_param, unsafe_candidate_w0)`.
4. **Рівень 4 — Інтерактивний TUI (`--tui` на базі `curses` та `--render-tui-frame`):**
   * Об'єднує на одному екрані шапку підключеної машини (`PYNQ2` / `SIM`), таблицю концептів (`Pre-Load W0 | Post-Load W0 | Current W0`), панель коду й потоків `STDIN / STDOUT / STDERR` та покрокову трасу каскаду.

---

## 3. Результати верифікації

Первинні сирі логи та JSON-артефакти збережені в [`raw/`](raw/):
* [`raw/pynq2_live_debugger_session.log`](raw/pynq2_live_debugger_session.log) та [`raw/pynq2_live_debugger_session.json`](raw/pynq2_live_debugger_session.json) — натурне підключення дебагера до фізичної плати `PYNQ-Z1` (`pynq2`, `xilinx@192.168.68.69`) під `flock -w 120 /tmp/km-bench.lock`;
* [`raw/article_examples_all_traces.log`](raw/article_examples_all_traces.log) та [`raw/article_examples_summary.json`](raw/article_examples_summary.json) — повні 4-блокові траси всіх 5 груп прикладів зі статей (`--example all`);
* [`raw/cli_compile_trace_events_bms.log`](raw/cli_compile_trace_events_bms.log) — вивід компілятора `compile_kpol_bram_image.py --dump-concepts --trace-events`;
* [`raw/stdio_unix_pipe_bms.log`](raw/stdio_unix_pipe_bms.log) — потокова перевірка через UNIX-пайп `--stdio`;
* [`raw/pytest_debugger_272.log`](raw/pytest_debugger_272.log) — результати тестового пакета включно з 5 мутантами `M1..M5`.

### 3.1. Натурна сесія підключення дебагера до фізичної `PYNQ-Z1` (`pynq2`): `PRE-LOAD` $\to$ `POST-LOAD` $\to$ `POST-RUN`

Джерело: [`raw/pynq2_live_debugger_session.log`](raw/pynq2_live_debugger_session.log), [`raw/pynq2_live_debugger_session.json`](raw/pynq2_live_debugger_session.json).

Перед підключенням дебагера з програмою BMS у BRAM фізичної плати `pynq2` (`0x40000000`, `HW_ID = 0x4B504D43 "KPMC"`) перебувала одноконцептна програма `Increase.kpol` після одного імпульсу (`Counter = 11`). Дебагер підключився до плати, зняв знімок `PRE-LOAD`, записав 4-концептну програму `BmsSafetyCascade`, перевірив 256 слів BRAM (`POST-LOAD`) і виконав 8 апаратних стимулів:

| Фаза сесії на `pynq2` | Активні концепти (`K / 64`) | Вільні слоти | Стан `W0` слотів `C00..C03` у BRAM кристала `Zynq-7020` | Апаратні лічильники `events / commits / rejects` | Контрольна сума `SHA-256` 1024-Б BRAM у ПЛІС |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **1. `PRE-LOAD` (до програмування BMS)** | **`1 / 64`** (`entry=[0]`) | `63` | `C00=11`, `C01=_`, `C02=_`, `C03=_` | `88 / 61 / 27` | `ef5e343eb743d5e4...` |
| **2. `POST-LOAD` (після внесення BMS)** | **`4 / 64`** (`entry=[0]`, `internal=[1,2]`, `leaf=[3]`) | `60` | `C00=0`, `C01=0`, `C02=2`, `C03=10` (`4` слоти змінено) | `88 / 61 / 27` (`0` побічних подій при завантаженні) | `de03442454424b5c...` (`256/256` слів readback OK) |
| **3. `POST-RUN` (після 8 подій у ПЛІС)** | **`4 / 64`** | `60` | **`C00=4, C01=4, C02=0, C03=0`** | `106 / 73 / 33` (**$\Delta = +18 / +12 / +6$**) | `3008529e017945aa...` (100% збіг із `KpolCascadeDebugger` та `C99`) |

### 3.2. Покрокова верифікація 5 груп прикладів зі статей та слайдів Автора

Джерело: [`raw/article_examples_all_traces.log`](raw/article_examples_all_traces.log), [`raw/article_examples_summary.json`](raw/article_examples_summary.json).

1. **Приклад 1 (`Increase` та `DecreaseFromOne`, профіль `KPOL-CME-1`):**
   * У `Increase` (`Counter = 10`, предикат `param < 20`): стимул `param = 5` дає `COMMIT` (`W0: 10 -> 11`); стимул `param = 25` відхиляється предикатом `::` (`REJECT_GUARD`, `W0 = 11`); пошкоджений вхід `_` (`valid = 0`) відхиляється шлюзом невизначеності (`REJECT_FAULT`, `W0 = 11`).
   * У `DecreaseFromOne` (`Counter = 1`, інваріант `Counter >= 0`): перший імпульс `param = 5` виконує `COMMIT` (`W0: 1 -> 0`). Другий імпульс `param = 5` проходить предикат `5 < 20 => True`, обчислює кандидат `W0' = 0 - 1 = -1`, але **блокується вентилем Великої Крапки `•` (`cand >= 0 && !ovf32 => False`, вердикт `REJECT_INVARIANT`)**, зберігаючи `W0 = 0`. Діагностика `diagnose_invariant_counterexample_z3` повертає `SAT_WITNESS_FOUND` (`witness_cur_state = 0`, `unsafe_candidate_w0 = -1`).
2. **Приклад 2 (`4-Concept Cascade`, профіль `KPOL-CME-2`):**
   * При зовнішньому стимулі `E0(param = 10)` (`10 < 50 => True`) за одне звернення відбувається 4-рівнева хвиля каскаду `C0 (depth 0, 10->11) -> C1 (depth 1, 0->1) -> C2 (depth 2, 2->1) -> C3 (depth 3, 0->1)` (`4` коміти).
   * При стимулі `E0(param = 100)` (`100 < 50 => False`) спрацьовує `REJECT_GUARD` на кореневому концепті `C0` (`depth 0`), що повністю блокує поширення хвилі на `C1..C3`.
   * На четвертому стимулі `E0(param = 10)`, коли `C2` вже дорівнює `0`, хвиля проходить `C0 (12->13)` та `C1 (2->3)`, але на `C2` (`depth 2`) зупиняється вердиктом `REJECT_INVARIANT` (`candidate = -1 < 0`), не зачіпаючи `C3`. Результат 100% збігається з RTL-симуляцією `kpol_bram_pipeline_axi.sv` у `Icarus Verilog` (`states = [13, 3, 0, 0]`, `events = 12`, `commits = 10`, `rejects = 2`).
3. **Приклад 3 (`BMS 4-Stage Safety Cascade with Sensor Fault '_'`, профіль `KPOL-CME-2`):**
   * Траса з 9 стимулів у [`raw/stdio_unix_pipe_bms.log`](raw/stdio_unix_pipe_bms.log) демонструє всі 4 типи вердиктів: фільтрацію штатного розбалансу `15 мВ` і завади `5500 мВ` (`REJECT_GUARD`), блокування пошкодженого кадру `isoUART` `_` (`REJECT_FAULT`, `fault_propagations = 1`), двоступеневу ескалацію аварії при `120 мВ` та `180 мВ` до розмикання контактора `Contactor_Interlock = 0` (`COMMIT` на глибинах `0..3`) та захист защіпки `Pack_Fault_Latch = 0` від від'ємного переповнення при `250 мВ` і `5000 мВ` (`REJECT_INVARIANT` на глибині `depth = 2`).
4. **Приклад 4 (`Author Native Counter Subset`, профіль `KPOL-AUTH`):**
   * Програма `Concept(Counter, 10, Lower=0, Upper=500); Concept(Mirror, 0, Lower=0, Upper=500); Counter • Assign(Mirror, Counter + 1)` транслюється пакетом `Engineering/sw/kpol-auth` у 5 слів 32-бітного байткоду `Do/Go` (`0x12000000, 0x30000001, 0x20000000, 0x11000001, 0x50000000`) та 1024-байтний образ маршрутизації `CME-RAW-1` (`C00 -> C01`), який покроково трасується в `KpolCascadeDebugger` (`Counter=25 -> Mirror=1`, `-5 -> REJECT_GUARD`, `_ -> REJECT_FAULT`).
5. **Приклад 5 (Академічні/слайдові приклади Автора: `If`, `Sum`, `Nod(120, 6) = 6`):**
   * **`If` (`trace_author_if_toggle_example`):** покроково демонструє переходи `_ -> ! -> ¬ -> !` при трьох імпульсах запису `Go If ←`, де правило анти-зациклення `RFC-001` (`self_suppress`) запобігає нескінченній генерації події від запису всередині власної підписки.
   * **`Sum` (`trace_author_sum_post_read_reset_example`):** демонструє накопичення `0 -> +10 -> 35` та двофазне читання `Go Sum →` із пост-адресним бар'єром Великої Крапки `→ • Sum = 0` (`RFC-013` / `RFC-017`): читання повертає `35` на шину, після чого підписка за `•` скидає `Sum = 0`.
   * **`Nod(120, 6) = 6` (`trace_author_euclid_nod_example` + `km_euclid_core.sv` у `Icarus Verilog`):** виконує рівно **`19` реактивних кроків віднімання** `a -= b` (`120 -> 114 -> 108 -> ... -> 12 -> 6`). На 20-му кроці оцінки (`a = 6, b = 6`) обидва предикати `a > b` та `b > a` стають `False`, реактивна хвиля природно згасає без жодного лічильника циклу `while`, і повертається результат **`6`**. Симуляція апаратного модуля `km_euclid_core.sv` у `Icarus Verilog 12.0` підтверджує ідентичний результат: `result = 6`, `iterations = 19`, `cycles = 58` (`19 * 3 + 1` тактів = `580 нс` @ `100 МГц`).

### 3.3. Підсумкова таблиця статусу прикладів зі статей та слайдів Автора

| Приклад програми зі статей / слайдів | Профіль / діалект | Апаратне ядро `CFG-P` / `CFG-P-HA` (`Zynq-7020 PL`) | Генератор `--emit-c99` + сертифікат `Z3 SMT` | Спеціалізований FSM `km_euclid_core.sv` (`iverilog`) | Статус відкритих RFC / межі чинності |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **1. `Increase` / `Decrease` (`Counter >= 0`)** | `KPOL-CME-1` | **Виконується** (`100%` bit-exact, `8` тактів/подію) | **Виконується** (`VERIFIED P1..P4`) | Не застосовується | Усі вимоги закриті (`#150`, `#153`, `#8`) |
| **2. `4-Concept Cascade` (`C0 -> C1 -> C2 -> C3`)** | `KPOL-CME-2` | **Виконується** (`CFG-P` і двобанковий `CFG-P-HA`) | **Виконується** (`VERIFIED P1..P4`, `WCET = 4` кроки) | Не застосовується | Усі вимоги закриті (`#184`, `#227`, `#253`) |
| **3. `BMS 4-Stage Safety Cascade` зі станом `_`** | `KPOL-CME-2` + `valid_mask` | **Виконується** на `pynq2` (валідна траса); біт `_` — у `ADR B7` | **Виконується** (`VERIFIED P1..P4`, включно з `P3` для `_`) | Не застосовується | `ADR B7` прийнято (`#185/#215`); арифметика над `_` — `RFC-017` п. 3 (`#186`) |
| **4. `Author Native Counter / Thermal Subset`** | Підмножина `KPOL-AUTH` | **Виконується** (`CME-RAW-1` + `Do/Go` VM `km_mcu_fpga_bridge.c`) | **Виконується** на згенерованих дескрипторах `CME-RAW-1` | Не застосовується | 12 точок невизначеності `U01..U12` заблоковані `fail-closed` (`#186`) |
| **5a. Слайдові `If` (`_ -> ! -> ¬`) та `Sum` (`→ • Sum = 0`)** | Розширена модель слайдів Автора | Довідковий трасувальник (потребує `•` на читання та біта `_` у `CME-RAW-2`) | Стан `_` реалізовано в `valid_mask`; `→ •` поза `CME-RAW-1` | Не застосовується | `RFC-013` та `RFC-017` п. 1–2 (статус `busy` і булеве `•`) |
| **5b. Алгоритм Евкліда `Nod(120, 6) = 6`** | Циклічна реактивна модель (слайд 3, DOU 36556) | Відхиляється статичним DAG-фільтром `P1` (захист `WCET`) | Відхиляється `P1_dag_lyapunov_acyclicity` (заборона циклів) | **Виконується** (`19` віднімань, `58` тактів = `580 нс`, результат `6`) | Суперечність `RFC-001` з циклами (DOU 36556 `Do [...] ↓ a~b ↑ a≠b`, `RFC-009/012`) |
| **5c. Ескізи `Factorial`, `Tachometer`, `Static(OpenBracket)`** | Незавершені слайдові ескізи Автора | **Не виконується** (`fail-closed` відмова `KPOL-AUTH-U01..U12`) | **Не виконується** (поза детермінованим профілем безпеки) | Не застосовується | Очікують відповідей Автора на відкриті `RFC-009, 015, 016–018` (`#186`) |

### 3.4. Результати мутантного тестування (`test_kpol_debugger_272.py`, `AGENTS.md §4.1`)

Джерело: [`Engineering/sw/tests/test_kpol_debugger_272.py`](../../../sw/tests/test_kpol_debugger_272.py), [`raw/pytest_debugger_272.log`](raw/pytest_debugger_272.log).

| Ідентифікатор мутанта | Суть внесеного дефекту в `KpolCascadeDebugger` / `MachineDebugConnection` | Як виявляється тестом | Статус |
| :--- | :--- | :--- | :---: |
| **`M1_debugger_invert_predicate`** | Інверсія результату оцінки предиката `_eval_predicate` (`not orig_eval(d, p)`) | Миттєва розбіжність траси дебагера з еталонним `ReferenceCmeSafetyEngine` на `Cascade4Concept` (`AssertionError: mismatch`). | **Killed** |
| **`M2_debugger_ignore_invariant_gate`** | Пропуск перевірки вентиля Великої Крапки `•` (`_eval_invariant_gate -> True`) при декременті з `0` | Дебагер помилково комітить `Counter = -1` замість `REJECT_INVARIANT` і падає при звірці з еталоном (`AssertionError: mismatch`). | **Killed** |
| **`M3_debugger_drop_cascade_subscriber`** | Втрата підписника `W3` (`_resolve_subscriber -> (None, False)`) | 4-концептний каскад BMS обривається на `depth = 0` (`1` крок замість `4`) і ловиться тестом (`AssertionError: step count mismatch`). | **Killed** |
| **`M4_debugger_mask_uncertainty_bit`** | Ігнорування `param_valid = False` (підміна невалідного кадру `_` на `param_valid = True`) | Замість `REJECT_FAULT` відбувається хибне обчислення над нулем; тест падає на розбіжності `fault_propagations` та стану. | **Killed** |
| **`M5_debugger_corrupt_preload_postload_diff`** | Повернення порожнього списку змін у `compute_pre_post_load_diff` між `PRE-LOAD` та `POST-LOAD` | Перевірка зміни 4 слотів під час програмування `Increase -> BMS` падає на `AssertionError`. | **Killed** |

---

## 4. Перевірка гіпотези / критеріїв приймання (Issue #272)

| Критерій | Очікувано | Отримано | Висновок |
| :--- | :--- | :--- | :--- |
| **1. 4-блоковий дебагер `kpol_debugger.py` та прапорці `--dump-concepts`, `--trace-events` у `compile_kpol_bram_image.py`** | Вивід коду, таблиці дескрипторів BRAM, 10-фазної траси каскаду та підсумкового `State Diff` | Реалізовано й перевірено на `KPOL-CME-1`, `KPOL-CME-2`, `KPOL-AUTH`; підтримує `--example <bms\|cascade\|increase\|decrease\|auth\|nod\|all>` | **Виконано** |
| **2. Потокове `STDIO` (`stdin` / `stdout` / `stderr`) у мові й рантаймі МК** | Прийом подій зі `stdin`, вивід `COMMIT` у `stdout` та `REJECT_*` у `stderr` через UNIX-пайп `--stdio` | Реалізовано директиви `# @stdin` / `# @stdout` та прапорець `--stdio` ([`raw/stdio_unix_pipe_bms.log`](raw/stdio_unix_pipe_bms.log)) | **Виконано** |
| **3. Підключення TUI-дебагера до машини (`sim` та фізичної `pynq2`) зі станом `PRE-LOAD` і `POST-LOAD`** | Відображення кількості активних концептів (`K / 64`) та diff слотів до і після програмування | Підтверджено на живій платі `pynq2` під `flock /tmp/km-bench.lock`: `PRE-LOAD: 1/64` (`Counter=11`) $\to$ `POST-LOAD: 4/64` (`BMS`) $\to$ `POST-RUN: [4,4,0,0]`, $\Delta = +18/+12/+6$ ([`raw/pynq2_live_debugger_session.log`](raw/pynq2_live_debugger_session.log)) | **Виконано** |
| **4. Верифікація 5 груп прикладів зі статей та `Nod(120, 6) = 6` проти `km_euclid_core.sv`** | 100% збіг дебагера з `ReferenceCmeSafetyEngine`, `C99`, `CFG-P` (`iverilog`) та `km_euclid_core.sv` (`19` ітерацій, `58` тактів, результат `6`) | Підтверджено в [`raw/article_examples_all_traces.log`](raw/article_examples_all_traces.log) та [`raw/article_examples_summary.json`](raw/article_examples_summary.json) | **Виконано** |
| **5. Негативні мутантні тести (`AGENTS.md §4.1`)** | Щонайменше 4 мутанти (`M1..M4`) детерміновано вбиваються | Усі 5 мутантів `M1..M5` у [`test_kpol_debugger_272.py`](../../../sw/tests/test_kpol_debugger_272.py) вбиті (`12 passed`) | **Виконано** |

---

## 5. Відтворення

```bash
# 1. Запуск усіх 5 показових прикладів зі статей (4 блоки для кожного прикладу)
python3 Engineering/sw/kpol-ref/kpol_debugger.py --example all

# 2. Запуск окремого прикладу (bms | cascade | increase | decrease | auth | nod)
python3 Engineering/sw/kpol-ref/kpol_debugger.py --example bms
python3 Engineering/sw/kpol-ref/kpol_debugger.py --example nod

# 3. Потокове тестування через стандартний UNIX-пайп (STDIO: stdin -> stdout / stderr)
printf "15\n5500\n_\n120\n49\n180\n250\n5000\n-10\n" | \
  python3 Engineering/sw/kpol-ref/kpol_debugger.py \
    --program Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol \
    --profile KPOL-CME-2 --stdio

# 4. Компіляція образу BRAM із одночасним виводом дескрипторів та покрокової траси
python3 Engineering/hw/scripts/compile_kpol_bram_image.py \
  --profile KPOL-CME-2 --dump-concepts \
  --trace-events "0:15,0:5500,0:invalid,0:120,0:180,0:250" \
  Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol \
  .pytest_cache/bms_debug_out.bin

# 5. Запуск повного тестового пакета дебагера (включно з мутантами M1..M5)
python3 -m pytest -v Engineering/sw/tests/test_kpol_debugger_272.py
```

---

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 1.0.0 | 2026-11-18 | Перша редакція звіту Issue #272: реалізовано 4-блоковий покроковий дебагер `kpol_debugger.py`, прапорці `--dump-concepts` і `--trace-events` у `compile_kpol_bram_image.py`, потоковий інтерфейс `STDIO` (`--stdio`), підключення TUI-дебагера до `PYNQ-Z1` (`pynq2`) зі знімками `PRE-LOAD` / `POST-LOAD` / `POST-RUN`, покрокову верифікацію 5 груп прикладів зі статей (включно з `Nod(120, 6) = 6` на `km_euclid_core.sv`) та мутантні тести `M1..M5`. |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| `BRAM` | Block RAM — блокова двопортова синхронна пам'ять кристала ПЛІС (`RAMB36E1`). |
| `CFG-P` | Конфігурація BRAM-конвеєра Машини Кузьміна (`kpol_bram_pipeline_axi.sv`, `HW_ID = 0x4B504D43`). |
| `CID` | Concept Identifier — індекс слота концепту (`0..63`) у таблиці `CME-RAW-1`. |
| `CME-RAW-1` | Чинний 16-байтний двійковий формат дескриптора концепту (`W0..W3`). |
| `DAG` | Directed Acyclic Graph — орієнтований ациклічний граф підписок між концептами. |
| `HIL` | Hardware-in-the-Loop — верифікація на реальному фізичному обладнанні (`PYNQ-Z1`). |
| `PRE-LOAD` / `POST-LOAD` | Знімки стану BRAM і лічильників машини безпосередньо до та після завантаження нової програми. |
| `STDIO` | Стандартні потоки введення-виведення (`stdin`, `stdout`, `stderr`), прив'язані до подій і комітів/відмов концептів. |
| `TUI` | Terminal User Interface — багатопанельний термінальний інтерфейс дебагера (`curses` / ASCII frame). |
| `WCET` | Worst-Case Execution Time — гарантована верхня межа часу виконання каскаду. |
| `Z3` | SMT-солвер (`QF_LIA` / `QF_BV`), використаний для формальної верифікації та пошуку контрприкладів інваріанта `•`. |
