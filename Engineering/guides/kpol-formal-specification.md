# Формальна специфікація мови програмування KPOL

* **Версія:** 1.0.0
* **Дата:** 2026-11-19
* **Тип WP:** Specification
* **Статус:** Запропоновано (*Proposed*) — на затвердження власником проєкту.
* **Мова:** KPOL — *Kuzmin Problem-Oriented Language*, класичний модульний запис `Problem / Solution / Proof`. Номер версії мови не присвоєно: документ фіксує поведінку еталонної реалізації на коміті нижче й **не** проголошує «KPOL v1.0».
* **Еталонна реалізація (джерело істини):** [`kpol_reference.py`](../sw/kpol-ref/kpol_reference.py) @ `6a09cf6` — функції `tokenize`, `Parser`, `infer`, `check_module`, `_normalize`, `_eval`, `Interpreter`, `verify_module`, `_compile_cme1_profile`, `_compile_cme2_profile`; RTL [`km_concept_micro_engine.sv`](../hw/rtl/core/km_concept_micro_engine.sv), [`kpol_txn_gate_v2.sv`](../hw/rtl/core/kpol_txn_gate_v2.sv), [`km_autonomous_sequencer.sv`](../hw/rtl/core/km_autonomous_sequencer.sv).
* **Супутній документ:** [Формальна специфікація мови EKPOL 0.1.0](../specifications/kpol/ekpol-specification.md).
* **Пов'язані нормативні профілі:** [KPOL-CME-1](../specifications/kpol/kpol-cme-subset.md), [KPOL-CME-2](../specifications/kpol/kpol-cme2-profile.md); описовий [консолідований контракт](../specifications/kpol/kpol-consolidated.md); навчальний [посібник KPOL/EKPOL](kpol-ekpol-language-guide.md).

---

## 0. Статус, межі та правило першості

### 0.1. Що визначає документ

1. Лексичну структуру, конкретний і абстрактний синтаксис модуля KPOL.
2. Статичну семантику: простори імен, систему типів і контекстні умови.
3. Динамічну семантику еталонного інтерпретатора: значення, тризначну логіку, транзакцію, каскади `change`, вимоги `Problem`.
4. Семантику перевірки блока `Proof`.
5. Апаратні профілі `KPOL-CME-1` і `KPOL-CME-2`, формат образу `CME-RAW-1` і функцію зниження (*lowering*) у нього.

### 0.2. Що документ не визначає

| Поза межами | Причина |
|---|---|
| `KPOL-AUTH` — авторський native-діалект М. Ю. Кузьміна (`Concept`, `Define`, `Go`/`Do`, `@`, пост-адресний `•`) | Окрема [похідна специфікація](../specifications/kpol/kpol-auth-subset.md) з відкритими RFC; інша граматика й інша семантика `•`. |
| EKPOL | Окремий документ: [EKPOL 0.1.0](../specifications/kpol/ekpol-specification.md). |
| Безпрофільне зниження `compile_concept_microcode_bram_image(..., profile=None)` і пасивний образ `compile_bram_image` | Позначені в реалізації як експериментальні; не нормуються. |
| Підписані образи, ACL, `--emit-c99`, Z3-сертифікати, генератори Verilog/RTM, `link_modules`, `parse_triad_files` | Інструменти над AST, а не семантика мови. ACL згадано лише як гейт профілів (§7.3, §7.4). |

### 0.3. Принцип «без вигадок»

Кожне нормативне правило має ідентифікатор (`KPOL-LEX-*`, `KPOL-SYN-*`, `KPOL-STA-*`, `KPOL-DYN-*`, `KPOL-PRF-*`, `KPOL-P1-*`, `KPOL-P2-*`) і джерело в коді (Додаток B). Якщо реалізація неоднозначна, розходиться з апаратурою або має дефект, це **не маскується** правилом, а фіксується як відома розбіжність `D-K*` у Додатку C.

### 0.4. Правило першості

1. Документ укладено з еталонної реалізації. Будь-яка виявлена розбіжність між цим документом і реалізацією є дефектом одного з двох артефактів і МУСИТЬ бути оформлена Issue з рішенням власника. До такого рішення чинною вважається поведінка еталонної реалізації на зафіксованому коміті.
2. У разі розбіжності між цим документом і посібником, статтями або описовими документами діє цей документ.
3. Профільні документи `KPOL-CME-1/2` лишаються нормативними джерелами обґрунтування й трасування; §7 зводить їхні умови без зміни змісту.

### 0.5. Нормативна лексика

Слова **МУСИТЬ**, **МУСИТЬ НЕ**, **ПОВИНЕН** (рекомендовано), **НЕ ПОВИНЕН**, **МОЖЕ** вживаються у значенні MUST, MUST NOT, SHOULD, SHOULD NOT, MAY за RFC 2119 / RFC 8174.

### 0.6. Відповідність

* **Відповідна програма KPOL** — текст, що задовольняє `KPOL-LEX-*`, `KPOL-SYN-*` і `KPOL-STA-*` та не використовує форм, позначених у Додатку C як невідповідні.
* **Програма профілю `KPOL-CME-n`** — відповідна програма, яка додатково задовольняє `KPOL-Pn-*`.
* **Відповідна реалізація** — реалізація, що для кожної відповідної програми дає ті самі вердикти прийняття/відхилення, стани й журнали, що й §5–§6, а для програм профілю — той самий образ `CME-RAW-1`, що й §7.

---

## 1. Нотації

| Призначення | Нотація | Примітка |
|---|---|---|
| Лексика й синтаксис | ISO/IEC 14977 EBNF | `=` визначення, `,` конкатенація, `\|` вибір, `[ ]` опція, `{ }` повторення 0..n, `( )` групування, `"…"` термінал, `(* … *)` коментар. |
| Абстрактний синтаксис і поля дескриптора | ASN.1, ITU-T X.680 | ASN.1 задає структуру й обмеження значень. Бітове кодування `CME-RAW-1` задано таблицею §7.1, **не** правилами BER/PER. |
| Типізація | Правила виводу `Γ ⊢ e : τ` | Записані в блоках коду, щоб уникнути спотворень MathJax. |
| Динамічна семантика | Рівняння `⟦e⟧ρ` і детерміновані алгоритми | Порядок кроків нормативний. |

Позначення: `⊥` — значення невизначеності `Unknown`; `tt`/`ff` — істина/хиба; `σ` — стан концептів; `π` — корисне навантаження події; `ρ = σ ⊕ π` — середовище, де `⊕` означає об'єднання з перевагою правого операнда.

---

## 2. Лексична структура

**KPOL-LEX-1 (кодування).** Вхідний текст — UTF-8. Відповідна програма МУСИТЬ містити поза коментарями лише друковані символи ASCII, пробіл, `\t`, `\r`, `\n`, а також — тільки як застарілі псевдоніми §2.4 — символи `←`, `→`, `•`. Ширші класи Unicode, які приймає еталонний лексер, описано в `D-K1`.

**KPOL-LEX-2 (пробіли й коментарі).** Між лексемами пропускаються пробільні символи та коментарі:

* рядковий коментар починається з `#` або `//` і триває до кінця рядка;
* блоковий коментар `/* … */` не вкладається; незакритий блоковий коментар — лексична помилка `unterminated block comment`.

Наслідок: символ `#` і послідовність `//` не можуть входити до жодної іншої лексеми. Рядки вигляду `# @stdin C`, `# @stdout C` є коментарями мови; інструменти (VMK, `kpol_debugger`) МОЖУТЬ використовувати їх для маршрутизації STDIO, але вони не впливають на семантику §5–§7.

**KPOL-LEX-3 (порядок розпізнавання).** У кожній позиції лексер перевіряє класи **у фіксованому порядку**; першого збігу достатньо, принцип найдовшого збігу між класами не діє:

1. псевдоніми: `(*)`, `<-`, `->`, `←`, `→`, `•`;
2. оператори з двох символів: `==`, `!=`, `<=`, `>=`, `:=`;
3. односимвольні лексеми: `{ } ( ) < > : , ; = + - * /`;
4. число;
5. ідентифікатор або ключове слово;
6. інакше — лексична помилка `unexpected character`.

Нормативні наслідки:

* `a<-1` розбирається як `a`, `<-`, `1` і дає синтаксичну помилку. Від'ємний літерал після `<` МУСИТЬ відокремлюватися пробілом: `a < -1`. Те саме для `x->y`.
* `(*)` завжди є псевдонімом, навіть усередині виразу на кшталт `f((*)x)`.
* Символи `!`, `&`, `|`, `[`, `]`, `@`, `"`, `'`, `.` поза числом є лексичною помилкою; `!` допустимий тільки у складі `!=`.

```ebnf
identifier   = id_start , { id_continue } ;
id_start     = letter | "_" ;
id_continue  = letter | digit | "_" ;
letter       = "A" | … | "Z" | "a" | … | "z" ;     (* відповідна програма: лише ASCII; див. D-K1 *)
digit        = "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" ;
number       = digit , { digit } , [ "." , digit , { digit } ] ;
```

**KPOL-LEX-4 (числа).** Знак не входить до літерала: `-5` — це унарний мінус і літерал `5`. Експоненти немає. `1.` — помилка `malformed numeric literal`. Провідні нулі допустимі: `007` означає ціле `7`. Число без `.` — ціле необмеженої розрядності; число з `.` — точне десяткове значення. Діапазон перевіряється статично або під час збереження (§4.3, §5.2).

**KPOL-LEX-5 (ключові слова).** Зарезервовано рівно 45 слів; вони МУСЯТЬ НЕ використовуватися як імена в позиціях оголошення:

```text
Problem Solution Proof Assumptions Invariants Hazards Alerts Goals
event state rule on reject change when covers set to
Bool Int32 U32 U64 Float Pin Void
true false Unknown gcd and or not
assert scenario step expect
every within timeout supervise channel Rendezvous Stream send receive
```

Слова `Void`, `every`, `within`, `timeout`, `supervise`, `channel`, `Rendezvous`, `Stream`, `send`, `receive` зарезервовані без жодної конструкції. Слова `module`, `import`, `owner`, `concept` тощо **не** зарезервовані; у неочікуваній позиції вони дають синтаксичну помилку.

**KPOL-LEX-6 (псевдоніми фази).** `•` і `(*)` у префіксній позиції виразу означають унарне `not`; модуль, що їх містить, отримує ознаку `phaseAliasesUsed = TRUE`. Це застарілий діагностичний запис: семантика `•` у `KPOL-AUTH` інша (пост-адресний бар'єр), а профіль `KPOL-CME-2` забороняє ці псевдоніми. Лексеми `<-`, `←`, `->`, `→` не мають синтаксичної продукції; будь-яка їх поява є синтаксичною помилкою.

---

## 3. Конкретний синтаксис

**KPOL-SYN-1.** Вхідний текст МУСИТЬ виводитися з нетермінала `module` і закінчуватися після нього; текст після модуля дає помилку `unexpected text after module`.

```ebnf
module          = problem_block , solution_block , [ proof_block ] ;

problem_block   = "Problem" , identifier , "{" , { section } , "}" ;
section         = section_kw , "{" , { requirement } , "}" ;
section_kw      = "Assumptions" | "Invariants" | "Hazards" | "Alerts" | "Goals" ;
requirement     = identifier , [ "on" , identifier ] , [ "to" , identifier ] ,
                  ":" , expression , ";" ;

solution_block  = "Solution" , identifier , "{" , { declaration } , "}" ;
declaration     = event_decl | state_decl | rule_decl ;
event_decl      = "event" , identifier , "(" , [ parameter , { "," , parameter } ] , ")" , ";" ;
parameter       = identifier , ":" , type ;
state_decl      = "state" , identifier , ":" , type , "=" , expression , ";" ;
rule_decl       = "rule" , identifier , "on" , [ "reject" ] , trigger ,
                  [ "when" , expression ] , [ "covers" , identifier ] ,
                  "{" , { set_action } , "}" ;
trigger         = "change" , "(" , identifier , { "," , identifier } , ")"
                | identifier ;
set_action      = "set" , identifier , ":=" , expression , ";" ;

type            = "Bool" | "Int32" | "U32" | "U64"
                | "Float" , "<" , unit , ">"
                | "Pin" , [ "<" , identifier , { "," , identifier } , ">" ] ;
unit            = "V" | "A" | "W" | "s" | "J" | "degC" | "bar"
                | "ns" | "us" | "ms" | "min" | "h" | "mm_s" | "L_min" ;

proof_block     = "Proof" , identifier , "{" , { proof_item } , "}" ;
proof_item      = "assert" , identifier , "on" , identifier , assert_body
                | "scenario" , identifier , "{" , { scenario_item } , "}" ;
assert_body     = "{" , assert_core , "}" | assert_core ;
assert_core     = [ "when" , expression ] , "expect" , expression , ";" ;
scenario_item   = "step" , identifier , "(" , [ step_arg , { "," , step_arg } ] , ")" , ";"
                | "expect" , expression , ";" ;
step_arg        = identifier , ( ":" | "=" ) , expression ;

(* Вирази. Пріоритет зростає згори донизу; усі бінарні оператори лівоасоціативні. *)
expression      = or_expr ;
or_expr         = and_expr , { "or" , and_expr } ;
and_expr        = rel_expr , { "and" , rel_expr } ;
rel_expr        = add_expr , { rel_op , add_expr } ;
rel_op          = "==" | "!=" | "<" | "<=" | ">" | ">=" ;
add_expr        = mul_expr , { ( "+" | "-" ) , mul_expr } ;
mul_expr        = unary , { ( "*" | "/" ) , unary } ;
unary           = ( "not" | "-" | "•" | "(*)" ) , unary
                | primary ;
primary         = number | "true" | "false" | "Unknown"
                | "gcd" , "(" , expression , "," , expression , ")"
                | name_ref
                | "(" , expression , ")" ;
name_ref        = identifier ;
```

Контекстні умови, які не виражаються в EBNF:

* **KPOL-SYN-2.** Кожен `section_kw` трапляється в `problem_block` щонайбільше один раз.
* **KPOL-SYN-3.** Ідентифікатор після `Solution` і після `Proof` МУСИТЬ збігатися з ідентифікатором після `Problem`.
* **KPOL-SYN-4.** У всіх позиціях `identifier`, крім `name_ref`, ключові слова заборонені. У позиції `name_ref` еталонний парсер приймає будь-яке слово, крім `true`, `false`, `Unknown` і виклику `gcd(…)`; ключове слово там відхиляється статично як `unresolved name` (KPOL-STA-4).
* **KPOL-SYN-5.** Унарні оператори зв'язують сильніше за всі бінарні. Тому `not x == 1` означає `(not x) == 1` і для числового `x` статично відхиляється. Заперечення порівняння МУСИТЬ мати дужки: `not (x == 1)`.
* **KPOL-SYN-6.** Ланцюжок порівнянь `a < b < c` синтаксично допустимий (`(a < b) < c`), але статично відхиляється через несумісність `Bool` і числа.
* **KPOL-SYN-7.** Порядок частин фіксований: у вимозі `on` передує `to`; у правилі `when` передує `covers`. `on reject change(…)` синтаксично допустимий, але статично відхиляється (KPOL-STA-9).

---

## 4. Абстрактний синтаксис (ASN.1)

**KPOL-SYN-8.** Розбір відповідної програми породжує значення типу `Module` нижче. Відсутній `when` у правилі дає `guard = literal : boolean : TRUE`; відсутній `when` в `assert` — так само.

```asn1
KPOL-AST DEFINITIONS AUTOMATIC TAGS ::= BEGIN

Identifier ::= UTF8String (SIZE (1..MAX))

Module ::= SEQUENCE {
    name             Identifier,
    requirements     SEQUENCE OF Requirement,
    events           SEQUENCE OF EventDecl,
    states           SEQUENCE OF StateDecl,
    rules            SEQUENCE OF Rule,
    proofPresent     BOOLEAN,
    proofs           SEQUENCE OF ProofItem,
    phaseAliasesUsed BOOLEAN
}

RequirementKind ::= ENUMERATED { assumption, invariant, hazard, alert, goal }

Requirement ::= SEQUENCE {
    kind        RequirementKind,
    name        Identifier,
    event       Identifier OPTIONAL,
    target      Identifier OPTIONAL,
    expression  Expr
}

Unit ::= ENUMERATED { v, a, w, s, j, degC, bar, ns, us, ms, min, h, mmS, lMin }

TypeRef ::= CHOICE {
    bool   NULL,
    int32  NULL,
    u32    NULL,
    u64    NULL,
    float  Unit,
    pin    SEQUENCE OF Identifier   -- порожня послідовність означає просто Pin
}

EventDecl ::= SEQUENCE {
    name        Identifier,
    parameters  SEQUENCE OF Parameter
}

Parameter ::= SEQUENCE {
    name  Identifier,
    type  TypeRef
}

StateDecl ::= SEQUENCE {
    name     Identifier,
    type     TypeRef,
    initial  Expr
}

Trigger ::= CHOICE {
    event   Identifier,
    change  SEQUENCE (SIZE (1..MAX)) OF Identifier   -- упорядкований кортеж спостереження
}

Rule ::= SEQUENCE {
    name     Identifier,
    reject   BOOLEAN,
    trigger  Trigger,
    guard    Expr,
    covers   Identifier OPTIONAL,
    actions  SEQUENCE OF SetAction
}

SetAction ::= SEQUENCE {
    target  Identifier,
    value   Expr
}

ProofItem ::= CHOICE {
    assertion  AssertDecl,
    scenario   ScenarioDecl
}

AssertDecl ::= SEQUENCE {
    name         Identifier,
    event        Identifier,
    guard        Expr,
    expectation  Expr
}

ScenarioDecl ::= SEQUENCE {
    name   Identifier,
    items  SEQUENCE OF ScenarioItem
}

ScenarioItem ::= CHOICE {
    step    StepAction,
    expect  Expr
}

StepAction ::= SEQUENCE {
    event      Identifier,
    arguments  SEQUENCE OF StepArgument
}

StepArgument ::= SEQUENCE {
    name   Identifier,
    value  Expr
}

Expr ::= CHOICE {
    literal  Literal,
    name     Identifier,
    unary    UnaryExpr,
    binary   BinaryExpr,
    gcd      GcdExpr
}

Literal ::= CHOICE {
    boolean  BOOLEAN,
    integer  INTEGER,
    decimal  DecimalLexeme,
    unknown  NULL
}

DecimalLexeme ::= VisibleString (FROM ("0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" | "."))

UnaryExpr ::= SEQUENCE {
    operator  UnaryOperator,
    operand   Expr
}

UnaryOperator ::= ENUMERATED { not, neg }

BinaryExpr ::= SEQUENCE {
    operator  BinaryOperator,
    left      Expr,
    right     Expr
}

BinaryOperator ::= ENUMERATED { or, and, eq, ne, lt, le, gt, ge, add, sub, mul, div }

GcdExpr ::= SEQUENCE {
    first   Expr,
    second  Expr
}

END
```

Відповідність лексем і AST: `•`/`(*)` дають `unary.not`; `-` у префіксі дає `unary.neg`; `(e)` не породжує окремого вузла. Тому дві програми, що відрізняються лише дужками, мають рівні AST; на цьому ґрунтується умова `covers` (KPOL-STA-10).

---

## 5. Статична семантика

### 5.1. Простори імен

* **KPOL-STA-1.** Імена подій попарно різні; імена станів попарно різні; імена правил попарно різні. Пара `(kind, name)` вимоги унікальна, тому однакові імена в різних секціях дозволені.
* **KPOL-STA-2.** Параметри однієї події попарно різні й МУСЯТЬ НЕ збігатися з іменами станів.
* **KPOL-STA-3.** Подія, стан і правило МОЖУТЬ мати однакові імена: події не видимі у виразах, а імена правил ніде не використовуються.
* **KPOL-STA-4.** Ім'я у виразі МУСИТЬ бути визначене в поточному середовищі `Γ` (таблиця нижче); інакше — помилка `unresolved name`.

| Контекст виразу | Середовище `Γ` |
|---|---|
| Ініціалізатор стану `s_i` | Типи станів `s_1 … s_(i-1)`, оголошених раніше. Сам `s_i` і пізніші стани недоступні. |
| Вимога без `on` | Типи всіх станів. |
| Вимога `on e`, охоронець і дії правила `on e`, `assert … on e` | Типи всіх станів і параметрів `e`. |
| Охоронець і дії правила `on change(…)` | Типи всіх станів. |
| Аргумент `step`, вираз `expect` у сценарії | Типи всіх станів. |

### 5.2. Типи та сумісність

Множина типів:

```text
τ ::= Bool | Int32 | U32 | U64 | Float⟨u⟩ | Pin | Pin⟨p₁,…,pₙ⟩      (оголошувані)
    | Number | Unknown                                            (допоміжні: літерал і ⊥)
Numeric(τ) ⇔ τ ∈ { Number, Int32, U32, U64 } ∪ { Float⟨u⟩ }
Int(τ)     ⇔ τ ∈ { Int32, U32, U64 }
range(Int32) = [-2³¹, 2³¹-1];  range(U32) = [0, 2³²-1];  range(U64) = [0, 2⁶⁴-1]
```

`Pin` **не** є числовим типом; рівність типів структурна й враховує одиницю та параметри `Pin`.

Згортка констант `fold(e)` визначена для літералів `integer`/`decimal`, унарного `-` і бінарних `+ - *` над визначеними `fold`; для решти виразів вона не визначена.

**KPOL-STA-5 (сумісність `τₑ ⊒ (τₐ, e)`).** Перевіряється в порядку:

```text
1. τₐ = Number ∧ Int(τₑ) ∧ fold(e) визначено  ⇒  ✓ ⇔ fold(e) ціле ∧ fold(e) ∈ range(τₑ)
2. τₑ = Pin(·) ∧ τₐ = Number ∧ fold(e) визначено  ⇒  ✓ ⇔ fold(e) ∈ {0, 1}
3. τₐ = Unknown                                   ⇒  ✓
4. τₑ = τₐ                                        ⇒  ✓
5. τₐ = Number ∧ Numeric(τₑ)                      ⇒  ✓
6. τₑ = Pin(·) ∧ (τₐ ∈ {Number, Int32, Bool} ∨ Numeric(τₐ))  ⇒  ✓
7. інакше                                         ⇒  ✗
```

Пункт 1 вважає `2.0` цілим, тому `state x: Int32 = 2.0;` проходить статичну перевірку, але відхиляється під час ініціалізації (`D-K3`). Відповідна програма МУСИТЬ ініціалізувати цілі типи цілими літералами.

### 5.3. Правила типізації

```text
[T-Bool]   Γ ⊢ true : Bool        Γ ⊢ false : Bool
[T-Num]    Γ ⊢ n : Number                                   (ціле або десяткове)
[T-Unk]    Γ ⊢ Unknown : Unknown
[T-Var]    x ∈ dom Γ  ⇒  Γ ⊢ x : Γ(x)
[T-Gcd]    Γ ⊢ eᵢ : τᵢ,  U64 ⊒ (τᵢ, eᵢ), i = 1,2  ⇒  Γ ⊢ gcd(e₁, e₂) : U64
[T-Not]    Γ ⊢ e : τ,  τ ∈ {Bool, Unknown}  ⇒  Γ ⊢ not e : Bool
[T-Neg]    Γ ⊢ e : τ,  Numeric(τ)  ⇒  Γ ⊢ -e : τ
[T-Logic]  Γ ⊢ eᵢ : τᵢ,  τᵢ ∈ {Bool, Unknown}  ⇒  Γ ⊢ e₁ and e₂ : Bool,  Γ ⊢ e₁ or e₂ : Bool
[T-Rel]    Γ ⊢ e₁ : τ₁,  Γ ⊢ e₂ : τ₂,
           (τ₁ = Unknown ∨ τ₂ = Unknown)
             ∨ ((τ₁ ⊒ (τ₂, e₂) ∨ τ₂ ⊒ (τ₁, e₁))
                ∧ (op ∈ {==, !=} ∨ (Numeric(τ₁) ∧ Numeric(τ₂))))
           ⇒  Γ ⊢ e₁ op e₂ : Bool
[T-Add]    op ∈ {+, -},  Numeric(τ₁) ∧ Numeric(τ₂),
           Int(τ₁) ⇒ τ₁ ⊒ (τ₂, e₂),   Int(τ₂) ⇒ τ₂ ⊒ (τ₁, e₁),
           τ₁ ≠ Float⟨degC⟩ ∧ τ₂ ≠ Float⟨degC⟩
           ⇒  Γ ⊢ e₁ op e₂ : join(τ₁, τ₂)
[T-Mul]    ті самі передумови, що й у [T-Add], і
           τ₁ = Number ⇒ результат τ₂;   τ₂ = Number ⇒ результат τ₁;
           τ₁ = Float⟨u⟩ ∧ τ₂ = Float⟨v⟩ ⇒ результат Float⟨prod(u, v)⟩,
              де prod(V, A) = prod(A, V) = W,  prod(W, s) = prod(s, W) = J, інакше ✗;
           інакше результат join(τ₁, τ₂)
[T-Div]    Numeric(τ₁) ∧ Numeric(τ₂) ∧ τ₁ ≠ Float⟨degC⟩, і
           τ₂ = Number ⇒ результат τ₁;
           τ₁ = τ₂ = Float⟨u⟩ ⇒ результат Number;
           інакше ✗
join(Number, τ) = join(τ, Number) = τ;   join(τ, τ) = τ;   інакше ✗
```

Наслідки [T-Div]: `Int32 / Int32` і `Number / Int32` статично відхиляються; `Int32 / 2` статично допустимий, але результат не можна зберегти в ціле (`D-K2`). Відповідна програма МУСИТЬ НЕ зберігати результат `/` у стан цілого типу.

### 5.4. Контекстні умови модуля

Умови перевіряються в наведеному порядку; перше порушення дає помилку `KpolError`.

* **KPOL-STA-6 (стани).** Для кожного стану `s : τ = e` у порядку оголошення: `Γ_init ⊢ e : τₐ` і `τ ⊒ (τₐ, e)`.
* **KPOL-STA-7 (вимоги).**

| Вид | `on e` | `to t` | Додатково |
|---|---|---|---|
| `Assumption` | необов'язковий | заборонений | — |
| `Invariant` | заборонений | заборонений | — |
| `Goal` | заборонений | заборонений | — |
| `Hazard` | обов'язковий | обов'язковий | `t` — оголошений стан типу `Bool`. |
| `Alert` | обов'язковий | заборонений | — |

Подія `e` МУСИТЬ бути оголошена. Вираз вимоги МУСИТЬ мати тип рівно `Bool`: вираз типу `Unknown`, зокрема літерал `Unknown`, відхиляється.

* **KPOL-STA-8 (правила подій).** Для `rule r on [reject] e` подія `e` МУСИТЬ бути оголошена.
* **KPOL-STA-9 (правила `change`).** Для `rule r on change(s₁,…,sₙ)`: `reject` заборонений, `n ≥ 1`, кожне `sᵢ` є оголошеним станом. Повтори в списку не відхиляються, але входять до кортежу спостереження (KPOL-DYN-8).
* **KPOL-STA-10 (охоронці та дії).** Охоронець МУСИТЬ мати тип рівно `Bool`. Для кожного `set t := e`: `t` — оголошений стан і `τ_t ⊒ (τₐ, e)`. Кілька дій над одним станом у межах правила статично дозволені.
* **KPOL-STA-11 (`covers`).** Для `covers h`: існує рівно одна вимога `Hazard` з іменем `h`; її подія дорівнює події правила; її AST-вираз дорівнює AST охоронця правила (умова рівності за §4, а не семантичної еквівалентності: `p > 10` не дорівнює `10 < p`); серед дій правила є `set target(h) := true` з літералом `true`. Статично не вимагається, щоб таке правило було `on reject`.
* **KPOL-STA-12.** Кожна вимога `Hazard` МУСИТЬ мати принаймні одне правило з відповідним `covers`.
* **KPOL-STA-13 (Proof).** Для `assert a on e`: подія `e` оголошена; охоронець і очікування мають тип `Bool` у контексті станів і параметрів `e`. Для `step e(…)`: подія `e` оголошена; **множина** імен аргументів дорівнює множині параметрів `e`; для кожного параметра `τₚ ⊒ (τₐ, arg)` у контексті станів. Для `expect φ`: `φ : Bool` у контексті станів. Повтор імені аргументу статично не виявляється (`D-K5`); відповідна програма МУСИТЬ НЕ повторювати імена аргументів.

---

## 6. Динамічна семантика (еталонний інтерпретатор)

### 6.1. Значення та нормалізація

**KPOL-DYN-1 (домени).** `Bool = {tt, ff}`; `Int32`, `U32`, `U64` — цілі з діапазонів §5.2; `Pin = {0, 1}`; `Float⟨u⟩` — скінченні десяткові числа (Python `decimal`, контекст за замовчуванням: 28 значущих цифр, `ROUND_HALF_EVEN`). Проміжні цілі обчислюються як математичні цілі без обмеження розрядності; діапазон перевіряється тільки функцією `norm`. Значення `⊥` (`Unknown`) допустиме у виразах і корисному навантаженні, але **ніколи** не зберігається в стані.

**KPOL-DYN-2 (`norm(v, τ)`).** Нормалізація перед збереженням у стан або параметр:

| `τ` | Прийнятне `v` | Результат |
|---|---|---|
| будь-який | `⊥` | для параметра події — `⊥`; для стану — **помилка виконання** |
| `Bool` | логічне значення | `v` |
| `Int32`, `U32`, `U64` | ціле (не логічне) у `range(τ)` | `v` |
| `Float⟨u⟩` | число, перетворюване на скінченне десяткове | `Decimal(str(v))` |
| `Pin` | `tt`/`ff` або ціле `0`/`1` | `1`/`0` або `v` |
| інакше | — | **помилка виконання** |

Помилка виконання — виняток `KpolError`, що перериває весь виклик `run` і не є відхиленням транзакції.

### 6.2. Обчислення виразів `⟦e⟧ρ`

**KPOL-DYN-3.**

```text
⟦lit⟧ρ = lit                     ⟦x⟧ρ = ρ(x), інакше помилка виконання
⟦gcd(a, b)⟧ρ = ⊥, якщо ⟦a⟧ρ = ⊥ або ⟦b⟧ρ = ⊥; інакше gcd(int ⟦a⟧ρ, int ⟦b⟧ρ)
⟦not e⟧ρ = ⊥, якщо ⟦e⟧ρ = ⊥; інакше ¬⟦e⟧ρ
⟦-e⟧ρ    = ⊥, якщо ⟦e⟧ρ = ⊥; інакше −⟦e⟧ρ
```

Логічні зв'язки обчислюються зліва направо зі скороченим обчисленням за сильною логікою Кліні:

| `a and b` | `b = tt` | `b = ff` | `b = ⊥` |
|---|---|---|---|
| `a = tt` | `tt` | `ff` | `⊥` |
| `a = ff` | `ff`, `b` не обчислюється | `ff` | `ff` |
| `a = ⊥` | `⊥` | `ff` | `⊥` |

`a or b` визначається двоїсто; при `a = tt` операнд `b` не обчислюється. Тому помилка виконання в правому операнді, наприклад ділення на нуль, не виникає, якщо лівий операнд уже визначив результат.

Порівняння й арифметика, де обидва операнди обчислюються зліва направо:

```text
a == b :  якщо a = ⊥ або b = ⊥ → tt ⇔ (a = ⊥ ∧ b = ⊥);   інакше рівність значень
a != b :  заперечення a == b за тим самим правилом
a op b, op ∈ {<, <=, >, >=, +, -, *, /} :  якщо a = ⊥ або b = ⊥ → ⊥;  інакше операція
a / b :   b = 0 → помилка виконання «division by zero»
```

Отже `Unknown == Unknown` дає `tt`, `Unknown == 5` дає `ff`, а `Unknown < 5` дає `⊥`. Рівність не є строгою за Кліні; це нормативна властивість еталонної реалізації. Ділення двох цілих повертає двійкове число з рухомою комою (`D-K2`).

### 6.3. Конфігурація та ініціалізація

**KPOL-DYN-4 (ініціалізація).** Під час створення інтерпретатора:

1. виконуються всі перевірки §5;
2. стани обчислюються в порядку оголошення: `σ(s) = norm(override(s) або ⟦init(s)⟧σ, τₛ)`; невідоме ім'я у `override` дає помилку;
3. кожна вимога `Assumption` **без** `on` і кожна `Invariant` МУСИТЬ мати значення `tt` на `σ`, інакше виникає помилка `initial … is not true`;
4. множина спостережень `W` — список кортежів `change(…)` усіх правил без повторів у порядку першої появи;
5. ознака `pendingInitial := true`.

Вимоги `Assumption` без `on` перевіряються **лише** під час ініціалізації, а не перед кожною подією.

### 6.4. Цикл обробки подій `run`

**KPOL-DYN-5.** Виклик `run(events, max_events = 10000)`:

```text
Q := (якщо pendingInitial: [change(w) | w ∈ W]; pendingInitial := false) ++ events
log := {hazards = [], alerts = [], rejected = [], diagnostics = [], goal_failures = []}
steps := 0
поки Q ≠ ∅:
    якщо steps ≥ max_events: помилка виконання «event limit exceeded»
    ev := pop_front(Q);  steps := steps + 1
    якщо ev — зовнішня подія з неоголошеним ім'ям: помилка виконання
    π := validate(ev)          (KPOL-DYN-6)
    якщо ev = change(w):  TX(ev, π, rejecting = false)
    інакше:               EXTERNAL(ev, π)
для кожної Goal g у порядку оголошення:  ⟦g⟧σ ≠ tt  ⇒  goal_failures += g
повернути (σ, log, steps)
```

**KPOL-DYN-6 (перевірка навантаження).** Для зовнішньої події множина ключів π МУСИТЬ дорівнювати множині параметрів; кожне значення нормалізується `norm(v, τₚ)` з дозволом `⊥`. Внутрішня подія `change(w)` має навантаження рівно `{_watch: w}` і `w ∈ W`.

**KPOL-DYN-7 (`EXTERNAL(e, π)`, фази подання).** Нехай `ρ = σ ⊕ π`, а вимоги перебираються в порядку оголошення.

```text
Фаза A (Assumptions з on e):
  якщо ∃ φ: ⟦φ⟧ρ ≠ tt:
      для кожної Hazard h з on e:  ⟦h⟧ρ = tt ⇒ hazards += h;  ⟦h⟧ρ = ⊥ ⇒ diagnostics += "UnknownHazard:h"
      для кожної Alert a з on e:   ⟦a⟧ρ = tt ⇒ alerts += a
      rejected += "RejectedInput:e";  TX(e, π, rejecting = true);  завершити подію

Фаза B (Hazards і Alerts з on e; fail_closed_hazards = true за замовчуванням):
  blocked := false
  для кожної Hazard h:  ⟦h⟧ρ = tt ⇒ hazards += h; якщо fail_closed: blocked := true, rejected += "RejectedHazard:h"
                        ⟦h⟧ρ = ⊥  ⇒ diagnostics += "UnknownHazard:h"; якщо fail_closed: blocked := true,
                                     rejected += "RejectedHazardUnknown:h"
  для кожної Alert a:   ⟦a⟧ρ = tt ⇒ alerts += a;   ⟦a⟧ρ = ⊥ ⇒ diagnostics += "UnknownAlert:a"
  якщо blocked: TX(e, π, rejecting = true); завершити подію

Фаза C:  TX(e, π, rejecting = false)
```

Сигнальні вимоги `Alert` не блокують транзакцію. Параметр `fail_closed_hazards = false` доступний лише як опція API; семантика мови, перевірка `Proof` і профілі використовують значення `true`.

**KPOL-DYN-8 (`TX(ev, π, rejecting)` — атомарна транзакція).**

```text
snap := σ;  ρ := snap ⊕ π;  writes := ∅
Sel := якщо ev = change(w):  правила з trigger = change(w′), де w′ = w як упорядкований кортеж, і ¬reject
       інакше:               правила з trigger = event(ev) і reject = rejecting
для r ∈ Sel у порядку оголошення:
    g := ⟦guard(r)⟧ρ
    g = ⊥  ⇒ diagnostics += "UnknownGuard:r";  ABORT
    g ≠ tt ⇒ перейти до наступного правила
    для set t := e у порядку запису:
        v := ⟦e⟧ρ                              (ρ — знімок до транзакції, а не проміжний стан)
        v = ⊥ ⇒ diagnostics += "UnknownWrite:r:t";  ABORT
        v := norm(v, τ_t)                      (може дати помилку виконання)
        t ∈ dom writes ∧ writes(t) ≠ v ⇒ diagnostics += "ConflictingWrites:t";  ABORT
        writes(t) := v
якщо rejecting:
    для кожної Hazard h з on ev і ціллю t:  h ∈ log.hazards ∧ t ∉ dom writes ⇒ writes(t) := tt
cand := snap ⊕ writes
для кожної Invariant φ:  ⟦φ⟧cand ≠ tt ⇒ diagnostics += "InvariantViolation:φ";  ABORT
σ := cand                                         (COMMIT)
changed := { s ∈ dom writes | cand(s) ≠ snap(s) }
для w ∈ W у порядку W:  set(w) ∩ changed ≠ ∅ ⇒ push_back(Q, change(w))
```

`ABORT` залишає `σ` без змін і нічого не ставить у чергу. Нормативні наслідки:

1. Усі праві частини обчислюються на знімку, тобто присвоєння в межах транзакції одночасні.
2. Каскад обходиться в ширину (FIFO). Підписник активується лише за **фактичної зміни** значення.
3. Спостереження `change(A, B)` і `change(B, A)` — різні кортежі (KPOL-STA-9).
4. Цикли підписок мовою не забороняються; завершення обмежене тільки `max_events`, після чого виникає помилка виконання.
5. Журнал `log.hazards` охоплює весь виклик `run`, а не одну подію (`D-K4`).

### 6.5. Семантика блока `Proof`

**KPOL-PRF-1.** Функція `verify(M)` повертає `(total, passed, failures)`:

```text
для кожного scenario S (у порядку оголошення):
    I := новий інтерпретатор (KPOL-DYN-4)
    для кожного елемента S:
        step e(args):
            π := { name: ⟦value⟧σ_I | (name, value) ∈ args }   (при повторі імені діє останнє, D-K5)
            pre := σ_I ⊕ π
            для кожного assert a on e:  total += 1
                ⟦guard(a)⟧pre = tt ⇒ a активний, activated += a;  інакше passed += 1
            I.run([e(π)])                                (повний каскад; початкові change лише в першому run)
            post := σ_I ⊕ π
            для кожного активного a:  ⟦expect(a)⟧post = tt ⇒ passed += 1;  інакше failures += a
        expect φ:  total += 1;  ⟦φ⟧σ_I = tt ⇒ passed += 1;  інакше failures += S
для кожного assert a ∉ activated:  failures += "Vacuous assert a"
якщо proofs ≠ ∅ ∧ total = 0 ∧ failures = ∅:  failures += "Vacuous Proof"
passed(M) ⇔ failures = ∅
```

Помилка виконання всередині сценарію поширюється як `KpolError`; профілі перетворюють її на код `…-PROOF`.

---

## 7. Профілі виконання на `CME-RAW-1`

### 7.1. Формат образу `CME-RAW-1`

**KPOL-P0-1.** Образ має рівно 1024 байти: 64 дескриптори по 16 байт; дескриптор `CID = k` починається зі зсуву `16·k`. Дескриптор складається з чотирьох 32-бітних слів little-endian:

| Слово | Біти | Поле | Значення |
|---|---|---|---|
| `W0` (`+0x00`) | `[31:0]` | `current_state` | Стан концепту, `Int32` у доповняльному коді. |
| `W1` (`+0x04`) | `[31:0]` | `operand_val` | Операнд предиката або кроку дії. |
| `W2` (`+0x08`) | `[7:0]` | `pred_opcode` | Код предиката. |
| | `[15:8]` | `guard_flags` | Прапорці охоронців. |
| | `[23:16]` | `hazard_limit` | Поріг небезпеки; профілі записують `0`. |
| | `[31:24]` | `action_opcode` | Код дії. |
| `W3` (`+0x0C`) | `[31:0]` | `subscriber_cid` | CID підписника каскаду. |

```asn1
CME-RAW-1 DEFINITIONS AUTOMATIC TAGS ::= BEGIN

Image ::= SEQUENCE (SIZE (64)) OF Descriptor     -- елемент k має CID = k

Descriptor ::= SEQUENCE {
    currentState   INTEGER (-2147483648..2147483647),   -- W0
    operandVal     INTEGER (0..4294967295),             -- W1
    predOpcode     PredOpcode,                          -- W2[7:0]
    guardFlags     GuardFlags,                          -- W2[15:8]
    hazardLimit    INTEGER (0..255),                    -- W2[23:16]
    actionOpcode   ActionOpcode,                        -- W2[31:24]
    subscriberCid  INTEGER (0..4294967295)              -- W3
}

PredOpcode ::= INTEGER { nop(0), eq(1), neq(2), gt(3), lt(4), range(5), bitmask(6) } (0..255)

ActionOpcode ::= INTEGER { assign(0), inc(1), dec(2), add(3), sub(4) } (0..255)

GuardFlags ::= BIT STRING {
    assumptionEn(0), invariantEn(1), hazardEn(2), invertAssumption(3), subscriberEn(4)
} (SIZE (8))

END
```

Примітка до кодування: номер біта `n` у `GuardFlags` відповідає біту `W2[8+n]`; невикористані біти дорівнюють `0`. Слот без програми є 16 нульовими байтами (`guard_flags = 0x00`).

### 7.2. Апаратна семантика кроку дескриптора

**KPOL-P0-2.** Для дескриптора `d` і 32-бітного параметра події `p` RTL обчислює:

```text
pred = case pred_opcode of
         0x00 → tt
         0x01 → p = W1                          0x02 → p ≠ W1
         0x03 → sgn(p) > sgn(W1)                0x04 → sgn(p) < sgn(W1)
         0x05 → sext16(W1[15:0]) ≤ sgn(p) ≤ sext16(W1[31:16])
         0x06 → (p AND W1) ≠ 0
         інше → ff
assume_ok = flags[0] ∧ (flags[3] ? ¬pred : pred)
(cand, ovf, valid) = case action_opcode of
         0x00 ASSIGN → (p, ff, tt)
         0x01 INC    → (W0+1, W0 = 2³¹−1, tt)
         0x02 DEC    → (W0−1, W0 = −2³¹, tt)
         0x03 ADD    → (W0+W1, знакове переповнення, tt)
         0x04 SUB    → (W0−W1, знакове переповнення, tt)
         інше        → (W0, ff, ff)
inv_ok    = flags[1] ∧ ¬ovf ∧ sgn(cand) ≥ 0
hazard_ok = ¬(flags[2] ∧ hazard_limit ≠ 0 ∧ sgn(p) > hazard_limit)
COMMIT ⇔ valid ∧ assume_ok ∧ inv_ok ∧ hazard_ok
COMMIT ⇒ W0 := cand
trigger ⇔ COMMIT ∧ W3 < 64 ∧ (flags[4] ∨ W3 ≠ 0)
```

Якщо `trigger` істинний, секвенсер ставить каскадну подію до `CID = W3[5:0]` з параметром, що дорівнює **новому** `W0`; подія до самого активного CID не ставиться. Черга, зворотний тиск і пріоритет каскаду визначені контрактом [B5](../specifications/hw/event-queue-ingress-specification.md).

Нормативні наслідки:

1. Апаратний інваріант фіксований: `cand ≥ 0 ∧ ¬ovf`. Тому профілі вимагають рівно інваріант `S >= 0`.
2. Апаратний каскад спрацьовує за `COMMIT`, навіть якщо значення не змінилося. Інтерпретатор породжує `change` лише за фактичної зміни, тому `KPOL-P2-14` вимагає ненульового кроку у видавця.
3. Невідомий код предиката або дії завжди дає відхилення (*fail-closed*).

### 7.3. Профіль `KPOL-CME-1`

Модуль належить профілю, якщо виконуються всі умови нижче; першим перевіряється `KPOL-P1-1`, далі — у порядку таблиці.

| ID | Умова | Код |
|---|---|---|
| `KPOL-P1-1` | Модуль проходить §5. | `B3-TYPE` |
| `KPOL-P1-2` | API-параметр `cascade_map` відсутній. | `B3-SHAPE` |
| `KPOL-P1-3` | Рівно один стан `S: Int32`, одна подія `E(p: Int32)`, одне правило. | `B3-SHAPE` |
| `KPOL-P1-4` | Ініціалізатор `S` — цілий літерал або `-` перед цілим літералом у `[0, 2³¹−1]`. | `B3-SHAPE` |
| `KPOL-P1-5` | Правило: `on E`, без `reject`, без `change`, без `covers`, рівно одна дія `set S := …`. | `B3-SHAPE` |
| `KPOL-P1-6` | Вимоги: рівно одна, `Invariant` без `on`/`to`, з AST-виразом рівно `S >= 0`. Форма `0 <= S` у цьому профілі не приймається. | `B3-INVARIANT` |
| `KPOL-P1-7` | Дія: рівно `S + 1` або `S - 1`; `S` ліворуч, літерал `1` праворуч. | `B3-ACTION` |
| `KPOL-P1-8` | Охоронець: відсутній або `true`; або `p op K`, де `op ∈ {<, >, ==, !=}`, `p` ліворуч, `K` — цілий літерал або `-` перед цілим літералом у `Int32`. | `B3-GUARD` |
| `KPOL-P1-9` | Якщо `Proof` присутній, він непорожній і містить лише `scenario`; кожен сценарій має щонайменше один `step E(p = K)` або `step E(p: K)` з цілим `K` і щонайменше один `expect S == K` після кроку; `verify` проходить з `total > 0`. | `B3-PROOF` |
| `KPOL-P1-10` | Якщо задано `acl_table`, перевірка ACL проходить. | `B3-ACL` |

**KPOL-P1-11 (зниження).** `CID 0`: `W0 = init`; `W1 = K` або `0` без охоронця; `pred = NOP | LT | GT | EQ | NEQ` за `op`; `guard_flags = 0x03`; `hazard_limit = 0`; `action = INC` для `+ 1`, `DEC` для `- 1`; `W3 = 0`. Слоти `CID 1..63` нульові.

### 7.4. Профіль `KPOL-CME-2`

| ID | Умова | Код |
|---|---|---|
| `KPOL-P2-1` | Модуль проходить §5. | `CME2-TYPE` |
| `KPOL-P2-2` | `cascade_map` відсутній. | `CME2-CASCADE` |
| `KPOL-P2-3` | Немає псевдонімів `•`/`(*)` (`phaseAliasesUsed = FALSE`). | `CME2-GUARD` |
| `KPOL-P2-4` | Немає `Hazard` (`CME2-HAZARD`) і `Assumption` (`CME2-GUARD`); інші види, крім `Invariant`, дають `CME2-INVARIANT`. | див. умову |
| `KPOL-P2-5` | `1 ≤ |states| ≤ 64`; кожен стан має тип `Int32`; ініціалізатор — цілий літерал або `-` перед ним у `Int32`; значення `≥ 0`. | `CME2-SHAPE` / `CME2-TYPE` / `CME2-INVARIANT` |
| `KPOL-P2-6` | Кожна подія має рівно один параметр `Int32`, ім'я якого не збігається з жодним станом. | `CME2-SHAPE` / `CME2-TYPE` |
| `KPOL-P2-7` | Кожне правило без `reject`/`covers`, з рівно однією дією; цільові стани правил попарно різні; кожен стан має рівно одне правило. | `CME2-SHAPE` |
| `KPOL-P2-8` | Правило `change` спостерігає рівно один оголошений стан; правило події посилається на оголошену подію; кожна подія використана рівно одним правилом. | `CME2-SHAPE` |
| `KPOL-P2-9` | Вимоги — рівно по одному `Invariant` без `on`/`to` для кожного стану, з AST `S >= 0` або `0 <= S`. | `CME2-INVARIANT` |
| `KPOL-P2-10` | Граф `src → dst` для `on change(src)` має `fan-out ≤ 1`, без петель `S → S` і без циклів. | `CME2-CASCADE` |
| `KPOL-P2-11` | Охоронець після зняття зовнішніх `not` є: логічним літералом; порівнянням `x op K` або `K op x`, де `x` — вхідна змінна правила, а `K ∈ Int32`; або `and` двох таких порівнянь з однією нижньою межею (`>=`, `>`) і однією верхньою (`<=`, `<`). | `CME2-GUARD` / `CME2-RANGE` |
| `KPOL-P2-12` | Для діапазону після зведення `>` до `lo+1` і `<` до `hi−1`: `−32768 ≤ lo ≤ hi ≤ 32767`. | `CME2-RANGE` |
| `KPOL-P2-13` | Дія: `set S := x` (`ASSIGN`), або `S + K`, `K + S`, `S − K` з цілим `K ∈ [1, 2³¹−1]`. Константа `set S := K`, крок `≤ 0` і інші форми відхиляються. | `CME2-ACTION` |
| `KPOL-P2-14` | Видавець каскаду (`src`) має дію `INC`, `DEC`, `ADD` або `SUB`. | `CME2-CASCADE` |
| `KPOL-P2-15` | Для кожного правила `on change(src)`: `⟦guard⟧ σ_init = ff`. | `CME2-CASCADE` |
| `KPOL-P2-16` | Предикат і дія не потребують `W1` одночасно: літеральний або діапазонний охоронець разом з `ADD`/`SUB` при `K ≥ 2` заборонений. | `CME2-OPERAND-COLLISION` |
| `KPOL-P2-17` | `Proof` присутній і непорожній; `verify` проходить; `total > 0`; `passed = total`. | `CME2-PROOF` |
| `KPOL-P2-18` | Якщо задано `acl_table`, перевірка ACL проходить. | `CME2-ACL` |

Вхідна змінна правила `x` — параметр події для правила події або спостережуваний стан `src` для правила `change`.

**KPOL-P2-19 (зниження).** Стан з індексом оголошення `i` отримує `CID = i`:

```text
inv := парність кількості зовнішніх not; охоронець false додатково інвертує inv
охоронець true/false       → pred = NOP,   W1 від предиката не використовується
x == K | x != K            → pred = EQ | NEQ,  W1 = K mod 2³²
x <  K | x >  K            → pred = LT | GT,   W1 = K mod 2³²
x >= K                     → pred = LT,  inv := ¬inv,  W1 = K mod 2³²
x <= K                     → pred = GT,  inv := ¬inv,  W1 = K mod 2³²
K op x                     → x op′ K, де op′ — дзеркальний оператор
діапазон [lo, hi]          → pred = RANGE, W1 = ((hi AND 0xFFFF) << 16) OR (lo AND 0xFFFF)
дія x | S±1 | S±K (K ≥ 2)  → ASSIGN | INC/DEC | ADD/SUB, для ADD/SUB W1 = K
guard_flags = 0x01 | 0x02 | (inv ? 0x08 : 0) | (S — видавець ? 0x10 : 0)
W0 = init(S);  W3 = CID(dst), якщо S — видавець, інакше 0;  hazard_limit = 0
слоти CID ∈ [|states|, 63] нульові
```

Якщо `W1` використовує предикат, він має пріоритет; без операнда предиката `W1` дорівнює кроку дії або `0`.

### 7.5. Відповідність інтерпретатора та апаратури

**KPOL-P0-3.** Для програми профілю внутрішня подія `change(src)` в інтерпретаторі відповідає апаратному каскаду `src → dst` з параметром, що дорівнює новому значенню `src`. Відхилення за охоронцем або інваріантом в обох моделях залишає стан без змін і не запускає каскад.

Гарантія відповідності обмежена:

* вона перевіряється обов'язковим гейтом `Proof` (`KPOL-P1-9`, `KPOL-P2-17`) і звітами [#153](../validation/kpol-cme/behavior-153/report.md), [#184](../validation/kpol-cme/cme2-profile-184/report.md), [#227](../validation/kpol-cme/cme2-formal-227/report.md); загальний доказ для довільних трас не заявляється;
* знакове переповнення поводиться різно: інтерпретатор дає помилку виконання, апаратура — `REJECT` (`D-K6`). Траси з переповненням не входять до гарантії;
* аргумент `Unknown` у `step` профілю `KPOL-CME-2` статично допустимий, але не має апаратного відповідника.

---

## 8. Діагностика

| Фаза | Форма | Приклади |
|---|---|---|
| Лексична | `рядок:стовпець: повідомлення` | `unexpected character`, `malformed numeric literal`, `unterminated block comment` |
| Синтаксична | `рядок:стовпець: повідомлення` | `expected '{', got …`, `reserved keyword … cannot be an identifier`, `Problem/Solution name mismatch` |
| Статична | `KpolError` без позиції | `unresolved name`, `incompatible comparison`, `hazards without a covers rule` |
| Виконання | `KpolError` | `expected Int32 value`, `division by zero`, `event limit exceeded` |
| Журнал транзакції | рядки `log` | `UnknownGuard:R`, `UnknownWrite:R:S`, `ConflictingWrites:S`, `InvariantViolation:I`, `UnknownHazard:H`, `UnknownAlert:A`, `RejectedInput:E`, `RejectedHazard:H`, `RejectedHazardUnknown:H` |
| Профілі | `КОД: module M: повідомлення` | `B3-*` (§7.3), `CME2-*` (§7.4), `B3-PROFILE` для невідомого профілю; CLI додає `*-SYNTAX` та `*-IO` |

---

## Додаток A. Еталонні тестові вектори

Вектори отримано функцією `compile_concept_microcode_bram_image` на коміті `6a09cf6`. Відповідна реалізація МУСИТЬ для тих самих входів дати побайтно тотожні образи.

| Вхід | Профіль | SHA-256 образу (1024 Б) | Дескриптор `CID 0` (16 Б, hex) |
|---|---|---|---|
| [`increase.kpol`](../sw/vmk-go/examples/increase.kpol) | `KPOL-CME-1` | `4df05b189b9bf12052d98ab6084e0256454c60cae4afd4449469c060ba8dcc5d` | `0a000000140000000403000100000000` |
| [`decrease.kpol`](../sw/vmk-go/examples/decrease.kpol) | `KPOL-CME-1` | `00ba66e57e21d14913c95d7d2fc8c45c3c450548510ca3155721d7eec67b78c3` | `0a000000140000000403000200000000` |
| [`cascade_4concept.kpol`](../sw/vmk-go/examples/cascade_4concept.kpol) | `KPOL-CME-2` | `032c4705c91cea6ddddb7d449cd0dcbd6ba62359af1f9e7a846f33c341a7ef38` | `0a000000320000000413000101000000` |
| [`bms_safety_cascade.kpol`](../sw/vmk-go/examples/bms_safety_cascade.kpol) | `KPOL-CME-2` | `de03442454424b5cf64478506f118c13f095ae24ba58db8894583c43567ea3ee` | `00000000320088130513000101000000` |

Негативні вектори: `bms_safety_cascade.kpol` у профілі `KPOL-CME-1` дає `B3-SHAPE`; `increase.kpol` у профілі `KPOL-CME-2` дає `CME2-PROOF`, бо `Proof` відсутній.

---

## Додаток B. Трасування правил до реалізації

| Правила | Джерело |
|---|---|
| `KPOL-LEX-1..6` | `tokenize`, `Parser._reserved`, `Parser.expression` |
| `KPOL-SYN-1..8` | `Parser.parse`, `assert_decl`, `scenario_decl`, `event_decl`, `type_ref`, `state_decl`, `rule`, `expression`, `_precedence`; датакласи `Module`, `Rule`, `Expr` |
| `KPOL-STA-1..13` | `check_module`, `infer`, `_compatible`, `_compatible_expression`, `_constant_number`, `_join_numeric` |
| `KPOL-DYN-1..8` | `_normalize`, `_eval`, `Interpreter.__init__`, `_check_initial_contracts`, `run`, `_validate_payload`, `_execute` |
| `KPOL-PRF-1` | `verify_module` |
| `KPOL-P0-1..3` | `ConceptMicroDescriptor.pack`, `km_concept_micro_engine.sv`, `kpol_txn_gate_v2.sv`, `km_autonomous_sequencer.sv` |
| `KPOL-P1-1..11` | `_compile_cme1_profile` |
| `KPOL-P2-1..19` | `_compile_cme2_profile` |

---

## Додаток C. Відомі розбіжності та невизначеності

Пункти нижче не є нормою мови. Вони описують фактичну поведінку, через яку відповідна програма МУСИТЬ уникати відповідних форм. Кожен пункт потребує рішення власника: виправити реалізацію або закріпити поведінку в нормі.

| ID | Опис фактичної поведінки | Вимога до відповідної програми |
|---|---|---|
| `D-K1` | Еталонний лексер використовує Unicode-класи Python: `isalpha`, `isalnum`, `isdigit`. Тому `змінна` є ідентифікатором, а `²` розпізнається як число й призводить до необробленого `ValueError` замість `KpolError`. VMK (Go) розпізнає лише ASCII. | Лише ASCII-ідентифікатори й цифри. |
| `D-K2` | Ділення двох цілих значень дає двійкове число з рухомою комою; збереження результату в ціле дає `expected Int32 value`, навіть якщо ділення точне. | Не зберігати результат `/` у цілий стан. |
| `D-K3` | `Int32 = 2.0` проходить статичну перевірку (`fold` вважає `2.0` цілим), але ініціалізація відхиляє десяткове значення. | Цілі типи ініціалізувати цілими літералами. |
| `D-K4` | Фіксація цілі `Hazard` у відхиленій транзакції перевіряє присутність `h` у журналі всього виклику `run`, а не поточної події. Небезпека, спостережена раніше в тому самому `run`, може зафіксувати ціль при пізнішому відхиленні з іншої причини. | Подавати події з `Hazards` окремими викликами `run` або не покладатися на фіксацію в змішаних пакетах. |
| `D-K5` | Повтор імені аргументу в `step` статично не виявляється; під час перевірки діє останнє значення. | Не повторювати імена аргументів. |
| `D-K6` | Знакове переповнення `Int32`: інтерпретатор дає помилку виконання, апаратура — `REJECT` (`ovf`). | Для профілів не будувати трас, що досягають межі `Int32`. |
| `D-K7` | У фазі A невизначений `Alert` (`⊥`) не журналюється, а у фазі B журналюється як `UnknownAlert`. | Не покладатися на телеметрію `Alert` у відхилених фазою A подіях. |
| `D-K8` | Компілятор VMK [`kpol_compiler.go`](../sw/vmk-go/internal/vmk/kpol_compiler.go) — регулярно-виразна підмножина: прибирає рядкові коментарі `#` і `//`, але не обробляє блокові `/* … */`, приймає ініціалізатори лише вигляду `-?[0-9]+`, одну дію в правилі тощо. Він не є відповідною реалізацією §2–§6. | Для VMK використовувати канонічний розклад профілів `KPOL-CME-1/2`; еталоном вважати `kpol_reference.py`. |
| `D-K9` | `•`/`(*)` у KPOL означають `not`, тоді як у `KPOL-AUTH` автор визначив `•` як пост-адресний бар'єр (RFC-013). | Не використовувати `•`/`(*)`; профіль `KPOL-CME-2` їх забороняє. |

---

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 1.0.0 | 2026-11-19 | Перша формальна специфікація KPOL: EBNF, ASN.1 AST і `CME-RAW-1`, правила типізації, операційна семантика інтерпретатора й апаратури, профілі `KPOL-CME-1/2`, тестові вектори та реєстр розбіжностей `D-K1..D-K9`. |

## Абревіатури та глосарій

* **KPOL** — *Kuzmin Problem-Oriented Language*, проблемно-орієнтована мова Машини Кузьміна в модульному записі `Problem / Solution / Proof`.
* **AST** — абстрактне синтаксичне дерево.
* **ASN.1** — *Abstract Syntax Notation One*, ITU-T X.680.
* **EBNF** — розширена форма Бекуса — Наура, ISO/IEC 14977.
* **CME** — *Concept Micro-Engine*, апаратний мікрорушій концепту.
* **CME-RAW-1** — 1024-байтний образ 64 дескрипторів концептів.
* **CID** — індекс концепту в образі (`0..63`).
* **`⊥` / `Unknown`** — значення невизначеності, яке не зберігається в стані.
* **Fail-closed** — відхилення транзакції за невідомого або небезпечного стану.
