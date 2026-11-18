# Специфікація мови EKPOL (Ergonomic KPOL 0.1.0): двостильова ASCII та програмістська нотація поруч із класичним KPOL

* **Версія:** 1.0.0
* **Дата:** 2026-11-18
* **Тип WP:** Specification
* **Статус:** Запропоновано на затвердження власником (Proposed)
* **ASPICE 4.0 процеси:** `SWE.1` (Software Requirements Analysis), `SWE.2` (Software Architectural Design), `SWE.3` (Software Detailed Design and Unit Construction)
* **Issue:** `Closes` [#278](https://github.com/nick-fedchik/kuzmin-machine/issues/278); пов'язані задачі [#276](https://github.com/nick-fedchik/kuzmin-machine/issues/276), [#274](https://github.com/nick-fedchik/kuzmin-machine/issues/274), [#272](https://github.com/nick-fedchik/kuzmin-machine/issues/272), [#270](https://github.com/nick-fedchik/kuzmin-machine/issues/270), [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186), [#184](https://github.com/nick-fedchik/kuzmin-machine/issues/184), [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8).
* **Відповідальний:** власник Микола Федчик; укладач — GitHub Copilot CLI (Lead Engineer / Programming Language Architect).
* **Реалізація у ПЗ:** [`Engineering/sw/kpol-ref/ekpol_frontend.py`](../../sw/kpol-ref/ekpol_frontend.py), [`Engineering/hw/scripts/compile_kpol_bram_image.py`](../../hw/scripts/compile_kpol_bram_image.py), [`Engineering/sw/kpol-ref/kpol_debugger.py`](../../sw/kpol-ref/kpol_debugger.py), [`Engineering/sw/vmk-go/internal/vmk/ekpol.go`](../../sw/vmk-go/internal/vmk/ekpol.go) (`VMK v0.2.0`), каталог прикладів [`Engineering/sw/vmk-go/examples/`](../../sw/vmk-go/examples/bms_safety_cascade.ekpol).
* **Верифікація:** [`Engineering/sw/tests/test_ekpol_278.py`](../../sw/tests/test_ekpol_278.py), [`Engineering/sw/vmk-go/internal/vmk/vmk_test.go`](../../sw/vmk-go/internal/vmk/vmk_test.go) та звіт [`Engineering/validation/kpol-cme/ekpol-278/report.md`](../../validation/kpol-cme/ekpol-278/report.md).

---

## 1. Призначення, мотивація та межі

### 1.1. Мотивація та архітектурне рішення
До впровадження Issue [#278](https://github.com/nick-fedchik/kuzmin-machine/issues/278) екосистема мов програмування Машини Кузьміна мала два полюси:
1. **Класичний авторський запис (`KPOL-AUTH`, [специфікація `kpol-auth-subset-0.1.0.md`](kpol-auth-subset-0.1.0.md)):** максимально лаконічний, але спирається на не-ASCII символи Unicode (`•`, `¬`, `←`, `→`, `¤`), які відсутні на стандартній англійській розкладці клавіатури, та має відкриті питання `RFC-009..018` ([#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186));
2. **Верифікаційні профілі `KPOL-CME-1` ([`kpol-cme-subset-0.1.0.md`](kpol-cme-subset-0.1.0.md)) та `KPOL-CME-2` ([`kpol-cme2-profile-0.1.0.md`](kpol-cme2-profile-0.1.0.md)):** однозначно компілюються в апаратний образ `CME-RAW-1` (`1024 B`), але вимагають багатослівної триблочної обгортки `Problem / Solution / Proof`, де оголошення одного концепту рознесене на три різні секції (`Invariants`, `state` + `event` + `rule`, `scenario`).

За прямою командою власника в межах [#278](https://github.com/nick-fedchik/kuzmin-machine/issues/278):
> *«залиш класичний KPOL і додай EKPOL де можна писати ASCII символами або легко зрозумілою для сучасних програмістів мовною нотацією»*

Ця специфікація вводить **EKPOL (`Ergonomic KPOL`, версія мови `0.1.0`, розширення файлів `.ekpol`, профіль компілятора `--profile EKPOL`)** — ергономічну концептно-орієнтовану мову програмування Машини Кузьміна, яка:
* **На 100% зберігає всі існуючі профілі класичного KPOL (`KPOL-CME-1`, `KPOL-CME-2`, `KPOL-AUTH`) та всі існуючі файли `.kpol` без жодних змін;**
* **Об'єднує оголошення стану, типу, початкового значення, інваріанта безпеки Великої Крапки та правил реакції в єдину локальну конструкцію `concept Name: Type = Init [Invariant] { ... }`;**
* **Надає дві взаємозамінні (еквівалентні на рівні AST та кодогенерації) форми запису правил у чистому 7-бітному ASCII:**
  1. **Символьна ASCII-нотація (`symbolic`):** `<-` (зовнішній запис), `->` (читання), `~` (підписка на зміну іншого концепту), `|` (виклик/виконання), `::` (предикат-охоронець), `=>` (дія), `.` (транзакційний бар'єр Великої Крапки);
  2. **Ключова програмістська нотація (`keyword`, у дусі Rust / Go / TypeScript):** `on write(x)`, `on read`, `on change(Src)`, `on call(...)`, `when`, `=>`, `commit;`, `after`;
* **Забезпечує двосторонню безвтратну трансляцію `EKPOL <-> класичний KPOL`** (`--emit-kpol` / `--to-kpol` та `--emit-ekpol` / `--to-ekpol` зі стилем `--ekpol-style symbolic|keyword`) і **100% побітову ідентичність (SHA-256)** згенерованих 1024-байтних образів BRAM (`CME-RAW-1`), C99-модулів (`--emit-c99`) та Z3-сертифікатів (`--emit-z3-cert`).

### 1.2. Межі та атрибуція (`AGENTS.md §6.1`)
- Автор концепції Машини Кузьміна та мови KPOL — **Михайло Ювеналійович Кузьмін** (первинні джерела в [`Research/sources/`](../../../Research/sources/README.md)). Мова `EKPOL 0.1.0`, її парсер, двосторонній транспайлер і підтримка у `VMK v0.2.0` є похідними інженерними розробками проєкту (М. Федчик, інженерні агенти), створеними для підвищення ергономіки розробки, читабельності коду та продуктивності сучасних програмістів.
- Процесна орієнтація на ASPICE 4.0 є добровільним внутрішнім орієнтиром проєкту згідно з [`Project/policies/standards-position.md`](../../../Project/policies/standards-position.md).

---

## 2. Таблиця еквівалентності нотацій: авторський KPOL, класичний `KPOL-CME-2` та `EKPOL 0.1.0`

Усі чотири колонки нижче описують **ту саму семантичну сутність Машини Кузьміна**. В `EKPOL 0.1.0` символьна ASCII-форма та ключова програмістська форма можуть вільно поєднуватися навіть у межах одного файлу `.ekpol`.

| Семантична сутність МК | Авторська нотація (`KPOL-AUTH` / слайди) | Класичний `KPOL-CME-1/2` (`.kpol`) | `EKPOL 0.1.0` — Символьна ASCII (`symbolic`) | `EKPOL 0.1.0` — Ключова програмістська (`keyword`) |
| :--- | :--- | :--- | :--- | :--- |
| **Оголошення концепту та інваріанта** | `Int32 Counter = 10` | `Invariants { I: Counter >= 0; }` + `state Counter: Int32 = 10;` | `concept Counter: i32 = 10 [>= 0] { ... }` | `concept Counter: int32 = 10 [>= 0] { ... }` |
| **Стан невизначеності** | `_` (`? If _`) | `Unknown` | `= _` | `= undef` (або `= _`) |
| **Логічні літерали (`Bool` / `?`)** | `!` (True), `¬` (False) | `true`, `false` | `true` (або `!`), `false` (або `~false`) | `true`, `false` |
| **Анотація потоків UNIX `STDIO`** | `STDIN`, `STDOUT`, `STDERR` | `# @stdin Counter` / `# @stdout Counter` | `@stdin` / `@stdout` / `@stderr` | `@stdin` / `@stdout` / `@stderr` |
| **Реакція на зовнішній запис (`Write` `←`)** | `← @ Int32 x : ...` | `event Ev(x: Int32); rule R on Ev ...` | `<- x :: ... => ... .` (або `<- Ev(x) :: ...`) | `on write(x) when ... => ... commit;` (або `on input(x)` / `on Ev(x)`) |
| **Підписка на зміну концепту (`Cascade`)** | `C0 • C1 += 1` | `rule R on change(C0) when ...` | `~ C0 :: ... => ... .` | `on change(C0) when ... => ... commit;` |
| **Пост-адресна дія після читання (`RFC-013`)** | `→ • Sum = 0` | *(концептуальний режим)* | `-> => . Sum = 0` | `on read => after Sum = 0;` |
| **Реактивний виклик / виконання (`Execute` `\|`)** | `\| @ U64 (a_ > b -=b ...)` | *(концептуальний режим)* | `\| (a, b) => ... .` | `on call(a, b) => ... commit;` |
| **Діапазонний предикат (`RANGE`)** | `[ 50 .. 5000 ]` | `when x >= 50 and x <= 5000` | `:: x in 50..5000` (або `RANGE(x, 50, 5000)`) | `when x in 50..5000` (або `when x >= 50 && x <= 5000`) |
| **Іменовані предикати стану** | `_`, `0`, `+`, `-`, парн./непарн. | `x == 0`, `x > 0`, `x < 0` | `:: x is undef`, `is null`, `is positive`, `is negative`, `is even`, `is odd` | `when x is undef`, `is null`, `is positive`, `is negative`, `is even`, `is odd` |
| **Дії (`INC`, `DEC`, `ADD`, `SUB`, `ASSIGN`, `NOP`)** | `+= 1`, `-= 1`, `+= K`, `-= K`, `= x` | `set S := S + 1;` тощо | `S += 1`, `S -= 1`, `S += K`, `S -= K`, `S = x` (`:=`), `pass` | `S += 1`, `S -= 1`, `S += K`, `S -= K`, `S = x` (`:=`), `nop` |
| **Бар'єр фіксації Великої Крапки** | `•` | `;` (закриття правила + `Invariants`) | `.` (крапка) | `commit;` (або `commit` / `;`) |
| **Вбудований сценарій верифікації** | — | `Proof M { scenario S { step ... expect ... } }` | `test S { send C(15); expect C == 0; }` | `test S { send C(15); expect C == 0; }` |

---

## 3. Формальна EBNF-граматика мови `EKPOL 0.1.0`

Нижче наведено повну, однозначну граматику `EKPOL 0.1.0` у розширеній нотації Бекуса — Наура (ISO/IEC 14977). Пробільні символи (` `, `\t`, `\r`, `\n`), однорядкові коментарі (`# ...` та `// ...`) і багаторядкові коментарі (`/* ... */`) пропускаються лексером між токенами.

```ebnf
ekpol_program      = [ module_decl ] , { top_item } ;

module_decl        = "module" , identifier , ( ";" | "{" , { top_item } , "}" ) ;

top_item           = { annotation } , concept_decl
                   | test_decl ;

annotation         = "@stdin" | "@stdout" | "@stderr" ;

concept_decl       = "concept" , identifier , ":" , type_spec ,
                     "=" , init_expr , [ bracket_invariant ] ,
                     "{" , { concept_member } , "}" ;

type_spec          = "i32" | "int32" | "Int32"
                   | "u64" | "uint64" | "U64"
                   | "f64" | "float64" | "Float"
                   | "bool" | "Bool" | "?" ;

init_expr          = integer_literal
                   | float_literal
                   | "true" | "false" | "!" | "~false"
                   | "_" | "undef" ;

bracket_invariant  = "[" , invariant_clause , { "," , invariant_clause } , "]" ;

invariant_clause   = ( ">=" | ">" | "<=" | "<" | "==" | "!=" ) , signed_number
                   | signed_number , ".." , signed_number ;

concept_member     = annotation , [ ";" ]
                   | body_invariant
                   | reaction_rule ;

body_invariant     = "invariant" , [ identifier , ":" ] ,
                     identifier , ( ">=" | ">" | "<=" | "<" | "==" | "!=" ) ,
                     signed_number , [ ";" | "." ] ;

reaction_rule      = write_rule
                   | change_rule
                   | read_rule
                   | exec_rule
                   | state_transition_rule ;

(* 1. Зовнішній запис / вхідна подія *)
write_rule         = ( "<-" , [ identifier , "(" , identifier , ")" | "(" , identifier , ")" | identifier ]
                     | "on" , ( "write" | "input" | identifier ) , "(" , identifier , [ ":" , type_spec ] , ")" ) ,
                     [ guard_clause ] , "=>" , action_stmt , rule_terminator ;

(* 2. Підписка на зміну іншого концепту (каскад) *)
change_rule        = ( "~" , ( "(" , identifier , ")" | identifier )
                     | "on" , "change" , "(" , identifier , ")" ) ,
                     [ guard_clause ] , "=>" , action_stmt , rule_terminator ;

(* 3. Читання з пост-адресним бар'єром Великої Крапки (RFC-013) *)
read_rule          = ( "->" , [ guard_clause ] , "=>" , ( "." | "•" | "after" ) , action_stmt
                     | "on" , "read" , [ guard_clause ] , "=>" , [ "after" | "." | "•" ] , action_stmt ) ,
                     [ rule_terminator ] ;

(* 4. Реактивний виклик / виконання алгоритму (концептуальний режим) *)
exec_rule          = ( "|" | "on" , ( "call" | "exec" ) ) ,
                     [ "(" , [ identifier , { "," , identifier } ] , ")" ] ,
                     [ guard_clause ] , "=>" , action_stmt , rule_terminator ;

(* 5. Автономний перехід за власним станом (наприклад, T-тригер If: _ / true / false) *)
state_transition_rule = guard_clause , "=>" , action_stmt , rule_terminator ;

guard_clause       = ( "::" | "when" ) , bool_expr ;

bool_expr          = bool_term , { ( "&&" | "and" ) , bool_term } ;

bool_term          = ( "!" | "not" ) , bool_term
                   | "(" , bool_expr , ")"
                   | "true" | "false"
                   | range_predicate
                   | named_state_predicate
                   | comparison_predicate ;

range_predicate    = identifier , "in" , signed_number , ".." , signed_number
                   | "RANGE" , "(" , identifier , "," , signed_number , "," , signed_number , ")" ;

named_state_predicate = [ identifier ] , "is" , [ "not" ] ,
                        ( "undef" | "null" | "positive" | "negative" | "even" | "odd" | "uneven" ) ;

comparison_predicate  = operand_expr , ( "==" | "=" | "!=" | "<=" | ">=" | "<" | ">" | "&" ) , operand_expr ;

operand_expr       = identifier | signed_number | "_" | "undef" | "true" | "false" | "!" | "~false" ;

action_stmt        = "pass" | "nop"
                   | single_action , { ";" , single_action } ;

single_action      = identifier , ( "+=" | "-=" | "=" | ":=" ) , expr ;

rule_terminator    = "." , [ ";" ]
                   | "commit" , [ ";" ]
                   | ";"
                   | "•" , [ ";" ] ;

(* 6. Вбудований блок перевірки / сценарій *)
test_decl          = ( "test" | "scenario" ) , identifier , "{" , { test_stmt } , "}" ;

test_stmt          = ( "send" | "step" ) , identifier , "(" , [ [ identifier , ( "=" | ":" ) ] , signed_number , { "," , signed_number } ] , ")" , [ ";" | "." ]
                   | "expect" , identifier , ( "==" | "=" | "!=" | "<=" | ">=" | "<" | ">" ) , operand_expr , [ ";" | "." ] ;
```

---

## 4. Семантичні правила, зниження в `CME-RAW-1` та двостороння трансляція

### 4.1. Відображення типів і початкових станів
1. **Канонізація типів:**
   - `i32`, `int32`, `Int32` $\to$ канонічний `Int32` (32-бітне знакове ціле у доповняльному коді; єдиний тип, підтримуваний апаратним профілем `KPOL-CME-1/2`);
   - `u64`, `uint64`, `U64` $\to$ канонічний `U64` (підтримується в концептуальному режимі `VMK` для `Nod`, `Factorial`, `Tachometer`);
   - `f64`, `float64`, `Float` $\to$ канонічний `Float` (підтримується в концептуальному режимі `VMK` для `Sum`, `Tachometer`);
   - `bool`, `Bool`, `?` $\to$ канонічний `Bool` (`?`, підтримується в концептуальному режимі `VMK` для `If`).
2. **Стан невизначеності (`_` / `undef`):**
   - Літерали `_` та `undef` у позиції початкового стану (`concept If: ? = _`) або в предикатах (`when x is undef`, `:: x == _`) позначають апаратний стан невизначеності (`Valid = false`, `KPOL-SYS-02`).
   - Спроба скомпілювати концепт із початковим станом `_` / `undef` або з типом поза `Int32` у апаратний 1024-байтний образ `CME-RAW-1` (`bram64`) детерміновано відхиляється компілятором із кодом `EKPOL-TYPE-ERR`, тоді як у `--mode conceptual` виконується нативно.

### 4.2. Семантика інваріантів `[>= 0]` та пост-адресного бар'єра Великої Крапки
1. **Інваріант у заголовку або тілі концепту:**
   - Запис `concept C: i32 = 0 [>= 0] { ... }` (або `invariant C >= 0;` всередині тіла) вмикає біт `CME_GUARD_INVARIANT_EN (0x02)` у слові `W2` дескриптора `CME-RAW-1` і транслюється в секцію `Invariants { inv_c: C >= 0; }` класичного `KPOL-CME-1/2`.
   - Якщо концепт має додаткову верхню межу небезпеки `[>= 0, <= H]` (де $1 \le H \le 255$) у розширеному режимі дескрипторів, встановлюється `hazard_limit = H` та `CME_GUARD_HAZARD_EN (0x04)`.
   - Якщо в програмі профілю `bram64` (`CME-RAW-1`) інваріант `[>= 0]` відсутній або порушується початковим станом (`Init < 0`), компілятор відхиляє програму з кодом `EKPOL-INVARIANT-ERR`.
2. **Пост-адресний бар'єр читання (`-> => . Sum = 0` / `on read => after Sum = 0;`):**
   - Відповідає авторському правилу `RFC-013` (`→ • Sum = 0`): під час операції читання спочатку поточне значення концепту видається на шину читання / у `STDOUT`, і **строго після цього** (після маркера `.` або ключового слова `after`) виконується дія скидання `Sum = 0`.

### 4.3. Правила зниження предикатів та дій у мікрокод `CME-RAW-1`
1. **Предикати (`::` / `when`):**
   - Без предиката або `:: true` / `when true` $\to$ `CME_PRED_NOP (0x00)`, `invert = 0`;
   - `x == K` (або `x = K`), `x is null` (`K = 0`) $\to$ `CME_PRED_EQ (0x01)`, `W1 = K`;
   - `x != K`, `x is not null` (`K = 0`) $\to$ `CME_PRED_NEQ (0x02)`, `W1 = K`;
   - `x > K`, `x is positive` (`K = 0`) $\to$ `CME_PRED_GT (0x03)`, `W1 = K`;
   - `x < K`, `x is negative` (`K = 0`) $\to$ `CME_PRED_LT (0x04)`, `W1 = K`;
   - `x >= K` $\to$ `CME_PRED_LT (0x04)` + `CME_GUARD_INVERT_ASSUMPTION (0x08)`, `W1 = K`;
   - `x <= K` $\to$ `CME_PRED_GT (0x03)` + `CME_GUARD_INVERT_ASSUMPTION (0x08)`, `W1 = K`;
   - `x in LO..HI`, `RANGE(x, LO, HI)`, або `x >= LO && x <= HI` $\to$ `CME_PRED_RANGE (0x05)`, де `LO, HI` — знакові `int16` (`-32768 <= LO <= HI <= 32767`), упаковані у `W1 = ((HI & 0xFFFF) << 16) | (LO & 0xFFFF)`. Якщо `LO > HI` або межі виходять за `int16`, компілятор генерує `EKPOL-RANGE-ERR`;
   - `(x & MASK) != 0`, `x is odd` / `x is uneven` (`MASK = 1`), `x is even` (`MASK = 1` + `invert = 1`) $\to$ `CME_PRED_BITMASK (0x06)`, `W1 = MASK`.
2. **Дії (`=>`):**
   - `C += 1` $\to$ `CME_ACT_INC (0x01)`;
   - `C -= 1` $\to$ `CME_ACT_DEC (0x02)`;
   - `C += K` ($K \ge 2$) $\to$ `CME_ACT_ADD (0x03)`, `W1 = K`;
   - `C -= K` ($K \ge 2$) $\to$ `CME_ACT_SUB (0x04)`, `W1 = K`;
   - `C = x` або `C := x` (де `x` — вхідний параметр або стан концепту-видавця) $\to$ `CME_ACT_ASSIGN (0x00)`;
   - `pass` або `nop` $\to$ `CME_ACT_NOP (0x05)` (у розширеному VMK) або тотожний перехід.
3. **Виявлення колізії `W1` (`EKPOL-COLLISION-ERR`) та циклів підписок (`EKPOL-CYCLE-ERR`):**
   - Якщо правило одночасно вимагає запису константи/діапазону в `W1` для предиката і кроку $K \ge 2$ у `W1` для дії `ADD`/`SUB`, фронтенд видає `EKPOL-COLLISION-ERR`.
   - Орієнтований граф каскадних підписок `~ Src` / `on change(Src)` у режимі `bram64` перевіряється алгоритмом пошуку циклів (3-кольоровий DFS): будь-який цикл `C0 -> ... -> C0` або самопідписка `C -> C`, а також `fan-out > 1` детерміновано блокуються з кодом `EKPOL-CYCLE-ERR`.

### 4.4. Алгоритм двосторонньої трансляції `EKPOL <-> класичний KPOL`
1. **Пряма трансляція `transpile_ekpol_to_kpol(ekpol_src) -> str`:**
   - Якщо програма містить рівно 1 концепт `Int32` із зовнішньою подією, інваріантом `[>= 0]`, дією `+= 1` або `= - 1` і простим предикатом без блоку `test` (або з `test`), генерує канонічний модуль `KPOL-CME-1` / `KPOL-CME-2` (`Problem <Name> { Invariants { ... } } Solution <Name> { ... } [Proof <Name> { ... }]`).
   - Імена подій та правил відновлюються детерміновано: якщо в правилі вказано явне ім'я події `on EvCellDelta(delta_mv)` або `<- EvCellDelta(delta_mv)`, зберігається `event EvCellDelta(delta_mv: Int32);`; якщо вказано скорочено `<- delta_mv`, ім'я події виводиться за канонічним правилом (`Pulse` для 1-концептного лічильника з параметром `param`, `E0` для `C0`, або `Ev<ConceptName>`).
2. **Зворотна трансляція `transpile_kpol_to_ekpol(kpol_src, style="symbolic" | "keyword") -> str`:**
   - Парсить класичний модуль `.kpol`, зберігає прагми `# @stdin` / `# @stdout` як нативні анотації `@stdin` / `@stdout`, об'єднує кожен `state`, його `Invariant` та `rule` в охайний блок `concept <Name>: i32 = <init> [>= 0] { ... }`, згортає двосторонні кон'юнкції `x >= LO and x <= HI` у діапазон `x in LO..HI`, а секцію `Proof { scenario ... }` перетворює на блок `test <ScenarioName> { send ...; expect ...; }`.

---

## 5. Коди діагностичних помилок компілятора `EKPOL`

| Код помилки | Категорія | Умова виникнення |
| :--- | :--- | :--- |
| `EKPOL-SYNTAX-ERR` | Лексика / Синтаксис | Неочікуваний токен, незакриті дужки `{ ... }` / `[ ... ]`, відсутній оператор `=>` або термінатор правила. |
| `EKPOL-TYPE-ERR` | Система типів | Невідомий тип даних, невідповідність початкового значення типу концепту або спроба скомпілювати не-`Int32` / `_` у профіль `CME-RAW-1`. |
| `EKPOL-INVARIANT-ERR` | Безпека / Велика Крапка | Відсутній інваріант `[>= 0]` у режимі `CME-RAW-1` або початковий стан концепту порушує оголошений інваріант (`Init < 0`). |
| `EKPOL-RANGE-ERR` | Межі діапазону | Нижня межа діапазону `in LO..HI` більша за верхню (`LO > HI`) або межі виходять за знаковий 16-бітний інтервал `[-32768, 32767]`. |
| `EKPOL-COLLISION-ERR` | Апаратний слот `W1` | Одночасне використання літерального/діапазонного предиката та дії `+= K` / `-= K` ($K \ge 2$) в одному 16-байтному дескрипторі `CME-RAW-1`. |
| `EKPOL-CYCLE-ERR` | Топологія каскаду | Цикл підписок (`C0 -> C1 -> C0`), самопідписка в `bram64`, `fan-out > 1`, посилання на неоголошений концепт або порушення стартової узгодженості каскаду. |
| `EKPOL-PROOF-ERR` | Вбудований тест | Сценарій `test { ... }` не проходить перевірку на еталонному інтерпретаторі або містить звернення до неоголошеного концепту. |

---

## 6. Приклади програм на `EKPOL 0.1.0`

### 6.1. Каскад безпеки BMS у символьній ASCII-нотації (`symbolic`)

```ekpol
@stdin
@stdout
concept Cell_Delta_mV: i32 = 0 [>= 0] {
    <- EvCellDelta(delta_mv) :: delta_mv in 50..5000 => Cell_Delta_mV += 1 .
}

@stdout
concept Module_Thermal_Guard: i32 = 0 [>= 0] {
    ~ Cell_Delta_mV :: Cell_Delta_mV >= 1 => Module_Thermal_Guard += 1 .
}

@stdout
concept Pack_Fault_Latch: i32 = 2 [>= 0] {
    ~ Module_Thermal_Guard :: Module_Thermal_Guard >= 1 => Pack_Fault_Latch -= 1 .
}

@stdout
concept Contactor_Interlock: i32 = 10 [>= 0] {
    ~ Pack_Fault_Latch :: !(Pack_Fault_Latch == 2) => Contactor_Interlock = Pack_Fault_Latch .
}

test BmsFourLevelProtectionAndLatch {
    send Cell_Delta_mV(15);
    expect Cell_Delta_mV == 0;
    expect Contactor_Interlock == 10;
    send Cell_Delta_mV(120);
    expect Cell_Delta_mV == 1;
    expect Module_Thermal_Guard == 1;
    expect Pack_Fault_Latch == 1;
    expect Contactor_Interlock == 1;
    send Cell_Delta_mV(180);
    expect Cell_Delta_mV == 2;
    expect Module_Thermal_Guard == 2;
    expect Pack_Fault_Latch == 0;
    expect Contactor_Interlock == 0;
    send Cell_Delta_mV(250);
    expect Cell_Delta_mV == 3;
    expect Module_Thermal_Guard == 3;
    expect Pack_Fault_Latch == 0;
    expect Contactor_Interlock == 0;
}
```

### 6.2. Той самий каскад безпеки BMS у ключовій програмістській нотації (`keyword`)

```ekpol
module BmsSafetyCascade;

@stdin
@stdout
concept Cell_Delta_mV: int32 = 0 [>= 0] {
    on EvCellDelta(delta_mv) when delta_mv in 50..5000 => Cell_Delta_mV += 1 commit;
}

@stdout
concept Module_Thermal_Guard: int32 = 0 [>= 0] {
    on change(Cell_Delta_mV) when Cell_Delta_mV >= 1 => Module_Thermal_Guard += 1 commit;
}

@stdout
concept Pack_Fault_Latch: int32 = 2 [>= 0] {
    on change(Module_Thermal_Guard) when Module_Thermal_Guard >= 1 => Pack_Fault_Latch -= 1 commit;
}

@stdout
concept Contactor_Interlock: int32 = 10 [>= 0] {
    on change(Pack_Fault_Latch) when not (Pack_Fault_Latch == 2) => Contactor_Interlock = Pack_Fault_Latch commit;
}
```

Обидва варіанти (§6.1 та §6.2) компілюються в **абсолютно ідентичний 1024-байтний образ BRAM** із контрольною сумою SHA-256:
`de03442454424b5cf64478506f118c13f095ae24ba58db8894583c43567ea3ee`.

### 6.3. Концептуальні приклади (`Sum` із пост-адресним скиданням `-> => .` та T-тригер `If` зі станом `_`)

```ekpol
// Sum: акумулятор із пост-адресним скиданням після читання (RFC-013)
@stdin
@stdout
concept Sum: f64 = 0 [>= 0] {
    <- x :: true => Sum += x .
    -> => . Sum = 0
}

// Або в ключовій нотації:
concept SumKeyword: float64 = 0 [>= 0] {
    on write(x) => SumKeyword += x commit;
    on read => after SumKeyword = 0;
}

// If: T-тригер зі станом невизначеності '_' (RFC-001)
concept If: bool = undef {
    when If is undef => If = true commit;
    when If == true  => If = false commit;
    when If == false => If = true commit;
}
```

---

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 1.0.0 | 2026-11-18 | Первинний випуск специфікації мови `EKPOL 0.1.0` (`Ergonomic KPOL`): двостильова ASCII-символьна та ключова програмістська граматика EBNF, правила зниження в `CME-RAW-1`, двостороння трансляція `EKPOL <-> KPOL` та діагностичні коди помилок (Issue [#278](https://github.com/nick-fedchik/kuzmin-machine/issues/278)). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| **EKPOL** | Ergonomic KPOL (`0.1.0`) — ергономічна концептно-орієнтована мова програмування Машини Кузьміна у чистому 7-бітному ASCII з підтримкою символьної (`<-`, `->`, `~`, `::`, `=>`, `.`) та ключової (`on write`, `on read`, `on change`, `when`, `commit`, `after`) нотацій. |
| **KPOL** | Kuzmin Concept-Oriented Language — базова мова програмування Машини Кузьміна (класичні профілі `KPOL-CME-1`, `KPOL-CME-2`, `KPOL-AUTH`). |
| **CME-RAW-1** | 1024-байтний двійковий формат таблиці 64 дескрипторів концептів по 16 байтів (`W0..W3`) для апаратного конвеєра `CFG-P` / `CFG-P-HA`. |
| **VMK** | Virtual Machine of Kuzmin — двомодовий емулятор, транспайлер і 4-панельний TUI-дебагер Машини Кузьміна (`Engineering/sw/vmk-go`, `v0.2.0`). |
| **Велика Крапка (`•` / `.` / `commit` / `after`)** | Апаратний інваріантний вентиль фіксації транзакції та пост-адресний бар'єр порядку виконання (`RFC-013`). |
| **WP** | Work Product — робочий продукт інженерного процесу за ASPICE 4.0. |
