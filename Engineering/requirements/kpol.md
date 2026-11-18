# Вимоги KPOL: RFC та авторські поняття й синтаксис

* **Версія:** 0.10.0
* **Дата:** 2026-11-18
* **Тип WP:** Requirement / SYS / SW
* **Відповідальний:** власник Микола Федчик; укладач — GitHub Copilot CLI, Auto.
* **WI:** [#150](https://github.com/nick-fedchik/kuzmin-machine/issues/150), [#151](https://github.com/nick-fedchik/kuzmin-machine/issues/151), [#155](https://github.com/nick-fedchik/kuzmin-machine/issues/155), [#157](https://github.com/nick-fedchik/kuzmin-machine/issues/157), [#159](https://github.com/nick-fedchik/kuzmin-machine/issues/159), [#183](https://github.com/nick-fedchik/kuzmin-machine/issues/183), [#184](https://github.com/nick-fedchik/kuzmin-machine/issues/184), [#185](https://github.com/nick-fedchik/kuzmin-machine/issues/185), [#218](https://github.com/nick-fedchik/kuzmin-machine/issues/218), [#219](https://github.com/nick-fedchik/kuzmin-machine/issues/219), [#227](https://github.com/nick-fedchik/kuzmin-machine/issues/227), [#237](https://github.com/nick-fedchik/kuzmin-machine/issues/237), [#243](https://github.com/nick-fedchik/kuzmin-machine/issues/243), [#245](https://github.com/nick-fedchik/kuzmin-machine/issues/245), [#252](https://github.com/nick-fedchik/kuzmin-machine/issues/252), [#255](https://github.com/nick-fedchik/kuzmin-machine/issues/255), [#270](https://github.com/nick-fedchik/kuzmin-machine/issues/270), [#272](https://github.com/nick-fedchik/kuzmin-machine/issues/272), [#274](https://github.com/nick-fedchik/kuzmin-machine/issues/274), [#278](https://github.com/nick-fedchik/kuzmin-machine/issues/278), закриття S5 у [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8) (відкрита межа native RFC — [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186)).
* **Потреба:** G1/N1 — визначені правила; G1/N2 — текст KPOL → виконуваний образ.
* **Підстава:** команди власника 2026-11-12 щодо RFC та 2026-11-13 щодо нового авторського матеріалу й релевантних WP.
* **Погодження:** профіль KPOL-CME-1 — Decision B3-01; ця деталізація на рецензію, не прийнята системна baseline.
* **Пріоритет:** P1 для профільного компілятора за WI; інші розширення не пріоритизовано.

## 1. Походження та межі

Джерело уточнень — [картка авторських відповідей](../../Research/sources/author/rfc-2026-11-12.md);
її межі автентичності й повноти збережено. Це похідні вимоги проєкту,
не повна специфікація М. Ю. Кузьміна.
Наявний ширший референс не звужується до CME. Для виконуваного образу
діє [KPOL-CME-1 / CME-RAW-1](../specifications/kpol/kpol-cme-subset-0.1.0.md).
Нові ID нижче введено в #150; вони не замінюють успадковані `REQ-*`.
У #155 додано [нову презентацію / Source](../../Research/sources/author/introduction-2026-11-13.md)
та окремі кандидати `KPOL-AUTH-*` для повного native шляху.
Вони не змінюють погоджений KPOL-CME-1, чинний DSL або RFC-записи.
Докладне зіставлення й `Q-AUTH-*` —
у [Report #155](../../Research/studies/author-semantics/kpol-syntax-155-report.md).
Редакцію Static й окремі передані уточнення 2026-11-13 оцінено у
[Report #157](../../Research/studies/author-semantics/kpol-syntax-157-report.md).
Його входи — [новий PPTX](../../Research/sources/author/introduction-revision-2026-11-13.md)
та [окрема Source-картка відповідей](../../Research/sources/author/clarifications-2026-11-13.md).
Нижче тепер вісім Proposed AUTH-кандидатів; новий AUTH-08 не є
погодженням native baseline або розширенням чинного профілю.
[Окремий фрагмент #159](../../Research/sources/author/group-execution-2026-11-13.md)
уточнює залежність Min/Max від типу над-/підрядкових значень;
[Report #159](../../Research/studies/author-semantics/kpol-syntax-159-report.md)
переоцінює AUTH-03/Q-AUTH-01 без додавання нового AUTH-ID.

## 2. Системні правила та їх виділення

| ID / походження | Формулювання та обґрунтування | Критерій / метод | Реалізація / стан |
|---|---|---|---|
| KPOL-SYS-01 / RFC-005 | При кожній адресації концепту виконавець повинен повторно перевіряти його події з урахуванням зайнятості підписки; порівняння не підміняється edge-фільтром. | Повторні адресації за істинного предиката; окремо busy до `•`. Потактовий/трасовий тест майбутнього виконавця. | Повна адресаційна модель поза KPOL-CME-1; референс перевіряє guard явних подій, не кожне читання. |
| KPOL-SYS-02 / RFC-005 | Для підтримки `_` стан ініціалізації повинен бути відокремлений від числового значення; відомість guard не є станом ініціалізації концепту. | Визначити ABI біта й перевірити неініціалізоване/ініціалізоване значення та підписку `_`. | **Прийнято ADR B7 за Варіантом А (#185, #215) та реалізовано у C99-бекенді безпеки (`valid_mask`, #270):** [ADR B7 / `CME-RAW-2`](../decisions/cme-raw2-kpol-sys02.md) (`W1.state_valid`, [звіт #185](../validation/kpol-cme/cr-cme-raw2-185/report.md)); у програмному генераторі [`c99_emitter.py`](../sw/kpol-ref/c99_emitter.py) (`--emit-c99`, [висновок #270](../../Research/studies/commercialization-and-final-conclusions.md)) реалізовано явну 64-бітну маску визначеності `uint64_t valid_mask` із формальним доказом `Z3` (`P3_no_commit_on_invalid_param_or_state`). У чинному апаратному `CFG-P` (`CME-RAW-1`) `Unknown`-стан відхиляється компілятором і не кодується нулем, а у `KPOL-AUTH` читання `_` у виразах заблоковано `KPOL-AUTH-U10` до відповіді Автора на `RFC-017` п. 3. |
| KPOL-SYS-03 / RFC-006; новий слайд 5 | Якщо підтримано авторський синтаксис, `@` повинен позначати формальні параметри підписки, а не автоматично оператор адреси/розіменування. | Новий Source дає явний локатор; узгодити повну граматику й незалежну очікувану трасу перед реалізацією. | У прототипі [`Engineering/sw/kpol-auth/`](../sw/kpol-auth/__init__.py) вузол `ParamCST` зберігає `@target` без підміни на MMIO-адресу і блокується у lowering (`KPOL-LOWER-UNSUPPORTED-CST` / `KPOL-AUTH-U04`); стекова граматика `@` поза `KPOL-CME-1`/`2`. |
| KPOL-SYS-04 / RFC-007 | При повній черзі породжувач повинен зберегти неприйняту подію до можливості прийняття, не замінювати очікування відкиданням з лічильником. | Повна черга, одночасні каскад/зовнішня подія, один вільний слот; рівно одне виконання збережених подій після розвантаження. | **Реалізовано в RTL та формально доведено для керованих джерел (#151, #227/#237/#242 до $N=16$, #255 для міжбанкового кластера $N=1..8$).** [B5 v2.2.0](../specifications/hw/event-queue-ingress-specification.md), [Report #151](../validation/kpol-cme/queue-retention-151/report.md), [Report #227](../validation/kpol-cme/cme2-formal-227/report.md), [Report #255](../validation/kpol-cme/manycore-scaling-255/report.md); фізичний edge-вхід PMOD без буфера і HIL залишаються окремими межами. |
| KPOL-SYS-05 / RFC-007 | В описаному рандеву за зайнятого пулу ядер поточне ядро повинно брати ще не призначену залежну лінію на виконання. | Погодити атомарне захоплення; тест конкуренції не допускає подвійного виконавця. | **Досліджено в межах багатоядерного кластера `CFG-P` ($N=1..8$, #255):** [Report #255](../validation/kpol-cme/manycore-scaling-255/report.md) реалізує міжбанковий комутатор `km_event_crossbar.sv` із round-robin арбітражем (`MC2_rr_fairness`) і доводить відсутність втрат (`MC1_event_conservation`) та завершення міжбанкових DAG (`MC3_dag_progress`), а також конструктивно фіксує межу взаємного блокування на циклічних графах `Bank 0 <-> Bank 1` (`MC4_cyclic_deadlock_witness`). Динамічний work-stealing рандеву залишається поза поточним RTL. |
| KPOL-SYS-06 / RFC-008 | Результат зіставлення реалізацій повинен мати версії програм/форматів, початкові значення, вхідні події й спостережувану трасу. | Повторення конкретного сценарію з незалежним очікуванням; артефакти та права доступу ідентифіковані. | **Реалізовано у порівняльному Baseline (#254), приймальному пакеті S5 (#8) та покроковому дебагері каскадів (#272):** [Report #254](../../Research/studies/comparative-baseline-254/report.md) звіряє C99 (`-O3`), `eventfd`, регістровий RTL і `CFG-P` на тотожних трасах `KPOL-CME-2` ($K^* = 26\text{ SLICE\_LUTX}$); [Report S5 #8](../validation/kpol-cme/s5-compiler-8/report.md) звіряє `KPOL-CME-1`, `KPOL-CME-2` (`CFG-P` і двобанковий `CFG-P-HA` за #252) та `KPOL-AUTH`; [Report #272](../validation/kpol-cme/debugger-trace-272/report.md) ([`kpol_debugger.py`](../sw/kpol-ref/kpol_debugger.py), `--dump-concepts`, `--trace-events`, `--stdio`, `--tui`) забезпечує покрокове 10-фазне трасування прикладів зі статей та знімків `PRE-LOAD` / `POST-LOAD` на `PYNQ-Z1`. |

Це прийняті до опрацювання входи, не звіт про їх реалізацію.
Для SYS-02/03/05 ще немає достатнього контракту для кодування.
Загальна відсутність втрат для фізично незупинного джерела не обіцяється:
потрібні окремі межі навантаження та буферизації.

## 3. Виконуваний SW-контракт цього кроку

Об'єкт — `compile_concept_microcode_bram_image(..., profile="KPOL-CME-1")`
та CLI `Engineering/hw/scripts/compile_kpol_bram_image.py`.
Безпрофільний API лишається сумісним **експериментальним** шляхом,
не підтриманим профільним компілятором; ABI референсу не змінюється.

| Вимога / залежність | Вхід, вихід та відмова | Приймання / метод / локатор |
|---|---|---|
| B3-REQ-01/03 → SYS-02/03 | Приймати тільки §2 профілю; непідтриманий AST, `cascade_map`, ім'я профілю або тип не підміняти нулем/NOP/першим правилом. Відмова `KpolError` до емісії. | `KpolCmeProfileTests.test_profile_rejects_unsupported_programs`; негативні випадки й CLI без образу. |
| B3-REQ-02 → SYS-01 | Для одного Int32 state/event/rule та INC/DEC емітувати CME-RAW-1 із signed порівнянням payload. Імена не впливають на guard/opcode. | `test_profile_encodes_guards_and_renaming`: ручне пакування W0–W3, границі signed літералів; direct/AXI — окремі наявні сценарії. |
| B3-REQ-04 | CLI розрізняє `B3-SYNTAX`, `B3-TYPE`, профільні B3-коди та I/O; ненульовий код, наявний образ незмінний, новий при відмові відсутній. | `test_profile_cli_rejects_before_output`; помилкові grammar/type/guard/Proof та existing output. |
| B3-REQ-05 → SYS-06 | Якщо Proof присутній, він містить дозволені непорожні scenario/step/expect та проходить ненульову скінченну перевірку до пакування. | `test_profile_checks_proof_before_emission`: правильний, хибний, порожній, непідтриманий Proof. |
| B3-REQ-06 → SYS-06 | Для дозволених трас звіряти початковий і кожний наступний стан, незмінність W1–W3 та commit/reject/записи; нульовий payload не підміняти. | `test_profile_per_event_in_simulated_pipeline`: direct, AXI-MMIO, AXI-HW, signed guards, overflow/underflow, перейменування, інверсний negative control; [Report #153](../validation/kpol-cme/behavior-153/report.md). |

Підтримані діапазони, граматика й правила §2–4 профілю є залежним
контрактом. Нефункціональний поріг часу/пам'яті джерелом не заданий.
Скінченний Proof і поведінкова матриця не доводять усіх трас.
Вхідний валідатор перед PL, HIL, backpressure й Serial Fallback не закриваються.

### 3.1. Кандидати за новою презентацією

**Статус усіх AUTH:** запропоновано, не погоджено й не реалізовано
як повний native frontend/backend. Це вимоги до окремого майбутнього
шляху, не додаткові обмеження чинного Parser або KPOL-CME-1.
Пріоритет і версію такого продукту власник ще не визначив.

| ID / слайд Source | Кандидат вимоги | Приймання й залежності |
|---|---|---|
| KPOL-AUTH-01 / 1–2; [RFC-010](../../Research/sources/author/clarifications-2026-11-13.md#2-витяги-та-локатори) | Для native Concept відокремлювати 4-бітний Token, байт `Def` (8-бітна маска присутності елементів концепту, `1` = елемент присутній), обов'язковий Class та безіменний атрибут розміру `Token` (замість вилученого окремого `Size`); не трактувати W0–W3 як цю структуру. | Узгоджений ABI з точною бітовою розкладкою `Def`, кодами `Class` для `Token`/`Byte` та межею між порожнім присутнім елементом і його відсутністю (відкрита частина Q-AUTH-02/06 до кодування); byte-level decode/encode та негативні випадки. |
| KPOL-AUTH-02 / 1–2, 5, 7 | Native представлення має зберігати Name, Help, порядок та безіменний атрибут, якщо вони присутні; Help не підміняти службовим коментарем. | Round-trip текст → концепти → спостережуване представлення, включно з пустим ім'ям і відсутнім default. Канонічна лексика й довжина Name — Q-AUTH-03. |
| KPOL-AUTH-03 / 3; редакція 5; #159, слайд 1 | Розрізняти Collection/Array/Text/Name, групу, одиничний індекс і дужки виразу; зберігати тип та позицію індексів. Для значень типу Token підрядкове означає Min, надрядкове — Max. Відділяти успіх вмісту від кратності успіху групи; у Static — порожній/непорожній випадок. | Незалежні траси Collection/Array, single-element і Static cases; type-sensitive позитивні/негативні приклади після погодження нетокенних індексів. Q-AUTH-01 до трактування Max=0, лічби й кількості повторів; Q-AUTH-07 до семантики виконуваних дужок. Не декодувати 0 як «безмежно» або «+1» без контракту. |
| KPOL-AUTH-04 / 4 | Розрізняти концепт перелічуваного значення, ім'я, індекс і подію; не вводити числове присвоєння чи Bool-коди current DSL як авторську норму. | Узгоджені типізовані приклади Boolean/Compare, відмова для помилкового присвоєння, трасування події; спосіб серіалізації — окремий ABI. |
| KPOL-AUTH-05 / 3; RFC-013 | Native `•` моделювати як результат виконання/метаподію, не як унарний `not`; розділити діалекти явно. Підписка за крапкою виконується після відповідної адресації: після читання або після запису. | Незалежні траси порядку R/W → підписка; завершення/busy та помилки ще потребують Q-AUTH-05. Окремий тест проти мовчазного lowering у NOT; без припущень про між'ядерну видимість. |
| KPOL-AUTH-06 / 5–6 | Розділяти `@`-параметри, режим резолюції адреси, контент/static і вид активації R/W/execute/init. | Q-AUTH-06: версійований адресний ABI, резолюція/помилки й траси; не підміняти адресну групу CID або MMIO-адресою. |
| KPOL-AUTH-07 / 5, 7–8; RFC-011 | Native лексичний/синтаксичний шар має відділяти Lexeme з Type/First/Length від Token пам'яті, перевіряти незавершені конструкції й відповідність типів парних дужок, зберігати структурні дані. | Канонічний корпус прикладів після Q-AUTH-03/04; позитивні й негативні parse cases, діагностика span, збереження Help і вкладення. Намір звільнити `#` не задає завершеної лексики. |
| KPOL-AUTH-08 / редакція 5; окреме повідомлення Автора | У native шляху зберігати виконувану роль OpenBracket і закривального концепту, не зводити їх безумовно до пунктуації/NOP. Повідомлення містить `CloseBracked`, PPTX — `CloseBracket`; alias не встановлений. | Q-AUTH-07: погодити імена, етап і ефекти; отримати незалежну трасу відкриття/закриття, порожнього/непорожнього Static та помилкової пари до реалізації. Не призначати апаратний opcode без контракту. |

Фактична розбіжність `• → not`, відхилені лексемні фрагменти й
прийняте довге ім'я правила записані у raw Report #155.
Це не доказ підтримки авторської мови й не усунення розбіжності.
За [оцінкою #157](../../Research/studies/author-semantics/kpol-syntax-157-report.md#33-оцінка-q-auth)
Q-AUTH-01/02 залишаються відкритими, 03–05 уточнені частково,
06 відкладене до платформи; додано Q-AUTH-07 про виконувані дужки.
Подальший [Report #159](../../Research/studies/author-semantics/kpol-syntax-159-report.md#32-auth-та-q-auth)
змінює оцінку Q-AUTH-01 на «частково уточнено»: роль Token-індексів
відома, але default Min=1/Max=0 ще не узгоджений зі звичайним інтервалом.
За переданою відповіддю [RFC-010](../../Research/sources/author/clarifications-2026-11-13.md#2-витяги-та-локатори)
Q-AUTH-02 також переведено до стану «частково уточнено» (`Size` замінено
безіменним атрибутом розміру `Token`, а `Def` визначено як 8-бітну маску
присутності елементів концепту; точний порядок 8 бітів і коди `Class`
залишаються відкритими). У картці [відповідей 2026-11-15](../../Research/sources/author/rfc-answers-2026-11-15.md) (#218)
уточнено правило `Min=1, Max=15 → 1..16` (`RFC-009` п. 1), порядок бітів `Def` зліва молодший (`RFC-018` п. 1, де `Child` названо зайвим)
та заглушковий статус `OpenBracket`/`CloseBracket` (`RFC-015`). На цій основі у пакетах [#219](https://github.com/nick-fedchik/kuzmin-machine/issues/219), [#243](https://github.com/nick-fedchik/kuzmin-machine/issues/243) та [#245](https://github.com/nick-fedchik/kuzmin-machine/issues/245) реалізовано ізольований прототип [`Engineering/sw/kpol-auth/`](../sw/kpol-auth/__init__.py) та специфікацію підмножини [`kpol-auth-subset-0.1.0.md`](../specifications/kpol/kpol-auth-subset-0.1.0.md) із детермінованим lowering у `Do/Go` і `CME-RAW-1` (`KPOL-LOWER-CYCLE`) та блокуванням 12 відкритих точок `KPOL-AUTH-U01..U12` (які залишаються в [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186)).
Відповідь RFC-012 про відсутність циклів не визначає рекурентну
реалізацію, fan-out за один такт або відсутність усіх лічильників.

## 4. Трасування та результати

Прямий шлях: G1/N1–N2 → Source/RFC → SYS-01–06 та B3-REQ →
профільний compiler/CLI → `KpolCmeProfileTests` →
[Report](../validation/kpol-cme/profile-150/report.md).
Продовження B3-REQ-06: §3/§7 профілю →
`test_profile_per_event_in_simulated_pipeline` → [Report #153](../validation/kpol-cme/behavior-153/report.md).
Виправлення верифікатора `Proof`, інкрементного `change(...)` і базового lowering `>=`/`<=`/знакового `RANGE` у референсі (#183):
`kpol_reference.py` → `KpolIssue183LanguageAndLoweringTests` → [Report #183](../validation/kpol-cme/verifier-lowering-183/report.md).
Багатоконцептний профіль `KPOL-CME-2` на `CME-RAW-1` (#184) та формальна індукція до $N=16$ (#227/#237/#242/#249):
[специфікація `KPOL-CME-2`](../specifications/kpol/kpol-cme2-profile-0.1.0.md) → `KpolCme2ProfileTests` → [Report #184](../validation/kpol-cme/cme2-profile-184/report.md) → [формальний доказ `Z3` на $N=4, 16$](../validation/kpol-cme/cme2-formal-227/report.md).
Підмножинний фронтенд і lowering `KPOL-AUTH` (#219/#243/#245) та приймальне закриття S5 (#8):
[специфікація `KPOL-AUTH`](../specifications/kpol/kpol-auth-subset-0.1.0.md) → `Engineering/sw/kpol-auth/` → [Report #219](../validation/kpol-cme/kpol-auth-frontend-219/report.md) → `test_s5_compiler_acceptance_8.py` → [Report S5 #8](../validation/kpol-cme/s5-compiler-8/report.md).
Генератор детермінованого MISRA-орієнтованого C99 та сертифіката `Z3 SMT` (#270):
[`c99_emitter.py`](../sw/kpol-ref/c99_emitter.py) / [`compile_kpol_bram_image.py`](../hw/scripts/compile_kpol_bram_image.py) (`--emit-c99`, `--emit-z3-cert`) → [`test_c99_emitter_270.py`](../sw/tests/test_c99_emitter_270.py) (`M1..M4`) → [Commercialization & Final Conclusions #270](../../Research/studies/commercialization-and-final-conclusions.md).
Покроковий дебагер-трасувальник каскадів МК, потокове `STDIO`, двомодовий Go-емулятор `VMK v0.2.0` та ергономічна мова `EKPOL 0.1.0` (#272, #274, #278):
[`kpol_debugger.py`](../sw/kpol-ref/kpol_debugger.py) / [`compile_kpol_bram_image.py`](../hw/scripts/compile_kpol_bram_image.py) (`--dump-concepts`, `--trace-events`, `--stdio`, `--tui`, `--emit-kpol`, `--emit-ekpol`) → [`test_kpol_debugger_272.py`](../sw/tests/test_kpol_debugger_272.py) (`M1..M5`) → [Report #272](../validation/kpol-cme/debugger-trace-272/report.md); самодостатній Go-емулятор VMK та 4-панельний TUI-дебагер ([специфікація `vmk-go` `1.1.0`](../specifications/sw/vmk-go-emulator-and-tui-debugger-0.1.0.md), [специфікація `EKPOL 0.1.0`](../specifications/kpol/ekpol-specification-0.1.0.md), [`ekpol_frontend.py`](../sw/kpol-ref/ekpol_frontend.py), [`Engineering/sw/vmk-go/`](../sw/vmk-go/go.mod)) → [`test_vmk_go_274.py`](../sw/tests/test_vmk_go_274.py), [`test_ekpol_278.py`](../sw/tests/test_ekpol_278.py) (`M1..M5`) → [Report #274](../validation/kpol-cme/vmk-go-274/report.md), [Report #278](../validation/kpol-cme/ekpol-278/report.md).
Зворотний шлях задається ID й назвами перевірок у таблицях вище.
Історичні REQ-SW-001–003 є входами, не дубльованими PASS.
Новий шлях G1/N1–N2, G3/N4 → Source/слайд →
KPOL-AUTH/Q-AUTH → [Compiler Design](../design/software/compiler.md) /
Specification → Reports #155/#157/#159/#201/#219. Тестований нинішній профіль зберігає
окремий шлях через B3-REQ і Reports #150/#153/#184/#8.

* **Рецензія:** не проведена; автор не приймає власну роботу.
* **Стан погодження системних деталей:** запропоновано для наступних контрактів.
* **Стан перевірки реалізації:** фактичні результати й обмеження — тільки в Report.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.10.0 | 2026-11-18 | #278: додано трасування ергономічної мови `EKPOL 0.1.0` (`ekpol-specification-0.1.0.md`, `ekpol_frontend.py`, `internal/vmk/ekpol.go` у `VMK v0.2.0`, `ekpol-278/report.md`, `test_ekpol_278.py`) поруч із незмінним класичним KPOL. |
| 0.9.0 | 2026-11-18 | #274: додано трасування двомодового Go-емулятора VMK (`bram64` + `conceptual`) та 4-панельного TUI-дебагера (`Engineering/sw/vmk-go/`, `vmk-go-emulator-and-tui-debugger-0.1.0.md`, `vmk-go-274/report.md`). |
| 0.8.0 | 2026-11-18 | #272: додано трасування покрокового дебагера каскадів (`kpol_debugger.py`, `--dump-concepts`, `--trace-events`, `--stdio`, `--tui`), інспекції `PRE-LOAD` / `POST-LOAD` та верифікації прикладів зі статей (`debugger-trace-272/report.md`, `KPOL-SYS-06`). |
| 0.7.0 | 2026-11-17 | #270: додано трасування генератора детермінованого C99 (`c99_emitter.py`, `--emit-c99`, `--emit-z3-cert`), явної маски визначеності `valid_mask` (`KPOL-SYS-02`) та підсумкового висновку `commercialization-and-final-conclusions.md`. |
| 0.6.0 | 2026-11-17 | #8: актуалізовано статуси та трасування `KPOL-SYS-02..06` і `KPOL-AUTH` за результатами `#218/#219/#243/#245` (`kpol-auth-subset-0.1.0.md`), `#227/#237/#242` (формальна $k$-індукція до $N=16$), `#252` (`CFG-P-HA`), `#254` (порівняльний Baseline, $K^* = 26$), `#255` (багатоядерний кластер $N=1..8$) та звіту закриття кроку S5 (`s5-compiler-8/report.md`). |
| 0.5.4 | 2026-11-14 | #185: зв'язано `KPOL-SYS-02` із запропонованим проєктом контракту [ADR B7 (`CME-RAW-2`)](../decisions/cme-raw2-kpol-sys02.md) та [Report #185](../validation/kpol-cme/cr-cme-raw2-185/report.md) без модифікації чинного `CFG-P`. |
| 0.5.3 | 2026-11-14 | #184: додано трасування багатоконцептного профілю `KPOL-CME-2` (`kpol-cme2-profile-0.1.0.md` і `cme2-profile-184/report.md`) зі збереженням `KPOL-CME-1` без змін. |
| 0.5.2 | 2026-11-14 | #183: інтегровано уточнення RFC-010 у KPOL-AUTH-01 / Q-AUTH-02 (безіменний атрибут розміру `Token`, 8-бітна маска `Def`) та додано трасування звіту виправлень верифікатора й lowering референсу. |
| 0.5.1 | 2026-11-13 | #151: оновлено стан реалізації та трасування KPOL-SYS-04 на B5 v2.1 і Report #151 зі збереженням межі незупинного джерела та HIL. |
| 0.5.0 | 2026-11-13 | #159: типізовані індекси AUTH-03, успіх вмісту/групи й часткове уточнення Q-AUTH-01; без нових AUTH-ID або змін профілю. |
| 0.4.0 | 2026-11-13 | #157: delta Static, AUTH-08, уточнення AUTH-03/05/07, оцінка відкритих Q; профіль і код незмінні. |
| 0.3.0 | 2026-11-13 | #155: авторський Source, кандидати AUTH і невизначене Q-AUTH; current DSL/профіль не змінено. |
| 0.1.0 | 2026-11-12 | Входи RFC-005–008, межі профілю та перевірні критерії #150. |
| 0.2.0 | 2026-11-13 | Трасування поведінкової матриці B3-REQ-06 / #153; межі повного доказу збережено. |

## Абревіатури та глосарій

SYS/SW — системна/програмна вимога; ABI — двійковий контракт;
CME — Concept Micro-Engine; AST — синтаксичне дерево;
HIL — запуск із фізичним обладнанням; WI — робота; G/N — ціль/потреба.
