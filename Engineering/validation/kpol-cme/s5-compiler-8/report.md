# Звіт S5-COMPILER-8: Консолідована приймальна верифікація компілятора KPOL → образ BRAM та байткод Do/Go (крок S5, Issue #8)

* **Версія:** 0.1.0
* **Дата:** 2026-11-17
* **Тип WP редакції NG:** Report
* **Issue:** [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8) (консолідує результати влитих підзадач [#150](https://github.com/nick-fedchik/kuzmin-machine/issues/150), [#153](https://github.com/nick-fedchik/kuzmin-machine/issues/153), [#155](https://github.com/nick-fedchik/kuzmin-machine/issues/155), [#157](https://github.com/nick-fedchik/kuzmin-machine/issues/157), [#159](https://github.com/nick-fedchik/kuzmin-machine/issues/159), [#164](https://github.com/nick-fedchik/kuzmin-machine/issues/164), [#183](https://github.com/nick-fedchik/kuzmin-machine/issues/183), [#184](https://github.com/nick-fedchik/kuzmin-machine/issues/184), [#185](https://github.com/nick-fedchik/kuzmin-machine/issues/185), [#191](https://github.com/nick-fedchik/kuzmin-machine/issues/191), [#192](https://github.com/nick-fedchik/kuzmin-machine/issues/192), [#197](https://github.com/nick-fedchik/kuzmin-machine/issues/197), [#198](https://github.com/nick-fedchik/kuzmin-machine/issues/198), [#201](https://github.com/nick-fedchik/kuzmin-machine/issues/201), [#203](https://github.com/nick-fedchik/kuzmin-machine/issues/203), [#207](https://github.com/nick-fedchik/kuzmin-machine/issues/207), [#211](https://github.com/nick-fedchik/kuzmin-machine/issues/211), [#213](https://github.com/nick-fedchik/kuzmin-machine/issues/213), [#215](https://github.com/nick-fedchik/kuzmin-machine/issues/215), [#218](https://github.com/nick-fedchik/kuzmin-machine/issues/218), [#219](https://github.com/nick-fedchik/kuzmin-machine/issues/219), [#224](https://github.com/nick-fedchik/kuzmin-machine/issues/224), [#233](https://github.com/nick-fedchik/kuzmin-machine/issues/233), [#243](https://github.com/nick-fedchik/kuzmin-machine/issues/243), [#245](https://github.com/nick-fedchik/kuzmin-machine/issues/245)). **PR:** у гілці `feat/8-s5-compiler-and-project-docs`.
* **Виконавець:** GitHub Copilot CLI (`Gemini 4 Argon`, `gemini-4-argon`, родина Gemini). **Рецензент:** очікує незалежної рецензії агентом іншої родини моделей (`claude-sonnet-5.5`) за [PROJECT-MANUAL §2.1](../../../../Project/guides/project-manual.md#21-агенти-проєкту).
* **Коміт бази, на якому виконано:** `467cd4e13c2812d5fe3b1be004110864e11448ba` (`origin/main`). **Хост / плата:** `Linux 7.0.0-42-generic x86_64` (`Python 3.14.4`, `pytest 9.0.2`, `Icarus Verilog 12.0`); фізична плата FPGA `PYNQ-Z1` у цьому консолідованому прогоні не залучалася (`evidence_kind: host_compiler_and_iverilog_rtl_simulation_not_physical_hil`). **Бітстрім (SHA-256):** не генерувався.
* **Критерії успіху (зафіксовано до виконання в описі [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8)):** (1) консолідована специфікація KPOL та явні профілі; (2) автоматична трансляція «текст KPOL → 1024-байтний образ BRAM (`CME-RAW-1` + опційний підписаний контейнер `Secure Boot` HMAC-SHA256) та байткод `Do/Go`» без ручного RTL; (3) тести компілятора, що вміють впасти (з мутантами та негативними корпусами); (4) звіт WP та передача на незалежну рецензію.

---

## 1. Що не вдалося і обмеження

1. **Відкрита дослідницька задача [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186) для невідповіджених RFC Автора поза межами закриття S5 (`#8`):**
   * Закриття інженерного епіка S5 (`#8`) фіксує виконані профілі `KPOL-CME-1`, `KPOL-CME-2` та детерміноване підмножинне ядро `KPOL-AUTH`, але **не закриває** окрему дослідницьку задачу [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186).
   * До отримання відповідей Автора концепції (М. Ю. Кузьміна) на відкриті запити у `nick-fedchik/drafts` (`RFC-016` — нова пара роздільників замість `#`, екранування в `Text`/`Help`, одиниця довжини `Name` $\le 16$; `RFC-017` п. 2–3 та проміжний стан `busy(A)` у п. 1 — булеве значення `(A • B)` і читання неініціалізованого стану `_` у виразах `C := _ + B`; `RFC-018` п. 2 та остаточна доля `Child` у 8-бітному `Def`; `RFC-009` п. 3 та правило взаємодії `И`/`ИЛИ` з `Min`/`Max`) усі 12 відповідних точок невизначеності `KPOL-AUTH-U01..U12` залишаються заблокованими в режимі `fail-closed` ([`kpol-auth-subset-0.1.0.md`](../../../specifications/kpol/kpol-auth-subset-0.1.0.md)).
2. **Відкладена RTL-реалізація `CFG-P2` (`CME-RAW-2`, 32-байтний дескриптор за [ADR B7](../../../decisions/cme-raw2-kpol-sys02.md)):**
   * Чинний апаратний конвеєр `CFG-P` (`kpol_bram_pipeline_axi.sv`) та його двобанкова модифікація високої готовності `CFG-P-HA` (`kpol_bram_pipeline_axi_ha.sv`) працюють із незмінним 16-байтним дескриптором `CME-RAW-1` ($64 \times 16 = 1024$ байти).
   * Через спільне 32-бітне поле `W1 = operand_val` у `CME-RAW-1` поєднання літерального/діапазонного охоронця з дією `ADD`/`SUB` кроку $K \ge 2$ (`CME2-OPERAND-COLLISION`), константний `ASSIGN`, порівняння власного стану в охоронці (`state-guard`), неініціалізований стан `_` (`KPOL-SYS-02`) та секція `Hazards` (`CME2-HAZARD`) у `KPOL-CME-2` детерміновано відхиляються до емісії образу. Проєкт 32-байтного дескриптора `CME-RAW-2` (`W0..W7`, окремий біт `W1.state_valid` для `_` та розділені 32-бітні операнди) прийнятий власником на рівні [ADR B7](../../../decisions/cme-raw2-kpol-sys02.md) за Варіантом А ([#185](https://github.com/nick-fedchik/kuzmin-machine/issues/185), [#215](https://github.com/nick-fedchik/kuzmin-machine/issues/215)), а його втілення в RTL `CFG-P2` залишається окремою відкладеною межею до відповіді на `RFC-017` п. 3.
3. **Обмеження `CME-RAW-1` на розгалуження каскаду (`fan-out <= 1`) та ациклічність (`DAG`):**
   * У форматі `CME-RAW-1` кожний слот містить одне поле `W3 = subscriber_cid`, тому компілятор `KPOL-CME-2` (`CME2-CASCADE`) та бекенд `KPOL-AUTH` (`KPOL-LOWER-FANOUT`, `KPOL-LOWER-CYCLE`) підтримують щонайбільше одного `POST_CHANGE`-підписника на концепт і вимагають строгої ациклічності графа підписок (статична передумова `cap_dag_ok_w` формальної леми завершення `P2` у [#227](https://github.com/nick-fedchik/kuzmin-machine/issues/227)/[#242](https://github.com/nick-fedchik/kuzmin-machine/issues/242)/[#249](https://github.com/nick-fedchik/kuzmin-machine/issues/249) та відсутності міжбанкового дедлока `MC3`/`MC4` у [#255](https://github.com/nick-fedchik/kuzmin-machine/issues/255)).
4. **Клас доказів консолідованого прогону (`rtl_simulation` та `software_vm`, не новий фізичний HIL):**
   * Усі перевірки у приймальному тестовому пакеті [`test_s5_compiler_acceptance_8.py`](../../../sw/tests/test_s5_compiler_acceptance_8.py) виконуються на хості (`Python 3.14.4`, `ReferenceDoGoVM`) та в потактовій RTL-симуляції `Icarus Verilog 12.0` (`kpol_bram_pipeline_axi.sv` і `kpol_bram_pipeline_axi_ha.sv`). Натурні HIL-вимірювання на платах `PYNQ-Z1` зафіксовані в окремих звітах (`S4-07` та HIL-регресії каскаду BRAM). Відповідність стандартам функціональної безпеки (`ISO 26262`, `IEC 61508`, `DO-178C`/`DO-254`) або `ASPICE` не заявляється і не оцінювалася згідно з [`standards-position.md`](../../../../Project/policies/standards-position.md).

---

## 2. Метод і виконання 4 пунктів чекліста Issue #8

Консолідований приймальний тест [`Engineering/sw/tests/test_s5_compiler_acceptance_8.py`](../../../sw/tests/test_s5_compiler_acceptance_8.py) об'єднує наскрізну перевірку всіх чотирьох пунктів батьківської задачі [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8):

1. **Пункт 1 чекліста — Консолідована специфікація KPOL та явні профілі ([`Engineering/specifications/kpol/README.md`](../../../specifications/kpol/README.md)):**
   * [`kpol-consolidated-0.1.0.md`](../../../specifications/kpol/kpol-consolidated-0.1.0.md) — опис ширшого референсного фронтенду та інтерпретатора `Problem / Solution / Proof` із задокументованими межами безпрофільного lowering;
   * [`kpol-cme-subset-0.1.0.md`](../../../specifications/kpol/kpol-cme-subset-0.1.0.md) — початковий профіль одноконцептного виконання `KPOL-CME-1` на 1024-байтному образі `CME-RAW-1` (`Decision B3-01`, [#150](https://github.com/nick-fedchik/kuzmin-machine/issues/150), [#153](https://github.com/nick-fedchik/kuzmin-machine/issues/153));
   * [`kpol-cme2-profile-0.1.0.md`](../../../specifications/kpol/kpol-cme2-profile-0.1.0.md) — багатоконцептний профіль `KPOL-CME-2` до 64 станів на незмінному `CME-RAW-1` з ациклічними каскадами `on change(...)` (включно з `CID 0`), `ADD/SUB/ASSIGN`, знаковими межами `int16` `RANGE` та детектором `CME2-OPERAND-COLLISION` ([#184](https://github.com/nick-fedchik/kuzmin-machine/issues/184), [#191](https://github.com/nick-fedchik/kuzmin-machine/issues/191), [#197](https://github.com/nick-fedchik/kuzmin-machine/issues/197));
   * [`kpol-auth-subset-0.1.0.md`](../../../specifications/kpol/kpol-auth-subset-0.1.0.md) — похідна специфікація ізольованого фронтенду й детермінованого lowering `KPOL-AUTH` із трирівневим розмежуванням атрибуції (`[П]` / `[В]` / `[Відкрито]`), UTF-8 координатами `Span` та гейтами `KPOL-AUTH-U01..U12` ([#219](https://github.com/nick-fedchik/kuzmin-machine/issues/219), [#243](https://github.com/nick-fedchik/kuzmin-machine/issues/243), [#245](https://github.com/nick-fedchik/kuzmin-machine/issues/245)).
2. **Пункт 2 чекліста — Автоматична трансляція «текст KPOL → образ BRAM / байткод» без ручного RTL:**
   * **Контур 1 (`KPOL-CME-1`):** CLI [`compile_kpol_bram_image.py`](../../../hw/scripts/compile_kpol_bram_image.py) (`--profile KPOL-CME-1`) транслює валідні програми (`SingleCme1`, `kpol_bram_pipeline_increase.kpol`, `kpol_bram_pipeline_decrease.kpol`) у 1024-байтний образ `CME-RAW-1`, а функції `compile_signed_bram_image` / `verify_bram_signature` у [`kpol_reference.py`](../../../sw/kpol-ref/kpol_reference.py) пакують і верифікують 1088-байтний контейнер `Secure Boot` (`v0x0006`, HMAC-SHA256, 16-байтний криптографічний `nonce`, захист від replay та pre-auth nonce poisoning за [#164](https://github.com/nick-fedchik/kuzmin-machine/issues/164)).
   * **Контур 2 (`KPOL-CME-2`):** CLI `compile_kpol_bram_image.py --profile KPOL-CME-2` компілює 4-ступеневий ациклічний каскад `Cascade4Stage` (`C0 -> C1 -> C2 -> C3` із предикатами `RANGE [10, 1000]`, `GT 10`, `>= 1`, `!= 2`, діями `INC`, `DEC`, `ASSIGN` та відсіканням каскаду за інваріантом `C2 >= 0`) і 4-ступеневий каскад `ChainToCid0` (`C3 -> C2 -> C1 -> C0` із ціллю `CID 0` та `ADD 5`) у 1024-байтний образ `CME-RAW-1`. Згенеровані образи виконуються без зміни RTL як на базовому однобанковому конвеєрі [`kpol_bram_pipeline_axi.sv`](../../../hw/rtl/bus/kpol_bram_pipeline_axi.sv) (`CFG-P`), так і на двобанковому конвеєрі високої готовності [`kpol_bram_pipeline_axi_ha.sv`](../../../hw/rtl/bus/kpol_bram_pipeline_axi_ha.sv) (`CFG-P-HA`, включно з гарячим оновленням правил через тіньовий банк `0x030..0x038`).
   * **Контур 3 (`KPOL-AUTH`):** CLI `python3 -m kpol_auth <input> --check --emit-bram <bram.bin> --emit-dogo <dogo.json|.bin>` ([`Engineering/sw/kpol-auth/__main__.py`](../../../sw/kpol-auth/__main__.py), [`lowering.py`](../../../sw/kpol-auth/lowering.py)) транслює підтримувану підмножину (`Concept` + `•` + `OnPositive` + `OnAbort` на графах `THERMAL_GRAPH_SOURCE` та `AUTH_CASCADE_4STAGE_SOURCE`) у 1024-байтний образ маршрутизації `CME-RAW-1` та 32-бітний байткод стекової ВМ `Do/Go` (`code_o`), сумісний із `km_mcu_fpga_bridge.c`.
3. **Пункт 3 чекліста — Негативні та мутантні контролі, що вміють впасти (`AGENTS.md §4.1`):**
   * детерміноване відхилення позапрофільних конструкцій до емісії вихідного файлу: `B3-SYNTAX`, `B3-TYPE`, `B3-GUARD`, `B3-ACTION`, `B3-PROOF` у `KPOL-CME-1`; `CME2-OPERAND-COLLISION` і `CME2-CASCADE` (2-вузловий цикл, самопетля, `fan-out = 2`) у `KPOL-CME-2`; `KPOL-LOWER-CYCLE` (самопетля `C0 -> C0`, 2-вузловий цикл `A <-> B`, зворотний ранг `dst_cid <= src_cid`) та всі 12 точок невизначеності `KPOL-AUTH-U01..U12` у `KPOL-AUTH`;
   * **7 явних мутантних контролів (`M1..M5`)** у `test_s5_negative_and_mutant_controls_hmac_rtl_vm_and_cycles` (деталізовано у §3.2).

---

## 3. Результати

Первинні дані прогону збережено в [`raw/s5_acceptance_summary.json`](raw/s5_acceptance_summary.json) (SHA-256 `0c68726bbdc34a70ea7e86a9ed9410629594064ecaf9825b27a5b15cdc95aae4` / перераховано детерміновано) та [`raw/s5_acceptance_run.log`](raw/s5_acceptance_run.log) (містить заголовок `# cmd:`, `# timestamp: 2026-11-17T12:39:36+02:00`, `# git_base_sha: 467cd4e13c2812d5fe3b1be004110864e11448ba`, `# host: Linux 7.0.0-42-generic x86_64`).

### 3.1. Зведена таблиця наскрізної верифікації трьох контурів компілятора S5

| Контур / профіль | Вхідні програми | Вихідні артефакти компілятора (`SHA-256`) | Перевірений виконавець (`[rtl_simulation]` / `[software_vm]`) | Збіжність станів і телеметрії | Перевірені коди відмов до емісії файлу (`[negative_control]`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`KPOL-CME-1`** (`compile_kpol_bram_image.py --profile KPOL-CME-1` + `Secure Boot`) | `SingleCme1`, `increase.kpol`, `decrease.kpol` | `CME-RAW-1` (`1024 Б`):<br>`SingleCme1`: `da1d69c5...` (ідентичний golden `cme1_single_ca9dbb3.bin`);<br>`increase`: `4df05b18...`;<br>`decrease`: `00ba66e5...`;<br>`Secure Boot`: `1088 Б` (`v0x0006`, HMAC-SHA256) | `Interpreter` $\leftrightarrow$ `kpol_bram_pipeline_axi.sv` (`CFG-P`, `iverilog 12.0`) | `64/64` слотів `W0..W3` побітово тотожні; `events=4, commits=3, rejects=1`, `W0[0]=11` (`increase`) і `W0[0]=9` (`decrease`) | `B3-SYNTAX`, `B3-TYPE`, `B3-GUARD`, `B3-ACTION`, `B3-PROOF` (`returncode = 2`, файл не створюється) |
| **`KPOL-CME-2`** (`compile_kpol_bram_image.py --profile KPOL-CME-2`) | `Cascade4Stage` (`C0->C1->C2->C3`), `ChainToCid0` (`C3->C2->C1->C0`) | `CME-RAW-1` (`1024 Б`):<br>`Cascade4Stage`: `fbab4381...`;<br>`ChainToCid0`: `ce744c95...` | `Interpreter` $\leftrightarrow$ `kpol_bram_pipeline_axi.sv` (`CFG-P`) $\leftrightarrow$ `kpol_bram_pipeline_axi_ha.sv` (`CFG-P-HA` + гарячий swap `0x030..0x038`) | `64/64` слотів `W0..W3` побітово тотожні в усіх 3 виконавцях (`Cascade4Stage`: `events=13, commits=10, rejects=3`; `CFG-P-HA`: `swap_count=1`, `seq_mon=8`, `0` колізій і `0` stall-тактів) | `CME2-OPERAND-COLLISION`, `CME2-CASCADE` (2-цикл, самопетля, `fan-out=2`) (`returncode = 2`, файл не створюється) |
| **`KPOL-AUTH`** (`python3 -m kpol_auth` + `lowering.py`) | `THERMAL_GRAPH_SOURCE` (`4` концепти), `AUTH_CASCADE_4STAGE_SOURCE` (`4` концепти) | `CME-RAW-1` (`1024 Б`):<br>`thermal`: `6ef255e1...` (`18` слів `Do/Go`);<br>`cascade4_auth`: `e061db20...` (`15` слів `Do/Go`) | `ReferenceDoGoVM` (`[software_vm]`) + структурна перевірка `CME-RAW-1` (`W0..W3`) | Штатні каскади (`[25, 50, 50, 0]`, `[30, 80, 100, 0]`) та перехоплення відмови інваріанта `OnAbort` (`big_dot_ok[1]=1`, `[45, 50, 100, 1]`, `[200, 80, 100, 1]`) | `KPOL-LOWER-CYCLE` (самопетля, 2-цикл, `dst_cid <= src_cid`), `KPOL-LOWER-FANOUT`, усі 12 гейтів `KPOL-AUTH-U01..U12` |

Загальний результат об'єднаного тестового прогону у [`raw/s5_acceptance_run.log`](raw/s5_acceptance_run.log): **`93 passed, 391 subtests passed in 4.07s`** (`exit_code = 0`), та окремо приймального пакета `test_s5_compiler_acceptance_8.py` — **`5 passed in 2.35s`**.

### 3.2. Результати мутантних та негативних контролів (`AGENTS.md §4.1`)

| Ідентифікатор мутанта | Внесене пошкодження / дефект | Об'єкт перевірки | Спостережувана реакція тесту | Статус |
| :--- | :--- | :--- | :--- | :--- |
| **`M1_secure_boot_hmac_byte_tamper_and_replay`** | Інверсія 1 біта у байтах `20` (`nonce`), `40` (`auth_tag`), `64`, `512`, `1087` (`CME-RAW-1` payload) 1088-байтного контейнера та повторна подача валідного контейнера | `verify_bram_signature` (`kpol_reference.py`) | Усі 5 пошкоджених контейнерів відхилено (`Cryptographic tag mismatch`) зі збереженням `len(seen_nonces) == 0`; повтор валідного контейнера відхилено (`Replay attack detected`) | **Killed** |
| **`M2a_bram_action_opcode_inc_to_dec_rtl_divergence`** | Підміна `action_opcode` у байті `11` (`CID 0`, `W2[31:24]`) згенерованого образу `CME-RAW-1` з `INC (0x01)` на `DEC (0x02)` | Симуляція `kpol_bram_pipeline_axi.sv` (`CFG-P`) та `kpol_bram_pipeline_axi_ha.sv` (`CFG-P-HA`) проти `Interpreter` | Обидва RTL-конвеєри видають `W0[0] = 9` замість еталонного `11` в `Interpreter`; перевірка еквівалентності фіксує розбіжність | **Killed** |
| **`M2b_bram_threshold_w1_10_to_50_rtl_divergence`** | Підміна порога охоронця `W1` (`CID 1`, зміщення `20 Б`) у згенерованому образі `CME-RAW-1` з `GT 10` на `GT 50` | Симуляція `kpol_bram_pipeline_axi.sv` (`CFG-P`) та `kpol_bram_pipeline_axi_ha.sv` (`CFG-P-HA`) проти `Interpreter` | Каскад зупиняється на `CID 1` (`rejects = 1` у RTL проти `rejects = 0` в `Interpreter`); перевірка еквівалентності фіксує розбіжність | **Killed** |
| **`M3a_dogo_opcode_add_to_sub_vm_divergence`** | Підміна інструкції `KM_DO_ADD` на `KM_DO_SUB` у згенерованому масиві `code_o` | `ReferenceDoGoVM` (`KPOL-AUTH`) | Стан після події `Temp=25` дорівнює `[25, 0, 0, 0]` замість `[25, 50, 50, 0]`; асерт станів фіксує розбіжність | **Killed** |
| **`M3b_dogo_missing_exit_opcode_vm_abort`** | Заміна термінатора лінії підписки `KM_OPC_EXIT (0x5)` на `KM_OPC_NOP (0x0)` у `code_o` | `ReferenceDoGoVM` (`KPOL-AUTH`) | Виконання підписки аварійно переривається з `AssertionError` | **Killed** |
| **`M4_bram_cycle_validator_stub_caught`** | Заміна `_validate_bram_acyclic` у `kpol_auth.lowering` на порожню заглушку на вході із самопетлею `C0 • Assign(C0, C0 + 1)` | Гейт ациклічності `KPOL-LOWER-CYCLE` (передумова формальної леми `P2`) | Із заглушкою цикл проходить у 1024-Б образ, а незмінений код гарантовано підіймає `KPOL-LOWER-CYCLE` до емісії | **Killed** |
| **`M5_uncertainty_gate_stub_caught`** | Заміна `emit_uncertainty` у `kpol_auth.lexer` на порожню заглушку на вході `#legacy_comment` | Гейт невизначеності `KPOL-AUTH-U05` | Із заглушкою заборонена конструкція проходить без помилки, а незмінений код гарантовано підіймає `KPOL-AUTH-U05` | **Killed** |

---

## 4. Перевірка гіпотези / критеріїв приймання Issue #8

| Критерій батьківської Issue #8 | Очікувано | Отримано | Висновок |
| :--- | :--- | :--- | :--- |
| **1. Консолідована специфікація KPOL** | Узгоджені контракти мови та профілів компіляції з явними межами | Наявні й узгоджені [`kpol-consolidated-0.1.0.md`](../../../specifications/kpol/kpol-consolidated-0.1.0.md), [`kpol-cme-subset-0.1.0.md`](../../../specifications/kpol/kpol-cme-subset-0.1.0.md), [`kpol-cme2-profile-0.1.0.md`](../../../specifications/kpol/kpol-cme2-profile-0.1.0.md) та [`kpol-auth-subset-0.1.0.md`](../../../specifications/kpol/kpol-auth-subset-0.1.0.md) | **Виконано** |
| **2. Текст KPOL → образ BRAM / байткод без ручного RTL** | Автоматична генерація 1024-Б образу `CME-RAW-1` (+ опційний 1088-Б `Secure Boot`) та 32-бітного `Do/Go` байткоду, що виконуються на незмінному RTL / ВМ | Підтверджено для `KPOL-CME-1`, `KPOL-CME-2` (на `kpol_bram_pipeline_axi.sv` і `kpol_bram_pipeline_axi_ha.sv`) та `KPOL-AUTH` (`ReferenceDoGoVM` + `CME-RAW-1`) | **Виконано** |
| **3. Тести компілятора, що можуть впасти (без бутафорії)** | Наявність негативних корпусів і мутантних контролів для підпису, опкодів, порогів, циклів і гейтів `U01..U12` | Усі 7 мутантів `M1..M5` і негативні тести `B3-*`, `CME2-*`, `KPOL-LOWER-*`, `KPOL-AUTH-U01..U12` детерміновано ловлять дефекти (`93 passed, 391 subtests passed`) | **Виконано** |
| **4. Report + Review Report** | Оформлений звіт WP із сирими даними та передача PR на рецензію іншому агенту | Сформовано цей звіт, [`raw/s5_acceptance_summary.json`](raw/s5_acceptance_summary.json) та [`raw/s5_acceptance_run.log`](raw/s5_acceptance_run.log); PR передається на рецензію `claude-sonnet-5.5` | **Виконано (очікує рецензії PR)** |

---

## 5. Відтворення

```bash
# Генерація зведеного JSON приймальної перевірки S5:
python3 Engineering/sw/tests/test_s5_compiler_acceptance_8.py \
  --emit-summary Engineering/validation/kpol-cme/s5-compiler-8/raw/s5_acceptance_summary.json

# Запуск приймального пакета S5 (#8) та всіх тестів компілятора KPOL:
python3 -m pytest -v Engineering/sw/tests/test_s5_compiler_acceptance_8.py \
  Engineering/sw/kpol-ref/tests/test_kpol_reference.py \
  Engineering/sw/kpol-auth/tests/

# Повна перевірка репозиторію:
python3 -m pytest -q
KM_DRAFTS_REPO=/home/mfedchyk/GitHub/nick-fedchik/drafts python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
git diff --check origin/main
```

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-17 | Перша редакція консолідованого звіту приймальної верифікації кроку S5 ([#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8)): наскрізна перевірка `KPOL-CME-1`, `KPOL-CME-2` (на `CFG-P` і двобанковому `CFG-P-HA`) та підмножини `KPOL-AUTH` (`Do/Go` + `CME-RAW-1`), 7 мутантних контролів `M1..M5` і фіксація відкритих меж `#186` та `ADR B7`. |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| BRAM | Block RAM — вбудована двопортова блокова пам'ять ПЛІС (`RAMB36E1`). |
| `CFG-P` / `CFG-P-HA` | Базова однобанкова (`kpol_bram_pipeline_axi.sv`) та двобанкова високої готовності (`kpol_bram_pipeline_axi_ha.sv`) конфігурації апаратного конвеєра дескрипторів. |
| `CME-RAW-1` | Чинний 1024-байтний ($64 \times 16$ Б) двійковий формат таблиці концептних дескрипторів `W0..W3`. |
| CST | Concrete Syntax Tree — дерево конкретного синтаксису з точними координатами `Span`. |
| DAG | Directed Acyclic Graph — спрямований ациклічний граф підписок концептів. |
| HIL | Hardware-in-the-Loop — випробування на фізичній апаратній платі (у цьому звіті не виконувалося). |
| KPOL | Kuzmin Problem-Oriented Language — проблемно-орієнтована мова програмування Машини Кузьміна. |
| WP | Work Product — робочий продукт проєкту з визначеним призначенням. |
