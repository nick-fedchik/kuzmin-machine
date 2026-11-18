# Звіт VMK-GO-274: Двомодовий емулятор Віртуальної Машини Кузьміна (`VMK`) та повноекранний TUI-дебагер на Go (`Engineering/sw/vmk-go`, SemVer `0.3.0`, Issues #274, #280)

* **Версія:** 1.1.1
* **Дата:** 2026-11-18
* **Тип WP редакції NG:** Report
* **Issue:** `Closes` [#274](https://github.com/nick-fedchik/kuzmin-machine/issues/274), оновлено в [#280](https://github.com/nick-fedchik/kuzmin-machine/issues/280). **PR:** [#275](https://github.com/nick-fedchik/kuzmin-machine/pull/275) у гілці `feat/274-vmk-go-emulator-and-tui-debugger`, оновлення повноекранного TUI `v0.3.0` у [PR #281](https://github.com/nick-fedchik/kuzmin-machine/pull/281) (гілка `feat/280-fullscreen-interactive-tui-debugger-v030`).
* **Виконавець:** GitHub Copilot CLI (Lead Engineer / Architect). **Рецензент:** `claude-sonnet-5.5` ([рецензія PR #275 на `c366224`](https://github.com/nick-fedchik/kuzmin-machine/pull/275#issuecomment-6975587372) — «Прийнято із зауваженнями», `N1..N6` закрито у версії `1.0.1`; [рецензія PR #281 на `c0208bc`](https://github.com/nick-fedchik/kuzmin-machine/pull/281#issuecomment-6980909750) — «Прийнято із зауваженнями», `N1..N5` закрито у версії `1.1.1`).
* **Коміт виконання:** `c366224485c8210784b1cba041832c24d7d666a9` (`origin/main`: `6616ab80dd196919980a6f1ba7f8c362a81bf525` для Issue #274); `c0208bcfaffd43af9d98382fc2d833a0f201d46b` (`origin/main`: `d556b35bc1cf2c885f6d13c3d018cb7e65d03dc0` для повноекранного TUI `v0.3.0` та мутантів `M1..M7` в Issue #280).
* **Хост верифікації:** `Linux 7.0.0-42-generic x86_64` (`go1.27.1 linux/amd64`, `GCC 15.2.0`, `Python 3.14.4`, `pytest 9.0.2`, `Icarus Verilog 12.0`).
* **Фізична плата HIL (`pynq2`, під `flock` `/tmp/km-bench.lock`):** `Digilent PYNQ-Z1` (`xilinx@192.168.68.69`, двоядерний `ARM Cortex-A9 @ 650 МГц` + кристал `Xilinx Zynq-7020 XC7Z020-1CLG400C` @ `100.0 МГц`, активний конвеєр `CFG-P` `HW_ID = 0x4B504D43` `"KPMC"`).
* **Критерії успіху (зафіксовано до виконання в Issues #274, #280 та командах власника):**
  1. Створення самодостатнього Go-модуля [`Engineering/sw/vmk-go/`](../../../sw/vmk-go/go.mod) (SemVer `0.3.0`, `go 1.22` у `go.mod`, нуль зовнішніх залежностей поза `std`) із двома режимами виконання: `--mode bram64` (`CME-RAW-1` / `CFG-P` / `CFG-P-HA`, `Bank 0 / Bank 1` з `CRC-8`, `FIFO 16`, підключення до `PYNQ-Z1`) та `--mode conceptual` (`RFC-001..018`: типи `?`, `Int32/U64`, `Float`, біт `_`, адресації `←`, `→`, `|`, `:`, пост-адресний бар'єр `•` за `RFC-013`, блокування `Busy` за `RFC-001`) і 6+ вбудованими прикладами (`if`, `sum`, `nod`, `factorial`, `tachometer`, `bms`, `increase`, `decrease`, `cascade`, `auth`, `all`);
  2. Життєвий цикл підключення до машини (`PRE-LOAD -> POST-LOAD -> RUNNING`) із підрахунком концептів до і після внесення програми (`PreLoadActiveConcepts / 64`, `PostLoadActiveConcepts / 64`, `Entry / Internal / Leaf / Free`, `ReadbackVerified: 256/256 words OK`, таблиця `Pre-Load vs Post-Load Diff`);
  3. Потоковий інтерфейс `STDIO` (`--stdio`, `--fail-on-reject`, прагми `# @stdin` / `# @stdout`), повноекранний інтерактивний TUI-дебагер у вікні термінала (`--tui`, `--tui-canvas`, `--render-fullscreen-tui`, [`internal/vmk/tui_fullscreen.go`](../../../sw/vmk-go/internal/vmk/tui_fullscreen.go)) та детермінований 4-панельний TUI-кадр (`--render-tui-frame`, [`internal/vmk/tui.go`](../../../sw/vmk-go/internal/vmk/tui.go));
  4. Натурний прогін скомпільованого Go-бінарника `vmk` проти фізичної плати `pynq2`, перехресна звірка з Python `kpol_debugger.py`, C99 (`--emit-c99`) та `Icarus Verilog` (`kpol_bram_pipeline_axi.sv` і `km_euclid_core.sv`), а також вбивство 7 мутантів Go-коду (`M1..M7`) у [`Engineering/sw/tests/test_vmk_go_274.py`](../../../sw/tests/test_vmk_go_274.py) (`test_go_code_mutants_m1_to_m7`, `5 passed`) та інтеграція `go test -v ./...` у [`.github/workflows/ci.yml`](../../../../.github/workflows/ci.yml);
  5. Повна проектна документація за SemVer 2.0.0: специфікація [`vmk-go-emulator-and-tui-debugger-0.1.0.md`](../../../specifications/sw/vmk-go-emulator-and-tui-debugger-0.1.0.md), цей звіт із сирими артефактами в [`raw/`](raw/) та оновлення реєстрів проєкту.

---

## 1. Що не вдалося і обмеження

1. **Межа апаратного формату `CME-RAW-1` (`CFG-P`) щодо концептуальних конструкцій `RFC-001..018`:**
   * Фізичний конвеєр `kpol_bram_pipeline_axi.sv` (`CFG-P`, 64 слоти по 16 байтів `W0..W3`) виконує ациклічні графові каскади (`DAG`, теорема Ляпунова `P1_dag_lyapunov_acyclicity` зі звіту [`#227`](../cme2-formal-227/report.md)) над знаковими 32-бітними цілими `Int32`.
   * Тому циклічні та рекурсивні приклади зі слайдів і статей Автора (`Nod(120, 6) = 6`, `Factorial(5) = 120`, пост-адресне скидання після читання `→ • Sum = 0`, T-тригер `? If _` та клас `Tachometer`) виконуються у концептуальному рушії Go VMK (`--mode conceptual`, [`internal/vmk/conceptual.go`](../../../sw/vmk-go/internal/vmk/conceptual.go)), а для `Nod(120, 6) = 6` додатково перехресно звіряються такт-у-такт із історичним RTL-ядром `km_euclid_core.sv` у `Icarus Verilog` (`19` віднімань, `58` тактів).
2. **Передача подій зі станом невизначеності `_` при роботі з фізичною `PYNQ-Z1` (`--target pynq2`):**
   * Оскільки регістр `REG_EVENT_PARAM (0x00C)` у чинному `CFG-P` (`CME-RAW-1`) приймає 32-бітне слово без окремого апаратного біта `state_valid` (який спроєктовано для 32-байтного слота `CME-RAW-2` в [`ADR B7`](../../../decisions/cme-raw2-kpol-sys02.md)), під час живої сесії `vmk --target pynq2` валідні стимули (`8` подій BMS) виконуються безпосередньо в кремнії `Zynq-7020 PL` ($\Delta\text{events} = +18$, $\Delta\text{commits} = +12$, $\Delta\text{rejects} = +6$, кінцеві стани `W0 = [4, 4, 0, 0]`), а подія з невалідним входом `_` (`param_valid = false`) відхиляється на рівні шлюзу визначеності `BRAM64Engine` (`REJECT_FAULT`, `fault_propagations = 1`).
3. **Відкриті питання авторської семантики (`Issue #186`) та розширені мікрокоди `PredUGT (0x07)` / `ActNOP (0x05)`:**
   * Поява навчально-концептуального режиму `--mode conceptual` у Go VMK не закриває 12 відкритих точок невизначеності `KPOL-AUTH-U01..U12` (`RFC-009, 015–018` у [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186)) для компілятора [`Engineering/sw/kpol-auth/`](../../../sw/kpol-auth/__init__.py) і не оголошує непідтверджені слайдові ескізи частиною апаратного профілю безпеки `KPOL-CME-2`.
   * У режимі `bram64` Go VMK додатково підтримує коди `PredUGT = 0x07` (`u32(param) > u32(operand)`) та `ActNOP = 0x05` (`W0' := W0`), тоді як у поточному RTL `km_concept_micro_engine.sv` і `kpol_debugger.py` реалізовано діапазони `pred_opcode = 0x00..0x06` та `action_opcode = 0x00..0x04` (коди `0x07` і `0x05` там відхиляються гілкою `default`).

---

## 2. Метод реалізації та верифікації

1. **Чиста модульна архітектура на Go (`std` only, `go 1.22`):**
   * У каталозі [`Engineering/sw/vmk-go/`](../../../sw/vmk-go/go.mod) створено точку входу [`cmd/vmk/main.go`](../../../sw/vmk-go/cmd/vmk/main.go) та внутрішній пакет `internal/vmk` із 7 модулів: [`version.go`](../../../sw/vmk-go/internal/vmk/version.go), [`bram64.go`](../../../sw/vmk-go/internal/vmk/bram64.go), [`kpol_compiler.go`](../../../sw/vmk-go/internal/vmk/kpol_compiler.go), [`snapshot.go`](../../../sw/vmk-go/internal/vmk/snapshot.go), [`conceptual.go`](../../../sw/vmk-go/internal/vmk/conceptual.go), [`stdio.go`](../../../sw/vmk-go/internal/vmk/stdio.go), [`tui.go`](../../../sw/vmk-go/internal/vmk/tui.go) та [`examples.go`](../../../sw/vmk-go/internal/vmk/examples.go).
   * Детальний архітектурний контракт зафіксовано в специфікації [`Engineering/specifications/sw/vmk-go-emulator-and-tui-debugger-0.1.0.md`](../../../specifications/sw/vmk-go-emulator-and-tui-debugger-0.1.0.md) (`1.0.0`).
2. **Чотирирівнева перехресна звірка з незалежними еталонами (`AGENTS.md §4.3`, `N5`):**
   * Очікування для режиму `bram64` у [`test_vmk_go_274.py`](../../../sw/tests/test_vmk_go_274.py) беруться не з виходу самої Go-реалізації, а з чотирьох незалежних еталонів: (а) Python-компілятора `kpol_reference.py` (`compile_concept_microcode_bram_image`, побітовий збіг 1024-байтного образу `SHA-256 = de03442454424b5c...`) і `ReferenceCmeSafetyEngine`; (б) покрокового трасувальника `KpolCascadeDebugger` (збіг усіх 19 кроків, вердиктів і станів `[4, 4, 0, 0]`); (в) скомпільованого `gcc -std=c99 -O2` C99-модуля безпеки (`emit_c99_safety_module`); (г) RTL-симуляції `kpol_bram_pipeline_axi.sv` та `km_euclid_core.sv` у `Icarus Verilog 12.0`.
   * **Походження початкового стану `PRE-LOAD` у `--target sim` проти `--target pynq2` (`N3`, `N4`, `N6`):**
     - На фізичній платі `PYNQ-Z1` (`--target pynq2`, записані HIL-артефакти [`raw/pynq2_live_vmk_session.log`](raw/pynq2_live_vmk_session.log) та `.json`, не повторювані офлайн-рецензентом без доступу до стенда) знімок `PRE-LOAD` вичитується безпосередньо з апаратної BRAM кристала `Zynq-7020` через MMIO `0x40000000` (`256` слів).
     - У локальному симуляторі (`--target sim`) для вбудованих прикладів `PRE-LOAD` формується детерміновано: у концептуальних прикладах (`if`, `sum`, `nod`, `factorial`, `tachometer`) до завантаження користувацьких концептів у VMK присутні `3 / 64` вбудовані віртуальні потоки (`STDIN`, `STDOUT`, `STDERR`); у прикладі `--example bms` (зокрема при рендері `--render-fullscreen-tui` у [`raw/vmk_fullscreen_tui_280.log`](raw/vmk_fullscreen_tui_280.log)) симулятор навмисно передініціалізується образом 1-концептної програми `Increase.kpol` із початковим станом `state Counter: Int32 = 10` (`Pre-load: 1 / 64`, тому в інспекторі `C00` у `sim` відображається `Pre-Load W0: 10 -> Post-Load W0: 0`, на відміну від `Pre-Load W0: 11` на фізичній `pynq2`, де перед BMS у ПЛІС було виконано один імпульс `10 -> 11`); у прикладах `increase`, `decrease`, `cascade`, `auth` симулятор стартує з нульової BRAM (`Pre-load: 0 / 64`). При запуску дескрипторних прикладів (`bms`, `cascade`, `increase`, `decrease`, `auth`) із `--mode conceptual` (зокрема з `--stdio`) вони виконуються на дескрипторному трасувальнику з позначкою `Mode: conceptual (descriptor-backed)`.
3. **Мутаційний контроль Go-коду (`AGENTS.md §4.1`):**
   * У [`Engineering/sw/tests/test_vmk_go_274.py`](../../../sw/tests/test_vmk_go_274.py) (`test_go_code_mutants_m1_to_m7`) реалізовано 7 мутантів Go-коду (`M1..M7`), кожен із яких копіює дерево `Engineering/sw/vmk-go` в ізольований каталог `.pytest_cache`, вносить точкову синтаксично коректну мутацію в `.go`-файл і перевіряє, що `go test ./...` завершується з ненульовим кодом.

---

## 3. Результати верифікації

Усі первинні сирі артефакти збережено в [`raw/`](raw/) із заголовками походження (`# cmd:`, `# timestamp:`, `# git_commit:`, `# host:`):
* [`raw/pynq2_live_vmk_session.log`](raw/pynq2_live_vmk_session.log) та [`raw/pynq2_live_vmk_session.json`](raw/pynq2_live_vmk_session.json) — живий прогін скомпільованого Go-бінарника `vmk` проти фізичної плати `pynq2` (`xilinx@192.168.68.69`);
* [`raw/vmk_examples_all_traces.log`](raw/vmk_examples_all_traces.log) та [`raw/vmk_examples_all_summary.json`](raw/vmk_examples_all_summary.json) — повні траси та TUI-кадри всіх 10 вбудованих прикладів (`vmk --example all`);
* [`raw/vmk_stdio_bms_session.log`](raw/vmk_stdio_bms_session.log) — потокова перевірка `STDIO` (`--stdio --fail-on-reject`) у режимах `bram64` і `conceptual`;
* [`raw/go_test_vmk_274.log`](raw/go_test_vmk_274.log) та [`raw/pytest_vmk_go_274.log`](raw/pytest_vmk_go_274.log) — незмінні сирі логи первинного прогону Issue #274 (`c366224485c8210784b1cba041832c24d7d666a9`, мутанти `M1..M5`);
* [`raw/vmk_fullscreen_tui_280.log`](raw/vmk_fullscreen_tui_280.log), [`raw/go_test_vmk_280.log`](raw/go_test_vmk_280.log) та [`raw/pytest_vmk_go_280.log`](raw/pytest_vmk_go_280.log) — сирі логи Issue #280 (`c0208bcfaffd43af9d98382fc2d833a0f201d46b`): інтерактивна сесія повноекранного TUI-дебагера `VMK v0.3.0` (`--render-fullscreen-tui` та `--tui-canvas` з покроковим мікро-хопом хвилі `C00 -> C01 -> C02 -> C03`, ручним створенням подій `[e]`, інжекцією `_` `[f]`, редактором стану `[m]` та таблицею `Pre-Load vs Post-Load Diff` `[d]`), вивід `go test -v ./...` (включно з `TestFullScreenTUIDebuggerBRAM64AndConceptual`) та вивід `pytest -v Engineering/sw/tests/test_vmk_go_274.py` (`5 passed`, убито всі 7 мутантів `M1..M7`).

### 3.1. Натурний сеанс Go `vmk` проти фізичної плати `PYNQ-Z1` (`pynq2`): `PRE-LOAD` $\to$ `POST-LOAD` $\to$ `POST-RUN`

Джерело: [`raw/pynq2_live_vmk_session.log`](raw/pynq2_live_vmk_session.log), [`raw/pynq2_live_vmk_session.json`](raw/pynq2_live_vmk_session.json).

Перед запуском BMS у BRAM фізичної плати `pynq2` (`0x40000000`, `HW_ID = 0x4B504D43 "KPMC"`) перебував образ одноконцептної програми `Increase.kpol` зі станом `Counter = 11`. Скомпільований Go-бінарник `vmk` під міжпроцесним блокуванням `/tmp/km-bench.lock` підключився до `pynq2`, зняв знімок `PRE-LOAD`, запрограмував 256 слів `BmsSafetyCascade`, верифікував `POST-LOAD` readback і виконав серію стимулів:

| Фаза сесії Go `vmk` на `pynq2` | Активні концепти (`K / 64`) | Розподіл слотів (`Entry / Internal / Leaf / Free`) | Стан `W0` слотів `C00..C03` у BRAM `Zynq-7020` | Апаратні лічильники `events / commits / rejects / dropped` | Контрольна сума `SHA-256` 1024-Б BRAM |
| :--- | :---: | :--- | :---: | :---: | :--- |
| **1. `PRE-LOAD` (до програмування BMS)** | **`1 / 64`** | `entry=[0]`, `internal=[]`, `leaf=[]`, `free=63` | `C00=11`, `C01=_`, `C02=_`, `C03=_` | `112 / 78 / 34 / 0` | `ef5e343eb743d5e4...` |
| **2. `POST-LOAD` (після внесення BMS)** | **`4 / 64`** | `entry=[0]`, `internal=[1, 2]`, `leaf=[3]`, `free=60` | `C00=0`, `C01=0`, `C02=2`, `C03=10` (`Changed on load = 4`) | `112 / 78 / 34 / 0` (`0` побічних подій) | `de03442454424b5c...` (`256/256 words OK`) |
| **3. `POST-RUN` (після 8 валідних стимулів у ПЛІС)** | **`4 / 64`** | `entry=[0]`, `internal=[1, 2]`, `leaf=[3]`, `free=60` | **`C00=4, C01=4, C02=0, C03=0`** | `130 / 90 / 40 / 0` (**$\Delta = +18 / +12 / +6 / +0$**) | `3008529e017945aa...` (`100%` збіг із Go `BRAM64Engine`, Python і C99) |

Після завершення сесії перевірено, що штатний `/lib/firmware/pipeline.bin` на `pynq1` та `pynq2` залишається активним і тест `pytest Engineering/hw/tests/test_kpol_bram_cascade_hil.py` проходить (`2 passed`).

### 3.2. Результати виконання вбудованих прикладів у Go VMK (`--example all`)

Джерело: [`raw/vmk_examples_all_traces.log`](raw/vmk_examples_all_traces.log), [`raw/vmk_examples_all_summary.json`](raw/vmk_examples_all_summary.json).

| Приклад (`--example`) | Режим VMK (`--mode`) | Вхідні стимули / команди | Кількість кроків траси / подій | Ключовий спостережуваний результат і перевірений інваріант |
| :--- | :---: | :--- | :---: | :--- |
| **`if`** (`IfToggle`) | `conceptual` | `write If 1` ($\times 3$) | `3` імпульси (`3` коміти) | Траєкторія станів **`_ -> ! -> ¬ -> !`**; прапорець `Busy` за `RFC-001` блокує самозбудження від запису всередині власної підписки (`SUPPRESSED_SELF`). |
| **`sum`** (`SumPostReadReset`) | `conceptual` | `write Sum 10`, `write Sum 25`, `read Sum` | `3` події (`3` коміти) | Накопичення `0 -> 10 -> 35`; при `read Sum` шина читання та `STDOUT` отримують **`35`**, і **строго після цього** бар'єр `→ •` (`RFC-013`) скидає `Sum = 0`. |
| **`nod`** (`EuclidNod`) | `conceptual` | `call Nod 120 6` | **`19`** віднімань + `1` збіжність = `20` кроків | Реактивна хвиля `a -= b` (`120 -> 114 -> ... -> 6`) природно згасає при `a == b == 6`; результат **`6`** і `58` тактів (`19 * 3 + 1`) 100% збігаються з `km_euclid_core.sv` у `Icarus Verilog`. |
| **`factorial`** (`FactorialRecursive`) | `conceptual` | `call Factorial 5` | `9` кроків (`5` спусків + `4` множення) | На `n = 1` спрацьовує масив вибору `[ 0 1 ] { Factorial = 1 Exit }`, після чого зворотний хід обчислює `1 * 2 * 3 * 4 * 5 =` **`120`**. |
| **`tachometer`** (`TachometerClass`) | `conceptual` | `Tick` ($\times 3$), `_Tick(dt=1s)` | `7` кроків (`7` комітів) | Три імпульси колеса дають `Revolutions = 3`, `Distance = 6`; імпульс таймера `_Tick(1s)` обчислює **`Speed = 6`** і пост-адресно скидає `Revolutions = 0`. |
| **`bms`** (`BmsSafetyCascade`) | `bram64` | `15, 5500, _, 120, 180, 250` (`6` стимулів у демо) / `9` у `STDIO` | `14` кроків (демо) / `19` кроків (`STDIO`) | Демонструє всі вердикти: `REJECT_GUARD` (`15`, `5500`), `REJECT_FAULT` на `_`, 4-рівневий каскад `COMMIT` (`120`, `180` $\to$ `Contactor_Interlock = 0`) та `REJECT_INVARIANT` на `Pack_Fault_Latch = 0` (`cand = -1`). |
| **`increase` / `decrease`** | `bram64` | `5, 25, _` / `5, 5, 25` | `3` / `3` кроки | Профіль `KPOL-CME-1`: перевірка `COMMIT`, `REJECT_GUARD`, `REJECT_FAULT` (`_`) та блокування переходу `0 -> -1` вентилем Великої Крапки `•` (`REJECT_INVARIANT`). |
| **`cascade`** (`Cascade4Concept`) | `bram64` | `0 10`, `0 100`, `0 10`, `0 10` | `12` кроків (`10` комітів, `2` відмови) | Профіль `KPOL-CME-2`: 4-рівнева хвиля `C0->C1->C2->C3`, блокування на `C0` при `100 >= 50` та зупинка каскаду на `C2` (`depth = 2`) при `cand = -1`; кінцеві стани `[13, 3, 0, 0]`. |
| **`auth`** (`AuthCounterSubset`) | `bram64` | `Counter 25`, `Counter -5`, `Counter _` | `4` кроки (`2` коміти, `2` відмови) | Профіль `KPOL-AUTH`: емісія 5 слів байткоду `Do/Go` (`0x12000000..0x50000000`) та трасування каскаду `Counter -> Mirror`. |

### 3.3. Результати мутаційного тестування Go-коду (`M1..M7`, `AGENTS.md §4.1`)

Джерело: [`raw/pytest_vmk_go_280.log`](raw/pytest_vmk_go_280.log), [`raw/go_test_vmk_280.log`](raw/go_test_vmk_280.log), [`raw/pytest_vmk_go_274.log`](raw/pytest_vmk_go_274.log), [`Engineering/sw/tests/test_vmk_go_274.py`](../../../sw/tests/test_vmk_go_274.py).

| ID мутанта | Файл Go-модуля | Внесена мутація | Який тест у `vmk_test.go` ловить дефект | Статус |
| :--- | :--- | :--- | :--- | :---: |
| **`M1_go_invert_predicate`** | `internal/vmk/bram64.go` | Інверсія результату предиката `::`: `return assumpKnown && (!assumpTrue)` | `TestBRAM64PredicatesActionsInvariantsAndUncertainties` (відхиляє валідний стимул `param = 5 < 20`) | **KILLED** (`exit != 0`) |
| **`M2_go_bypass_invariant_gate`** | `internal/vmk/bram64.go` | Пропуск вентиля Великої Крапки `•` у `EvalInvariantGate`: `return true` | `TestBRAM64PredicatesActionsInvariantsAndUncertainties` та `TestBRAM64OverflowFIFO16AndDualBankCRC8` (допускає `W0 = -1` та переповнення `0x7FFFFFFF + 1`) | **KILLED** (`exit != 0`) |
| **`M3_go_ignore_uncertainty_bit`** | `internal/vmk/bram64.go` | Ігнорування стану невизначеності `_`: `isUncertaintyFault := false` | `TestBRAM64PredicatesActionsInvariantsAndUncertainties` (пропускає `param_valid = false` і неініціалізований концепт без `REJECT_FAULT`) | **KILLED** (`exit != 0`) |
| **`M4_go_skip_post_read_dot_reset`** | `internal/vmk/conceptual.go` | Пропуск пост-адресного скидання `→ • Sum = 0` у `ExecuteSumReadWithPostDotReset` | `TestConceptualModeAllSixExamples` (`post_read_state` залишається `35` замість `0`, порушуючи `RFC-013`) | **KILLED** (`exit != 0`) |
| **`M5_go_corrupt_pre_post_load_diff`** | `internal/vmk/snapshot.go` | Ігнорування зміни слів `W1/W2/W3` у `ComputePrePostLoadDiff`: `slotChanged := w0Changed` | `TestBMSSafetyCascadeAndPrePostLoadDiff` (не помічає заміну правила `W1/W2` при однаковому початковому `W0 = 42`) | **KILLED** (`exit != 0`) |
| **`M6_go_break_single_hop_subscriber_enqueue`** | `internal/vmk/bram64.go` | Пропуск постановки підписника `nextHop` у `StepSingleHop` (`if false && enqueuedCID != nil`) | `TestFullScreenTUIDebuggerBRAM64AndConceptual` (хвиля не перестрибує `C00 -> C01 -> C02 -> C03` при натисканні `n` / `Space`) | **KILLED** (`exit != 0`) |
| **`M7_go_break_modify_concept_state`** | `internal/vmk/bram64.go` | Ігнорування нового значення `newW0` у `ModifyConceptState` (`e.State[cid] = 0`) | `TestFullScreenTUIDebuggerBRAM64AndConceptual` (редактор стану `[m]` не встановлює введене значення `W0 = 77`) | **KILLED** (`exit != 0`) |

---

## 4. Таблиця перевірки критеріїв приймання Issue #274

| № | Критерій успіху з Issue #274 | Фактичний результат і доказ | Статус |
| :---: | :--- | :--- | :---: |
| 1 | Go-модуль `Engineering/sw/vmk-go/` (SemVer `0.1.0`, `go 1.22`, тільки `std`) із двома режимами `--mode bram64` та `--mode conceptual` і 6+ вбудованими прикладами | Створено [`Engineering/sw/vmk-go/`](../../../sw/vmk-go/go.mod) (`0` зовнішніх залежностей); `go test -v ./...` проходить за `0.017 с` ([`raw/go_test_vmk_274.log`](raw/go_test_vmk_274.log)); усі 10 вбудованих прикладів верифіковані ([`raw/vmk_examples_all_traces.log`](raw/vmk_examples_all_traces.log)). | **ВИКОНАНО** |
| 2 | Життєвий цикл `PRE-LOAD -> POST-LOAD -> RUNNING`, підрахунок активних концептів та послотний `Pre-Load vs Post-Load Diff` | Перевірено в симуляції та на фізичній платі `pynq2` (`1 / 64` $\to$ `4 / 64` активних концептів, `256/256 words OK`, [`raw/pynq2_live_vmk_session.log`](raw/pynq2_live_vmk_session.log)); при недосяжній цілі повертається `VMK-TARGET-IO:` з кодом `2`. | **ВИКОНАНО** |
| 3 | Потоковий інтерфейс `STDIO` (`--stdio`, `--fail-on-reject`, `# @stdin` / `# @stdout`) та 4-панельний TUI (`--tui`, `--render-tui-frame`) | Перевірено маршрутизацію `COMMIT`/`READ` у `stdout` та `REJECT_*` у `stderr` з кодом виходу `1` при `--fail-on-reject` ([`raw/vmk_stdio_bms_session.log`](raw/vmk_stdio_bms_session.log)) і рендер 4 панелей TUI. | **ВИКОНАНО** |
| 4 | Перехресна звірка з Python, C99, `iverilog` RTL, живим `pynq2`, 7 мутантів `M1..M7` та оновлення `.github/workflows/ci.yml` | Пакети [`test_vmk_go_274.py`](../../../sw/tests/test_vmk_go_274.py) (`5 passed`, убито `M1..M7`, [`raw/pytest_vmk_go_280.log`](raw/pytest_vmk_go_280.log), [`raw/pytest_vmk_go_274.log`](raw/pytest_vmk_go_274.log)) і [`test_kpol_bram_cascade_hil.py`](../../../hw/tests/test_kpol_bram_cascade_hil.py) (`2 passed`) проходять; `.github/workflows/ci.yml` оновлено. | **ВИКОНАНО** |
| 5 | Повна проектна документація та реєстри за SemVer 2.0.0 | Створено специфікацію [`vmk-go-emulator-and-tui-debugger-0.1.0.md`](../../../specifications/sw/vmk-go-emulator-and-tui-debugger-0.1.0.md) (`1.2.0`), цей звіт (`1.1.1`) та оновлено реєстри проєкту й `wp-index.json`. | **ВИКОНАНО** |

---

## 5. Команди для незалежного відтворення

```bash
# 1. Модульні тести Go VMK (виконуються < 0.1 с офлайн без зовнішніх залежностей)
(cd Engineering/sw/vmk-go && go test -v ./...)

# 2. Запуск усіх 10 вбудованих прикладів (Conceptual + BRAM64)
(cd Engineering/sw/vmk-go && go run ./cmd/vmk --example all)

# 3. Потоковий режим STDIO та 4-панельний TUI-кадр для каскаду захисту BMS
printf "Cell_Delta_mV 15\nCell_Delta_mV _\nCell_Delta_mV 120\nCell_Delta_mV 180\nCell_Delta_mV 250\n" | \
  (cd Engineering/sw/vmk-go && go run ./cmd/vmk --mode bram64 --example bms --stdio --render-tui-frame)

# 4. Повний інтеграційний та мутаційний набір pytest (Python + C99 + iverilog + 7 мутантів M1..M7)
python3 -m pytest -v Engineering/sw/tests/test_vmk_go_274.py

# 5. Структурні перевірки посилань та індексу Work Products
python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
```

---

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 1.1.1 | 2026-11-18 | За рецензією PR #281 (`claude-sonnet-5.5`, `N1..N5`): усунено зайвий порожній рядок наприкінці `.gitignore` та `test_vmk_go_274.py` (`N1`); додано SHA `c0208bcfaffd43af9d98382fc2d833a0f201d46b` у шапку звіту та `vmk_fullscreen_tui_280.log` (`N2, N4`); узгоджено назву тесту `test_go_code_mutants_m1_to_m7` і кількість мутантів `M1..M7` (`5 passed`) по всьому тексту звіту (`N3`); записано нові сирі логи [`raw/go_test_vmk_280.log`](raw/go_test_vmk_280.log) та [`raw/pytest_vmk_go_280.log`](raw/pytest_vmk_go_280.log) без модифікації `*_274.log` (`N4`); пояснено `Pre-Load W0: 10 -> Post-Load W0: 0` для `C00` у симуляторі (`N5`). |
| 1.1.0 | 2026-11-18 | #280: додано повноекранний інтерактивний TUI-дебагер `VMK v0.3.0` (`internal/vmk/tui_fullscreen.go`, `--tui`, `--tui-canvas`, `--render-fullscreen-tui`), сирий лог сесії [`raw/vmk_fullscreen_tui_280.log`](raw/vmk_fullscreen_tui_280.log) та мутанти `M6..M7` на `StepSingleHop` і `ModifyConceptState`. |
| 1.0.1 | 2026-11-18 | За рецензією PR #275 (`claude-sonnet-5.5`, `N1..N6`): виконано `gofmt -w`, усунено trailing whitespace, додано підтримку всіх 10 прикладів у `--mode conceptual --stdio` (`conceptual (descriptor-backed)`), роз'яснено походження станів `PRE-LOAD` у `sim` (`3/64`, `1/64`, `0/64`) проти фізичної `pynq2`, незалежні еталони `kpol_reference.py`/`C99`/`iverilog` та оновлено `# git_commit:` у `raw/*.log` на `c366224485c8210784b1cba041832c24d7d666a9`. |
| 1.0.0 | 2026-11-18 | Первинний випуск звіту верифікації двомодового емулятора VMK та 4-панельного TUI-дебагера на Go (`Engineering/sw/vmk-go`, SemVer `0.1.0`), натурної сесії на `pynq2` та 5 мутантів `M1..M5` за Issue #274. |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| VMK | Virtual Machine of Kuzmin — програмний емулятор і TUI-дебагер Машини Кузьміна на мові Go (`Engineering/sw/vmk-go`). |
| CME-RAW-1 | 16-байтний (`W0..W3`) двійковий формат дескриптора концепту в 64-слотовій BRAM (`1024 B`). |
| CFG-P / CFG-P-HA | Однобанкова та двобанкова конфігурації апаратного BRAM-конвеєра МК у ПЛІС Zynq-7020. |
| TUI | Text-based User Interface — 4-панельний текстовий інтерфейс налагодження. |
| STDIO | Стандартні потоки вводу/виводу (`stdin`, `stdout`, `stderr`). |
| HIL | Hardware-in-the-Loop — верифікація за участю фізичної плати `PYNQ-Z1`. |
