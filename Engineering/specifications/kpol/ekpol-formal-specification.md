# Формальна специфікація мови програмування EKPOL 0.1.0

* **Версія:** 1.0.0
* **Дата:** 2026-11-19
* **Тип WP:** Specification
* **Статус:** Запропоновано (*Proposed*) — на затвердження власником проєкту.
* **Мова:** EKPOL 0.1.0 — *Ergonomic KPOL*, концептно-орієнтований запис у файлах `.ekpol` у двох стилях: символьному (`<-`, `~`, `::`, `=>`, `.`) і ключовому (`on write`, `on change`, `when`, `=>`, `commit;`).
* **Реалізації:**
  * еталонна (джерело істини): [`ekpol_frontend.py`](../../sw/kpol-ref/ekpol_frontend.py) @ `6a09cf6` — `_strip_comments_preserve_pragmas`, `parse_ekpol`, `_split_concept_statements`, `_parse_concept_rule`, `_parse_predicate`, `_parse_actions`, `_parse_test_block`, `validate_ekpol_for_bram64`, `transpile_ekpol_to_kpol`, `transpile_kpol_to_ekpol`, `compile_ekpol_to_bram_image`;
  * друга: VMK, [`ekpol.go`](../../sw/vmk-go/internal/vmk/ekpol.go) — `ParseEKPOL`, `ValidateEKPOLForBRAM64`, `CompileEKPOLSource`.
* **Супутній документ:** [Формальна специфікація мови KPOL](kpol-formal-specification.md) — визначає `CME-RAW-1`, апаратну семантику кроку дескриптора та профілі `KPOL-CME-1/2`.
* **Описові документи:** [специфікація EKPOL (описова)](ekpol-specification.md), [посібник KPOL/EKPOL](../../guides/kpol-ekpol-language-guide.md).

---

## 0. Статус, межі та правило першості

### 0.1. Що визначає документ

1. Попередню обробку тексту: коментарі та STDIO-прагми.
2. Конкретний синтаксис програми, концепту, правила, охоронця, дії та тесту.
3. Абстрактний синтаксис і нормалізовану модель охоронців і дій.
4. **Нормативну семантику профілю `EKPOL-B64`**: умови прийняття, зниження в `CME-RAW-1`, семантику тестів і зв'язок із `KPOL-CME-1/2`.
5. Двосторонню трансляцію `EKPOL ↔ KPOL` з точними областями визначення.

### 0.2. Шари мови та їх нормативний статус

| Шар | Конструкції | Статус семантики |
|---|---|---|
| Синтаксис EKPOL | усі конструкції §3–§7 | **Нормативний**. |
| Профіль `EKPOL-B64` | концепти `Int32`, правила `write` і `change`, охоронці `nop`/`cmp`/`range`/`bitmask`, дії `inc`/`dec`/`add`/`sub`/`assign` | **Нормативна** семантика через `CME-RAW-1` (§9). |
| Концептуальні конструкції | типи `U64`, `Float`, `Bool`; початкове `_`; правила `read`, `exec`, `state`; предикати `undef`, логічні порівняння, символьні порівняння `a > b`; дії-константи й присвоєння з іншого концепту; кілька дій у правилі | **Синтаксис нормативний, семантика НЕ визначена** в EKPOL 0.1.0 (§11). |

### 0.3. Принцип «без вигадок» і дві реалізації

1. Кожне правило має ідентифікатор `EKPOL-*` і джерело в коді (Додаток B).
2. **Нормативна мова — перетин** того, що однаково приймають і однаково інтерпретують обидві реалізації. Форми, які приймає лише одна реалізація або які дві реалізації тлумачать по-різному, **не входять** до відповідної мови й наведені в Додатку C як `D-E*`.
3. Якщо в цьому документі сказано «МУСИТЬ НЕ використовуватися», а реалізація таку форму приймає, поведінка реалізації для неї не є нормою й може змінитися.

### 0.4. Правило першості

1. Документ укладено з еталонної реалізації. Розбіжність між ним і реалізацією є дефектом одного з артефактів і МУСИТЬ бути оформлена Issue з рішенням власника; до рішення чинною вважається поведінка еталонної реалізації на зафіксованому коміті.
2. У разі розбіжності з [описовою специфікацією EKPOL](ekpol-specification.md), посібником чи статтями діє цей документ. Виявлені невідповідності описової специфікації перелічено в `D-E15`.

### 0.5. Нормативна лексика й відповідність

Слова **МУСИТЬ**, **МУСИТЬ НЕ**, **ПОВИНЕН**, **НЕ ПОВИНЕН**, **МОЖЕ** вживаються за RFC 2119 / RFC 8174.

* **Відповідна програма EKPOL** задовольняє `EKPOL-PRE-*`, `EKPOL-LEX-*`, `EKPOL-SYN-*` і `EKPOL-STA-*` та не використовує форм із Додатку C.
* **Відповідна програма `EKPOL-B64`** додатково задовольняє `EKPOL-B64-*`.

---

## 1. Нотації

| Призначення | Нотація |
|---|---|
| Лексика та контекстно-вільна структура | ISO/IEC 14977 EBNF (`=`, `,`, `\|`, `[ ]`, `{ }`, `( )`, `"…"`, `(* … *)`). |
| Класифікація правил, охоронців і дій | PEG (B. Ford, 2004): `/` — **упорядкований** вибір, перша успішна альтернатива; `&e` — позитивний предикат; `!e` — негативний предикат; `.` — будь-який символ. PEG використано там, де реалізації розв'язують неоднозначність пріоритетом перевірок. |
| Абстрактний синтаксис | ASN.1, ITU-T X.680 (§8). |
| Зниження та семантика | Таблиці відповідності й детерміновані алгоритми. |

Пробільні класи:

```ebnf
ws    = { " " | "\t" | "\r" | "\n" } ;      (* рівень програми, §3 *)
ws1   = ( " " | "\t" | "\r" | "\n" ) , ws ;
sp    = { " " | "\t" } ;                     (* усередині інструкції, §4–§7 *)
sp1   = ( " " | "\t" ) , sp ;
```

Усередині інструкції фізичні рядки вже з'єднані одним пробілом (§4), тому там діють лише `sp` і `sp1`.

---

## 2. Попередня обробка та лексика

**EKPOL-PRE-1 (кодування).** Текст — UTF-8. Відповідна програма МУСИТЬ містити поза коментарями лише друковані символи ASCII, пробіл, `\t`, `\r`, `\n`. Символи `•` і `¬`, які приймають обидві реалізації, є застарілими псевдонімами й не належать до відповідної мови (`D-E6`).

**EKPOL-PRE-2 (блокові коментарі).** Спочатку кожен фрагмент `/* … */` (без вкладення) замінюється стількома символами `\n`, скільки їх було у фрагменті. Незакритий `/*` дає `EKPOL-SYNTAX-ERR`. Прагми всередині блокових коментарів **не** розпізнаються.

**EKPOL-PRE-3 (рядкові коментарі).** У кожному рядку найраніша позиція `//` або `#` починає коментар до кінця рядка. Символ `#` і послідовність `//` тому не можуть мати іншого значення.

**EKPOL-PRE-4 (STDIO-прагми).** Якщо текст рядкового коментаря після обрізання пробілів починається з `@stdin`, `@stdout` або `@stderr`, решта коментаря розбивається за пробілами й комами. Отримані лексеми додаються до відповідного списку потоків. Відповідна програма МУСИТЬ записувати в прагмі лише ідентифікатори концептів (`D-E3`).

**EKPOL-PRE-5.** Текст програми `T` — результат кроків 2–3 з обрізаними крайніми пробільними символами. Порожній `T` дає `EKPOL-SYNTAX-ERR`.

```ebnf
letter      = "A" | … | "Z" | "a" | … | "z" ;
digit       = "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" ;
nz_digit    = "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" ;
hex_digit   = digit | "a" | … | "f" | "A" | … | "F" ;
ident       = ( letter | "_" ) , { letter | digit | "_" } ;
dec_int     = [ "-" ] , ( "0" | nz_digit , { digit } ) ;
hex_int     = [ "-" ] , "0x" , hex_digit , { hex_digit } ;
int_lit     = dec_int | hex_int ;
float_lit   = [ "-" ] , digit , { digit } , [ "." , digit , { digit } ] ;
```

**EKPOL-LEX-1 (класи цілих за позицією).** Реалізації застосовують різні розпізнавачі в різних позиціях. Нормативно:

| Позиція | Клас |
|---|---|
| Межі `in LO..HI` і `RANGE(x, LO, HI)`; число в пункті інваріанта `op N`; крок у формі `C = C ± K` | `dec_int` |
| Константа порівняння в охоронці; маска `&`; крок `+=`/`-=`; початкове значення `Int32`/`U64`; межі діапазонного інваріанта `LO..HI`; значення `send` та цілі значення `expect` | `int_lit` |

Відповідна програма МУСИТЬ НЕ використовувати цілих із провідними нулями (`010`), префіксів `0o`, `0b`, `0X`, знака `+`, роздільників `_`, а також експоненти, `inf` чи `nan` у дійсних числах. Ці форми реалізації приймають або тлумачать по-різному (`D-E1`).

**EKPOL-LEX-2 (зарезервовані слова).** Такі слова МУСЯТЬ НЕ використовуватися як імена модуля, концептів, подій, параметрів і тестів:

```text
module concept test scenario invariant on write input read change call exec
when after commit in is not and RANGE true false True False undef Unknown invalid
pass nop send step expect null positive negative even odd uneven
```

Реалізації не відхиляють ці імена явно; для таких програм розбір неоднозначний, тому поведінка не нормується.

**EKPOL-LEX-3 (типи).** Ім'я типу відображається на канонічний тип:

| Канонічний тип | Записи |
|---|---|
| `Int32` | `i32`, `int32`, `Int32` |
| `U64` | `u64`, `uint64`, `U64` |
| `Float` | `f64`, `float64`, `Float` |
| `Bool` | `bool`, `Bool`, `?` |

Будь-яке інше ім'я дає `EKPOL-TYPE-ERR`.

---

## 3. Синтаксис рівня програми

**EKPOL-SYN-1.** Текст `T` розбирається так:

```ebnf
program        = [ module_semi ] , items
               | module_brace ;
module_semi    = "module" , ws1 , ident , ws , ";" ;
module_brace   = "module" , ws1 , ident , ws , "{" , items , "}" ;   (* "}" — останній непробільний символ T *)
items          = ws , { item , ws } ;
item           = annotation | concept_decl | test_decl ;
annotation     = "@" , ( "stdin" | "stdout" | "stderr" ) ;           (* далі не може йти letter, digit або "_" *)
concept_decl   = "concept" , ws1 , ident , ws , ":" , ws , type_name , ws , "=" , ws ,
                 init_text , [ ws , inv_brackets ] , ws , "{" , balanced , "}" ;
type_name      = type_char , { type_char } ;
type_char      = letter | digit | "_" | "?" ;
init_text      = init_char , { init_char } ;    (* найкоротший збіг; крайні пробіли обрізаються *)
init_char      = ? будь-який символ, крім "[", "{" і нового рядка ? ;
inv_brackets   = "[" , { ? будь-який символ, крім "]" ? } , "]" ;
test_decl      = ( "test" | "scenario" ) , ws1 , ident , ws , "{" , balanced , "}" ;
balanced       = ? текст, у якому лічильник "{" мінус "}" ніколи не стає від'ємним і дорівнює 0 у кінці ? ;
```

Нормативні наслідки:

* початкове значення концепту МУСИТЬ бути в тому самому рядку, що й `=`;
* тіло концепту й тесту МУСИТЬ мати збалансовані фігурні дужки;
* форма `module_semi` перевіряється першою; без заголовка `module` ім'я модуля визначається реалізацією (EKPOL-STA-3).

**EKPOL-SYN-2 (контекстні умови рівня програми).**

1. Анотації накопичуються й приєднуються до **наступного** концепту; повтори ігноруються.
2. Анотація безпосередньо перед `test`/`scenario` дає `EKPOL-SYNTAX-ERR`.
3. Анотації в кінці тексту без наступного концепту реалізація мовчки відкидає (`D-E10`); відповідна програма МУСИТЬ НЕ мати таких анотацій.
4. Програма МУСИТЬ оголошувати хоча б один концепт; імена концептів МУСЯТЬ бути попарно різними (`EKPOL-SYNTAX-ERR`).
5. Будь-який інший текст на рівні програми дає `EKPOL-SYNTAX-ERR` `unexpected token`.

---

## 4. Тіло концепту: розбиття на інструкції

**EKPOL-SEG-1 (алгоритм розбиття).** Тіло концепту розбивається на інструкції за фізичними рядками:

```text
depth := 0;  cur := []
для кожного рядка тіла:
    line := trim(рядок);  якщо line порожній — пропустити
    для кожного символу c у line:  c = "(" ⇒ depth += 1;  c = ")" ⇒ depth := max(0, depth − 1)
    cur += line
    якщо depth = 0 і (line закінчується на ".", ";", "commit" або "•", або line містить "=>"):
        видати інструкцію join(cur, " ");  cur := []
якщо cur ≠ []: видати join(cur, " ")
```

**EKPOL-SEG-2 (нормативне правило розкладу).** Наслідки алгоритму обов'язкові для відповідної програми:

1. Рядок, що містить `=>`, завершує інструкцію. Тому `=>`, **уся** дія і термінатор МУСЯТЬ бути в одному фізичному рядку. Частина правила до `=>` МОЖЕ займати кілька рядків.
2. Рядок частини до `=>` МУСИТЬ НЕ закінчуватися на `.`, `;` або `commit`, інакше інструкцію буде завершено передчасно.
3. В одному фізичному рядку МУСИТЬ бути щонайбільше одне правило.

**EKPOL-SEG-3 (класифікація інструкції).** Після обрізання пробілів інструкція є:

* анотацією, якщо дорівнює `@stdin`, `@stdout` або `@stderr` з необов'язковою `;`; анотація приєднується до цього концепту;
* інваріантом, якщо починається з `invariant` і пробілу (§5.2);
* правилом — в усіх інших випадках (§6).

---

## 5. Початкові значення та інваріанти

### 5.1. Початкове значення

**EKPOL-STA-1.** `init_text` після обрізання тлумачиться так:

| Тип | Допустимий запис | Значення |
|---|---|---|
| будь-який | `_`, `undef` | `⊥`, тобто концептуальне значення (§11) |
| `Bool` | `true` / `false` | `tt` / `ff` |
| `Int32` | `int_lit` у `[-2³¹, 2³¹−1]` | ціле |
| `U64` | `int_lit` у `[0, 2⁶⁴−1]` | ціле |
| `Float` | `float_lit` | дійсне |

Інші записи дають `EKPOL-TYPE-ERR`. Записи `Unknown`, `True`, `False`, `!`, `~false`, `¬` реалізації приймають як псевдоніми, але вони не належать до відповідної мови (`D-E6`).

### 5.2. Інваріанти

```ebnf
inv_brackets_content = inv_clause , { "," , inv_clause } ;     (* порожні елементи між комами ігноруються *)
inv_clause           = range_clause | cmp_clause ;
range_clause         = sp , int_lit , sp , ".." , sp , int_lit , sp ;    (* обирається, якщо пункт містить ".." *)
cmp_clause           = [ ident , sp ] , cmp_op , sp , dec_int ;
cmp_op               = ">=" | "<=" | "==" | "!=" | ">" | "<" ;
body_invariant       = "invariant" , " " , sp , [ label , ":" ] , inv_brackets_content , { ";" | "." } ;
label                = ? будь-який текст без ":" ? ;
```

**EKPOL-STA-2.** Порожні дужки `[]` дають `EKPOL-INVARIANT-ERR`. Для `range_clause` МУСИТЬ виконуватися `LO ≤ HI`. У `cmp_clause` ідентифікатор, якщо його вказано, МУСИТЬ дорівнювати імені концепту. Пункти з дужок і з `invariant` у тілі об'єднуються в один список.

**EKPOL-STA-2a.** Інваріант описує множину допустимих станів концепту. Апаратний профіль виконує **лише** перевірку невід'ємності (§9.3, `D-E8`).

---

## 6. Правила (PEG)

**EKPOL-SYN-3 (поділ правила).** Інструкція правила `s` МУСИТЬ містити `=>`, інакше виникає `EKPOL-SYNTAX-ERR`. `lhs := trim(s до першого "=>")`, `rhs := trim(s після першого "=>")`.

**EKPOL-SYN-4 (класифікація `lhs`, упорядкований вибір).**

```peg
Lhs        <- ReadLhs / ChangeLhs / ExecLhs / WriteLhs / StateLhs
ReadLhs    <- ("->" / "on" Sp1 "read" !IdChar) Sp GuardOpt
ChangeLhs  <- ("~" / "on" Sp1 "change" !IdChar) Sp "("? Sp Ident Sp ")"? Sp GuardOpt
ExecLhs    <- ("|" / "on" Sp1 ("call" / "exec") !IdChar) Sp ("(" ParamList? ")")? Sp GuardOpt
WriteLhs   <- "<-" Sp WriteSym
            / "on" Sp1 Ident Sp ("(" Sp Ident Sp (":" Sp TypeName)? Sp ")")? Sp GuardOpt
WriteSym   <- Ident Sp "(" Sp Ident Sp (":" Sp TypeName)? Sp ")" Sp GuardOpt     # подія з параметром
            / "(" Sp Ident Sp (":" Sp TypeName)? Sp ")" Sp GuardOpt              # лише параметр
            / !("when" !IdChar) Ident (Sp ":" Sp TypeName)? Sp GuardOpt          # голий параметр
            / GuardOpt                                                            # параметр "param"
StateLhs   <- GuardKw Sp1 GuardText
GuardOpt   <- (GuardKw Sp1 GuardText)? !.
GuardKw    <- "::" / "when"
GuardText  <- .+
ParamList  <- Param (Sp "," Sp Param)*
Param      <- Ident (Sp ":" Sp TypeName)?
IdChar     <- [A-Za-z0-9_]
Sp         <- [ \t]*
Sp1        <- [ \t]+
```

Відповідні форми синтаксичної нотації — `->`, `~ Src`, `| (a, b)`, `<- Ev(p)`, `<- p`, `<- (p)`; ключової — `on read`, `on change(Src)`, `on call(a, b)`, `on exec(a, b)`, `on Ev(p)`, `on write(p)`, `on input(p)`. Непарні дужки у `ChangeLhs`, наприклад `~ (Src`, реалізації приймають, але вони не належать до відповідної мови.

**EKPOL-STA-4 (семантичні ролі тригерів).**

| Тригер | Вид правила | Подія | Вхідна змінна |
|---|---|---|---|
| `ReadLhs` | `read` | читання концепту | ім'я концепту |
| `ChangeLhs` | `change` | зміна концепту `Src` | `Src` |
| `ExecLhs` | `exec` | виклик | перший параметр або ім'я концепту |
| `WriteLhs`, ім'я події `write` або `input`, чи без імені | `write` | анонімна подія запису | параметр; без нього — `param` |
| `WriteLhs` з іншим ім'ям події `E` | `write` | іменована подія `E` | параметр; без нього — `param` |
| `StateLhs` | `state` | автономний перехід | ім'я концепту |

Наслідок: імена подій `read`, `change`, `call`, `exec` недоступні, а `write` та `input` означають анонімну подію. Анотація типу параметра `x: T` синтаксично допустима; у профілі `EKPOL-B64` вона МУСИТЬ позначати `Int32`, бо інакше її мовчки ігнорують (`D-E9`).

**EKPOL-SYN-5 (ключові слова охоронця).** Після `::` і після `when` МУСИТЬ бути хоча б один пробіл; форми `::x` і `when(x)` не належать до відповідної мови (`D-E2`).

**EKPOL-SYN-6 (термінатор і бар'єр).**

* Для правил, крім `read`, `rhs` МУСИТЬ закінчуватися термінатором. Відповідні термінатори: `.`, `.;`, `commit`, `commit;`, `;`; інакше виникає `EKPOL-SYNTAX-ERR` `missing Big Dot terminator`.
* Для `read`: якщо `rhs` починається з `.` або слова `after`, правило має пост-адресний бар'єр (`postReadBarrier = TRUE`), а маркер вилучається. Термінатор необов'язковий.
* Перед розбором дії з кінця `rhs` повторно вилучаються суфікси `commit;`, `commit`, `.;`, `.`, `;`.

---

## 7. Охоронці, дії та тести

### 7.1. Охоронець (PEG) і нормалізований предикат

Результат розбору охоронця — нормалізований предикат `P = ⟨kind, var, op, value, lo, hi, inv⟩`, де `kind ∈ {nop, cmp, range, bitmask, undef, raw}`. Нехай `d` — вхідна змінна правила (EKPOL-STA-4), а `g` — обрізаний `GuardText`; за відсутності охоронця `P = ⟨nop, d, inv = ff⟩`.

**EKPOL-SYN-7 (префікси).** Поки `g` починається з `not` і пробілу чи `(`, або з `!`, за яким не йде `=`, і `g ≠ "!"`: маркер вилучається, `inv := ¬inv`, і знімається **один** шар зовнішніх дужок, якщо вони охоплюють увесь `g`. Після циклу зовнішні дужки, що охоплюють увесь `g`, знімаються повторно.

**EKPOL-SYN-8 (альтернативи після префіксів, перша успішна).**

```peg
Guard     <- G_Bool / G_Range / G_And / G_Named / G_Mask / G_Bare / G_Special / G_Cmp / G_Raw
G_Bool    <- ("true" / "false") !.
G_Range   <- Ident Sp1 "in" Sp1 DecInt Sp ".." Sp DecInt !.
           / "RANGE"i Sp "(" Sp Ident Sp "," Sp DecInt Sp "," Sp DecInt Sp ")" !.
G_And     <- CmpClause Sp1 ("&&" / "and") Sp1 CmpClause !.        # рівно два пункти
G_Named   <- (Ident Sp1)? "is"i Sp1 ("not"i Sp1)? NamedWord !.
NamedWord <- "undef"i / "null"i / "positive"i / "negative"i / "even"i / "odd"i / "uneven"i
G_Mask    <- "("? Sp Ident Sp "&" Sp IntLit Sp ")"? (Sp ("!=" / "==") Sp "0")? !.
G_Bare    <- ("_" / "undef" / "!" / "~false" / "¬") !.
G_Special <- Ident Sp ("==" / "!=" / "=") Sp ("_" / "undef" / "true" / "false" / "!" / "~false" / "¬") !.
G_Cmp     <- CmpClause !.
G_Raw     <- Ident Sp RelOp Sp Ident !.
CmpClause <- "("* Sp (Ident Sp CmpOp Sp IntLit / IntLit Sp CmpOp Sp Ident) Sp ")"*
CmpOp     <- "==" / "!=" / "<=" / ">=" / "<" / ">" / "="
RelOp     <- "==" / "!=" / "<=" / ">=" / "<" / ">"
```

Нормативні уточнення:

* `G_And` застосовується, лише якщо поділ за ` && ` / ` and ` дає **рівно два** пункти. Помилка розбору пункту одразу дає `EKPOL-SYNTAX-ERR`. Обидва пункти МУСЯТЬ стосуватися однієї змінної, інакше виникає `EKPOL-SYNTAX-ERR`. Рівно один пункт МУСИТЬ бути нижньою межею (`>=`, `>`), а інший — верхньою (`<=`, `<`), інакше виникає `EKPOL-RANGE-ERR`. Диз'юнкції (`or`, `||`) і кон'юнкції з трьох і більше пунктів не підтримуються.
* Для `G_Range` і `G_And`: `−32768 ≤ lo ≤ hi ≤ 32767` після зведення `> K` до `K + 1` і `< K` до `K − 1`; інакше виникає `EKPOL-RANGE-ERR`.
* Однорядкове `=` у `CmpOp` є псевдонімом `==`.
* Якщо жодна альтернатива не підходить, виникає `EKPOL-SYNTAX-ERR`.

**EKPOL-SYN-9 (нормалізація; `inv` — результат префіксів).**

| Альтернатива | `P` |
|---|---|
| `true` | `⟨nop, d, inv⟩` |
| `false` | `⟨nop, d, ¬inv⟩` |
| `G_Range`, `G_And` | `⟨range, x, lo, hi, inv⟩` |
| `x is [not] undef` | `⟨undef, x, inv ⊕ not⟩` |
| `x is null` / `is not null` | `⟨cmp, x, == / !=, 0, ff⟩`; вид визначає `inv ⊕ not` |
| `x is positive` / `is not positive` | `⟨cmp, x, > / <=, 0, ff⟩`; вид визначає `inv ⊕ not` |
| `x is negative` / `is not negative` | `⟨cmp, x, < / >=, 0, ff⟩`; вид визначає `inv ⊕ not` |
| `x is odd` / `x is uneven` | `⟨bitmask, x, 1, inv ⊕ not⟩` |
| `x is even` | `⟨bitmask, x, 1, ¬(inv ⊕ not)⟩` |
| `x & M`, `(x & M) != 0` | `⟨bitmask, x, M, inv⟩` |
| `(x & M) == 0` | `⟨bitmask, x, M, ¬inv⟩` |
| `_`, `undef` | `⟨undef, d, inv⟩` |
| `!` / `~false`, `¬` | `⟨cmp, d, ==, tt / ff, inv⟩` |
| `x == _` / `x != _` | `⟨undef, x, inv ⊕ (op = !=)⟩` |
| `x op b`, де `b` — логічний літерал | `⟨cmp, x, op, b, inv⟩` |
| `x op K`, `K op x` | `⟨cmp, x, op′, K, inv⟩`; для `K op x` оператор віддзеркалюється |
| `a op b`, обидва — імена | `⟨raw, a, op, b, inv⟩` |

Ім'я `x` у `G_Named` за відсутності береться як `d`.

### 7.2. Дії

**EKPOL-SYN-10.** Після вилучення термінаторів (EKPOL-SYN-6) тіло дії порожнє — це `EKPOL-SYNTAX-ERR`. Тіло `pass` або `nop` дає дію `nop`. Інакше тіло ділиться за `;` на частини, і кожна частина розбирається упорядкованим вибором:

```peg
Action    <- A_Aug / A_Set
A_Aug     <- Ident Sp ("+=" / "-=") Sp .+                 # праву частину розібрано як int_lit
A_Set     <- Ident Sp (":=" / "=") Sp .+
```

| Форма | Умова | Вид дії |
|---|---|---|
| `C += K` / `C -= K` | `K = 1` | `inc` / `dec` |
| `C += K` / `C -= K` | `K` — `int_lit`, `K ≠ 1` | `add` / `sub` з операндом `K` |
| `C += e` / `C -= e` | `e` не є `int_lit` | `raw` |
| `C = C + K`, `C = C - K` (`dec_int`) | ціль дорівнює лівому імені | як для `+=` / `-=` |
| `C = x` або `C := x` | `x` — вхідна змінна правила | `assign(x)` |
| `C = v` | `v ∈ {true, false, _, undef, !, ~false, ¬}` | `set_const(v)` |
| `C = K` | `K` — `int_lit` | `set_const(K)` |
| `C = y` | `y` — інший ідентифікатор | `assign(y)` |
| інше | — | `raw`; інший текст без `=`/`+=`/`-=` дає `EKPOL-SYNTAX-ERR` |

### 7.3. Тести

**EKPOL-SYN-11.** Тіло `test`/`scenario` ділиться на інструкції за кожною послідовністю символів `;` і нового рядка; кінцева `.` вилучається. Порожній тест дає `EKPOL-PROOF-ERR`.

```ebnf
test_stmt   = send_stmt | expect_stmt ;
send_stmt   = ( "send" | "step" ) , sp1 , ident , sp , "(" , first_arg , { "," , sp , int_lit , sp } , ")" ;
first_arg   = sp , [ ident , sp , ( "=" | ":" ) , sp ] , ( int_lit | "_" | "undef" | "invalid" ) , sp ;
expect_stmt = "expect" , sp1 , ident , sp , exp_op , sp , exp_value ;
exp_op      = "==" | "=" | "!=" | "<=" | ">=" | "<" | ">" ;
exp_value   = int_lit | float_lit | "_" | "undef" | "true" | "false" ;
```

Відповідна програма МУСИТЬ записувати кожну інструкцію тесту в одному рядку. Для `exp_value` реалізації також приймають `!`, `~false`, `¬`, але це не відповідна форма.

---

## 8. Абстрактний синтаксис (ASN.1)

```asn1
EKPOL-AST DEFINITIONS AUTOMATIC TAGS ::= BEGIN

Identifier ::= VisibleString (SIZE (1..MAX))

Program ::= SEQUENCE {
    moduleName      Identifier,
    concepts        SEQUENCE (SIZE (1..MAX)) OF Concept,
    tests           SEQUENCE OF Test,
    stdinConcepts   SEQUENCE OF Identifier,
    stdoutConcepts  SEQUENCE OF Identifier,
    stderrConcepts  SEQUENCE OF Identifier
}

CanonicalType ::= ENUMERATED { int32, u64, float, bool }

InitialValue ::= CHOICE {
    undef    NULL,
    boolean  BOOLEAN,
    integer  INTEGER,
    real     REAL
}

Concept ::= SEQUENCE {
    name         Identifier,
    type         CanonicalType,
    initial      InitialValue,
    invariants   SEQUENCE OF Invariant,
    annotations  SEQUENCE OF StreamTag,
    rules        SEQUENCE OF Rule
}

StreamTag ::= ENUMERATED { stdin, stdout, stderr }

Invariant ::= CHOICE {
    compare  SEQUENCE { op CompareOp, value INTEGER },
    range    SEQUENCE { lo INTEGER, hi INTEGER }
}

CompareOp ::= ENUMERATED { eq, ne, lt, le, gt, ge }

Rule ::= SEQUENCE {
    trigger          Trigger,
    predicate        Predicate,
    actions          SEQUENCE (SIZE (1..MAX)) OF Action,
    postReadBarrier  BOOLEAN    -- TRUE лише для read з маркером "." або "after"
}

Trigger ::= CHOICE {
    write   SEQUENCE { event Identifier OPTIONAL, parameter Identifier },   -- без event: анонімна подія
    change  Identifier,
    read    NULL,
    exec    SEQUENCE OF Identifier,
    state   NULL
}

Predicate ::= SEQUENCE {
    kind      PredicateKind,
    variable  Identifier,
    op        PredicateOp,
    value     PredicateValue,
    inverted  BOOLEAN
}

PredicateKind ::= ENUMERATED { nop, cmp, range, bitmask, undef, raw }

PredicateOp ::= ENUMERATED { eq, ne, lt, le, gt, ge, in, and }

PredicateValue ::= CHOICE {
    none     NULL,
    integer  INTEGER,
    boolean  BOOLEAN,
    range    SEQUENCE { lo INTEGER (-32768..32767), hi INTEGER (-32768..32767) },
    name     Identifier
}

Action ::= SEQUENCE {
    kind     ActionKind,
    target   Identifier,
    operand  ActionOperand
}

ActionKind ::= ENUMERATED { inc, dec, add, sub, assign, setConst, nop, raw }

ActionOperand ::= CHOICE {
    none     NULL,
    integer  INTEGER,
    boolean  BOOLEAN,
    undef    NULL,
    name     Identifier,
    text     UTF8String
}

Test ::= SEQUENCE {
    name   Identifier,
    steps  SEQUENCE (SIZE (1..MAX)) OF TestStep
}

TestStep ::= CHOICE {
    send    SEQUENCE {
                target     Identifier,
                parameter  Identifier OPTIONAL,
                value      SendValue,
                extra      SEQUENCE OF INTEGER
            },
    expect  SEQUENCE {
                target  Identifier,
                op      CompareOp,
                value   ExpectValue
            }
}

SendValue ::= CHOICE { integer INTEGER, undef NULL }

ExpectValue ::= CHOICE { integer INTEGER, real REAL, boolean BOOLEAN, undef NULL }

END
```

`PredicateOp` для `bitmask` дорівнює `and` (побітове `&`), а для `range` — `in`.

---

## 9. Профіль `EKPOL-B64`: нормативна семантика

### 9.1. Умови прийняття

Програма належить профілю, якщо виконуються всі умови в порядку перевірки:

| ID | Умова | Код |
|---|---|---|
| `EKPOL-B64-1` | `1 ≤ |concepts| ≤ 64`. | `EKPOL-SYNTAX-ERR` |
| `EKPOL-B64-2` | Кожен концепт має тип `Int32`. | `EKPOL-TYPE-ERR` |
| `EKPOL-B64-3` | Початкове значення — ціле, не `⊥`. | `EKPOL-TYPE-ERR` |
| `EKPOL-B64-4` | Серед інваріантів є пункт невід'ємності: `>= v` з `v ≥ 0`, `> v` з `v ≥ −1` або `LO..HI` з `LO ≥ 0`. | `EKPOL-INVARIANT-ERR` |
| `EKPOL-B64-5` | Початкове значення `≥ 0`. | `EKPOL-INVARIANT-ERR` |
| `EKPOL-B64-6` | Рівно одне правило в концепті. | `EKPOL-SYNTAX-ERR` |
| `EKPOL-B64-7` | Вид правила — `write` або `change`; для `change` джерело оголошене, не є самим концептом і має щонайбільше одного підписника. | `EKPOL-TYPE-ERR` / `EKPOL-CYCLE-ERR` |
| `EKPOL-B64-8` | Граф підписок ациклічний. | `EKPOL-CYCLE-ERR` |
| `EKPOL-B64-9` | Якщо `P.kind ≠ nop`, то `P.var` дорівнює вхідній змінній правила. | `EKPOL-SYNTAX-ERR` |
| `EKPOL-B64-10` | `P.kind ∈ {nop, cmp, range, bitmask}`; для `cmp` значення ціле, не логічне; межі `range` лежать в `int16`. | `EKPOL-TYPE-ERR` / `EKPOL-RANGE-ERR` |
| `EKPOL-B64-11` | Для правила `change(src)`: `eval(P, init(src)) = ff` (§9.4). | `EKPOL-CYCLE-ERR` |
| `EKPOL-B64-12` | Рівно одна дія, її ціль — сам концепт. | `EKPOL-SYNTAX-ERR` |
| `EKPOL-B64-13` | Дія `inc`, `dec`, `add`/`sub` з `K ≥ 1` або `assign` з вхідної змінної. | `EKPOL-SYNTAX-ERR` |
| `EKPOL-B64-14` | Видавець каскаду має дію `inc`, `dec`, `add` або `sub`. | `EKPOL-CYCLE-ERR` |
| `EKPOL-B64-15` | Предикат `cmp`, `range` або `bitmask` разом з `add`/`sub` заборонений через спільне слово `W1`. | `EKPOL-COLLISION-ERR` |
| `EKPOL-B64-16` | Перехресна перевірка й тести за §9.5 проходять. | `EKPOL-PROOF-ERR` |

### 9.2. Зниження в `CME-RAW-1`

**EKPOL-B64-17.** Концепт з індексом оголошення `i` отримує `CID = i`; слоти `CID ≥ |concepts|` нульові. Для концепту `c` з правилом `r` і предикатом `P` у полях `CME-RAW-1` записуються:

| `P` | `pred_opcode` | `inv` у прапорці `0x08` | `W1` |
|---|---|---|---|
| `nop` | `NOP` | `P.inv` | — |
| `cmp ==` / `!=` | `EQ` / `NEQ` | `P.inv` | `K mod 2³²` |
| `cmp <` / `>` | `LT` / `GT` | `P.inv` | `K mod 2³²` |
| `cmp >=` | `LT` | `¬P.inv` | `K mod 2³²` |
| `cmp <=` | `GT` | `¬P.inv` | `K mod 2³²` |
| `range [lo, hi]` | `RANGE` | `P.inv` | `((hi AND 0xFFFF) << 16) OR (lo AND 0xFFFF)` |
| `bitmask M` | `BITMASK` | `P.inv` | `M mod 2³²` |

| Дія | `action_opcode` | `W1` |
|---|---|---|
| `inc` / `dec` | `INC` / `DEC` | — |
| `add K` / `sub K` | `ADD` / `SUB` | `K mod 2³²` |
| `assign(x)` | `ASSIGN` | — |

Інші поля: `W0 = init mod 2³²`; `guard_flags = 0x01 | 0x02 | (inv ? 0x08 : 0) | (c — видавець ? 0x10 : 0)`; `hazard_limit = 0`; `W3 = CID` підписника для видавця, інакше `0`. Якщо `W1` використовує предикат, він має пріоритет над дією; за правилом `EKPOL-B64-15` обидва одночасно не трапляються.

### 9.3. Динамічна семантика

**EKPOL-B64-18.** Виконання програми профілю тотожне виконанню її образу за [§7.2 специфікації KPOL](kpol-formal-specification.md#72-апаратна-семантика-кроку-дескриптора):

* зовнішня подія правила `write` концепту `c` з параметром `p` подається до `CID(c)`;
* після `COMMIT` видавця каскадна подія надходить до підписника з параметром, що дорівнює новому значенню видавця;
* інваріант, що перевіряє апаратура, — це **лише** `стан ≥ 0 ∧ ¬переповнення`.

> **Попередження безпеки.** Пункти інваріанта, відмінні від невід'ємності, наприклад `<= 200`, і сильніші межі, наприклад `>= 5`, приймаються, але **не виконуються** апаратурою й не переносяться в KPOL (`D-E8`). Відповідна програма `EKPOL-B64` НЕ ПОВИННА оголошувати таких пунктів, доки власник не вирішить відхиляти або реалізовувати їх.

### 9.4. Оцінка предиката на цілому

```text
eval(P, v) = (P.inv ? ¬b : b), де
  b = tt                         для nop
  b = v op K                     для cmp
  b = lo ≤ v ≤ hi                для range
  b = (v AND M) ≠ 0              для bitmask
```

### 9.5. Тести та перехресна перевірка з KPOL

**EKPOL-B64-19 (тести).** Блок `test` у профілі МУСИТЬ використовувати:

* `send` до концепту з правилом `write` або до імені його події, з одним аргументом `int_lit`; додаткові аргументи ігноруються (`D-E13`);
* `expect C op K`, де `C` — концепт, а `K` — `int_lit`.

Семантика тесту: `send` подає зовнішню подію й чекає завершення каскаду; `expect` перевіряє стан після кроку. Це семантика `step`/`expect` KPOL (KPOL-PRF-1) для `T_EK(P)` за §10.1, рівна апаратній за [KPOL §7.5](kpol-formal-specification.md#75-відповідність-інтерпретатора-та-апаратури).

**EKPOL-B64-20 (перехресна перевірка в еталонній реалізації).** Якщо програма не містить предикатів `bitmask`, еталонна реалізація:

1. будує `T_EK(P)` (§10.1);
2. обирає профіль `KPOL-CME-1`, якщо `|concepts| = 1`, тестів немає, а дія є `inc` або `dec`; інакше — `KPOL-CME-2`;
3. для `KPOL-CME-2` без тестів при `|concepts| > 1` синтезує сценарій `AutoGeneratedSanityCheck`;
4. компілює `T_EK(P)` у вибраному профілі й вимагає побайтної рівності з образом §9.2.

Будь-яка відмова дає `EKPOL-PROOF-ERR`, а нерівність образів — `EKPOL-SYNTAX-ERR` `internal lowering mismatch`. Наслідки для відповідної програми:

* програма з одним концептом без `test` приймається лише тоді, коли `T_EK(P)` належить `KPOL-CME-1`: дія `inc`/`dec` і охоронець `true`, `x < K`, `x > K`, `x == K`, `x != K`, `is positive`, `is negative`, `is null` або `is not null` без заперечення. Тому програма з одним концептом ПОВИННА містити блок `test`;
* програма з одним концептом без `test`, що має дію `assign`, `add` або `sub`, відхиляється (`CME2-PROOF`) (`D-E12`).

Програми з предикатами `bitmask` еталонна реалізація не перевіряє перехресно й **не виконує** їхніх тестів; VMK їх виконує (`D-E7`).

---

## 10. Трансляція EKPOL ↔ KPOL

### 10.1. `T_EK`: EKPOL-B64 → KPOL

Область визначення: програми `EKPOL-B64` без предикатів `bitmask`. Для `bitmask` еталонна функція повертає текст з охоронцем `x != 0`, що змінює семантику (`D-E7`).

| Елемент EKPOL | Результат KPOL |
|---|---|
| ім'я модуля | `Problem M`, `Solution M`, `Proof M` |
| інваріант кожного концепту | `NonNeg: c >= 0;` при одному концепті, інакше `I_c: c >= 0;` |
| концепт `c` | `state c: Int32 = init;` |
| правило `write` концепту `c` | `event ev(c)(p: Int32);` і `rule rn(c) on ev(c) when guard(P) { set …; }` |
| правило `change(src)` | `rule rn(c) on change(src) when guard(P) { set …; }` |
| `guard(P)` | `true`/`false` для `nop`; `x op K`; `x >= lo and x <= hi`; з `inv` — `not (…)` |
| `inc`, `dec`, `add K`, `sub K`, `assign(x)` | `set c := c + 1;`, `c - 1`, `c + K`, `c - K`, `x` |
| `test T` | `scenario T { step ev(c)(p = v); expect c op K; }` |
| прагми потоків | рядки `# @stdin …`, `# @stdout …` |

Детерміновані імена: `ev(c)` — ім'я події, якщо воно задане в правилі; інакше `Pulse`, якщо програма має один концепт з іменем `Counter`; інакше `E<n>` для імені `C<n>`; інакше `Ev` + ім'я концепту без підрядків `_mV` і символів `_`. `rn(c)`: `Step` для одного концепту `Counter`; `R<n>` для `C<n>`; інакше `R_` + ім'я. Збіг похідних імен подій, наприклад для `A_B` і `AB`, дає `EKPOL-PROOF-ERR` (`D-E11`).

### 10.2. `T_KE`: KPOL → EKPOL

Область, на якій трансляція не втрачає інформації: модулі `KPOL-CME-1/2`, у яких ініціалізатори є невід'ємними цілими літералами, аргументи `step` — цілі літерали або заперечені літерали, `expect` має вигляд `ім'я op невід'ємний_літерал`, а `assert` відсутні. Поза цією областю еталонна функція підставляє `0` замість нелітерального ініціалізатора й аргументу, мовчки пропускає інші `expect` і `assert` та завжди пише `[>= 0]`.

Відображення: стан → `concept c: i32|int32 = init [>= 0]`; правило події → `<- E(p) :: g => a .` або `on E(p) when g => a commit;`; правило `change` → `~ s :: g => a .` або `on change(s) when g => a commit;`. Охоронець переписується так: зовнішні `not` дають `!(…)` або `not (…)`; пара меж `and` — `x in lo..hi`; порівняння — з іменем ліворуч. Сценарій → `test` з `send <концепт або подія>(v);` і `expect …;`.

**EKPOL-TR-1 (властивість образу).** Для кожного модуля `M` з області §10.2: `image(T_KE(M)) = image(M)` в обох стилях. Властивість перевірено на корпусі Додатка A; загальний доказ не заявляється.

---

## 11. Концептуальні конструкції: статус

**EKPOL-CON-1.** Для конструкцій шару «концептуальні» з §0.2 EKPOL 0.1.0 визначає **лише синтаксис** і модель AST. Динамічна семантика не визначена: її вимагає рішення власника з урахуванням відкритих авторських питань `RFC-016` і `RFC-017`.

**EKPOL-CON-2 (фактична поведінка VMK, не норма).** Режим `vmk --mode conceptual`:

* вибирає один із п'яти вбудованих симуляторів — `if`, `sum`, `nod`, `factorial`, `tachometer` — за іменем модуля або першого концепту;
* для інших програм виконує запис як пряме присвоєння параметра, **ігноруючи** охоронці та дії.

Тому результати концептуальних прикладів, наприклад `Factorial(5) = 120` у `factorial.ekpol`, є властивостями симулятора й **не виводяться** з тексту програми. Їх МУСИТЬ НЕ використовувати як доказ семантики EKPOL.

---

## 12. Діагностика

| Код | Значення |
|---|---|
| `EKPOL-SYNTAX-ERR` | Порожнє джерело; незакритий коментар або дужка; невідомий текст рівня програми; повтор концепту; відсутній `=>` або термінатор; нерозпізнаний тригер, охоронець, дія чи інструкція тесту; невідповідність змінної охоронця; кількість концептів поза `1..64`; кількість правил або дій ≠ 1 у B64; крок `< 1`; невідповідність образів під час перехресної перевірки. |
| `EKPOL-TYPE-ERR` | Невідомий тип; недопустиме початкове значення; ціле поза діапазоном; концептуальна конструкція в B64. |
| `EKPOL-INVARIANT-ERR` | Порожні дужки; недопустимий пункт; `LO > HI`; чужий ідентифікатор; немає пункту невід'ємності; початкове значення `< 0`. |
| `EKPOL-RANGE-ERR` | Межі поза `int16`; `lo > hi`; неповна або неправильна пара меж у кон'юнкції. |
| `EKPOL-COLLISION-ERR` | Спільне використання `W1` предикатом і кроком `add`/`sub`. |
| `EKPOL-CYCLE-ERR` | Підписка на неоголошений концепт; самопідписка; `fan-out > 1`; цикл; активний на старті охоронець `change`; видавець без ненульового кроку. |
| `EKPOL-PROOF-ERR` | Порожній тест; невідома ціль `send`; провал тесту; відмова профілю KPOL під час перехресної перевірки, коли вкладене повідомлення містить код `B3-*` або `CME2-*`. |

---

## Додаток A. Еталонні тестові вектори

Для кожного файлу `.ekpol` профілю B64 образ МУСИТЬ побайтно збігатися з образом відповідного `.kpol` ([Додаток A специфікації KPOL](kpol-formal-specification.md#додаток-a-еталонні-тестові-вектори)). Рівність образів після `T_KE` перевірено для обох стилів.

| Файл | Профіль | SHA-256 образу |
|---|---|---|
| [`increase.ekpol`](../../sw/vmk-go/examples/increase.ekpol) | B64 | `4df05b189b9bf12052d98ab6084e0256454c60cae4afd4449469c060ba8dcc5d` |
| [`decrease.ekpol`](../../sw/vmk-go/examples/decrease.ekpol) | B64 | `00ba66e57e21d14913c95d7d2fc8c45c3c450548510ca3155721d7eec67b78c3` |
| [`cascade_4concept.ekpol`](../../sw/vmk-go/examples/cascade_4concept.ekpol) | B64 | `032c4705c91cea6ddddb7d449cd0dcbd6ba62359af1f9e7a846f33c341a7ef38` |
| [`bms_safety_cascade.ekpol`](../../sw/vmk-go/examples/bms_safety_cascade.ekpol) | B64 | `de03442454424b5cf64478506f118c13f095ae24ba58db8894583c43567ea3ee` |

Концептуальні файли [`factorial.ekpol`](../../sw/vmk-go/examples/factorial.ekpol), [`if_toggle.ekpol`](../../sw/vmk-go/examples/if_toggle.ekpol), [`nod_euclid.ekpol`](../../sw/vmk-go/examples/nod_euclid.ekpol), [`sum_autoreset.ekpol`](../../sw/vmk-go/examples/sum_autoreset.ekpol) і [`tachometer.ekpol`](../../sw/vmk-go/examples/tachometer.ekpol) синтаксично відповідні, але в B64 відхиляються з `EKPOL-TYPE-ERR`, бо використовують `U64`, `Float` або `Bool`.

---

## Додаток B. Трасування правил до реалізації

| Правила | Python | Go |
|---|---|---|
| `EKPOL-PRE-*` | `_strip_comments_preserve_pragmas`, `parse_ekpol` | `stripCommentsPreserveEKPOLPragmas`, `ParseEKPOL` |
| `EKPOL-LEX-*`, `EKPOL-STA-1` | `TYPE_SYNONYMS`, `_parse_init_value`, `_parse_int_literal` | `ekpolTypeSynonyms`, `ParseEKPOL` |
| `EKPOL-SYN-1/2` | `parse_ekpol` | `ParseEKPOL` |
| `EKPOL-SEG-*` | `_split_concept_statements` | `splitEKPOLConceptStatements` |
| `EKPOL-STA-2` | `_parse_bracket_invariants` | `parseEKPOLBracketInvariants` |
| `EKPOL-SYN-3..6`, `EKPOL-STA-4` | `_parse_concept_rule` | `parseEKPOLConceptRule`, `extractGuardClause` |
| `EKPOL-SYN-7..9` | `_parse_predicate`, `_parse_single_cmp_clause` | `parseEKPOLPredicate`, `parseEKPOLSingleCmpClause` |
| `EKPOL-SYN-10` | `_parse_actions` | `parseEKPOLActions` |
| `EKPOL-SYN-11` | `_parse_test_block` | `parseEKPOLTestBlock` |
| `EKPOL-B64-1..18` | `validate_ekpol_for_bram64`, `_eval_pred_on_int` | `ValidateEKPOLForBRAM64`, `evalEKPOLPredOnInt` |
| `EKPOL-B64-19/20` | `compile_ekpol_to_bram_image`, `transpile_ekpol_to_kpol` | `CompileEKPOLSource` |
| `EKPOL-TR-*` | `transpile_ekpol_to_kpol`, `transpile_kpol_to_ekpol` | `TranspileEKPOLToKPOL`, `TranspileKPOLToEKPOL` |
| `EKPOL-CON-2` | — | `NewConceptualVMFromEKPOL`, `ExecuteGenericWrite` |

---

## Додаток C. Відомі розбіжності та невизначеності

| ID | Фактична поведінка | Вимога до відповідної програми |
|---|---|---|
| `D-E1` | Цілі з провідним нулем: Python відхиляє `010`, Go читає `010` як вісімкове `8`. Обидві реалізації також приймають `0o…`, `0b…`, `_`, `+`, `0X…`. | Лише форми `dec_int` / `int_lit` з `EKPOL-LEX-1`. |
| `D-E2` | Go приймає `::x` і `when(x)` без пробілу; Python вимагає пробіл. | Пробіл після `::` і `when`. |
| `D-E3` | Python бере з прагм лише ідентифікатори, Go — будь-які лексеми. | Лише імена концептів у прагмах. |
| `D-E4` | Go не перевіряє діапазон `Int32` для початкового значення й записує `uint32(int32(x))`, тобто з переповненням; Python відхиляє значення поза діапазоном. | Початкові значення в `Int32`. |
| `D-E5` | Без `module` ім'я модуля обирається евристикою за конкретними іменами (`Counter` → `Increase`/`Decrease`/`DecreaseFromOne`, набори BMS і `C0..C3`); у Go евристика менш точна. | Завжди оголошувати `module`. |
| `D-E6` | Обидві реалізації приймають не-ASCII `•`, `¬` і псевдоніми `!`, `~false`, `True`, `False`, `Unknown`. | Лише відповідні форми. |
| `D-E7` | `bitmask` не має відповідника в KPOL: `T_EK` дає `x != 0`. Python не виконує перехресної перевірки й тестів для таких програм; Go тести виконує. | Для `bitmask` покладатися лише на тести, виконані VMK, і на звітну перевірку. |
| `D-E8` | Пункти інваріанта, крім невід'ємності, приймаються й ігноруються в B64 та `T_EK`. | Не оголошувати їх у B64 (§9.3). |
| `D-E9` | Тип параметра `write`-правила ігнорується в B64 і `T_EK`. | Лише `Int32` або без анотації. |
| `D-E10` | Анотації в кінці файлу без концепту мовчки відкидаються. | Не залишати таких анотацій. |
| `D-E11` | Похідні імена подій можуть збігатися. | Унікальні імена або явні `on Ev(p)`. |
| `D-E12` | Перехресна перевірка `EKPOL-B64-20` відхиляє частину програм з одним концептом без `test`; Go такої перевірки не має. | Завжди мати `test` у B64. |
| `D-E13` | Додаткові аргументи `send` ігноруються в `T_EK`. Python відхиляє `send` до концепту з правилом `change`, Go подає подію до його CID. | Один аргумент; `send` лише до `write`-концептів. |
| `D-E14` | Концептуальний режим VMK використовує диспетчеризацію за іменами (§11). | Не вважати його реалізацією семантики. |
| `D-E15` | [Описова специфікація EKPOL](ekpol-specification.md) містила твердження, яких немає в реалізації: `[>= 0, <= H]` → `hazard_limit` і `HAZARD_EN`; `pass`/`nop` → `CME_ACT_NOP (0x05)`; «безвтратна» трансляція для всіх програм; EBNF з довільними `&&`-ланцюжками й `&`-порівняннями. | Керуватися цим документом. |

---

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 1.0.0 | 2026-11-19 | Перша формальна специфікація EKPOL 0.1.0: попередня обробка, EBNF, PEG, ASN.1 AST, нормативний профіль `EKPOL-B64`, трансляції `T_EK`/`T_KE`, статус концептуальних конструкцій, тестові вектори та реєстр розбіжностей `D-E1..D-E15`. |

## Абревіатури та глосарій

* **EKPOL** — *Ergonomic KPOL*, ергономічний ASCII-запис програм Машини Кузьміна.
* **B64 / `bram64`** — профіль, що знижується в 64-слотовий образ `CME-RAW-1`.
* **PEG** — *Parsing Expression Grammar*, граматика з упорядкованим вибором.
* **EBNF** — розширена форма Бекуса — Наура, ISO/IEC 14977.
* **ASN.1** — *Abstract Syntax Notation One*, ITU-T X.680.
* **`T_EK` / `T_KE`** — трансляції EKPOL → KPOL і KPOL → EKPOL.
* **Видавець / підписник** — концепт-джерело `change(src)` і концепт, що на нього підписаний.
* **`⊥`** — невизначене значення (`_`, `undef`).
