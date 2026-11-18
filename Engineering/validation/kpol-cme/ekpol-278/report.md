# Звіт про верифікацію мови EKPOL (Ergonomic KPOL 0.1.0), двостороннього транслятора EKPOL <-> KPOL та оновлення Go VMK v0.2.0

* **Версія:** 1.0.1
* **Дата:** 2026-11-18
* **Тип WP:** Report
* **Статус:** Запропоновано на затвердження власником (Proposed)
* **ASPICE 4.0 процеси:** `SWE.4` (Software Unit Verification), `SWE.5` (Software Component Verification and Integration), `SWE.6` (Software Verification)
* **Issue:** `Closes` [#278](https://github.com/nick-fedchik/kuzmin-machine/issues/278); пов'язані задачі [#276](https://github.com/nick-fedchik/kuzmin-machine/issues/276), [#274](https://github.com/nick-fedchik/kuzmin-machine/issues/274), [#272](https://github.com/nick-fedchik/kuzmin-machine/issues/272), [#270](https://github.com/nick-fedchik/kuzmin-machine/issues/270), [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186).
* **Відповідальний:** власник Микола Федчик; укладач — GitHub Copilot CLI (Lead Engineer / Programming Language Architect).
* **Рецензент:** `claude-sonnet-5.5` ([Review Report у PR #279](https://github.com/nick-fedchik/kuzmin-machine/pull/279#issuecomment-6978746030), вердикт «Прийнято із зауваженнями»; зауваження `F1..F4` усунено у версії `1.0.1`).
* **Нормативна специфікація:** [`Engineering/specifications/kpol/ekpol-specification.md`](../../../specifications/kpol/ekpol-specification.md) (`1.0.1`).
* **Верифіковані модулі та тести:** [`Engineering/sw/kpol-ref/ekpol_frontend.py`](../../../sw/kpol-ref/ekpol_frontend.py), [`Engineering/hw/scripts/compile_kpol_bram_image.py`](../../../hw/scripts/compile_kpol_bram_image.py), [`Engineering/sw/kpol-ref/kpol_debugger.py`](../../../sw/kpol-ref/kpol_debugger.py), [`Engineering/sw/vmk-go/`](../../../sw/vmk-go/README.md) (`v0.2.0`), [`Engineering/sw/tests/test_ekpol_278.py`](../../../sw/tests/test_ekpol_278.py).
* **Сирі логи та артефакти:** [`Engineering/validation/kpol-cme/ekpol-278/raw/`](raw/ekpol_ergonomics_and_sha256.json) ([`ekpol_ergonomics_and_sha256.log`](raw/ekpol_ergonomics_and_sha256.log), [`go_test_v020.log`](raw/go_test_v020.log), [`pytest_ekpol_278.log`](raw/pytest_ekpol_278.log), [`pytest_ekpol_278_rerun_a19bca2.log`](raw/pytest_ekpol_278_rerun_a19bca2.log)).

---

## 1. Обмеження, межі застосування та що не заявляється (`AGENTS.md §3`, `AGENTS.md §4 п. 2`)

Відповідно до правил [`AGENTS.md §3–4`](../../../../AGENTS.md) звіт починається з явного переліку обмежень і того, що **не виконувалося** в межах цієї задачі:
1. **Незмінність апаратного ядра RTL та двійкового формату `CME-RAW-1`:** у межах Issue [#278](https://github.com/nick-fedchik/kuzmin-machine/issues/278) не змінювалися жодні файли SystemVerilog (`Engineering/hw/rtl/*.sv`) і не вводився 32-байтний формат дескриптора `CME-RAW-2` ([#185](https://github.com/nick-fedchik/kuzmin-machine/issues/185)). Апаратні обмеження 16-байтного слота `CME-RAW-1` (єдине 32-бітне поле `W1 = operand_val` для літерала предиката або кроку `ADD`/`SUB` $\ge 2$, знаковий тип `Int32`, однослотовий підписник `subscriber_cid`) залишаються чинними для режиму `--mode bram64` і контролюються статичним верифікатором `validate_ekpol_for_bram64` (`EKPOL-COLLISION-ERR`, `EKPOL-CYCLE-ERR`, `EKPOL-TYPE-ERR`).
2. **Незмінність класичного KPOL та відкритих авторських питань `KPOL-AUTH-U01..U12`:** жоден існуючий файл `.kpol` (`kpol_bram_pipeline_increase.kpol`, `kpol_bram_pipeline_decrease.kpol`, `bms_safety_cascade.kpol`) не змінювався (`0` рядків diff). Дванадцять відкритих питань авторського native-діалекту `KPOL-AUTH-U01..U12` у [`Engineering/sw/kpol-auth/`](../../../sw/kpol-auth/__init__.py) залишаються заблокованими за принципом `fail-closed` до відповідей Автора концепції М. Ю. Кузьміна в межах [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186).
3. **Походження доказів (`AGENTS.md §4 п. 2, п. 4`):** верифікація `EKPOL 0.1.0` та `VMK v0.2.0` у цьому звіті виконана на програмних компіляторах/транспайлерах Python (`3.14.4`) і Go (`go1.27.1 linux/amd64`), компіляторі `gcc` (`C99`), вирішувачі `Z3 SMT` (`QF_LIA + QF_BV BitVec32`) та симуляторі `Icarus Verilog` на хості `workstation` (`x86_64 GNU/Linux`, базовий коміт `c49869a`, коміт реалізації `a19bca2157ec1a6fd632b7bcd9b34654a96adea0`). Новий синтез бітстріму FPGA або прямий апаратний прогін `.ekpol` на платі у межах [#278](https://github.com/nick-fedchik/kuzmin-machine/issues/278) не проводився, оскільки згенеровані з `.ekpol` 1024-байтні образи BRAM є **побітово ідентичними (100% збіг SHA-256)** образам класичного `.kpol`, які раніше пройшли натурну HIL-верифікацію на платі `PYNQ-Z1` (`pynq2`, див. [`Engineering/validation/kpol-cme/vmk-go-274/report.md`](../vmk-go-274/report.md)).

---

## 2. Критерії приймання та зведені результати перевірки (`AGENTS.md §4 п. 2`)

Критерії приймання були зафіксовані в описі Issue [#278](https://github.com/nick-fedchik/kuzmin-machine/issues/278) до початку реалізації:

| № | Критерій приймання Issue #278 | Артефакт / Команда перевірки | Фактичний результат | Статус (`AGENTS.md §4 п. 2`) |
| :--- | :--- | :--- | :--- | :--- |
| **C1** | 100% збереження класичних профілів `KPOL-CME-1`, `KPOL-CME-2`, `KPOL-AUTH` та існуючих файлів `.kpol` | `git diff origin/main -- "*.kpol"` + `test_classic_kpol_files_unmodified_and_sha256_preserved` | `0` змінених файлів `.kpol`; усі класичні SHA-256 збережено | **PASS (програмна компіляція / симуляція VMK, без запуску на FPGA)** |
| **C2** | Специфікація EBNF-граматики `EKPOL 0.1.0` (символьна ASCII + ключова нотація) | [`Engineering/specifications/kpol/ekpol-specification.md`](../../../specifications/kpol/ekpol-specification.md) (`1.0.1`, `Specification`) | Задокументовано повну EBNF, таблицю еквівалентності та коди `EKPOL-*-ERR` | **PASS (програмна компіляція / симуляція VMK, без запуску на FPGA)** |
| **C3** | Побітова ідентичність (SHA-256) 1024-байтних образів BRAM між `.kpol` та `.ekpol` (`symbolic` і `keyword`) у Python та Go `VMK v0.2.0` | `test_ekpol_bit_identical_bram_and_bidirectional_roundtrip_python_and_go`, `TestEKPOLBRAMBitIdenticalSHA256AndRoundtrip` | `4 / 4` канонічних BRAM-програм (`increase`, `decrease`, `cascade`, `bms`) мають 100% збіг SHA-256 | **PASS (програмна компіляція / симуляція VMK, без запуску на FPGA)** |
| **C4** | Двостороння безвтратна трансляція `KPOL <-> EKPOL` (`--emit-kpol`, `--emit-ekpol`, `--to-kpol`, `--to-ekpol`) та генерація `--emit-c99` / `--emit-z3-cert` із `.ekpol` | `test_compile_cli_c99_z3_and_debugger_on_ekpol` | Roundtrip `KPOL -> EKPOL -> KPOL -> BRAM` без втрати семантики; Z3 `passed: true` | **PASS (програмна компіляція / симуляція VMK, без запуску на FPGA)** |
| **C5** | Виконання всіх 9 канонічних прикладів `Engineering/sw/vmk-go/examples/*.ekpol` у Go `VMK v0.2.0` (`bram64` + `conceptual`) | `test_all_nine_ekpol_examples_in_vmk_v020`, `TestEKPOLConceptualExamplesAndPostReadBarrier` | Усі 9 прикладів (`bms`, `cascade`, `increase`, `decrease`, `if`, `sum`, `nod`, `factorial`, `tachometer`) виконуються з кодом `0` | **PASS (програмна компіляція / симуляція VMK, без запуску на FPGA)** |
| **C6** | П'ять мутаційних тестів `M1..M5` за критерієм Issue #278 та `AGENTS.md §4 п. 1` | `test_mutants_m1_to_m5_all_killed` ([`pytest_ekpol_278.log`](raw/pytest_ekpol_278.log), [`pytest_ekpol_278_rerun_a19bca2.log`](raw/pytest_ekpol_278_rerun_a19bca2.log)) | `5 / 5` мутантів детерміновано вбиті (`M1..M5 KILLED`) | **PASS (програмна компіляція / симуляція VMK, без запуску на FPGA)** |

---

## 3. Побітова ідентичність образів BRAM (`SHA-256`) та порівняльна таблиця ергономіки

Дані отримані автоматизованим бенчмарком ([`raw/ekpol_ergonomics_and_sha256.json`](raw/ekpol_ergonomics_and_sha256.json), [`raw/ekpol_ergonomics_and_sha256.log`](raw/ekpol_ergonomics_and_sha256.log), базовий коміт `c49869a`, коміт прогону `a19bca2157ec1a6fd632b7bcd9b34654a96adea0`, хост `workstation x86_64 GNU/Linux`).

### 3.1. Побітова ідентичність 1024-байтних образів `CME-RAW-1`

| Програма | Класичний профіль | Незмінний `SHA-256` 1024-байтного образу BRAM (`CME-RAW-1`) | Збіг `.kpol` == `.ekpol (symbolic)` == `.ekpol (keyword)` (Python & Go `v0.2.0`) |
| :--- | :--- | :--- | :--- |
| **`Increase`** ([`increase.ekpol`](../../../sw/vmk-go/examples/increase.ekpol)) | `KPOL-CME-1` | `4df05b189b9bf12052d98ab6084e0256454c60cae4afd4449469c060ba8dcc5d` | **100% (`1024 / 1024 B`)** |
| **`Decrease`** ([`decrease.ekpol`](../../../sw/vmk-go/examples/decrease.ekpol)) | `KPOL-CME-1` | `00ba66e57e21d14913c95d7d2fc8c45c3c450548510ca3155721d7eec67b78c3` | **100% (`1024 / 1024 B`)** |
| **`Cascade4Concept`** ([`cascade_4concept.ekpol`](../../../sw/vmk-go/examples/cascade_4concept.ekpol)) | `KPOL-CME-2` | `032c4705c91cea6ddddb7d449cd0dcbd6ba62359af1f9e7a846f33c341a7ef38` | **100% (`1024 / 1024 B`)** |
| **`BmsSafetyCascade`** ([`bms_safety_cascade.ekpol`](../../../sw/vmk-go/examples/bms_safety_cascade.ekpol)) | `KPOL-CME-2` | `de03442454424b5cf64478506f118c13f095ae24ba58db8894583c43567ea3ee` | **100% (`1024 / 1024 B`)** |

### 3.2. Порівняльна таблиця ергономіки (`Класичний KPOL-CME-1/2` та `KPOL-AUTH` проти `EKPOL 0.1.0`)

| Програма / Приклад | Нотація | Рядків коду (`LOC`, без порожніх/коментарів) | Кількість лексичних токенів | Обсяг тексту (символів) | Кількість не-ASCII символів (`•`, `¬`, `←`, `→`) | Скорочення обсягу коду (символів) проти `KPOL-CME` |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`Increase`** (1 концепт) | Класичний `KPOL-CME-1` | `10` | `46` | `229` | `0` | базова лінія |
| **`Increase`** (1 концепт) | **`EKPOL 0.1.0` (`symbolic`)** | **`6` (`-40.0%`)** | **`29` (`-37.0%`)** | **`122`** | **`0`** | **`-46.7%`** |
| **`Increase`** (1 концепт) | **`EKPOL 0.1.0` (`keyword`)** | **`6` (`-40.0%`)** | **`30` (`-34.8%`)** | **`132`** | **`0`** | **`-42.4%`** |
| **`Cascade4Concept`** (4 концепти + тест) | Класичний `KPOL-CME-2` | `31` | `202` | `851` | `0` | базова лінія |
| **`Cascade4Concept`** (4 концепти + тест) | **`EKPOL 0.1.0` (`symbolic`)** | **`28` (`-9.7%`)** | **`145` (`-28.2%`)** | **`531`** | **`0`** | **`-37.6%`** |
| **`Cascade4Concept`** (4 концепти + тест) | **`EKPOL 0.1.0` (`keyword`)** | **`28` (`-9.7%`)** | **`158` (`-21.8%`)** | **`601`** | **`0`** | **`-29.4%`** |
| **`BmsSafetyCascade`** (4 концепти + тест) | Класичний `KPOL-CME-2` | `49` | `252` | `1849` | `0` | базова лінія |
| **`BmsSafetyCascade`** (4 концепти + тест) | **`EKPOL 0.1.0` (`symbolic`)** | **`38` (`-22.4%`)** | **`201` (`-20.2%`)** | **`1226`** | **`0`** | **`-33.7%`** |
| **`BmsSafetyCascade`** (4 концепти + тест) | **`EKPOL 0.1.0` (`keyword`)** | **`38` (`-22.4%`)** | **`214` (`-15.1%`)** | **`1296`** | **`0`** | **`-29.9%`** |
| **`If` / `Sum`** (слайди Автора) | Авторський запис (`KPOL-AUTH`) | `3..4` | `14..15` | `48..50` | **`2..3` (`¬`, `←`, `→`, `•`)** | вимагає спецсимволів Unicode |
| **`If` / `Sum`** ([`if_toggle.ekpol`](../../../sw/vmk-go/examples/if_toggle.ekpol), [`sum_autoreset.ekpol`](../../../sw/vmk-go/examples/sum_autoreset.ekpol)) | **`EKPOL 0.1.0` (з блоком `test`)** | **`13..14`** | **`73..80`** | **`319..358`** | **`0` (100% 7-bit ASCII)** | набирається на стандартній клавіатурі |

---

## 4. Результати мутаційного тестування (`M1..M5`, критерій C6 Issue #278 та `AGENTS.md §4 п. 1`)

Згідно з правилом `AGENTS.md §4 п. 1` («Тест має вміти впасти») та критерієм приймання C6 Issue [#278](https://github.com/nick-fedchik/kuzmin-machine/issues/278), у [`Engineering/sw/tests/test_ekpol_278.py`](../../../sw/tests/test_ekpol_278.py) реалізовано та виконано 5 цільових мутантів ([`raw/pytest_ekpol_278.log`](raw/pytest_ekpol_278.log), [`raw/pytest_ekpol_278_rerun_a19bca2.log`](raw/pytest_ekpol_278_rerun_a19bca2.log)):

| ID мутанта | Цільовий модуль і мутована ділянка | Опис дефекту | Чим і як перехоплено | Вердикт |
| :--- | :--- | :--- | :--- | :--- |
| **`M1_ekpol_cycle_detection`** | `ekpol_frontend.py` (`validate_ekpol_for_bram64`: вимкнення перевірки `visit_state[cur] == 1`) | Пропуск циклу підписок `C0 -> C1 -> C0` у режимі `bram64` | Перевірка відхилення циклічної програми з кодом `EKPOL-CYCLE-ERR` | **KILLED** |
| **`M2_ekpol_range_bounds_swap`** | `ekpol_frontend.py` (`validate_ekpol_for_bram64`: заміна місцями `pred.lo` та `pred.hi` при пакуванні `W1`) | Неправильне пакування меж діапазону `in 50..5000` у 32-бітне слово `W1` | Незбіжність контрольної суми `SHA-256` 1024-байтного образу BRAM із еталоном `de034424...` | **KILLED** |
| **`M3_ekpol_keyword_vs_symbolic_divergence`** | `ekpol_frontend.py` (`transpile_kpol_to_ekpol`: заміна `on change(...)` на `on write(...)` у `keyword`-стилі) | Розходження семантики між символьною (`~`) та ключовою (`on change`) нотаціями | Перевірка побітової рівності образів BRAM, скомпільованих зі стилів `symbolic` та `keyword` | **KILLED** |
| **`M4_ekpol_post_read_dot_order`** | `Engineering/sw/vmk-go/internal/vmk/ekpol.go` (`parseEKPOLConceptRule`: скидання `PostReadBarrier: false`) | Ігнорування пост-адресного бар'єра Великої Крапки після читання (`-> => . Sum = 0` / `on read => after Sum = 0;`) | Падіння `TestEKPOLConceptualExamplesAndPostReadBarrier` під час запуску `go test ./...` (`postReadState = 35 != 0`) | **KILLED** |
| **`M5_ekpol_invariant_bracket_drop`** | `ekpol_frontend.py` (`validate_ekpol_for_bram64`: вилучення біта `CME_GUARD_INVARIANT_EN` при парсингу `[>= 0]`) | Вимкнення апаратного вентиля інваріанта Великої Крапки в `W2` | Незбіжність `SHA-256` образу BRAM та відмова формальної верифікації Z3 (`P2_invariant_preservation_all_bv32: passed = False`) | **KILLED** |

---

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 1.0.1 | 2026-11-18 | Ураховано всі 4 зауваження рецензії `claude-sonnet-5.5` у PR #279 (`F1..F4`): замінено посилання на `AGENTS.md §4 п. 1` та `AGENTS.md §4 п. 2` (`F1`); зафіксовано SHA коміту `a19bca2157ec1a6fd632b7bcd9b34654a96adea0` у звіті та сирих логах `raw/*` (`F2`); перейменовано тест на `test_all_nine_ekpol_examples_in_vmk_v020` з охопленням усіх 9 прикладів (`F3`); додано явну позначку `PASS (програмна компіляція / симуляція VMK, без запуску на FPGA)` до вердиктів таблиці §2 (`F4`). |
| 1.0.0 | 2026-11-18 | Первинний випуск звіту про верифікацію мови `EKPOL 0.1.0`, двостороннього транслятора `EKPOL <-> KPOL` та Go `VMK v0.2.0` за Issue [#278](https://github.com/nick-fedchik/kuzmin-machine/issues/278). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| **EKPOL** | Ergonomic KPOL (`0.1.0`) — ергономічна концептно-орієнтована мова програмування Машини Кузьміна у 7-бітному ASCII з символьною та ключовою нотаціями. |
| **CME-RAW-1** | 1024-байтний двійковий формат таблиці 64 дескрипторів концептів по 16 байтів (`W0..W3`) для апаратного конвеєра `CFG-P`. |
| **LOC** | Lines of Code — кількість непорожніх рядків коду без коментарів. |
| **VMK** | Virtual Machine of Kuzmin — двомодовий емулятор, транспайлер і 4-панельний TUI-дебагер на Go (`Engineering/sw/vmk-go`, `v0.2.0`). |
| **WP** | Work Product — робочий продукт інженерного процесу за ASPICE 4.0. |
