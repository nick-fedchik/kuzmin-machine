# Підсумковий інженерно-комерційний аналіз проєкту Машини Кузьміна та верифікація генератора детермінованого C99 (`--emit-c99` + Z3 Safety Certificate)

* **Версія:** 1.0.1
* **Дата:** 2026-11-17
* **Тип WP редакції NG:** Report / Analysis
* **Issue:** `Closes` [#270](https://github.com/nick-fedchik/kuzmin-machine/issues/270) (пов'язані базові артефакти: [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8), [#77](https://github.com/nick-fedchik/kuzmin-machine/issues/77), [#120](https://github.com/nick-fedchik/kuzmin-machine/issues/120), [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186), [#216](https://github.com/nick-fedchik/kuzmin-machine/issues/216), [#225](https://github.com/nick-fedchik/kuzmin-machine/issues/225), [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226), [#227](https://github.com/nick-fedchik/kuzmin-machine/issues/227), [#235](https://github.com/nick-fedchik/kuzmin-machine/issues/235), [#240](https://github.com/nick-fedchik/kuzmin-machine/issues/240), [#242](https://github.com/nick-fedchik/kuzmin-machine/issues/242), [#245](https://github.com/nick-fedchik/kuzmin-machine/issues/245), [#252](https://github.com/nick-fedchik/kuzmin-machine/issues/252), [#253](https://github.com/nick-fedchik/kuzmin-machine/issues/253), [#254](https://github.com/nick-fedchik/kuzmin-machine/issues/254), [#255](https://github.com/nick-fedchik/kuzmin-machine/issues/255), [#256](https://github.com/nick-fedchik/kuzmin-machine/issues/256)).
* **Виконавець:** GitHub Copilot CLI (Lead Engineer / Architect role). **Рецензент `1.0.0`:** `claude-sonnet-5.5` у [PR #271](https://github.com/nick-fedchik/kuzmin-machine/pull/271#issuecomment-6957224311) (вердикт «Доопрацювати», знахідки `F-01..F-10` враховано у `1.0.1`).
* **Базовий коміт:** `9d28d3126e415d257e3c523fc295422fc9d70683` (`origin/main`: `6f1dc29`).
* **Хост верифікації:** `Linux 7.0.0-42-generic x86_64` (`GCC 15.2.0`, `Python 3.14.4`, `pytest 9.0.2`, `z3-solver 5.4.1`, `/usr/bin/z3 4.13.3`, `Icarus Verilog 12.0`).
* **Фізичний стенд HIL (`pynq2`, під `flock -w 600 /tmp/km-bench.lock`):** плата `Digilent PYNQ-Z1` (`xilinx@192.168.68.69`, двоядерний `ARM Cortex-A9 @ 650 МГц`, `gcc 11.2.0` + кристал `Xilinx Zynq-7020 XC7Z020-1CLG400C` @ `100.0 МГц`, активний конвеєр `CFG-P` `0x4B504D43` `"KPMC"`).
* **Окремий верифікаційний звіт WP (`Report`):** [`Engineering/validation/kpol-cme/c99-emitter-270/report.md`](../../Engineering/validation/kpol-cme/c99-emitter-270/report.md).
* **Первинні артефакти та сирі дані цього звіту:**
  * Генератор C99 та Z3-сертифікатів: [`Engineering/sw/kpol-ref/c99_emitter.py`](../../Engineering/sw/kpol-ref/c99_emitter.py), CLI [`Engineering/hw/scripts/compile_kpol_bram_image.py`](../../Engineering/hw/scripts/compile_kpol_bram_image.py);
  * Референсний BMS-пакет: [`bms_safety_cascade.kpol`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol), [`bms_safety_cascade.bin`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.bin) (SHA-256 `de03442454424b5cf64478506f118c13f095ae24ba58db8894583c43567ea3ee`), [`bms_safety_cascade_gen.c`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade_gen.c) (SHA-256 `108447cfb1fb623378ce92ace2189e8e46e0c21140b1a07b4fe8f8f9965c486f`), [`bms_safety_z3_certificate.json`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_z3_certificate.json) (SHA-256 `022ea96d25a9be09597e7ca823ec2960ec101e18a23f251876c00fc46ab2f1bc`), [`bms_c99_hil_bench.c`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_c99_hil_bench.c) (SHA-256 `1509a8a513f6528cdb78facead0c59e4495d4a2a0afcd7620cb8a275dfbdcb80`), [`run_bms_c99_verification.py`](../../Engineering/validation/kpol-cme/c99-emitter-270/run_bms_c99_verification.py);
  * Сирі логи та JSON-звіти: [`x86_64_bms_c99_verification.json`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/x86_64_bms_c99_verification.json), [`x86_64_bms_c99_verification.log`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/x86_64_bms_c99_verification.log), [`iverilog_bms_cfg_p_trace.log`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/iverilog_bms_cfg_p_trace.log), [`pynq_cortex_a9_bms_c99_hil.json`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/pynq_cortex_a9_bms_c99_hil.json), [`pynq_cortex_a9_bms_c99_hil.log`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/pynq_cortex_a9_bms_c99_hil.log), [`pytest_c99_emitter_270.log`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/pytest_c99_emitter_270.log);
  * Автоматизований тестовий пакет із негативними мутантами (`M1..M4`): [`Engineering/sw/tests/test_c99_emitter_270.py`](../../Engineering/sw/tests/test_c99_emitter_270.py).

---

## 1. Що не вдалося, межі доведеного та рекомендація власнику щодо закриття неперспективних напрямів

Згідно з правилами науково-інженерної чесності (`AGENTS.md §3, §4.2, §4.7`) та [позицією щодо стандартів](../../Project/policies/standards-position.md), підсумковий аналіз починається з фіксації того, що не підтвердилося, де лежать технічні межі створених прототипів і які первинні напрями рекомендується закрити за результатами проведених перевірок.

### 1.1. Технічні та процесні межі доведеного (`AGENTS.md §4.2, §4.7`)

1. **Рівень готовності (`TRL 3–4` за самооцінкою) та відсутність сертифікації й зовнішніх ринкових даних:**
   * Усі створені в репозиторії програмно-апаратні вузли (`CFG-P`, `CFG-P-HA`, компіляторні профілі `KPOL-CME-1`/`2`, генератор `--emit-c99 + Z3`, GPU-диспетчер `persistent_subscribers.cu`) є дослідницькими прототипами рівня **`TRL 3–4` за внутрішньою самооцінкою** ([`Project/assessments/trl/report.md`](../../Project/assessments/trl/report.md)), перевіреними диференційними, формальними та лабораторними HIL-тестами.
   * Жоден компонент не проходив зовнішнього аудиту чи сертифікації на відповідність `ISO 26262` (`ASIL A–D`), `IEC 61508` (`SIL 1–4`), `DO-178C` / `DO-254`, `MISRA-C:2012` або `Automotive SPICE PAM 4.0/4.1`. Також у проєкті не проводилися польові пілоти на реальних B2B-замовниках ([`application-hypotheses/report.md`](application-hypotheses/report.md)); оцінки нижче є інженерно-архітектурними висновками та рекомендаціями власнику проєкту.
2. **Межа формального SMT-доказу `prove_c99_descriptor_safety_z3` (`F-03`, `F-04`, `F-09`):**
   * Функція `prove_c99_descriptor_safety_z3` парсить фактично згенерований текст `c99_source` (витягуючи таблиці `KM_SAFETY_DESCRIPTORS[64]`, `KM_SAFETY_TOPO_ORDER`, напрямок індексації циклу, Fail-Closed шлюз `!ev_param_valid || !concept_valid`, оператори предикатів/дій, формулу `invariant_true` і умову `target_cid != cid`) та розв'язує у `Z3` (`QF_LIA` та `QF_BV` `BitVec(32)`) чотири властивості `P1..P4` проти вхідної специфікації `CFG-P`.
   * Це є **формальною SMT-верифікацією згенерованих C99-таблиць, топологічного розкладу та шаблонів переходів C99 проти моделі `CFG-P`**, а не формальною верифікацією об'єктного коду компілятора `GCC` (`CompCert` / `CBMC` + `yosys write_smt2`). Відповідність скомпільованого бінарного коду `GCC` та RTL `CFG-P` перевіряється диференційними тестами на трасах подій. Крім того, відхилення `subscriber_cid >= 64` на етапі компіляції (`C99-DAG-RANGE`) є навмисним статичним звуженням відносно RTL (`km_concept_micro_engine.sv` блокує такі ребра в рантаймі через `subscriber_target_valid_w`).
3. **Обмеження вимірювань C99 на `ARM Cortex-A9` у просторі користувача Linux (`F-07`):**
   * Компіляція та вимірювання часу виконання згенерованого C99-модуля BMS (`bms_safety_cascade_gen.c`) на фізичній платі `PYNQ-Z1` (`pynq2`, `ARM Cortex-A9 @ 650 МГц`) виконані у просторі користувача `Linux 6.6.10-xilinx` серією з `25` пакетів по `8 000` ітерацій (`200 000` викликів на метрику) через процесорний таймер `clock()`: `mean = 223.85 нс` (`p50 = 223.12 нс`, `p99 = 227.62 нс`, $\sigma = 1.45\text{ нс}$) на відсікання помилки датчика `param_valid = false`; `mean = 286.73 нс` (`p50 = 285.12 нс`, `p99 = 306.00 нс`, $\sigma = 4.53\text{ нс}$) на одиночне відхилення; `mean = 1 038.26 нс` (`p50 = 1 035.88 нс`, `p99 = 1 081.88 нс`, $\sigma = 17.06\text{ нс}$, або `259.56 нс` на один крок концепту) на повний 4-рівневий каскад `C0 -> C1 -> C2 -> C3`. Цільові ядра безпеки автомобільної електроніки (`Infineon AURIX TC49x CSRM`, `ARM Cortex-R52` без ОС) у поточному лабораторному стенді відсутні.
4. **Вузька спеціалізація формату `CME-RAW-1` (`CFG-P` / `CFG-P-HA`) та спростування програмного `UDP/GbE` (`#226`):**
   * 16-байтний дескриптор `CME-RAW-1` підтримує лише 32-бітні знакові скаляри `Int32 >= 0`, один 32-бітний операнд `W1` на слот (`CME2-OPERAND-COLLISION`), `fan-out <= 1` та строго ациклічні графи (`DAG`). Проєкт 32-байтного дескриптора `CME-RAW-2` ([ADR B7](../../Engineering/decisions/cme-raw2-kpol-sys02.md), `#185`) залишається без реалізації RTL `CFG-P2`.
   * У міжплатному експерименті `PYNQ-Z1 -> GbE -> Jetson AGX Orin J501` ([звіт `EXP-GPU-01` Фази 1–2, 4](fpga-gpu-symbiosis/experiments/EXP-GPU-01/report-phase1-2-4-crossboard-egress.md), `#226`) програмний стек сокетів ядра Linux показав `p99.9 = 2 808.53 мкс` (`σ = 199.17 мкс`) при цільовому порозі `<= 15 мкс`, що спростувало придатність стандартного `UDP/GbE` без апаратного прямого вводу (`GPIO 1.8V` / `PCIe GPUDirect RDMA`).

### 1.2. Напрями, рекомендовані власнику до закриття за інженерно-економічним критерієм

За попередньо зафіксованими критеріями перевірки гіпотез (повнота семантики без здогадів за `G1/N1`, відсутність структурних дефектів читабельності в `Q3` `#216` та виграш за затримкою/площею проти стандартного C99 і регістрового RTL у `#254`/`#255`) два початкові напрями мають негативний інженерно-економічний баланс (`очікувана пряма монетизація = $0`) і виносяться на рішення власника щодо припинення інвестицій:

| Напрям для рішення власника | Доказова база репозиторію | Інженерні причини рекомендації щодо закриття |
| :--- | :--- | :--- |
| **1. Мова `KPOL` (`KPOL-AUTH` [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186) та user-study [#120](https://github.com/nick-fedchik/kuzmin-machine/issues/120)) як самостійний комерційний продукт для програмістів** | [Звіт #155](author-semantics/kpol-syntax-155-report.md), [Звіт #201/#203](author-semantics/rfc-impact-and-q3-draft-report.md), [Пілот Q3 #216](author-semantics/q3-llm-pilot-216-report.md), [Фронтенд #219/#245](../../Engineering/validation/kpol-cme/kpol-auth-frontend-219/report.md) | **1)** Авторська семантика залишається неповною: `12` фундаментальних точок (`KPOL-AUTH-U01..U12`, включно з читанням `_` у `RFC-017` п. 3, роздільниками в `RFC-016`, роллю `Child` у `RFC-018`) заблоковані в режимі `fail-closed`.<br>**2)** Незалежний сліпий пілот `Q3` на ізольованих LLM-агентах (`#216`) виявив системні колізії читабельності й неоднозначності синтаксису (`Q3-DEF-01..04`, зокрема інверсію змісту `•` між `not` і послідовністю підписки).<br>**3)** Для інтеграції у вбудовані контури безпеки замовникам потрібен стандартний C99-код (`--emit-c99`) або бітстрім ПЛІС, сумісний із наявними компіляторами `GCC`/`Clang`/`Tasking`, а не нова пропрієтарна мова загального призначення. |
| **2. «Універсальна не-фон-нейманівська заміна CPU» (загальноцільовий процесор МК)** | [Звіт МТ #77](turing-construction/report.md), [Порівняльний Baseline #254](comparative-baseline-254/report.md), [Багатоядерний звіт #255](../../Engineering/validation/kpol-cme/manycore-scaling-255/report.md) | **1)** На послідовних обчисленнях і циклах реактивна підпискова модель поступається фон-нейманівському CPU (`9.52..25.34 нс` у C99 на `x86_64`), а спроба побудувати рекурсивні/циклічні графи підписок у багатоядерній мережі породжує взаємний дедлок черг (`MC4_cyclic_deadlock_witness` у `#255`).<br>**2)** Навіть у ПЛІС для малих вузлів ($K < 26$ правил) інтерпретатор дескрипторів `CFG-P` поступається спеціалізованому регістрово-конфігурованому RTL за площею (`2 209` проти `3 351 SLICE_LUTX` при $K=4$ у `#254`) і затримкою (`1` такт проти `8` тактів). Технічна перевага `CFG-P` виникає лише як **спеціалізованого табличного шлюзу безпеки** при $K \ge 26$ правилах і потребі гарячого оновлення без пересинтезу. |

---

## 2. Три інженерні прототипи-активи (`TRL 3–4` за самооцінкою), створені в репозиторії

У ході виконання інженерно-дослідницької програми в репозиторії побудовано та перевірено диференційними, формальними й лабораторними HIL-тестами **три технічні прототипи**:

```
+---------------------------------------------------------------------------------------------------+
|                   ТРИ ІНЖЕНЕРНІ ПРОТОТИПИ-АКТИВИ ПРОЄКТУ МК (TRL 3-4 ЗА САМООЦІНКОЮ)              |
+---------------------------------+---------------------------------+-------------------------------+
| АКТИВ 1: Апаратне ядро безпеки  | АКТИВ 2: Формально-метрологічний| АКТИВ 3: Гетерогенний GPU     |
| CFG-P / CFG-P-HA (Zynq-7020 PL) | конвеєр перевірки (SMT + HIL)   | диспетчер (Jetson AGX Orin)   |
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

* **Склад прототипу:** RTL-модулі [`km_concept_micro_engine.sv`](../../Engineering/hw/rtl/core/km_concept_micro_engine.sv), [`kpol_txn_gate_v2.sv`](../../Engineering/hw/rtl/core/kpol_txn_gate_v2.sv), [`km_autonomous_sequencer.sv`](../../Engineering/hw/rtl/core/km_autonomous_sequencer.sv), двобанкова обгортка [`km_concept_bram_dual_ha.sv`](../../Engineering/hw/rtl/core/km_concept_bram_dual_ha.sv) зі збалансованим 8-рівневим бінарним деревом пріоритетного кодера, шинний міст [`kpol_bram_pipeline_axi_ha.sv`](../../Engineering/hw/rtl/bus/kpol_bram_pipeline_axi_ha.sv) та інжектор 16-байтних пакетів правил з `CRC-8-ATM` [`rule_injector.py`](fpga-gpu-symbiosis/experiments/EXP-GPU-02/rule_injector.py).
* **Виміряні та формально перевірені параметри ([звіт `EXP-GPU-02` `1.0.1`](fpga-gpu-symbiosis/experiments/EXP-GPU-02/report-stage1-2-cfg-p-ha.md), [#252](https://github.com/nick-fedchik/kuzmin-machine/issues/252), [#253](https://github.com/nick-fedchik/kuzmin-machine/issues/253), [#254](https://github.com/nick-fedchik/kuzmin-machine/issues/254)):**
  1. Повний час оцінки події та перевірки інваріанта в PL становить рівно **`8` тактів (`80.0 нс` при `100.0 МГц`)** із нульовим внутрішньокристальним джитером і незалежністю від завантаження процесора ARM/Linux;
  2. Відкритий маршрут синтезу та трасування `OpenXC7` (`Yosys` + `nextpnr-himbaechel --seed 8` для `xc7z020clg400-1`) закриває таймінг на частоті **`F_max = 100.69 МГц` (`PASS at 100.00 MHz`, `WNS = +0.069 нс`, `5 718 SLICE_LUTX`, `2 RAMB36E1`)**;
  3. Поріг окупності площі Block RAM-конвеєра проти регістрово-конфігурованого RTL становить **$K^* = 26\text{ SLICE\_LUTX}$** ($K^*_{\text{FF}} = 10$ тригерів, `#254`);
  4. На фізичному кристалі `Zynq-7020` (`pynq2`) виконано **`10 003` гарячих перемикань банків (`40 011` подій)** із результатом: `0` міжпортових колізій BRAM, `0` аномалій тривалості циклу (`last_seq_exec_cycles == 8`), `0` втрачених подій і `0` `torn-read`.

### 2.2. Актив 2: Автоматизований конвеєр формальної та стендової верифікації (`Z3 SMT + мутанти + LogicTracer 0.5.0 HIL`)

* **Склад прототипу:** формальні SMT-моделі [`cme2_formal_n16_props.sv`](../../Engineering/validation/kpol-cme/cme2-formal-227/scripts/cme2_formal_n16_props.sv) (`#227/#242`), [`cfg_p_ha_formal_props.sv`](fpga-gpu-symbiosis/experiments/EXP-GPU-02/formal/cfg_p_ha_formal_props.sv) (`#252/#253`), [`manycore_formal_props.sv`](../../Engineering/validation/kpol-cme/manycore-scaling-255/scripts/manycore_formal_props.sv) (`#255`), генератор SMT-сертифікатів C99 [`c99_emitter.py`](../../Engineering/sw/kpol-ref/c99_emitter.py) (`#270`) та апаратний комплекс метрології `LOGICTRACER_PICO_0.5.0` (`100 MS/s` + `200 МГц` blast-таймер міток тригерів).
* **Виміряні та перевірені параметри:**
  1. Необмежена за часом композиційна математична індукція (`yosys-smtbmc -s z3 -i`, **`0` операторів `assume` у кроці індукції**) для властивостей Fail-Closed збереження пам'яті при відмові (`P1`), монотонного спадання рангу Ляпунова в ациклічних каскадах (`P2`) та точного 8-тактового часу транзакції (`P3`) на $N = 16$ концептах ([звіт #227/#242](../../Engineering/validation/kpol-cme/cme2-formal-227/report.md));
  2. Гейт Поппера (`AGENTS.md §4.1`): кожна формальна властивість і кожен програмний тест супроводжуються інжекцією дефектних мутантів (`M1..M6`), де солвер `Z3` або тестовий раннер будує конкретну контрприкладову трасу `.vcd` / `AssertionError`;
  3. Зовнішня фізична верифікація часових діаграм на пінах ПЛІС (`JA2_COMMIT`, `100.0..110.0 нс` імпульси при `100 MS/s`, точність сегментного таймера `5.0 нс`).

### 2.3. Актив 3: Резидентний 1024-підписниковий GPU-диспетчер на `NVIDIA Jetson AGX Orin` (`1.74..2.04 мкс`)

* **Склад прототипу:** CUDA-ядра [`persistent_subscribers.cu`](fpga-gpu-symbiosis/experiments/EXP-GPU-01/persistent_subscribers.cu) та [`heterogeneous_subscribers.cu`](fpga-gpu-symbiosis/experiments/EXP-GPU-03/heterogeneous_subscribers.cu), архітектурне рішення [ADR B6 v0.5.0](../../Engineering/decisions/b6-gpu-persistent-kernel-subscribers.md), результати [`EXP-GPU-01` Фаза 3–4](fpga-gpu-symbiosis/experiments/EXP-GPU-01/report-phase3-warp-scaling.md) (`#225/#235/#240`) та [`EXP-GPU-03`](fpga-gpu-symbiosis/experiments/EXP-GPU-03/report.md) (`#256`).
* **Виміряні параметри:**
  1. Усунення накладних витрат `cudaLaunchKernel` (`10–50 мкс`) завдяки утриманню `32` спеціалізованих варпів (`1 024` підписники) резидентними на `16` мультипроцесорах SM (`Ampere SM 8.7`);
  2. Усунення когерентного шторму `L2 Read Snoop` через рознесення вхідної події у `16` індивідуальних 128-байтних кеш-ліній `ingress[blockIdx.x]`, що дало **`9.63..10.05x` прискорення** на `1 024` підписниках (`p99` знижено з `17.48 мкс` до **`1.74 мкс`**);
  3. Групування гетерогенних законів керування (`PID`, `Kalman`, `FIR`, `Envelope`) по окремих варпах (`grouped_warp`) усуває штрафи warp divergence (`2.03x` прискорення над змішаним варпом, чистий час обчислення на GPU **`163.8 нс`** у профілі `MAXN`, наскрізна затримка `Host -> L2 -> SM -> Host` **`p99.9 = 1.93..2.04 мкс`**).

---

## 3. Три прикладні B2B-гіпотези для досліджень і впровадження на замовлення

На основі трьох створених прототипів сформульовано **три прикладні B2B-кейси**, які можуть досліджуватися далі за наявності комерційного замовника:

### 3.1. Кейс 1 (Automotive / `Infineon AURIX TC49x CSRM` / BMS `isoUART`): генератор детермінованого C99-автомата безпеки (`--emit-c99`) + Z3 Safety Certificate

* **Цільова інженерна задача (Tier-1 / OEM Battery Management Systems):**
  * Логіка аварійного відключення високовольтних контакторів батареї (`Cell -> Module -> Pack -> Contactor`), написана вручну на C у вигляді вкладених `if-else`, ускладнює аналіз відсутності циклів, оцінку `WCET` та захист від **маскування несправності датчика нулем** (коли при обриві лінії або помилці `CRC` у кадрі `isoUART` драйвер повертає `0 mV` без перевірки прапорця валідності).
* **Реалізований прототип (`--emit-c99` + `--emit-z3-cert`, [звіт `c99-emitter-270/report.md`](../../Engineering/validation/kpol-cme/c99-emitter-270/report.md)):**
  1. Таблиця правил захисту компілюється одночасно у 1024-байтний образ BRAM (`bms_safety_cascade.bin`) і в **самодостатній MISRA-орієнтований C99-модуль** (`bms_safety_cascade_gen.c`) із функціями `static inline`, переносною дводоповняльною конверсією `km_u32_to_i32`, без `malloc`, без рекурсії та без динамічних циклів `while` (`WCET = O(K)` за один прохід масиву `KM_SAFETY_TOPO_ORDER`);
  2. Структура стану `km_safety_ctx_t` містить явну 64-бітну маску визначеності `uint64_t valid_mask` (`1 = визначено`, `0 = стан невизначеності '_' / Sensor Fault`), а функція `km_safety_step_event(ctx, root_cid, param, param_valid)` перевіряє `(!ev_param_valid) || (!concept_valid)` і виконує `Fail-Closed` відхилення з інкрементом `fault_propagations++`;
  3. Функція `prove_c99_descriptor_safety_z3` парсить згенерований текст `c99_source` і за допомогою `Z3` (`z3-solver` або системного `/usr/bin/z3 -in -smt2`) перевіряє ациклічність і топологічний розклад (`P1`), збереження інваріантів (`P2`), блокування при `!ev_param_valid || !concept_valid` (`P3`) та 32-бітну еквівалентність таблиць і шаблонів операторів C99 зі специфікацією `CFG-P` (`P4`).
* **Що перевірено в репозиторії і що потребує досліджень на замовлення:**
  * Перевірено компіляцію `gcc -std=c99 -O2 -Wall -Wextra -Werror -pedantic` (`0` попереджень), `100%` побітовий збіг між C99 (`x86_64` і `ARM Cortex-A9`), моделлю `CFG-P` та фізичним кристалом `Zynq-7020 PL` (`pynq2`), і час виконання `mean = 223.85..286.73 нс` на подію в кеші L1 на `Cortex-A9`.
  * *Предмет досліджень на замовлення:* перенесення згенерованого C99-модуля в ядро `Infineon AURIX TC49x CSRM` (`TriCore`), інтеграція з драйвером трансивера `isoUART` (`TLE9012DQU` / `LTC6811`), перевірка сертифікованим чекером `MISRA-C:2012` та статичний аналіз `WCET` (`aiT`).

### 3.2. Кейс 2 (MilTech / Robotics `Jetson Orin + FPGA`): «Апаратний запобіжник для ШІ та автопілота (Hardware Safety Cage for AI/Linux)»

* **Цільова інженерна задача (автономні БПЛА та роботизовані платформи):**
  * Керуючі алгоритми та нейромережі на `NVIDIA Jetson Orin` під Linux можуть видати команду за межами безпечного експлуатаційного конверта або зазнати затримок планувальника ОС, тоді як параметри самого конверта безпеки (Geofencing, ліміти тяги/струму) змінюються між фазами місії.
* **Реалізований прототип (`CFG-P-HA` як Hardware Safety Cage):**
  1. Апаратний шлюз `CFG-P-HA` у ПЛІС (`Zynq-7020`) за **`80.0 нс` (`8` тактів @ `100 МГц`, `0` джитера)** перевіряє предикати діапазонів (`CME_PRED_RANGE`), порогові обмеження та каскадні інваріанти незалежно від стану ОС Linux;
  2. При зміні фази місії супервізор оновлює параметри конверта в тіньовому банку `CFG-P-HA` коротким **16-байтним пакетом із контрольною сумою `CRC-8`** (`rule_injector.py`, регістри `0x030..0x038`), і ПЛІС атомарно перемикає активний банк на межі такту `ST_IDLE` без зупинки контуру захисту (`0` stall-тактів, `0` `torn-read`).
* **Що перевірено в репозиторії і що потребує досліджень на замовлення:**
  * Перевірено P&R `CFG-P-HA` на `100.69 МГц`, SMT-властивості `H1..H7` у `Z3` та роботу на `10 003` гарячих перемиканнях на фізичній `PYNQ-Z1` (`#252/#253`), а також обробку `1 024` підписників на `Jetson AGX Orin` за `1.74..2.04 мкс` (`#235/#240/#256`).
  * *Предмет досліджень на замовлення:* заміна спростованого `UDP/GbE` (`#226`) на апаратний зв'язок `PMOD 3.3V <-> 1.8V J501 GPIO/SPI` або `PCIe GPUDirect RDMA` та інтеграція з польотним контролером (`MAVLink` / `DroneCAN`).

### 3.3. Кейс 3 (Вбудована метрологія та інженерна верифікація ПЛІС `HWE.3 / HWE.4`): накристальний реєстратор `lt_capture.v` (`LogicTracer 0.5.0`)

* **Цільова інженерна задача:**
  * Потактова верифікація внутрішніх кінцевих автоматів (`ST_IDLE..ST_EVAL_GATE`), стробів коміту/відмови та переходів банків пам'яті в реальному кремнії без виведення десятків сигналів на дефіцитні зовнішні піни PMOD.
* **Реалізована база та предмет досліджень на замовлення:**
  * У репозиторії перевірено зовнішнє захоплення імпульсів `JA2_COMMIT` через `LOGICTRACER_PICO_0.5.0` на частоті `100 MS/s` та `200 МГц` blast-таймінг сегментів (`#226`, `#230`, `#253`).
  * *Предмет досліджень на замовлення:* інтеграція накристального кільцевого буфера `lt_capture.v` (`pynq://`) з тригером на `reject_pulse_o` або `collision_detected_o` безпосередньо в бітстрім `CFG-P-HA`.

---

## 4. Зведені результати верифікації генератора `--emit-c99 + Z3` на референсному кейсі BMS

Докладний інженерний звіт верифікації за шаблоном `Report` наведено в [`Engineering/validation/kpol-cme/c99-emitter-270/report.md`](../../Engineering/validation/kpol-cme/c99-emitter-270/report.md).

### 4.1. Артефакти компіляції 4-рівневого референсного каскаду BMS (`BmsSafetyCascade`)

Компіляція [`bms_safety_cascade.kpol`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol) (`C0: Cell_Delta_mV -> C1: Module_Thermal_Guard -> C2: Pack_Fault_Latch -> C3: Contactor_Interlock`) командою:
```bash
python3 Engineering/hw/scripts/compile_kpol_bram_image.py --profile KPOL-CME-2 \
  --emit-c99 Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade_gen.c \
  --emit-z3-cert Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_z3_certificate.json \
  Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol \
  Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.bin
```
породжує детерміновані артефакти з такими контрольними сумами `SHA-256`:
1. [`bms_safety_cascade.bin`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.bin): `de03442454424b5cf64478506f118c13f095ae24ba58db8894583c43567ea3ee`;
2. [`bms_safety_cascade_gen.c`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade_gen.c): `108447cfb1fb623378ce92ace2189e8e46e0c21140b1a07b4fe8f8f9965c486f`;
3. [`bms_safety_z3_certificate.json`](../../Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_z3_certificate.json): `022ea96d25a9be09597e7ca823ec2960ec101e18a23f251876c00fc46ab2f1bc` (`verdict: "VERIFIED"`, солвер `z3-solver 5.4.1`).

### 4.2. Зведена таблиця наскрізної верифікації на `x86_64`, `ARM Cortex-A9` та `Zynq-7020 PL` (`pynq2`)

Первинні дані: [`x86_64_bms_c99_verification.json`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/x86_64_bms_c99_verification.json), [`iverilog_bms_cfg_p_trace.log`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/iverilog_bms_cfg_p_trace.log), [`pynq_cortex_a9_bms_c99_hil.json`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/pynq_cortex_a9_bms_c99_hil.json), [`pytest_c99_emitter_270.log`](../../Engineering/validation/kpol-cme/c99-emitter-270/raw/pytest_c99_emitter_270.log).

| Середовище виконання та клас доказу (`AGENTS.md §4.2`) | Кінцевий стан `[C0, C1, C2, C3]` (`hw_trace`) | Лічильники `events / commits / rejects` (`hw_trace`) | Захист від помилки `isoUART` (`fault_trace`: `commits / rejects / faults`) | Час виконання `mean / p50 / p99` ($\sigma$), `25 x 8 000 = 200 000` викликів |
| :--- | :---: | :---: | :---: | :--- |
| **1. Python `Interpreter` та `ReferenceCmeSafetyEngine` (`[software_model]`)** | `[4, 4, 0, 0]` | `18 / 12 / 6` | `6 / 3 / 3` (`0` маскувань) | — (еталонна специфікація) |
| **2. Згенерований C99 на хості `Linux x86_64` (`GCC 15.2.0 -std=c99 -O2 -Wall -Wextra -Werror -pedantic -lm`, `[host_c99]`)** | `[4, 4, 0, 0]` | `18 / 12 / 6` | `6 / 3 / 3` (`0` маскувань) | *Fault reject:* `6.25 / 6.25 / 6.62 нс` ($\sigma = 0.16\text{ нс}$)<br>*Single reject:* `9.52 / 9.50 / 10.38 нс` ($\sigma = 0.38\text{ нс}$)<br>*4-stage cascade:* `25.34 / 25.25 / 27.62 нс` ($\sigma = 1.11\text{ нс}$, `6.33 нс`/концепт) |
| **3. Потактова RTL-симуляція `kpol_bram_pipeline_axi.sv` (`Icarus Verilog 12.0`, `[rtl_simulation]`)** | `[4, 4, 0, 0]` | `18 / 12 / 6` | — (перевіряє RTL `CFG-P`) | `9` тактів (`90 нс`) одиночне відхилення;<br>`32` такти (`320 нс`) 4-рівневий каскад |
| **4. Згенерований C99 на фізичному ядрі `ARM Cortex-A9 @ 650 МГц` (`pynq2`, `gcc 11.2.0 -std=c99 -O2 -Wall -Wextra -Werror -pedantic -lm`, `[physical_hil_ps]`)** | `[4, 4, 0, 0]` | `18 / 12 / 6` | `6 / 3 / 3` (`0` маскувань) | *Fault reject:* **`223.85 / 223.12 / 227.62 нс`** ($\sigma = 1.45\text{ нс}$)<br>*Single reject:* **`286.73 / 285.12 / 306.00 нс`** ($\sigma = 4.53\text{ нс}$)<br>*4-stage cascade:* **`1038.26 / 1035.88 / 1081.88 нс`** ($\sigma = 17.06\text{ нс}$, **`259.56 нс`/концепт**) |
| **5. Фізичний кристал ПЛІС `Xilinx Zynq-7020 PL @ 100 МГц` (`pynq2`, `0x40000000`, `ID = 0x4B504D43 "KPMC"`, `[physical_hil_pl]`)** | `[4, 4, 0, 0]` | `18 / 12 / 6` | — (апаратний тракт `CFG-P`) | `8` тактів/концепт у кремнії PL (`80.0 нс` @ `100.0 МГц`, `0` джитера) |

---

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 1.0.1 | 2026-11-17 | Враховано всі зауваження рецензії `claude-sonnet-5.5` ([PR #271](https://github.com/nick-fedchik/kuzmin-machine/pull/271#issuecomment-6957224311), `F-01..F-10`): виділено окремий верифікаційний звіт [`Engineering/validation/kpol-cme/c99-emitter-270/report.md`](../../Engineering/validation/kpol-cme/c99-emitter-270/report.md) (`F-01`); видалено фейковий fallback без Z3 і додано SMT-LIB2 парсинг тексту C99 у `prove_c99_descriptor_safety_z3` (`F-02..F-04`); прибрано `#ifdef KM_MUTANT_*` із продакшн C99 та замінено на текстові мутації в тестах (`F-06`); виправлено SHA-256 `bms_safety_cascade_gen.c` (`108447cf...`) з автоматичною перевіркою у `pytest` (`F-05`); додано `git_commit`, `flock` і статистику `mean/p50/p99/sigma` з 25 пакетів (`F-07`); позначено функції `static inline` з переносною конверсією `km_u32_to_i32` (`F-08`), задокументовано статичне звуження `subscriber_cid < 64` та атомарний запис CLI (`F-09`) і приведено формулювання до нейтрального інженерного стилю (`F-10`). |
| 1.0.0 | 2026-11-17 | Перша редакція підсумкового інженерно-комерційного висновку проєкту Машини Кузьміна та звіту верифікації генератора `--emit-c99 + Z3 Safety Certificate` на референсному кейсі BMS (`x86_64`, `ARM Cortex-A9`, `Zynq-7020 PL`, [#270](https://github.com/nick-fedchik/kuzmin-machine/issues/270)). |

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
