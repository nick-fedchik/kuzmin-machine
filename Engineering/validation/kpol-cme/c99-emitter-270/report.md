# Звіт C99-EMITTER-270: Верифікація генератора детермінованого C99 (`--emit-c99`) та сертифіката `Z3 SMT` на референсному каскаді BMS (Issue #270)

* **Версія:** 1.0.0
* **Дата:** 2026-11-17
* **Тип WP редакції NG:** Report
* **Issue:** `Closes` [#270](https://github.com/nick-fedchik/kuzmin-machine/issues/270). **PR:** [#271](https://github.com/nick-fedchik/kuzmin-machine/pull/271) у гілці `feat/270-commercial-conclusions-and-emit-c99`.
* **Виконавець:** GitHub Copilot CLI (Lead Engineer / Architect). **Рецензент першого проходу PR #271 (`9d28d31`):** `claude-sonnet-5.5` ([коментар](https://github.com/nick-fedchik/kuzmin-machine/pull/271#issuecomment-6957224311), вердикт «Доопрацювати», знахідки `F-01..F-10` враховано у цій редакції).
* **Коміт бази, на якому виконано:** робоча гілка PR на коміті `9d28d3126e415d257e3c523fc295422fc9d70683` (`origin/main`: `6f1dc29`).
* **Хост верифікації:** `Linux 7.0.0-42-generic x86_64` (`GCC 15.2.0`, `Python 3.14.4`, `pytest 9.0.2`, `z3-solver 5.4.1`, `/usr/bin/z3 4.13.3`, `Icarus Verilog 12.0`).
* **Фізична плата HIL (`pynq2`, під `flock -w 600 /tmp/km-bench.lock`):** `Digilent PYNQ-Z1` (`xilinx@192.168.68.69`, двоядерний `ARM Cortex-A9 @ 650 МГц`, `gcc 11.2.0` + кристал `Xilinx Zynq-7020 XC7Z020-1CLG400C` @ `100.0 МГц`, активний конвеєр `CFG-P` `0x4B504D43` `"KPMC"`).
* **Первинні артефакти та контрольні суми (`SHA-256`):**
  * Вхідна програма BMS: [`bms_safety_cascade.kpol`](bms_safety_cascade.kpol);
  * 1024-байтний образ BRAM: [`bms_safety_cascade.bin`](bms_safety_cascade.bin) (`de03442454424b5cf64478506f118c13f095ae24ba58db8894583c43567ea3ee`);
  * Згенерований C99-модуль: [`bms_safety_cascade_gen.c`](bms_safety_cascade_gen.c) (`108447cfb1fb623378ce92ace2189e8e46e0c21140b1a07b4fe8f8f9965c486f`);
  * Формальний сертифікат Z3: [`bms_safety_z3_certificate.json`](bms_safety_z3_certificate.json) (`022ea96d25a9be09597e7ca823ec2960ec101e18a23f251876c00fc46ab2f1bc`);
  * Драйвер перевірки й бенчмарку: [`bms_c99_hil_bench.c`](bms_c99_hil_bench.c) (`1509a8a513f6528cdb78facead0c59e4495d4a2a0afcd7620cb8a275dfbdcb80`);
  * Сирі логи та JSON: [`raw/x86_64_bms_c99_verification.json`](raw/x86_64_bms_c99_verification.json), [`raw/x86_64_bms_c99_verification.log`](raw/x86_64_bms_c99_verification.log), [`raw/iverilog_bms_cfg_p_trace.log`](raw/iverilog_bms_cfg_p_trace.log), [`raw/pynq_cortex_a9_bms_c99_hil.json`](raw/pynq_cortex_a9_bms_c99_hil.json), [`raw/pynq_cortex_a9_bms_c99_hil.log`](raw/pynq_cortex_a9_bms_c99_hil.log), [`raw/pytest_c99_emitter_270.log`](raw/pytest_c99_emitter_270.log).
* **Пов'язане аналітичне дослідження:** [`Research/studies/commercialization-and-final-conclusions.md`](../../../../Research/studies/commercialization-and-final-conclusions.md).

---

## 1. Що не вдалося і обмеження

1. **Межа формального SMT-доказу `prove_c99_descriptor_safety_z3` (`F-03`, `F-04`):**
   * Функція `prove_c99_descriptor_safety_z3` у [`c99_emitter.py`](../../../sw/kpol-ref/c99_emitter.py) парсить фактично згенерований текст `c99_source` (витягуючи масиви `KM_SAFETY_DESCRIPTORS[64]`, `KM_SAFETY_TOPO_ORDER`, спосіб індексації циклу обходу, умову блокування `!ev_param_valid || !concept_valid`, оператори предикатів `NOP..BITMASK`, дій `ASSIGN..SUB`, формулу `invariant_true`, кон'юнкцію `commit` та `target_cid != cid`) і розв'язує у `Z3` (`QF_LIA` та `QF_BV` `BitVec(32)`) чотири властивості `P1..P4` проти вхідної специфікації `CFG-P`.
   * Це є **формальною SMT-верифікацією згенерованих C99-таблиць, топологічного розкладу та шаблонів переходів C99 проти еталонної моделі `CFG-P`**, а **не** формальною верифікацією об'єктного машинного коду компілятора `GCC` за допомогою `CompCert` або `CBMC`/`ESBMC` та `yosys write_smt2`. Еквівалентність скомпільованого бінарного коду `GCC` та RTL `kpol_bram_pipeline_axi.sv` підтверджується диференційними тестами на трасах подій у симуляції `Icarus Verilog` та на фізичному кристалі `Zynq-7020 PL`.
2. **Орієнтир `MISRA-C99` та модель одиничного заголовкового файлу (`F-08`):**
   * Згенерований модуль `bms_safety_cascade_gen.c` оформлений як самодостатній C99-файл з include-guard та функціями `static inline` (що дозволяє безпечно включати його в один або декілька одиниць трансляції TU без помилок лінкера щодо повторного визначення символів) і використовує переносну функцію `km_u32_to_i32` замість implementation-defined приведення типів `(int32_t)u32`.
   * Дотримано структурних обмежень безпечного підмножинного C99 (відсутність `malloc`/`free`, рекурсії та необмежених циклів `while`), проте перевірка комерційним сертифікованим аналізатором `MISRA-C:2012` не проводилася (`standards-position.md`).
3. **Навмисне статичне звуження `subscriber_cid < 64` відносно RTL (`F-09`):**
   * В апаратному модулі `km_concept_micro_engine.sv` дескриптор із `subscriber_cid >= 64` та `SUBSCRIBER_EN == 1` приймається, але на виході каскад блокується вентилем `subscriber_target_valid_w = (subscriber_cid_w < 32'd64)`. Натомість `compute_topological_order` та `prove_c99_descriptor_safety_z3` відхиляють таблиці з `subscriber_cid >= 64` ще до генерації C99-коду (`C99-DAG-RANGE`), щоб унеможливити наявність невалідних індексів у статичній таблиці `KM_SAFETY_DESCRIPTORS`.
4. **Середовище вимірювання часу виконання на `ARM Cortex-A9` (`F-07`):**
   * Вимірювання часу виконання `km_safety_step_event` на платі `PYNQ-Z1` (`pynq2`, `ARM Cortex-A9 @ 650 МГц`) виконано у просторі користувача `Linux 6.6.10-xilinx` серією з `25` пакетів по `8 000` ітерацій (`200 000` викликів на метрику) через процесорний таймер `clock()`. Цільові автомобільні мікроконтролери `Infineon AURIX TC49x CSRM` або `ARM Cortex-R52` у лабораторному стенді відсутні.

---

## 2. Метод реалізації та верифікації

1. **Кодогенерація C99 (`emit_c99_safety_module` у [`Engineering/sw/kpol-ref/c99_emitter.py`](../../../sw/kpol-ref/c99_emitter.py)):**
   * Із 64-слотової таблиці дескрипторів `CME-RAW-1` виділяються активні концепти та орієнтовані ребра підписок `W3` (`extract_active_cids_and_edges`).
   * За детермінованим алгоритмом Кана з мінімальним індексом `CID` будується топологічний порядок `KM_SAFETY_TOPO_ORDER` (`compute_topological_order`).
   * Генерується чистий C99-код (без будь-яких макросів `#ifdef KM_MUTANT_*`), де `km_safety_step_event` виконує рівно один фіксований прохід `for (topo_idx = 0u; topo_idx < KM_SAFETY_NUM_ACTIVE_TOPO; ++topo_idx)` (`WCET = O(K)`).
2. **Нетавтологічна SMT-верифікація по розпарсеному тексту C99 (`prove_c99_descriptor_safety_z3`):**
   * Парсер `parse_emitted_c99_source(c99_source)` витягує безпосередньо з тексту `.c` файлу таблиці `KM_SAFETY_DESCRIPTORS[64]`, `KM_SAFETY_TOPO_ORDER`, напрямок індексації циклу, наявність Fail-Closed шлюзу `if ((!ev_param_valid) || (!concept_valid))`, оператори всіх гілок `switch (d->pred_opcode)` та `switch (d->action_opcode)`, формулу `invariant_true` і умову `self_suppress` (`target_cid != cid`).
   * Сформовані SMT-LIB2 запити (`QF_LIA` для `P1`, `QF_BV` `BitVec(32)` для `P2..P4`) розв'язуються через `z3-solver` Python API або системний бінарник `/usr/bin/z3 -in -smt2`. Якщо в середовищі відсутні обидва варіанти `Z3`, функція негайно генерує `RuntimeError("Z3 solver is required")` (`F-02`: жодних синтетичних `VERIFIED`-заглушок).
3. **Диференційне та мутаційне тестування ([`test_c99_emitter_270.py`](../../../sw/tests/test_c99_emitter_270.py)):**
   * Мутанти у `test_c99_emitter_270.py` створюються виключно шляхом текстової заміни `str.replace` у згенерованому C99-коді у тимчасовому каталозі тесту (з перевіркою `assert c99_src.count(old_snippet) == 1`) і перевіряються як компіляцією в `GCC` + запуском через `ctypes`, так і подачею мутованого тексту `c99_source` у `prove_c99_descriptor_safety_z3`.

---

## 3. Результати

### 3.1. Результати Z3 SMT-верифікації (`bms_safety_z3_certificate.json`)

| Властивість | Метод перевірки у `Z3` (`z3-solver 5.4.1` / `z3 4.13.3`) | Статус | Зміст перевірки розпарсеного C99-коду |
| :--- | :--- | :---: | :--- |
| **`P1_dag_lyapunov_acyclicity`** | `QF_LIA`: `rank[src] < rank[dst]` та `pos_c99[src] < pos_c99[dst]` для всіх ребер `W3` (`[0->1, 1->2, 2->3]`) | **`SAT_RANKING_FOUND`** (`passed: true`) | Масив `KM_SAFETY_TOPO_ORDER = {0, 1, 2, 3}` та прямий індекс `topo_idx` у C99-коді строго узгоджені з DAG підписок (`WCET = 4` кроки). |
| **`P2_invariant_preservation_all_bv32`** | `QF_BV`: $\forall \text{cur\_state}, \text{ev\_param} \in \text{BitVec}(32)$ на розпарсеній таблиці `KM_SAFETY_DESCRIPTORS` та виразі `commit_c99_fn` | **`UNSAT`** (`passed: true`) | Жоден активний концепт у розпарсеному C99-коді не може закомітити від'ємний стан (`cand < 0`) або арифметичне переповнення `ovf_rtl`. |
| **`P3_no_commit_on_invalid_param_or_state`** | `QF_BV`: $\forall \text{cur\_state}, \text{ev\_param} \in \text{BitVec}(32), \text{ev\_param\_valid}, \text{concept\_valid} \in \text{Bool}$ | **`UNSAT`** (`passed: true`) | Присутність у розпарсеному C99-коді шлюзу `(!ev_param_valid) || (!concept_valid)` гарантує `!commit`, збереження `cur_state` та `fault_propagations += 1`. |
| **`P4_c99_rtl_bitvec32_miter_equivalence`** | `QF_BV`: 32-бітний мітер між специфікацією `CFG-P` та розпарсеними C99-функціями `pred_c99`, `cand_c99_fn`, `ovf_c99_fn`, `commit_c99_fn`, `trig_c99` | **`UNSAT`** (`passed: true`) | 100% побітовий збіг таблиці `KM_SAFETY_DESCRIPTORS[64]` та операторів предикатів/дій/охоронців у C99 зі специфікацією `CFG-P`. |

### 3.2. Диференційна верифікація та статистика часу виконання (`25 x 8 000 = 200 000` ітерацій)

Первинні файли: [`raw/x86_64_bms_c99_verification.json`](raw/x86_64_bms_c99_verification.json), [`raw/pynq_cortex_a9_bms_c99_hil.json`](raw/pynq_cortex_a9_bms_c99_hil.json), [`raw/iverilog_bms_cfg_p_trace.log`](raw/iverilog_bms_cfg_p_trace.log).

| Виконавець (`evidence_kind`) | Стан після `hw_trace` (`8` подій) | `events / commits / rejects` (`hw_trace`) | `fault_trace` (`commits / rejects / faults`) | Затримка `mean` / `p50` / `p99` ($\sigma$), `25` серій по `8 000` викликів |
| :--- | :---: | :---: | :---: | :--- |
| **1. Python `Interpreter` + `ReferenceCmeSafetyEngine` (`[software_model]`)** | `[4, 4, 0, 0]` | `18 / 12 / 6` | `6 / 3 / 3` | — (еталонна модель) |
| **2. C99 на `Linux x86_64` (`GCC 15.2.0 -std=c99 -O2 -Wall -Wextra -Werror -pedantic -lm`, `[host_c99]`)** | `[4, 4, 0, 0]` | `18 / 12 / 6` | `6 / 3 / 3` | *Fault reject:* `6.25 / 6.25 / 6.62 нс` ($\sigma = 0.16\text{ нс}$)<br>*Single reject:* `9.52 / 9.50 / 10.38 нс` ($\sigma = 0.38\text{ нс}$)<br>*4-stage cascade:* `25.34 / 25.25 / 27.62 нс` ($\sigma = 1.11\text{ нс}$, `6.33 нс`/концепт) |
| **3. RTL `kpol_bram_pipeline_axi.sv` (`Icarus Verilog 12.0`, `[rtl_simulation]`)** | `[4, 4, 0, 0]` | `18 / 12 / 6` | — | `9` тактів (`90 нс`) одиночне відхилення; `32` такти (`320 нс`) 4-рівневий каскад |
| **4. C99 на `ARM Cortex-A9 @ 650 МГц` (`pynq2`, `gcc 11.2.0 -std=c99 -O2 -Wall -Wextra -Werror -pedantic -lm`, `[physical_hil_ps]`)** | `[4, 4, 0, 0]` | `18 / 12 / 6` | `6 / 3 / 3` | *Fault reject:* **`223.85 / 223.12 / 227.62 нс`** ($\sigma = 1.45\text{ нс}$)<br>*Single reject:* **`286.73 / 285.12 / 306.00 нс`** ($\sigma = 4.53\text{ нс}$)<br>*4-stage cascade:* **`1038.26 / 1035.88 / 1081.88 нс`** ($\sigma = 17.06\text{ нс}$, **`259.56 нс`/концепт**) |
| **5. Фізичний кристал `Zynq-7020 PL @ 100 МГц` (`pynq2`, `0x40000000`, `ID = 0x4B504D43`, `[physical_hil_pl]`)** | `[4, 4, 0, 0]` | `18 / 12 / 6` | — | `8` тактів/концепт у кремнії PL (`80.0 нс` @ `100.0 МГц`, `0` джитера) |

### 3.3. Результати мутантних та негативних контролів (`test_c99_emitter_270.py`, `AGENTS.md §4.1`)

| Ідентифікатор мутанта / контролю | Текстова мутація у згенерованому `.c` файлі або дескрипторі | Спостережувана реакція `Z3` та диференційного рантайм-тесту | Статус |
| :--- | :--- | :--- | :---: |
| **`M1_c99_bypass_invariant`** | Заміна в тексті `.c`: `invariant_true = (!arith_overflow) && ((cand_u32 & 0x80000000u) == 0u);` $\to$ `invariant_true = true; (void)arith_overflow;` | 1) `prove_c99_descriptor_safety_z3(descs, c99_source=mut_c)` повертає `REJECTED` (`P2` і `P4` знаходять 32-бітні контрприклади у `Z3`);<br>2) Скомпільований `.so` при `delta_mv = 250` пропускає `Pack_Fault_Latch = -1` і падає на `AssertionError`. | **Killed** |
| **`M2_c99_mask_invalid_sensor`** | Заміна в тексті `.c`: `if ((!ev_param_valid) || (!concept_valid))` $\to$ `if (false && ((!ev_param_valid) || (!concept_valid)))` | 1) `prove_c99_descriptor_safety_z3(descs, c99_source=mut_c)` повертає `REJECTED` (`P3` знаходить контрприклад маскування у `Z3`);<br>2) Скомпільований `.so` падає на сценаріях `(0, 0, False)`, `(0, 120, False)` та інвалідованого `CID 2`. | **Killed** |
| **`M3_c99_wrong_topo_order`** | Заміна в тексті `.c`: `KM_SAFETY_TOPO_ORDER[topo_idx]` $\to$ `KM_SAFETY_TOPO_ORDER[(KM_SAFETY_NUM_ACTIVE_TOPO - 1u) - topo_idx]` (або `{ 3u, 2u, 1u, 0u }`) | 1) `prove_c99_descriptor_safety_z3(descs, c99_source=mut_c)` повертає `REJECTED` (`P1` фіксує порушення топологічного розкладу);<br>2) Скомпільований `.so` зупиняє каскад після `C0` (`steps=1 != 4`). | **Killed** |
| **`M4_z3_cyclic_or_unsafe_descriptor_and_opcodes`** | Подача циклічного дескриптора `C0->C1->C0`, самопетлі `C0->C0`, `INVARIANT_EN=0`, а також текстових мутацій C99: `>` $\to$ `>=` (`PRED_GT`), `km_u16_to_i32_sext` $\to$ `(int32_t)` без знакового розширення (`PRED_RANGE`), `!= 0u` $\to$ `== 0u` у переповненні `ACT_SUB` | Усі 6 під-мутантів детерміновано відхиляються `prove_c99_descriptor_safety_z3` (`P1`, `P2`, `P4` повертають `UNSAT`/`SAT_DIVERGENCE`) та диференційним C99-тестом. | **Killed** |
| **`F02_no_z3_fail_closed_control`** | Симуляція відсутності `z3-solver` (`HAS_Z3_PYTHON=False`) та роботи через системний `/usr/bin/z3 -in -smt2`, а також повної відсутності `z3` (`shutil.which("z3") = None`) | При `HAS_Z3_PYTHON=False` + `/usr/bin/z3` всі перевірки `P1..P4` та мутанти працюють через CLI `z3 -in -smt2`; при відсутності обох солверів піднімається `RuntimeError("Z3 solver is required")`. | **Killed** |

---

## 4. Таблиця критеріїв приймання (Issue #270)

| Критерій Issue #270 | Артефакт / Тест | Результат |
| :--- | :--- | :---: |
| Підсумковий інженерно-комерційний висновок + звіт верифікації WP | [`commercialization-and-final-conclusions.md`](../../../../Research/studies/commercialization-and-final-conclusions.md), цей `report.md` | **Виконано** |
| Генератор `c99_emitter.py` та CLI `--emit-c99` / `--emit-z3-cert`, компіляція `gcc -std=c99 -O2 -Wall -Wextra -Werror -pedantic` з `0` попереджень | [`c99_emitter.py`](../../../sw/kpol-ref/c99_emitter.py), [`compile_kpol_bram_image.py`](../../../hw/scripts/compile_kpol_bram_image.py) | **Виконано** |
| 100% побітова тотожність C99, моделі `CFG-P`, RTL-симуляції та фізичного кристала `Zynq-7020 PL` на кейсі BMS | [`raw/x86_64_bms_c99_verification.json`](raw/x86_64_bms_c99_verification.json), [`raw/pynq_cortex_a9_bms_c99_hil.json`](raw/pynq_cortex_a9_bms_c99_hil.json) | **Виконано** |
| Усі негативні мутанти `M1..M4` (включно з текстовими мутаціями C99 та Z3 без фейкового fallback) детерміновано вбиваються | [`test_c99_emitter_270.py`](../../../sw/tests/test_c99_emitter_270.py), [`raw/pytest_c99_emitter_270.log`](raw/pytest_c99_emitter_270.log) | **Виконано** |

---

## 5. Команди для незалежного відтворення

```bash
python3 -m pytest -v Engineering/sw/tests/test_c99_emitter_270.py
python3 Engineering/validation/kpol-cme/c99-emitter-270/run_bms_c99_verification.py --skip-pynq
KM_DRAFTS_REPO=/home/mfedchyk/GitHub/nick-fedchik/drafts python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
```

---

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 1.0.0 | 2026-11-17 | Перша редакція окремого звіту верифікації генератора `--emit-c99 + Z3` (`#270`, усунення знахідок `F-01..F-10` рецензії PR #271). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| **BMS** | Battery Management System, система контролю та захисту акумуляторної батареї. |
| **CFG-P** | Однобанковий BRAM-конвеєр виконання дескрипторів концептів Машини Кузьміна. |
| **DAG** | Directed Acyclic Graph, орієнтований ациклічний граф підписок. |
| **HIL** | Hardware-in-the-Loop, перевірка з фізичним обладнанням у контурі. |
| **SMT / Z3** | Satisfiability Modulo Theories / солвер `Z3`. |
| **TU** | Translation Unit, одиниця трансляції компілятора C. |
| **WCET** | Worst-Case Execution Time, верхня межа часу виконання у найгіршому випадку. |
| **WP** | Work Product, робочий продукт з визначеним призначенням і походженням. |
