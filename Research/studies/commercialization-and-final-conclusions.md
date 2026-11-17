# Підсумковий інженерно-комерційний висновок проєкту Машини Кузьміна та верифікація генератора детермінованого C99 (`--emit-c99` + Z3 Safety Certificate)

* **Версія:** 1.0.0
* **Дата:** 2026-11-17
* **Тип WP редакції NG:** Report / Analysis
* **Issue:** `Closes` [#270](https://github.com/nick-fedchik/kuzmin-machine/issues/270) (пов'язані базові артефакти: [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8), [#77](https://github.com/nick-fedchik/kuzmin-machine/issues/77), [#120](https://github.com/nick-fedchik/kuzmin-machine/issues/120), [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186), [#216](https://github.com/nick-fedchik/kuzmin-machine/issues/216), [#225](https://github.com/nick-fedchik/kuzmin-machine/issues/225), [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226), [#227](https://github.com/nick-fedchik/kuzmin-machine/issues/227), [#235](https://github.com/nick-fedchik/kuzmin-machine/issues/235), [#240](https://github.com/nick-fedchik/kuzmin-machine/issues/240), [#242](https://github.com/nick-fedchik/kuzmin-machine/issues/242), [#245](https://github.com/nick-fedchik/kuzmin-machine/issues/245), [#252](https://github.com/nick-fedchik/kuzmin-machine/issues/252), [#253](https://github.com/nick-fedchik/kuzmin-machine/issues/253), [#254](https://github.com/nick-fedchik/kuzmin-machine/issues/254), [#255](https://github.com/nick-fedchik/kuzmin-machine/issues/255), [#256](https://github.com/nick-fedchik/kuzmin-machine/issues/256)).
* **Виконавець:** GitHub Copilot CLI (Lead Engineer / Architect role); очікує незалежної міжродинної рецензії за правилом `AGENTS.md §2.5`.
* **Базовий коміт:** `6f1dc29` (`origin/main`).
* **Хост верифікації:** `Linux 7.0.0-42-generic x86_64` (`GCC 15.2.0`, `Python 3.14.4`, `pytest 9.0.2`, `z3-solver 5.4.1`, `Icarus Verilog 12.0`).
* **Фізичний стенд HIL (`pynq2`):** плата `Digilent PYNQ-Z1` (`xilinx@192.168.68.69`, двоядерний `ARM Cortex-A9 @ 650 МГц`, `gcc 11.2.0` + кристал `Xilinx Zynq-7020 XC7Z020-1CLG400C` @ `100.0 МГц`, активний конвеєр `CFG-P` `0x4B504D43` `"KPMC"`).
* **Первинні артефакти та сирі дані цього звіту:**
  * Генератор C99 та Z3-сертифікатів: [`Engineering/sw/kpol-ref/c99_emitter.py`](../../Engineering/sw/kpol-ref/c99_emitter.py), CLI [`Engineering/hw/scripts/compile_kpol_bram_image.py`](../../Engineering/hw/scripts/compile_kpol_bram_image.py);
  * Референсний BMS-пакет: [`bms_safety_cascade.kpol`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol), [`bms_safety_cascade.bin`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.bin) (SHA-256 `de034424...`), [`bms_safety_cascade_gen.c`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade_gen.c) (SHA-256 `35461b0a...`), [`bms_safety_z3_certificate.json`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_z3_certificate.json), [`bms_c99_hil_bench.c`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_c99_hil_bench.c), [`run_bms_c99_verification.py`](../../Engineering/validation/kpol-cme/c99-emitter-270/run_bms_c99_verification.py);
  * Сирі логи та JSON-звіти: [`x86_64_bms_c99_verification.json`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/x86_64_bms_c99_verification.json), [`x86_64_bms_c99_verification.log`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/x86_64_bms_c99_verification.log), [`iverilog_bms_cfg_p_trace.log`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/iverilog_bms_cfg_p_trace.log), [`pynq_cortex_a9_bms_c99_hil.json`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/pynq_cortex_a9_bms_c99_hil.json), [`pynq_cortex_a9_bms_c99_hil.log`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/pynq_cortex_a9_bms_c99_hil.log), [`pytest_c99_emitter_270.log`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/pytest_c99_emitter_270.log);
  * Автоматизований тестовий пакет із 4 негативними мутантами (`M1..M4`): [`Engineering/sw/tests/test_c99_emitter_270.py`](../../Engineering/sw/tests/test_c99_emitter_270.py).

---

## 1. Що не вдалося, межі доведеного та що закривається без жалю (`$0`)

Згідно з правилами науково-інженерної чесності (`AGENTS.md §3, §4.2, §4.7`) та [позицією щодо стандартів](../../Project/policies/standards-position.md), підсумковий звіт починається з чіткої фіксації того, що не підтвердилося, де лежать технічні межі створених прототипів і які первинні гіпотези проєкту закриваються як комерційно безперспективні (`$0`).

### 1.1. Технічні та процесні межі доведеного (`AGENTS.md §4.2, §4.7`)

1. **Рівень готовності та відсутність формальної сертифікації:**
   * Усі створені в репозиторії програмно-апаратні вузли (`CFG-P`, `CFG-P-HA`, компіляторні профілі `KPOL-CME-1`/`2`, генератор `--emit-c99 + Z3`, GPU-диспетчер `persistent_subscribers.cu`) є дослідницькими прототипами рівня **`TRL 3–4` за внутрішньою самооцінкою** ([`Project/assessments/trl/report.md`](../../Project/assessments/trl/report.md)).
   * Жоден компонент не проходив зовнішнього аудиту чи сертифікації на відповідність `ISO 26262` (`ASIL A–D`), `IEC 61508` (`SIL 1–4`), `DO-178C` / `DO-254` або `Automotive SPICE PAM 4.0/4.1`. Згадки `MISRA-C99`, `ISO 26262` та `ASPICE` у цьому документі визначають інженерні орієнтири архітектури доказів і цільові ринкові вимоги потенційних B2B-замовників, а не заяву про сертифіковану відповідність.
2. **Обмеження вимірювань C99 на `ARM Cortex-A9` у просторі користувача Linux:**
   * Компіляція та вимірювання часу виконання згенерованого C99-модуля BMS (`bms_safety_cascade_gen.c`) на фізичній платі `PYNQ-Z1` (`pynq2`, `ARM Cortex-A9 @ 650 МГц`) виконані у просторі користувача `Linux 6.6.10-xilinx` за допомогою стандартного процесорного таймера `clock()` на серії `N = 200 000` гарячих викликів у кеші L1 (`215.17 нс` на відсікання помилки датчика `param_valid = false`, `266.88 нс` на одиночне відхилення, `257.87 нс` на один крок концепту в 4-рівневому каскаді або `1 031.47 нс` на повний 4-рівневий каскад `C0 -> C1 -> C2 -> C3`). Цільові ядра безпеки автомобільної електроніки (`Infineon AURIX TC49x CSRM`, `ARM Cortex-R52` з TCM-пам'яттю без ОС) у поточному лабораторному стенді фізично відсутні; перенесення на `AURIX TriCore` потребує запуску згенерованого C99-коду у компіляторі `Tasking` / `HighTec GCC` на цільовому кристалі замовника.
3. **Вузька спеціалізація формату `CME-RAW-1` (`CFG-P` / `CFG-P-HA`):**
   * Поточний 16-байтний дескриптор `CME-RAW-1` підтримує лише 32-бітні знакові скаляри `Int32 >= 0`, один 32-бітний операнд `W1` на слот (що виключає одночасний літеральний поріг і крок `ADD/SUB >= 2`, `CME2-OPERAND-COLLISION`), `fan-out <= 1` (`W3 = subscriber_cid`) та строго ациклічні графи підписок (`DAG`). Проєкт розширеного 32-байтного дескриптора `CME-RAW-2` ([ADR B7](../../Engineering/decisions/cme-raw2-kpol-sys02.md), `#185`) прийнято лише на рівні архітектурного рішення без реалізації RTL `CFG-P2`.
4. **Спростований програмний міжплатний контур `UDP/GbE` (`#226`):**
   * У натурному міжплатному експерименті `PYNQ-Z1 -> GbE -> Jetson AGX Orin J501` ([звіт `EXP-GPU-01` Фази 1–2, 4](fpga-gpu-symbiosis/experiments/EXP-GPU-01/report-phase1-2-4-crossboard-egress.md), `#226`) програмний стек сокетів ядра Linux показав `p99.9 = 2 808.53 мкс` (`σ = 199.17 мкс`) при цільовому порозі `<= 15 мкс`, що за критерієм Поппера спростувало придатність стандартного `UDP/GbE` без апаратного прямого вводу (`GPIO 1.8V` / `PCIe GPUDirect RDMA`).

### 1.2. Що закривається без жалю (`$0` комерційної цінності)

На основі проведеного циклу досліджень і фальсифікаційних експериментів два початкові напрями проєкту визнаються комерційно безперспективними (`$0`) і закриваються без подальших витрат ресурсів:

| Закритий напрям | Доказова база репозиторію | Причина відсутності комерційної перспективи (`$0`) |
| :--- | :--- | :--- |
| **1. Мова `KPOL` (`KPOL-AUTH` [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186) та user-study [#120](https://github.com/nick-fedchik/kuzmin-machine/issues/120)) як самостійний продукт для програмістів** | [Звіт #155](author-semantics/kpol-syntax-155-report.md), [Звіт #201/#203](author-semantics/rfc-impact-and-q3-draft-report.md), [Пілот Q3 #216](author-semantics/q3-llm-pilot-216-report.md), [Фронтенд #219/#245](../../Engineering/validation/kpol-cme/kpol-auth-frontend-219/report.md) | **1)** Авторська семантика залишається неповною: `12` фундаментальних точок (`KPOL-AUTH-U01..U12`, включно з читанням `_` у `RFC-017` п. 3, роздільниками в `RFC-016`, роллю `Child` у `RFC-018`) заблоковані в режимі `fail-closed`.<br>**2)** Незалежний сліпий пілот `Q3` на ізольованих LLM-агентах (`#216`) виявив системні колізії читабельності й неоднозначності синтаксису (`Q3-DEF-01..04`, зокрема інверсію змісту `•` між `not` і послідовністю підписки).<br>**3)** На B2B-ринку вбудованих систем ніхто не купує нову пропрієтарну мову програмування замість `C99`/`Rust`/`SPARK Ada`/`Simulink`: інженерам потрібен верифікований C99-код або бітстрім, який безшовно вбудовується в існуючий конвеєр `GCC`/`Clang`/`Tasking`. |
| **2. «Універсальна не-фон-нейманівська заміна CPU» (загальноцільовий процесор МК)** | [Звіт МТ #77](turing-construction/report.md), [Порівняльний Baseline #254](comparative-baseline-254/report.md), [Багатоядерний звіт #255](../../Engineering/validation/kpol-cme/manycore-scaling-255/report.md) | **1)** На загальноцільових обчисленнях і циклах реактивна підпискова модель програє фон-нейманівському CPU на порядки, а спроба побудувати рекурсивні/циклічні графи підписок у багатоядерній мережі породжує апаратний взаємний дедлок черг (`MC4_cyclic_deadlock_witness` у `#255`).<br>**2)** Навіть у ПЛІС для малих вузлів ($K < 26$ правил) універсальний інтерпретатор дескрипторів `CFG-P` програє спеціалізованому регістрово-конфігурованому RTL за площею (`2 209` проти `3 351 SLICE_LUTX` при $K=4$ у `#254`) і затримкою (`1` такт проти `8` тактів). Цінність `CFG-P` виникає виключно як **детермінованого табличного фаєрвола безпеки** при $K \ge 26$ правилах і потребі гарячого оновлення без пересинтезу. |

---

## 2. Три реальні інженерні активи, побудовані під капотом проєкту

Попри закриття утопічних цілей («нова мова для світу» та «заміна CPU»), у ході жорсткої інженерної верифікації в репозиторії було фактично створено і натурно перевірено **три працездатні B2B-активи**:

```
+---------------------------------------------------------------------------------------------------+
|                        ТРИ ВЕРИФІКОВАНІ ІНЖЕНЕРНІ АКТИВИ ПРОЄКТУ МК                               |
+---------------------------------+---------------------------------+-------------------------------+
| АКТИВ 1: Апаратне ядро безпеки  | АКТИВ 2: Формально-метрологічний| АКТИВ 3: Гетерогенний GPU     |
| CFG-P / CFG-P-HA (Zynq-7020 PL) | конвеєр верифікації (SMT + HIL) | диспетчер (Jetson AGX Orin)   |
+---------------------------------+---------------------------------+-------------------------------+
| * F_max = 100.69 МГц (OpenXC7)  | * Z3 SMT + yosys-smtbmc індукція| * 1024 резидентні підписники  |
| * 8 тактів (80 нс), 0 джитера   |   до N=16 без assume (#227/#242)| * Декуплінг L2 (16 x 128 Б):  |
| * Двобанковий гарячий swap 16 Б | * Двобанковий доказ H1..H7 (#253|   прискорення 9.63..10.05x    |
|   (CRC-8) за 0 stall-тактів     | * Мутаційний гейт (AV-07, M1..6)| * Grouped-warp спеціалізація: |
| * 10 003 swaps / 40 011 подій   | * LogicTracer 0.5.0 (100 MS/s + |   163.8 нс ядро, p99.9 E2E    |
|   на PYNQ-Z1: 0 torn-read (#253)|   200 МГц blast-таймер сегментів|   1.93..2.04 мкс (#240, #256) |
+---------------------------------+---------------------------------+-------------------------------+
```

### 2.1. Актив 1: Двобанковий апаратний фаєрвол правил `CFG-P-HA` у Block RAM (`100.69 МГц`, `80 нс`, `0` `torn-read`)

* **Склад активу:** RTL-модулі [`km_concept_micro_engine.sv`](../../Engineering/hw/rtl/core/km_concept_micro_engine.sv), [`kpol_txn_gate_v2.sv`](../../Engineering/hw/rtl/core/kpol_txn_gate_v2.sv), [`km_autonomous_sequencer.sv`](../../Engineering/hw/rtl/core/km_autonomous_sequencer.sv), двобанкова обгортка [`km_concept_bram_dual_ha.sv`](../../Engineering/hw/rtl/core/km_concept_bram_dual_ha.sv) зі збалансованим 8-рівневим бінарним деревом пріоритетного кодера, шинний міст [`kpol_bram_pipeline_axi_ha.sv`](../../Engineering/hw/rtl/bus/kpol_bram_pipeline_axi_ha.sv) та інжектор 16-байтних пакетів правил з `CRC-8-ATM` [`rule_injector.py`](fpga-gpu-symbiosis/experiments/EXP-GPU-02/rule_injector.py).
* **Доведені інженерні параметри ([звіт `EXP-GPU-02` `1.0.1`](fpga-gpu-symbiosis/experiments/EXP-GPU-02/report-stage1-2-cfg-p-ha.md), [#252](https://github.com/nick-fedchik/kuzmin-machine/issues/252), [#253](https://github.com/nick-fedchik/kuzmin-machine/issues/253), [#254](https://github.com/nick-fedchik/kuzmin-machine/issues/254)):**
  1. Повний час оцінки події та перевірки інваріанта в PL становить рівно **`8` тактів (`80.0 нс` при `100.0 МГц`)** із нульовим внутрішньокристальним джитером і повною незалежністю від завантаження процесора ARM/Linux;
  2. Повністю відкритий маршрут синтезу та трасування `OpenXC7` (`Yosys` + `nextpnr-himbaechel` для `xc7z020clg400-1`) закриває таймінг на частоті **`F_max = 100.69 МГц` (`PASS at 100.00 MHz`, `WNS = +0.069 нс`, `5 718 SLICE_LUTX`, `2 RAMB36E1`)**;
  3. Поріг окупності площі Block RAM-конвеєра проти регістрово-конфігурованого RTL становить **$K^* = 26\text{ SLICE\_LUTX}$** ($K^*_{\text{FF}} = 10$ тригерів): при $K = 64$ правилах `CFG-P` економить понад `2.5x` логічних ресурсів ПЛІС (`#254`);
  4. На фізичному кристалі `Zynq-7020` (`pynq2`) під час натурного стрес-тесту виконано **`10 003` гарячих перемикань банків (`40 011` подій)** із результатом: `0` міжпортових колізій BRAM, `0` аномалій тривалості циклу (`last_seq_exec_cycles == 8`), `0` втрачених подій і `0` `torn-read` (розривів читання 128-бітного дескриптора).

### 2.2. Актив 2: Автоматизований конвеєр формальної верифікації (`Z3 SMT + мутанти + LogicTracer 0.5.0 HIL`)

* **Склад активу:** формальні SMT-моделі та індуктивні докази [`cme2_formal_n16_props.sv`](../../Engineering/validation/kpol-cme/cme2-formal-227/scripts/cme2_formal_n16_props.sv) (`#227/#242`), [`cfg_p_ha_formal_props.sv`](fpga-gpu-symbiosis/experiments/EXP-GPU-02/formal/cfg_p_ha_formal_props.sv) (`#252/#253`), [`manycore_formal_props.sv`](../../Engineering/validation/kpol-cme/manycore-scaling-255/scripts/manycore_formal_props.sv) (`#255`), генератор SMT-сертифікатів C99 [`c99_emitter.py`](../../Engineering/sw/kpol-ref/c99_emitter.py) (`#270`) та апаратний комплекс метрології `LOGICTRACER_PICO_0.5.0` (`100 MS/s` + `200 МГц` blast-таймер міток тригерів).
* **Доведені інженерні параметри:**
  1. Необмежена за часом композиційна математична індукція (`yosys-smtbmc -s z3 -i`, **`0` операторів `assume` у кроці індукції**) для властивостей Fail-Closed збереження пам'яті при відмові (`P1`), монотонного спадання рангу Ляпунова в ациклічних каскадах (`P2`) та точного 8-тактового часу транзакції (`P3`) на $N = 16$ концептах ([звіт #227/#242](../../Engineering/validation/kpol-cme/cme2-formal-227/report.md));
  2. Строгий гейт Поппера (`AGENTS.md §4.1`): кожна формальна властивість і кожен програмний тест супроводжуються інжекцією дефектних мутантів (`M1..M6`), де солвер `Z3` або тестовий раннер зобов'язаний побудувати конкретну контрприкладову трасу `.vcd` / `AssertionError`;
  3. Зовнішня фізична верифікація часових діаграм на пінах ПЛІС (`JA2_COMMIT`, `100.0..110.0 нс` імпульси при `100 MS/s`, точність сегментного таймера `5.0 нс`).

### 2.3. Актив 3: Резидентний 1024-підписниковий GPU-диспетчер на `NVIDIA Jetson AGX Orin` (`1.74..2.04 мкс`)

* **Склад активу:** CUDA-ядра [`persistent_subscribers.cu`](fpga-gpu-symbiosis/experiments/EXP-GPU-01/persistent_subscribers.cu) та [`heterogeneous_subscribers.cu`](fpga-gpu-symbiosis/experiments/EXP-GPU-03/heterogeneous_subscribers.cu), архітектурне рішення [ADR B6 v0.5.0](../../Engineering/decisions/b6-gpu-persistent-kernel-subscribers.md), результати [`EXP-GPU-01` Фаза 3–4](fpga-gpu-symbiosis/experiments/EXP-GPU-01/report-phase3-warp-scaling.md) (`#225/#235/#240`) та [`EXP-GPU-03`](fpga-gpu-symbiosis/experiments/EXP-GPU-03/report.md) (`#256`).
* **Доведені інженерні параметри:**
  1. Усунення накладних витрат `cudaLaunchKernel` (`10–50 мкс`) завдяки утриманню `32` спеціалізованих варпів (`1 024` підписники) резидентними на `16` мультипроцесорах SM (`Ampere SM 8.7`);
  2. Усунення когерентного шторму `L2 Read Snoop` через рознесення вхідної події у `16` індивідуальних 128-байтних кеш-ліній `ingress[blockIdx.x]`, що дало **`9.63..10.05x` прискорення** на `1 024` підписниках (`p99` знижено з `17.48 мкс` до **`1.74 мкс`**);
  3. Групування гетерогенних законів керування (`PID`, `Kalman`, `FIR`, `Envelope`) по окремих варпах (`grouped_warp`) повністю усуває штрафи warp divergence (`2.03x` прискорення над змішаним варпом, чистий час обчислення на GPU **`163.8 нс`** у профілі `MAXN`, наскрізна затримка `Host -> L2 -> SM -> Host` **`p99.9 = 1.93..2.04 мкс`**).

---

## 3. Три комерційні B2B-ніші для прикладних досліджень та впровадження на замовлення

На перетині трьох створених активів і реального болю індустрії функціональної безпеки виділяються **три комерційно життєздатні B2B-кейси**:

### 3.1. Кейс 1 (Automotive / `Infineon AURIX TC49x CSRM` / BMS `isoUART`): генератор детермінованого C99-автомата безпеки (`--emit-c99`) + Z3 Safety Certificate

* **Інженерна проблема клієнта (Tier-1 / OEM Battery Management Systems):**
  * Логіка аварійного відключення високовольтних контакторів батареї (`Cell -> Module -> Pack -> Contactor`) традиційно пишеться вручну на C у вигляді розгалужених вкладених `if-else` та `switch` на сотні рядків.
  * У рукописному C-коді виникають три хронічні проблеми при підготовці до аудиту `ISO 26262 ASIL C/D`: (1) ризик прихованих циклів зворотного зв'язку та нестабільного `WCET`; (2) комбінаторний вибух кількості ручних unit-тестів для покриття `MC/DC`; (3) **маскування несправності датчика нулем** — коли при обриві лінії балансування комірки або помилці `CRC` у кадрі `isoUART` драйвер повертає `0 mV`, і наївний `if (delta_mV > 50)` вважає стан батареї ідеальним замість переходу у `Fail-Closed`.
* **Наше інженерне рішення (`--emit-c99` + `--emit-z3-cert`, реалізовано в цьому PR #270):**
  1. Таблиця правил захисту компілюється одночасно у 1024-байтний образ BRAM (`bms_safety_cascade.bin`) і в **чистий, самодостатній MISRA-орієнтований C99-модуль** (`bms_safety_cascade_gen.c`) без `malloc`, без рекурсії та без динамічних циклів `while` (`WCET = O(K)` за один фіксований прохід топологічно відсортованого масиву `KM_SAFETY_TOPO_ORDER`);
  2. Структура стану `km_safety_ctx_t` містить явну 64-бітну маску визначеності `uint64_t valid_mask` (`1 = визначено`, `0 = стан невизначеності '_' / Sensor Fault`), а функція `km_safety_step_event(ctx, root_cid, param, param_valid)` на першому ж кроці перевіряє `(!param_valid) || (!(ctx->valid_mask & (1ULL << cid)))` і миттєво виконує `Fail-Closed` відхилення з інкрементом `fault_propagations++`, унеможливлюючи маскування обриву датчика `isoUART` нульовим значенням;
  3. Разом із C99-кодом автоматично генерується машинно-перевірний сертифікат `Z3 SMT` (`bms_safety_z3_certificate.json`), який формально доводить ациклічність (`P1`), збереження інваріантів для всіх $2^{32} \times 2^{32}$ комбінацій `(state, param)` (`P2`), неможливість коміту при `param_valid == false` (`P3`) і побітову тотожність C99-формул та RTL-специфікації `CFG-P` (`P4`).
* **Що вже доведено в репозиторії і що можна досліджувати на замовлення:**
  * Доведено компіляцію `gcc -std=c99 -O2 -Wall -Wextra -Werror -pedantic` (`0` попереджень), `100%` побітовий збіг між C99 (`x86_64` і `ARM Cortex-A9`), моделлю `CFG-P` та фізичним кристалом `Zynq-7020 PL` (`pynq2`), і час виконання `215..267 нс` на подію в кеші L1 на `Cortex-A9`.
  * *Предмет комерційного R&D на замовлення:* порт згенерованого C99-модуля в ізольоване ядро безпеки `Infineon AURIX TC49x CSRM` (`TriCore`), інтеграція з реальним драйвером трансивера `isoUART` (`TLE9012DQU` / `LTC6811`) та статичний аналіз `WCET` (`aiT` / `Bound-T`).

### 3.2. Кейс 2 (MilTech / Robotics `Jetson Orin + FPGA`): «Апаратний запобіжник для ШІ та автопілота (Hardware Safety Cage for AI/Linux)»

* **Інженерна проблема клієнта (автономні БПЛА, роботизовані платформи, наземні комплекси):**
  * Сучасні автопілоти й візуальні навігатори працюють на `NVIDIA Jetson Orin` під керуванням Linux і нейромереж (`YOLO`, `VLM`, `RL`-політики). Нейромережа може видати галюцинацію (команду за межами безпечного кута крену, тяги чи дозволеного сектора), а ядро Linux може зазнати непередбачуваної затримки планувальника або зависання драйвера.
  * Водночас межі безпечного конверта (Geofencing, ліміти висоти/тяги/струму) змінюються динамічно при зміні фази місії («Зліт» $\to$ «Крейсерський політ» $\to$ «Посадка»), тому жорстко зашитий у компаратори поріг не підходить.
* **Наше інженерне рішення (`CFG-P-HA` як Hardware Safety Cage між `Jetson Orin` та приводами):**
  1. Усі керуючі команди від `Jetson Orin` до силових ключів / сервоприводів проходять крізь апаратний шлюз `CFG-P-HA` у ПЛІС (`Zynq-7020` / `Artix-7`), який за **`80.0 нс` (`8` тактів @ `100 МГц`, `0` джитера)** перевіряє предикати діапазонів (`CME_PRED_RANGE`), порогові обмеження та каскадні інваріанти незалежно від стану ОС Linux;
  2. Якщо команда ШІ порушує поточний безпечний конверт, транзакційний шлюз `kpol_txn_gate_v2.sv` блокує її в залізі (`Fail-Closed` за `80 нс`, як фізично продемонстровано з силовим ключем `IRLZ44N` та приводом `N20` на стенді);
  3. При зміні фази місії супервізор оновлює параметри польотного конверта в тіньовому банку `CFG-P-HA` коротким **16-байтним пакетом із криптографічним/контрольним захистом `CRC-8`** (`rule_injector.py`, регістри `0x030..0x038`), і ПЛІС атомарно перемикає активний банк на межі такту `ST_IDLE` без жодного такту зупинки контуру захисту (`0` stall-тактів, `0` `torn-read`).
* **Що вже доведено в репозиторії і що можна досліджувати на замовлення:**
  * Доведено синтез і трасування `CFG-P-HA` на `100.69 МГц`, формальну безпеку перемикання в `Z3` (`H1..H7`) та безпомилкову роботу на `10 003` гарячих перемиканнях на фізичній `PYNQ-Z1` (`#252/#253`), а також високошвидкісну обробку `1 024` підписників на `Jetson AGX Orin` за `1.74..2.04 мкс` (`#235/#240/#256`).
  * *Предмет комерційного R&D на замовлення:* заміна спростованого `UDP/GbE` (`#226`) на прямий апаратний зв'язок `PMOD 3.3V <-> 1.8V J501 GPIO/SPI` через перетворювач рівнів або `PCIe GPUDirect RDMA` та інтеграція з польотним контролером (`MAVLink` / `DroneCAN`).

### 3.3. Кейс 3 (Вбудована метрологія та інженерна верифікація ПЛІС `HWE.3 / HWE.4`): накристальний чорний ящик `lt_capture.v` (`LogicTracer 0.5.0`)

* **Інженерна проблема клієнта (розробники FPGA/SoC для промислової автоматики та авіоніки):**
  * Під час інтеграційних випробувань (`ASPICE HWE.3 / HWE.4`) необхідно довести потактову поведінку внутрішніх кінцевих автоматів (`ST_IDLE..ST_EVAL_GATE`), стробів коміту/відмови та переходів банків пам'яті в реальному кремнії без виведення десятків сигналів на зовнішні піни PMOD (де вільних ніжок часто немає або шлейфи зайняті суміжними платами, як зафіксовано в Обмеженні 1 звіту `#253`).
* **Наше інженерне рішення:**
  * Інтеграція легкої накристальної IP-обгортки захоплення трас `lt_capture.v` екосистеми `LogicTracer 0.5.0` (з уніфікованим транспортом `pynq://` та експортом стандартних `.vcd`/`.json` артефактів із заголовками походження) безпосередньо всередину бітстріму `CFG-P-HA` поруч із зовнішнім контролем через `LOGICTRACER_PICO_0.5.0`.
* **Що вже доведено в репозиторії і що можна досліджувати на замовлення:**
  * Доведено натурне захоплення зовнішніх імпульсів `JA2_COMMIT` на частоті `100 MS/s` та `200 МГц` blast-таймінг сегментів (`#226`, `#230`, `#253`).
  * *Предмет комерційного R&D на замовлення:* вбудова бойового кільцевого буфера `lt_capture.v` з тригером на `reject_pulse_o` або `collision_detected_o` як «чорного ящика» відмов у промислових ПЛІС-проєктах.

---

## 4. Результати верифікації генератора `--emit-c99 + Z3` на референсному кейсі BMS (`x86_64` + `ARM Cortex-A9` + `Zynq-7020 PL`)

### 4.1. Специфікація 4-рівневого референсного каскаду захисту BMS (`BmsSafetyCascade`)

Референсна конфігурація [`Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol) моделює 4-рівневий ациклічний каскад аварійного захисту високовольтної батареї (`DAG: C0 -> C1 -> C2 -> C3`):

| Слот `CID` | Ім'я концепту | Початковий стан `W0` | Правило / Охоронець (`W1`, `pred_opcode`, `guard_flags`) | Дія (`action_opcode`) | Підписник `W3` | Фізичний зміст у BMS |
| :---: | :--- | :---: | :--- | :--- | :---: | :--- |
| **`CID 0`** | `Cell_Delta_mV` | `0` | `delta_mv >= 50 and delta_mv <= 5000`<br>(`RANGE [50, 5000]`, `W1 = 0x13880032`, `pred = 0x05`, `flags = 0x13`) | `INC` (`+1`, `0x01`) | `CID 1` | Лічильник підтверджених подій розбалансу комірки в діапазоні `50..5000 мВ` (шум `< 50 мВ` і збої `> 5000 мВ` відсікаються). |
| **`CID 1`** | `Module_Thermal_Guard` | `0` | `Cell_Delta_mV >= 1`<br>(`LT 1` з інверсією `INVERT`, `W1 = 1`, `pred = 0x04`, `flags = 0x1B`) | `INC` (`+1`, `0x01`) | `CID 2` | Каскадний ескалатор теплового/струмового захисту батарейного модуля. |
| **`CID 2`** | `Pack_Fault_Latch` | `2` | `Module_Thermal_Guard >= 1`<br>(`LT 1` з інверсією `INVERT`, `W1 = 1`, `pred = 0x04`, `flags = 0x1B`) | `DEC` (`-1`, `0x02`) | `CID 3` | Ресурс допуску пака до жорсткого блокування (`2 -> 1 -> 0`); при `0` спроба `0 - 1 = -1` блокується інваріантом `>= 0` (`Fail-Closed`). |
| **`CID 3`** | `Contactor_Interlock` | `10` | `not (Pack_Fault_Latch == 2)`<br>(`EQ 2` з інверсією `INVERT`, `W1 = 2`, `pred = 0x01`, `flags = 0x0B`) | `ASSIGN` (`:=`, `0x00`) | `0` (лист) | Керування силовим контактором: `10` — штатно замкнений, `1` — попередження, `0` — аварійне розмикання (Interlock Open). |

Компіляція командою:
```bash
python3 Engineering/hw/scripts/compile_kpol_bram_image.py --profile KPOL-CME-2 \
  --emit-c99 Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade_gen.c \
  --emit-z3-cert Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_z3_certificate.json \
  Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol \
  Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.bin
```
породжує:
1. 1024-байтний образ BRAM [`bms_safety_cascade.bin`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.bin) (`SHA-256: de03442454424b5cf64478506f118c13f095ae24ba58db8894583c43567ea3ee`);
2. Детермінований C99-модуль [`bms_safety_cascade_gen.c`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade_gen.c) (`SHA-256: 35461b0aa57298672be41684eb1ca978cf7fd4071cfba034a2ca693545e00cb9`);
3. Машинно-перевірний сертифікат `Z3 SMT` [`bms_safety_z3_certificate.json`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_z3_certificate.json) (`verdict: "VERIFIED"`, солвер `z3-solver 5.4.1`).

### 4.2. Результати формальної SMT-верифікації `Z3` (`bms_safety_z3_certificate.json`)

| Формальна властивість у `prove_c99_descriptor_safety_z3` | Область квантифікації у `z3-solver 5.4.1` | Статус `Z3` | Інженерний зміст доказу |
| :--- | :--- | :---: | :--- |
| **`P1_dag_lyapunov_acyclicity`** | `rank_0..rank_63 in Int [0..63]` для всіх активних ребер `W3` (`[0->1, 1->2, 2->3]`) | **`SAT_RANKING_FOUND`** (`passed: true`) | Існує строга функція Ляпунова `rank = {0: 0, 1: 1, 2: 2, 3: 3}` (`rank[src] < rank[dst]`); граф гарантовано ациклічний, топологічний порядок `[0, 1, 2, 3]`, `WCET <= 4` кроків. |
| **`P2_invariant_preservation_all_bv32`** | $\forall \text{cur\_state}, \text{ev\_param} \in \text{BitVec}(32)$ по всіх активних концептах `CID 0..3` | **`UNSAT`** (`passed: true`) | Не існує жодної 32-бітної комбінації стану та вхідного параметра, за якої C99-автомат зафіксував би від'ємний стан (`cand < 0`) або знакове переповнення `Int32`. |
| **`P3_no_commit_on_invalid_param_or_state`** | $\forall \text{cur\_state}, \text{ev\_param} \in \text{BitVec}(32), \text{param\_valid}, \text{concept\_valid} \in \text{Bool}$ | **`UNSAT`** (`passed: true`) | За `param_valid == false` (помилка `CRC` / обрив `isoUART`) або `valid_mask[cid] == 0` коміт і зміна стану математично неможливі, а `fault_propagations` гарантовано зростає на `+1`. |
| **`P4_c99_rtl_bitvec32_miter_equivalence`** | $\forall \text{cur\_state}, \text{ev\_param}, \text{operand} \in \text{BitVec}(32)$, $\text{pred\_op}, \text{action\_op}, \text{flags}, \text{haz\_lim} \in \text{BitVec}(8)$ | **`UNSAT`** (`passed: true`) | Повна 32-бітна побітова тотожність формул предикатів, дій, дводоповняльного переповнення, інваріантів та `self_suppress` між згенерованим C99-кодом та RTL `km_concept_micro_engine.sv` + `kpol_txn_gate_v2.sv`. |

### 4.3. Наскрізне порівняння виконання на `x86_64`, `ARM Cortex-A9` та `Zynq-7020 PL` (`pynq2`)

Первинні дані: [`x86_64_bms_c99_verification.json`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/x86_64_bms_c99_verification.json), [`iverilog_bms_cfg_p_trace.log`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/iverilog_bms_cfg_p_trace.log), [`pynq_cortex_a9_bms_c99_hil.json`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/pynq_cortex_a9_bms_c99_hil.json), [`pynq_cortex_a9_bms_c99_hil.log`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/pynq_cortex_a9_bms_c99_hil.log).

На всіх п'яти виконавцях подано одну й ту саму 8-подійну трасу BMS `EvCellDelta(delta_mv)` = `[15, 5500, 120, 49, 180, 250, 5000, -10]` та окрему трасу інжекції помилок датчика `isoUART` (`param_valid = false` при `0 мВ` і `120 мВ`, а також інвалідація `CID 2` у стан невизначеності `_`):

| Середовище виконання та клас доказу (`AGENTS.md §4.2`) | Кінцевий стан `[C0, C1, C2, C3]` (`hw_trace`) | Лічильники `events / commits / rejects` (`hw_trace`) | Захист від помилки `isoUART` (`fault_trace`: `commits / rejects / fault_propagations`) | Час виконання в кеші L1 (`N = 200 000` ітерацій) |
| :--- | :---: | :---: | :---: | :--- |
| **1. Python `kpol_reference.Interpreter` та `ReferenceCmeSafetyEngine` (`[software_model]`)** | `[4, 4, 0, 0]` | `18 / 12 / 6` | `6 / 3 / 3` (`0` маскувань) | — (еталонна специфікація) |
| **2. Згенерований C99 на хості `Linux x86_64` (`GCC 15.2.0 -std=c99 -O2 -Wall -Wextra -Werror -pedantic`, `[host_c99]`)** | `[4, 4, 0, 0]` | `18 / 12 / 6` | `6 / 3 / 3` (`0` маскувань) | Fault reject: **`5.54 нс`**;<br>Single reject: **`11.01 нс`**;<br>1 крок каскаду: **`7.58 нс`** (`30.33 нс` за 4 рівні) |
| **3. Потактова RTL-симуляція `kpol_bram_pipeline_axi.sv` (`Icarus Verilog 12.0`, `[rtl_simulation]`)** | `[4, 4, 0, 0]` | `18 / 12 / 6` | — (перевіряє RTL `CFG-P`) | `9` тактів (`90 нс`) на одиночне відхилення;<br>`32` такти (`320 нс`) на 4-рівневий каскад |
| **4. Згенерований C99 на фізичному ядрі `ARM Cortex-A9 @ 650 МГц` (`pynq2`, `gcc 11.2.0 -std=c99 -O2 -Wall -Wextra -Werror -pedantic`, `[physical_hil_ps]`)** | `[4, 4, 0, 0]` | `18 / 12 / 6` | `6 / 3 / 3` (`0` маскувань) | Fault reject: **`215.17 нс`** (~`140` тактів CPU);<br>Single reject: **`266.88 нс`** (~`173` такти CPU);<br>1 крок каскаду: **`257.87 нс`** (`1 031.47 нс` за 4 рівні) |
| **5. Фізичний кристал ПЛІС `Xilinx Zynq-7020 PL @ 100 МГц` (`pynq2`, `0x40000000`, `ID = 0x4B504D43 "KPMC"`, `[physical_hil_pl]`)** | `[4, 4, 0, 0]` | `18 / 12 / 6` | — (апаратний тракт `CFG-P`) | `8` тактів/концепт у кремнії PL (`80.0 нс` @ `100.0 МГц`, `0` джитера) |

### 4.4. Результати мутаційного тестування (`Engineering/sw/tests/test_c99_emitter_270.py`, `AGENTS.md §4.1`)

Первинний лог прогону: [`pytest_c99_emitter_270.log`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/pytest_c99_emitter_270.log) (`6 passed in 1.04s`).

| Ідентифікатор мутанта | Внесене пошкодження / дефект | Спостережувана реакція верифікатора | Статус |
| :--- | :--- | :--- | :---: |
| **`M1_c99_bypass_invariant`** | Вимкнення перевірки інваріанта невід'ємності та переповнення в C99 (`-DKM_MUTANT_M1_BYPASS_INVARIANT`) і в Z3-моделі (`bypass_invariant=True`) | На 3-му спрацьовуванні каскаду `Pack_Fault_Latch` переходить у `-1` замість блокування на `0`; тест падає з `AssertionError`, а `prove_c99_descriptor_safety_z3` відхиляє сертифікат за `P2` та `P4` (`verdict: "REJECTED"`). | **Killed** |
| **`M2_c99_mask_invalid_sensor`** | Ігнорування прапорця `ev_param_valid == false` та `valid_mask` у C99 (`-DKM_MUTANT_M2_MASK_INVALID_SENSOR`) і в Z3-моделі (`mask_invalid_sensor=True`) | При подачі битого кадру `isoUART` (`param=0, valid=False` та `param=120, valid=False`) мутант маскує помилку датчика (`fault_propagated=False`) або хибно запускає каскад; тест падає з `AssertionError`, а Z3 відхиляє `P3`. | **Killed** |
| **`M3_c99_wrong_topo_order`** | Інверсія топологічного порядку обходу `KM_SAFETY_TOPO_ORDER` з `[0, 1, 2, 3]` на `[3, 2, 1, 0]` (`-DKM_MUTANT_M3_WRONG_TOPO_ORDER`) | Однопрохідний безцикловий автомат виконує лише `C0` (`steps_executed=1` замість `4`) і губить каскад `C1 -> C2 -> C3`; тест миттєво ловить розбіжність із `ReferenceCmeSafetyEngine`. | **Killed** |
| **`M4_z3_cyclic_or_unsafe_descriptor`** | Подача у `prove_c99_descriptor_safety_z3` та `emit_c99_safety_module`: (а) 2-вузлового циклу `C0 -> C1 -> C0`, (б) самопетлі `C0 -> C0`, (в) дескриптора з вимкненим `INVARIANT_EN`, (г) підміни опкоду `GT -> >=` | `z3-solver` повертає `UNSAT` для рівнянь рангу Ляпунова (`P1`), знаходить контрприклад інваріанта (`P2`) та розбіжність мітера (`P4`); генератор C99 блокує емісію коду винятком `C99EmitterError("C99-Z3-REJECTED")`. | **Killed** |

---

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 1.0.0 | 2026-11-17 | Перша повна редакція підсумкового інженерно-комерційного висновку проєкту Машини Кузьміна та звіту верифікації генератора `--emit-c99 + Z3 Safety Certificate` на референсному кейсі BMS (`x86_64`, `ARM Cortex-A9`, `Zynq-7020 PL`, [#270](https://github.com/nick-fedchik/kuzmin-machine/issues/270)). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| **BMS** | Battery Management System, система керування та захисту акумуляторної батареї. |
| **BRAM** | Block RAM, синхронна блокова пам'ять кристала ПЛІС (`RAMB36E1` у Xilinx 7-Series). |
| **CFG-P / CFG-P-HA** | Однобанкова та двобанкова (High-Availability) конфігурації апаратного BRAM-конвеєра Машини Кузьміна. |
| **CME** | Concept Micro-Engine (`km_concept_micro_engine.sv`), обчислювальне ядро оцінки 16-байтного дескриптора концепту. |
| **CSRM** | Cyber Security / Safety Realtime Module в автомобільних мікроконтролерах `Infineon AURIX TC49x`. |
| **DAG** | Directed Acyclic Graph, орієнтований ациклічний граф підписок. |
| **HIL** | Hardware-in-the-Loop, випробування з фізичним апаратним забезпеченням у контурі. |
| **isoUART** | Ізольований диференціальний інтерфейс зв'язку між високовольтними модулями комірок BMS і центральним контролером. |
| **MISRA-C** | Набір правил безпечної розробки мовою C для відповідальних вбудованих систем. |
| **SMT / Z3** | Satisfiability Modulo Theories / солвер `Z3` для формального математичного доведення властивостей. |
| **WCET** | Worst-Case Execution Time, гарантована верхня межа часу виконання у найгіршому випадку. |
| **WP** | Work Product, робочий продукт проєкту з визначеним призначенням і походженням. |
