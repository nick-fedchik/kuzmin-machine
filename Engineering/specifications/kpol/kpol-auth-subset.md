# KPOL-AUTH: специфікація підтримуваного підмножинного фронтенду та детермінованого lowering

* **Версія:** 0.1.0
* **Дата:** 2026-11-16
* **Тип WP редакції NG:** Specification
* **Статус:** Реалізовано у прототипному пакеті [`Engineering/sw/kpol-auth/`](../../sw/kpol-auth/__init__.py) для рецензування; **не закриває** дослідницьку задачу [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186), доки відкриті запити до Автора (`RFC-016`, `RFC-017` п. 2–3, `RFC-018` п. 2, `RFC-009` п. 3), і не змінює чинні інженерні профілі [`KPOL-CME-1`](kpol-cme-subset.md) та [`KPOL-CME-2`](kpol-cme2-profile.md).
* **WI:** закриває [#245](https://github.com/nick-fedchik/kuzmin-machine/issues/245); просуває [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186) та епік S5 [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8) (спирається на результати `#218`, `#219`, `#224`, `#233`, `#243`).
* **Походження та межа атрибуції:** цей документ і реалізація в `Engineering/sw/kpol-auth/` є **похідними інженерними артефактами проєкту** (М. Федчик, ШІ-агенти), а **не авторською специфікацією** Михайла Ювеналійовича Кузьміна. Первинні твердження Автора наведено виключно за картками [`Research/sources/`](../../../Research/sources/README.md) із позначкою **[П]**; похідні інженерні рішення позначено **[В]**; неврегульовані питання позначено **[Відкрито]** і заблоковано політикою `fail-closed`.
* **Укладач:** GitHub Copilot CLI (`Claude`); незалежна рецензія не проведена.

---

## 1. Призначення, архітектурні межі та правила атрибуції

Пакет [`Engineering/sw/kpol-auth/`](../../sw/kpol-auth/__init__.py) ізолює дослідницький native-діалект `KPOL-AUTH` від поточного інженерного референсу [`kpol_reference.py`](../../sw/kpol-ref/kpol_reference.py) (`Problem / Solution / Proof`), не змішуючи їх евристиками в одному парсері:

1. **Фронтенд native-діалекту (`lexer.py`, `cst.py`, `uncertainty.py`, `corpus.py`):** виконує контекстно-вільну лексичну сегментацію з точними координатами Unicode codepoints та байтовими зміщеннями UTF-8 (`byte_offset` / `byte_end`), перевіряє парність роздільників і дужок за `RFC-011`, будує дерево конкретного синтаксису (`CST`) і детерміновано блокує всі 12 відкритих семантичних/лексичних точок невизначеності (`KPOL-AUTH-U01..U12`) у режимі `fail-closed`.
2. **Похідний бекенд lowering (`lowering.py`, `__main__.py`):** транслює вузьку детерміновану підмножину `CST` без відкритих діагностик у:
   * 32-бітний байткод стекової віртуальної машини `Do/Go` (`code_o`) і таблицю підписок, побітово сумісні з [`km_mcu_fpga_bridge.c`](../../sw/runtime/mcu/km_mcu_fpga_bridge.c);
   * 1024-байтний образ маршрутизації `CME-RAW-1` ($64 \times 16$ байтів) для апаратного конвеєра `CFG-P` зі статичною перевіркою ациклічності та монотонності рангу (`KPOL-LOWER-CYCLE`).

У всьому тексті цієї специфікації застосовано трирівневе маркування тверджень:
* **[П]** — дослівно зафіксовано у первинних матеріалах або переданих відповідях М. Ю. Кузьміна в [`Research/sources/author/`](../../../Research/sources/README.md) (зокрема [`rfc-2026-11-12.md`](../../../Research/sources/author/rfc-2026-11-12.md), [`introduction-2026-11-13.md`](../../../Research/sources/author/introduction-2026-11-13.md), [`introduction-revision-2026-11-13.md`](../../../Research/sources/author/introduction-revision-2026-11-13.md), [`clarifications-2026-11-13.md`](../../../Research/sources/author/clarifications-2026-11-13.md), [`group-execution-2026-11-13.md`](../../../Research/sources/author/group-execution-2026-11-13.md), [`rfc-answers-2026-11-15.md`](../../../Research/sources/author/rfc-answers-2026-11-15.md));
* **[В]** — робоча інженерна інтерпретація або похідний контракт реалізації проєкту (не приписується Автору);
* **[Відкрито]** — питання поза межами наявних джерел (`RFC-016`, `RFC-017` п. 2–3 та проміжний стан `busy` у п. 1, `RFC-018` п. 2 та остаточна роль `Child`, `RFC-009` п. 3 та підтвердження атрибуції 2-ї відповіді до п. 2, `RFC-015` щодо фази виконання дужок і канонічного імені, `RFC-014` щодо фізичних адрес), які утримують [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186) у статусі очікування (див. [чинну карту цілей, потреб і WI](../../../Project/registers/goals-needs-work-items.md)).

---

## 2. Трасування кандидатів `KPOL-AUTH-01..08` до джерел та меж невизначеності

Таблиця нижче зіставляє вісім кандидатів вимог із [`Engineering/requirements/kpol.md §3.1`](../../requirements/kpol.md#31-кандидати-за-новою-презентацією) з первинними джерелами, похідним представленням у фронтенді/бекенді та відкритими межами (детальний аналіз варіантів — у [`rfc-impact-and-q3-draft-report.md`](../../../Research/studies/author-semantics/rfc-impact-and-q3-draft-report.md)):

| Елемент вимоги | Встановлено у первинних джерелах (**[П]**) | Похідне представлення у `kpol-auth` (**[В]**) | Відкриті питання та код блокування (**[Відкрито]**) |
| :--- | :--- | :--- | :--- |
| **`KPOL-AUTH-01`**<br>Розкладка концепту, `Token`, `Def`, `Class`, розмір | **[П]** `Size` замінено порожнім ім'ям з розміром у 4-бітних `Token`; `Def` — маска присутності елементів концепту (`RFC-010` у [`clarifications-2026-11-13.md`](../../../Research/sources/author/clarifications-2026-11-13.md)); слайд 2 ([`introduction-2026-11-13.md`](../../../Research/sources/author/introduction-2026-11-13.md)) перелічує `Def 0..7`; відповідь на [`RFC-018`](https://github.com/nick-fedchik/drafts/blob/84812f6448713d61caa30578b7021ca05ab80910/KuzminMachine/RFC/RFC-018-def-bitmask-order-and-empty-vs-uninit.md) ([`rfc-answers-2026-11-15.md`](../../../Research/sources/author/rfc-answers-2026-11-15.md)): «слева младший-справа старший… один лишний. Child… При разработке уточним». | **[В]** Вузол `DefLayoutCST` (`bit_order="lsb_left_msb_right"`) приймає підтверджений 7-бітний вектор без `Child` (`EX-03`), відхиляє ширини $\notin \lbrace 7, 8 \rbrace$ з `KPOL-AUTH-SYNTAX-04` і не змішує `Def` із `CME-RAW-1` `W0..W3`. У `lowering.py` `DefLayoutCST` не опускається в `BRAM` (`KPOL-LOWER-UNSUPPORTED-CST`). | **[Відкрито]** Остаточна доля 8-го біта `Child` (`RFC-018` п. 1 → `KPOL-AUTH-U11`) та розрізнення `Def[i]=0` проти присутнього елемента зі значенням `_` (`RFC-018` п. 2 / `RFC-010` п. 3 → `KPOL-AUTH-U12`); двійкові коди `Class`. |
| **`KPOL-AUTH-02`**<br>`Name`, `Help`, безіменний атрибут, порядок | **[П]** Слайд 1–2, 5, 7 ([`introduction-2026-11-13.md`](../../../Research/sources/author/introduction-2026-11-13.md)): концепт зберігає `Name` (ліміт 16), `Help` і порядок елементів; `RFC-011` ([`clarifications-2026-11-13.md`](../../../Research/sources/author/clarifications-2026-11-13.md)): текстові сутності обмежуються парними знаками, що звільняє `#`. | **[В]** `CallOrConstructCST` зберігає `Name(...)` та `TEXT`-літерали в `"..."` і `«...»` із точними зміщеннями `Span`; `AuthFrontendConfig.name_length_unit` має консервативний типовий режим `"utf8_bytes"` (альтернатива `"codepoints"`). | **[Відкрито]** [`RFC-016`](https://github.com/nick-fedchik/drafts/blob/84812f6448713d61caa30578b7021ca05ab80910/KuzminMachine/RFC/RFC-016-updated-delimiters-after-hash.md) (відповіді немає): нова пара роздільників замість `#` (`KPOL-AUTH-U05`), екранування закривального знака в `Text`/`Help` (`KPOL-AUTH-U06`), одиниця вимірювання ліміту 16 для `Name` (`KPOL-AUTH-U07`). |
| **`KPOL-AUTH-03`**<br>`Collection`, `Array`, межі `Min`/`Max`, відсутність циклів | **[П]** [`group-execution-2026-11-13.md`](../../../Research/sources/author/group-execution-2026-11-13.md) та 1-ша відповідь на [`RFC-009`](https://github.com/nick-fedchik/drafts/blob/84812f6448713d61caa30578b7021ca05ab80910/KuzminMachine/RFC/RFC-009-group-execution-bounds.md) ([`rfc-answers-2026-11-15.md`](../../../Research/sources/author/rfc-answers-2026-11-15.md)): «min=1 -одно обязательное выполнение max=15 максимум 16 раз. На 1 больше»; 2-га репліка: «пусть пока будет запуски. Внутри группы выполняются как семантическое И Array -ИЛИ»; `RFC-012`: апаратні цикли відсутні. | **[В]** Вузол `GroupBoundsCST` обчислює `min_effective = min_raw`, `max_effective = max_raw + 1` (зокрема `Min=1, Max=0` → `1..1`, `Min=1, Max=15` → `1..16`, `EX-01`, `EX-02`); атрибуція 2-ї репліки до `RFC-009` п. 2 зафіксована як припущення до підтвердження власника. | **[Відкрито]** Правило поєднання семантичного `И`/`ИЛИ` з `Min`/`Max` (`RFC-009` п. 2 → `KPOL-AUTH-U01`) та не-`Token` індекси / вихід `Count` за межі `[min_effective, max_effective]` (`RFC-009` п. 3 → `KPOL-AUTH-U02`). |
| **`KPOL-AUTH-04`**<br>Булеві/перелічувані концепти та події порівняння | **[П]** Слайд 4 ([`introduction-2026-11-13.md`](../../../Research/sources/author/introduction-2026-11-13.md)) та 2-га відповідь на [`RFC-017`](https://github.com/nick-fedchik/drafts/blob/84812f6448713d61caa30578b7021ca05ab80910/KuzminMachine/RFC/RFC-017-busy-release-and-uninitialized-ops.md) ([`rfc-answers-2026-11-15.md`](../../../Research/sources/author/rfc-answers-2026-11-15.md)): порівняння `A` і `B` формує три події `<`, `>`, `=`, за однією з яких запускається підписка; `_` кодується окремим валідним бітом (`RFC-005` у [`rfc-2026-11-12.md`](../../../Research/sources/author/rfc-2026-11-12.md)). | **[В]** Лексер зберігає окремі токени `BOOL_BANG` (`!`), `BOOL_NOT_SIGN` (`¬`), `UNINIT` (`_`), `EQ`/`LT`/`GT` без підміни нулем. У похідному `lowering.py` підтримано лише явні числові тригери `KM_EV_CHANGED`, `OnPositive` (`KM_EV_POSITIVE`) та `OnAbort`. | **[Відкрито]** Поведінка читання стану `_` в обчисленнях на зразок `C := _ + B` (`RFC-017` п. 3 → `KPOL-AUTH-U10`, через що відкладено RTL `CFG-P2` за [`ADR B7`](../../decisions/cme-raw2-kpol-sys02.md)) та серіалізація перелічуваних типів. |
| **`KPOL-AUTH-05`**<br>Метаподія / послідовність підписки `•` | **[П]** Слайд 3 ([`introduction-2026-11-13.md`](../../../Research/sources/author/introduction-2026-11-13.md)), [`RFC-001`](https://github.com/nick-fedchik/drafts/blob/84812f6448713d61caa30578b7021ca05ab80910/KuzminMachine/RFC/RFC-001-event-semantics.md) (відповідь 2026-11-11, локатор і межі у [`rfc-impact-and-q3-draft-report.md §3.2`](../../../Research/studies/author-semantics/rfc-impact-and-q3-draft-report.md#32-розмежування-джерел-первинне-vs-похідне--припущення-vs-не-визначено)), `RFC-013` ([`clarifications-2026-11-13.md`](../../../Research/sources/author/clarifications-2026-11-13.md)) та відповіді 2–3 на [`RFC-017`](https://github.com/nick-fedchik/drafts/blob/84812f6448713d61caa30578b7021ca05ab80910/KuzminMachine/RFC/RFC-017-busy-release-and-uninitialized-ops.md): у `A • B` підписка `B` стартує після читання поточного значення, виконує `Do` і лише після цього записує нове значення; `•` **не є** унарним `not`. | **[В]** `SubscriptionSeqCST` розбирає бінарну форму `left • right` (`EX-05`); унарний префікс `• Flag` відхиляється синтаксичною помилкою `KPOL-AUTH-SYNTAX-03` (`EX-06`). У `lowering.py` форма `Src • Assign(Dst, Expr)` генерує лінію `Do/Go` (`READ` → `DO` → `WRITE` → `EXIT`) та ребро каскаду `POST_CHANGE`. | **[Відкрито]** Булеве значення виразу `(A • B)` у присвоєнні (`RFC-017` п. 2 → `KPOL-AUTH-U08`) та видимий стан `busy(A)` між читанням і записом (`RFC-017` п. 1 → `KPOL-AUTH-U09`). |
| **`KPOL-AUTH-06`**<br>Параметри `@`, адресація та види активації | **[П]** `RFC-006` ([`rfc-2026-11-12.md`](../../../Research/sources/author/rfc-2026-11-12.md)) і слайди 5–6 ([`introduction-2026-11-13.md`](../../../Research/sources/author/introduction-2026-11-13.md)): `@` позначає параметри транслятора/підписки; `RFC-014` ([`clarifications-2026-11-13.md`](../../../Research/sources/author/clarifications-2026-11-13.md)): адресація апаратних портів відкладена до платформи. | **[В]** `ParamCST` зберігає вузол `@target` у CST без підміни на розіменування вказівника чи MMIO-адресу; у `lowering.py` `ParamCST` відхиляється як `KPOL-LOWER-UNSUPPORTED-CST`. | **[Відкрито]** Формат фізичних адрес пінів/портів та режимів резолюції (`RFC-014`, `Q-AUTH-06`); використання `@runtime` для дужок блокується `KPOL-AUTH-U04`. |
| **`KPOL-AUTH-07`**<br>Лексеми `Type/First/Length` і парні дужки | **[П]** Слайди 5, 7–8 ([`introduction-2026-11-13.md`](../../../Research/sources/author/introduction-2026-11-13.md)) та `RFC-011` ([`clarifications-2026-11-13.md`](../../../Research/sources/author/clarifications-2026-11-13.md)): закривальна дужка зобов'язана відповідати типу відкривальної (`{...}`, `(...)`, `[...]`); у круглих дужках елементи розділяються комами. | **[В]** `tokenize()` і `parse_bracket_group()` контролюють строгу відповідність пар дужок (`KPOL-AUTH-SYNTAX-02`), зберігають `comma_tokens` і точні `offset`/`length` у codepoints разом із `byte_offset`/`byte_end` у UTF-8. | **[Відкрито]** Остаточна таблиця парних роздільників після скасування `#` та одиниця полів `First`/`Length` (`RFC-016` п. 1–3 → `KPOL-AUTH-U05..U07`). |
| **`KPOL-AUTH-08`**<br>Виконувані дужки `OpenBracket` / `CloseBracket` у `Static` | **[П]** Слайд 5 редакції ([`introduction-revision-2026-11-13.md`](../../../Research/sources/author/introduction-revision-2026-11-13.md)), повідомлення у [`clarifications-2026-11-13.md`](../../../Research/sources/author/clarifications-2026-11-13.md) та відповідь на [`RFC-015`](https://github.com/nick-fedchik/drafts/blob/84812f6448713d61caa30578b7021ca05ab80910/KuzminMachine/RFC/RFC-015-executable-brackets-in-static.md) ([`rfc-answers-2026-11-15.md`](../../../Research/sources/author/rfc-answers-2026-11-15.md)): «OpenBracket і CloseBracket не придумал как реализовывать… Считай пока заглушками… В трансляторе реализовано двумя функциями». | **[В]** `BracketGroupCST.has_stub_brackets = True` фіксує присутність структурних заглушок `OpenBracket` / `CloseBracket` у CST (`EX-04`) без генерації фіктивного апаратного opcode. | **[Відкрито]** Розбіжність написання `CloseBracket` проти `CloseBracked` (`RFC-015` → `KPOL-AUTH-U03`) та момент виконання в рантаймі проти транслятора (`@runtime`, `RFC-015` → `KPOL-AUTH-U04`). |

---

## 3. Лексична структура, координати UTF-8, CST та реєстр `KPOL-AUTH-U01..U12`

### 3.1. Координати `Span` і контекстно-вільний лексер (`lexer.py`)

Кожний токен `Token(kind, value, span)` та вузол `CSTNode(span)` несуть незмінну структуру `Span` ([`uncertainty.py`](../../sw/kpol-auth/uncertainty.py)):

* `line`, `column`, `end_line`, `end_column` — 1-базовані координати початку й кінця у кодових точках Unicode (властивості-синоніми `col`, `end_col`);
* `offset`, `length` — 0-базований індекс і довжина у символах Python `str`;
* `byte_offset`, `byte_end` — точні 0-базовані зміщення байтового зрізу у кодуванні UTF-8 (`source.encode("utf-8")[byte_offset:byte_end]`), що гарантує однозначну прив'язку діагностики на багатобайтових кириличних ідентифікаторах та символах `•`, `«`, `»`, `¬`.

Таблиця токенів [`lexer.py`](../../sw/kpol-auth/lexer.py):

| Клас токенів | Лексеми | Код `Token.kind` | Поведінка та коди помилок |
| :--- | :--- | :--- | :--- |
| Відкривальні дужки | `{`, `(`, `[` | `LBRACE`, `LPAREN`, `LBRACKET` | Вимагають парної закривальної дужки того самого типу (`BRACKET_PAIRS`: `{`→`}`, `(`→`)`, `[`→`]`) |
| Закривальні дужки | `}`, `)`, `]` | `RBRACE`, `RPAREN`, `RBRACKET` | Невідповідність типу або зайва/незакрита дужка → `KPOL-AUTH-SYNTAX-02` |
| Парні текстові роздільники | `"..."`, `«...»` | `TEXT` | Незакритий літерал → `KPOL-AUTH-SYNTAX-01`; символ `\` всередині → `KPOL-AUTH-U06` |
| Звільнений символ `#` | `#` | `HASH_LEGACY` | Перед емісією токена спрацьовує гейт `KPOL-AUTH-U05` (`RFC-016` п. 1) |
| Оператори підписки й присвоєння | `•`, `:=`, `:` | `SUBSCRIPTION_SEQ`, `ASSIGN`, `COLON` | `•` — виключно бінарний роздільник послідовності підписки (`A • B`) |
| Маркер параметра й стан `_` | `@`, `_` (ізольований) | `AT`, `UNINIT` | `_` розпізнається як `UNINIT`, якщо за ним не йде буква/цифра/`_`; інакше частина `IDENT` |
| Арифметика, порівняння, кома | `+`, `-`, `*`, `/`, `=`, `<`, `>`, `,` | `PLUS`, `MINUS`, `STAR`, `SLASH`, `EQ`, `LT`, `GT`, `COMMA` | Використовуються у виразах, іменованих параметрах `Key=Val` і групах |
| Булеві знаки, цілі, ідентифікатори | `!`, `¬`, `[0-9]+`, `[A-Za-zА-Яа-яІіЇїЄєҐґ_][...]*` | `BOOL_BANG`, `BOOL_NOT_SIGN`, `INT`, `IDENT` | Будь-який інший символ поза пробільними → `KPOL-AUTH-LEX-01` |

### 3.2. Вузли дерева конкретного синтаксису (`cst.py`)

Парсер `parse_kpol_auth(source, config)` ([`cst.py`](../../sw/kpol-auth/cst.py)) будує корінь `ProgramCST(items, diagnostics, metadata)` із таких незмінних (`@dataclass(frozen=True)`) вузлів:

* `IdentifierCST(span, token)` — ідентифікатор концепту, конструкції або параметра;
* `LiteralCST(span, token)` — літерал `INT`, `TEXT`, `BOOL_BANG`, `BOOL_NOT_SIGN` або `HASH_LEGACY`;
* `UninitCST(span, token)` — явне позначення неініціалізованого стану `_`;
* `ParamCST(span, at_token, target)` — параметричний префікс `@target`;
* `BracketGroupCST(span, open_token, close_token, kind, elements, comma_tokens, has_stub_brackets)` — група виду `"collection_brace"` (`{...}`), `"collection_paren"` (`(...)`) або `"array_bracket"` (`[...]`), де `has_stub_brackets` фіксує присутність `OpenBracket`/`CloseBracket`;
* `CallOrConstructCST(span, name, group, bounds)` — іменована конструкція виду `Concept(...)`, `Static(...)`, `Collection(...)`, `Array(...)`, `Assign(...)`, `Name(...)`, `Property(...)`;
* `GroupBoundsCST(span, target, bracket_group, min_raw, max_raw, min_effective, max_effective)` — постфіксні межі `[Min=..., Max=...]` зі збереженням як сирих значень, так і ефективного діапазону `[min_raw, max_raw + 1]`;
* `DefLayoutCST(span, keyword, group, bits, bit_order)` — 7-бітна маска присутності `Def(...)` у порядку `"lsb_left_msb_right"`;
* `SubscriptionSeqCST(span, left, dot_token, right)` — бінарний ланцюжок підписки `left • right`;
* `AssignmentCST(span, target, op_token, value)` — оператор присвоєння `target := value`;
* `BinaryExprCST(span, left, op_token, right)` — бінарний арифметичний, порівняльний або ключовий (`Key=Val`) вираз.

Синтаксичні та лексичні коди відмов фронтенду (незалежно від політики `AuthFrontendConfig` завжди кидають `KpolAuthError`):
* `KPOL-AUTH-LEX-01` — невідомий символ у вхідному потоці;
* `KPOL-AUTH-SYNTAX-01` — несподіваний токен/EOF або незакритий текстовий роздільник (`"` / `«`);
* `KPOL-AUTH-SYNTAX-02` — незакрита, зайва або невідповідна за типом дужка (`{ A )`, `( A ]`, `[ A }`);
* `KPOL-AUTH-SYNTAX-03` — спроба використати `•` в унарній префіксній позиції (`• Flag`);
* `KPOL-AUTH-SYNTAX-04` — ширина `Def(...)` не дорівнює 7 бітам (8-бітний запис окремо маршрутизується в `KPOL-AUTH-U11`).

### 3.3. Реєстр `fail-closed` точок невизначеності `KPOL-AUTH-U01..U12` (`uncertainty.py`)

Єдина точка конфігурації `AuthFrontendConfig` за промовчанням встановлює для всіх 12 кодів політику `"fail-closed"` (генерація `KpolAuthError` з `Diagnostic(severity="error")`). Режим `"record-diagnostic"` дозволений лише для дослідницького інспектування CST у тестах, але все одно блокується перед кодогенерацією в `lowering.py` (`KPOL-LOWER-UNCERTAINTY`).

| Код | Джерело RFC | Предмет невизначеності | Умова спрацьовування у фронтенді | Еталон у `corpus.py` |
| :--- | :--- | :--- | :--- | :--- |
| `KPOL-AUTH-U01` | `RFC-009` п. 2 | Зв'язок семантичного `И` (`Collection`) / `ИЛИ` (`Array`) з межами `Min`/`Max` | Ключі `Logic=...` або `Op=...` у постфіксних межах `[...]` | `EX-07` |
| `KPOL-AUTH-U02` | `RFC-009` п. 3 | Не-`Token` індекси `Min`/`Max` та поведінка при виході `Count` за межі | Значення `Min`/`Max` не є цілим літералом або `Count` поза `[min_effective, max_effective]` | `EX-08` |
| `KPOL-AUTH-U03` | `RFC-015` | Канонічне написання `CloseBracket` проти `CloseBracked` | Ідентифікатор `CloseBracked` у вхідному тексті | `EX-09` |
| `KPOL-AUTH-U04` | `RFC-015` | Момент виконання `OpenBracket`/`CloseBracket` (транслятор проти рантайму) | Анотація `@runtime` у `ParamCST` | `EX-10` |
| `KPOL-AUTH-U05` | `RFC-016` п. 1 | Нова пара роздільників замість `#` та роль звільненого `#` | Поява символу `#` у вхідному потоці | `EX-11` |
| `KPOL-AUTH-U06` | `RFC-016` п. 2 | Запис (екранування/вкладення) закривального знака всередині `Text`/`Help` | Поява `\` всередині `"..."` або `«...»` | `EX-12` |
| `KPOL-AUTH-U07` | `RFC-016` п. 3 | Одиниця вимірювання довжини `Name` ($\le 16$: байти UTF-8, символи чи `Token`) | Довжина аргументу `Name("...")` перевищує `16` у обраній `name_length_unit` | `EX-13` |
| `KPOL-AUTH-U08` | `RFC-017` п. 2 | Зміст булевого значення `•` (факт звернення проти результату підписки `B`) | Присвоєння `Target := (... • ...)` із `SubscriptionSeqCST` справа | `EX-14` |
| `KPOL-AUTH-U09` | `RFC-017` п. 1 | Статус зайнятості `busy` концепту `A` між читанням і записом в `A • B` | Звернення до `busy` / `busy(...)` у правій частині `A • ...` | `EX-15` |
| `KPOL-AUTH-U10` | `RFC-017` п. 3 | Читання неініціалізованого стану `_` в арифметичних виразах | Оператор `+`, `-`, `*`, `/` над операндом `UninitCST` (`_`) | `EX-16` |
| `KPOL-AUTH-U11` | `RFC-018` п. 1 | Статус елемента `Child` («один лишний») та ширина маски `Def` (7 проти 8 бітів) | Ідентифікатор `Child` або 8-елементний виклик `Def(...)` | `EX-17` |
| `KPOL-AUTH-U12` | `RFC-018` п. 2 / `RFC-010` п. 3 | Розрізнення відсутнього елемента (`Def[i]=0`) і присутнього зі значенням `_` | Поєднання `DefBit=...` та `Value=_` у конструкції `Property(...)` | `EX-18` |

---

## 4. Розмежування символу `•` між `KPOL-AUTH` та інженерними профілями `KPOL-CME-1` / `KPOL-CME-2`

Ключова вимога [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186) та формальної верифікації [#227](https://github.com/nick-fedchik/kuzmin-machine/issues/227)/[#237](https://github.com/nick-fedchik/kuzmin-machine/issues/237) — повне відокремлення авторського значення символу `•` («Велика Крапка») від історичної нормалізації в похідному інженерному DSL:

| Критерій порівняння | Native-діалект `KPOL-AUTH` (`Engineering/sw/kpol-auth/`) | Інженерний референс без профілю (`kpol_reference.py`) | Профілі компіляції `KPOL-CME-1` / `KPOL-CME-2` |
| :--- | :--- | :--- | :--- |
| **Лексичний токен** | `SUBSCRIPTION_SEQ` (`•`); для булевого заперечення існують окремі лексеми `¬` (`BOOL_NOT_SIGN`) і `!` (`BOOL_BANG`). | **[В]** Історично лексер нормалізував `•` до ключового слова унарного логічного `not` (помічаючи `module.phase_aliases_used = True`). | **Повністю заборонено** в тексті модуля: будь-яка поява `•` або `(*)` відхиляється до емісії образу (`B3-GUARD` у `KPOL-CME-1`, `CME2-GUARD` у `KPOL-CME-2`). |
| **Синтаксична позиція** | Виключно інфіксний бінарний оператор `A • B` (`SubscriptionSeqCST`). Унарний запис `• Flag` відхиляється з `KPOL-AUTH-SYNTAX-03`. | Унарний префіксний булевий оператор у виразах `when` / `Invariants` / `Proof`. | Для логічного заперечення використовується виключно явне ключове слово `not` у секціях `when` та `Proof`. |
| **Операційна семантика** | **[П]** Пост-адресний бар'єр запуску підписки за `RFC-001`, `RFC-013`, `RFC-017` (відповіді 2–3): читання поточних значень → виконання підписки `Do` → запис результату в цільову комірку. | Булеве інвертування предиката ($\neg P$). | Апаратний каскад кодується декларативно через `rule R on change(S_src) when G { set S_dst := ...; }`, а взаємовиключність `commit` / `reject` у RTL доведена лемою `P_bigdot_mutex_pulse` ([#248](../../validation/kpol-cme/cme2-formal-227/report.md)). |
| **Булева роль `•` та читання `_`** | **[Відкрито]** Присвоєння `Flag := (A • B)` блокується `KPOL-AUTH-U08` (`RFC-017` п. 2); проміжний `busy` блокується `KPOL-AUTH-U09` (`RFC-017` п. 1); арифметика над `_` блокується `KPOL-AUTH-U10` (`RFC-017` п. 3); `DefBit` із `_` блокується `KPOL-AUTH-U12`, `@runtime`-дужки — `KPOL-AUTH-U04`. | Стан `Unknown` підтримується лише в програмному інтерпретаторі поза `CME-RAW-1`. | Стан `Unknown` (`_`) відхиляється компілятором (`B3-SHAPE` / `CME2-SHAPE`); апаратне представлення `W1.state_valid` винесено у відкладений проєкт [`ADR B7` (`CME-RAW-2`)](../../decisions/cme-raw2-kpol-sys02.md). |
| **Інваріанти та реакція на відмову** | **[В]** У похідній підмножині `lowering.py` межі задаються параметрами `Concept(C, Init, Lower=L, Upper=U)` (`KM_FLAG_HW_PROTECTED`), а реакція на відмову шлюзу — підпискою `OnAbort(C) • Assign(...)`. | Перевірка секцій `Invariants` / `Hazards` та сценаріїв `Proof` в `Interpreter`. | Обов'язковий інваріант `S >= 0` у `Problem` (`kpol_txn_gate_v2.sv`) та непорожній pre-emission гейт `Proof` (`B3-PROOF` / `CME2-PROOF`). |

---

## 5. Похідний контракт lowering (`Do/Go` + `CME-RAW-1`), `KPOL-LOWER-CYCLE` і CLI

### 5.1. Підтримувана детермінована підмножина CST (`lowering.py`)

Модуль [`lowering.py`](../../sw/kpol-auth/lowering.py) (**[В]** похідна інженерна реалізація) надає функції `lower_document(document, config)`, `lower_kpol_auth(program)` і `build_bram_routing_image(concepts, subscriptions)`. Вхідний `ProgramCST` повинен мати порожній список `diagnostics` (`len(program.diagnostics) == 0`) і складатися виключно з:

1. **Оголошень концептів:** `Concept(Name, Init[, Lower=L, Upper=U])`
   * кількість концептів $N \in [0, 64]$ (`KM_MAX_CONCEPTS = 64`), унікальні імена, `CID` призначається в порядку оголошення `0 .. N-1`;
   * `Init`, `Lower`, `Upper` — цілі літерали в діапазоні знакового `Int32` (`[-2147483648, 2147483647]`), за умови `Lower <= Upper`; наявність `Lower` або `Upper` вмикає `KM_FLAG_HW_PROTECTED (0x08)` та `CME_GUARD_INVARIANT_EN (0x02)`.
2. **Підписок за `•`:** `<Trigger> • Assign(Dst, Expr)` або `<Trigger> • { Assign(Dst_1, Expr_1), ... }`
   * `<Trigger>` є одним із трьох варіантів над уже оголошеним концептом `Src`:
     * `Src` → фаза `KM_PHASE_POST_CHANGE (1)`, маска `KM_EV_CHANGED (0x40)`;
     * `OnPositive(Src)` → фаза `KM_PHASE_POST_CHANGE (1)`, маска `KM_EV_POSITIVE (0x04)`;
     * `OnAbort(Src)` → фаза `KM_PHASE_ON_ABORT (4)`, маска `KM_EV_ALWAYS (0x80)`;
   * `Expr` — детерміноване дерево з ідентифікаторів оголошених концептів, знакових 16-бітних констант `INT` (`[-32768, 32767]`), одноелементних дужок `(Expr)` та бінарних операторів `+`, `-`, `*`.

### 5.2. Двійковий формат інструкцій `Do/Go` та 1024-байтного образу `CME-RAW-1`

1. **32-бітне слово інструкції `Do/Go` (`km_pack_instr`):**
   $$\text{word} = ((\text{opc} \ \mathrm{bitand} \ \text{0xF}) \ll 28) \mid ((\text{sub-op} \ \mathrm{bitand} \ \text{0xF}) \ll 24) \mid ((\text{flags} \ \mathrm{bitand} \ \text{0xFF}) \ll 16) \mid (\text{operand} \ \mathrm{bitand} \ \text{0xFFFF})$$
   * `KM_OPC_IMM (0x3)`: завантажує знаковий 16-бітний операнд `operand` у стек VM;
   * `KM_OPC_GO (0x1)`: `KM_GO_READ (0x2)` кладе поточне значення концепту `operand` у стек; `KM_GO_WRITE (0x1)` знімає вершину стека й записує її в концепт `operand` через шлюз інваріантів;
   * `KM_OPC_DO (0x2)`: виконує `KM_DO_ADD (0)`, `KM_DO_SUB (1)` або `KM_DO_MUL (2)` над двома верхніми елементами стека;
   * `KM_OPC_EXIT (0x5)`: обов'язковий термінатор кожної лінії підписки; загальна довжина `code_o` обмежена `KM_MAX_INSTRUCTIONS = 512`, кількість підписок — `KM_MAX_SUBSCRIPTIONS = 128`.
2. **1024-байтний образ маршрутизації `CME-RAW-1` (`build_bram_routing_image`):**
   * містить рівно $64$ слоти по $16$ байтів (`struct.pack("<4I", W0, W1, W2, W3)` у little-endian):
     * `W0` = `init_val & 0xFFFFFFFF` (початковий 32-бітний стан концепту);
     * `W1` = `0` (операнд мікроядра CME у цьому маршрутному представленні не задіяний);
     * `W2` = `(guard_flags & 0xFF) << 8`, де біт `0x02` (`CME_GUARD_INVARIANT_EN`) виставляється для `KM_FLAG_HW_PROTECTED`, а біт `0x10` (`CME_GUARD_SUBSCRIBER_EN`) — за наявності ребра `POST_CHANGE`;
     * `W3` = `subscriber_cid` (`0..63`) для єдиного підписника `POST_CHANGE` або `0` для листового слота; невикористані слоти `N..63` заповнюються нулями `(0, 0, 0, 0)`.

### 5.3. Статична ациклічність `_validate_bram_acyclic` та зв'язок із формальною лемою `P2`

Функція `_validate_bram_acyclic(edges)` є виділеним чистим кроком валідації графа каскадів `POST_CHANGE` перед пакуванням слів `W0..W3` у `build_bram_routing_image`:

1. **Відхилення самопетель (`dst_cid == src_cid`):** будь-яка підписка концепту на самого себе (`C0 -> C0`) негайно відхиляється з кодом `KPOL-LOWER-CYCLE`.
2. **Відхилення орієнтованих циклів довільної довжини (`A -> ... -> A`):** 3-кольоровий обхід у глибину (DFS) виявляє всі зворотні ребра графа (зокрема 2-вузлові цикли `A -> B -> A`) і відхиляє їх із `KPOL-LOWER-CYCLE`.
3. **Строга монотонність топологічного рангу (`dst_cid > src_cid`):** кожне ребро `POST_CHANGE` зобов'язане задовольняти `dst_cid > src_cid` (порушення `dst_cid <= src_cid` відхиляється з `KPOL-LOWER-CYCLE`).

**Роль для формальної верифікації RTL (`#227`, `#237`, PR `#248`):** у звіті [`Engineering/validation/kpol-cme/cme2-formal-227/report.md`](../../validation/kpol-cme/cme2-formal-227/report.md) доведено, що апаратний секвенсор `km_autonomous_sequencer.sv` не виконує повного пошуку циклів у таблиці BRAM під час роботи, а спирається на індуктивну лему спадання рангу Ляпунова **`P2` (`P2_rank_step_n16`, $V(\text{cid}) = 15 - \text{cid}$)** за зовнішньої статичної передумови компілятора `cap_dag_ok_w` (`subscriber_cid > active_cid_q` при увімкненому `SUBSCRIBER_EN`, тоді як незмінність слів `W1..W3` у рантаймі захищена індуктивним твердженням `P1f_cfg_words_immutable`). Отже, перевірка `_validate_bram_acyclic` (`KPOL-LOWER-CYCLE`) у `lowering.py` (разом із `CME2-CASCADE` у `KPOL-CME-2`) безпосередньо забезпечує виконання передумови леми `P2` для згенерованих образів `CME-RAW-1`.

Якість тестового захисту `_validate_bram_acyclic` у [`test_kpol_auth_lowering.py`](../../sw/kpol-auth/tests/test_kpol_auth_lowering.py) підтверджено мутантними контролями (`AGENTS.md §4.1`, закриття [#245](https://github.com/nick-fedchik/kuzmin-machine/issues/245)):
* **Мутант `M1` / `M2`:** підміна арифметичного підкоду `KM_DO_ADD → KM_DO_SUB` та видалення термінатора `KM_OPC_EXIT` перехоплюються незалежною еталонною `ReferenceDoGoVM`;
* **Мутант `M3a`:** заміна `_validate_bram_acyclic` на no-op (`lambda *a, **k: None`) пропускає 2-вузловий цикл `A -> B -> A`, який немутований код детерміновано блокує з `KPOL-LOWER-CYCLE`;
* **Мутант `M3b`:** заміна `_validate_bram_acyclic` на дефектний варіант, що перевіряє лише 2-вузлові цикли `u != v` і пропускає самопетлю `dst_cid == src_cid`, пропускає `C0 -> C0`, тоді як немутований код відхиляє самопетлю з `KPOL-LOWER-CYCLE` як у прямому виклику `build_bram_routing_image`, так і через `lower_document`.

### 5.4. Повний реєстр кодів відмов `KPOL-LOWER-*` та контракт CLI (`__main__.py`)

| Код відмови `LoweringError` | Умова спрацьовування |
| :--- | :--- |
| `KPOL-LOWER-UNCERTAINTY` | У `ProgramCST.diagnostics` присутня хоча б одна незакрита діагностика `KPOL-AUTH-U*` |
| `KPOL-LOWER-CONCEPT` | Некоректна сигнатура або невідомий іменований параметр у `Concept(...)` |
| `KPOL-LOWER-DUPLICATE-CONCEPT` | Повторне оголошення концепту з тим самим ім'ям |
| `KPOL-LOWER-LIMIT` | Перевищено ліміт концептів (`64`), підписок (`128`) або інструкцій `code_o` (`512`) |
| `KPOL-LOWER-LITERAL` | Очікувався цілочисельний літерал `INT` в оголошенні концепту або межах |
| `KPOL-LOWER-RANGE` | Літерал концепту поза `Int32`, константа виразу поза `[-32768, 32767]` або `Lower > Upper` |
| `KPOL-LOWER-EXPR` | Дужковий вираз `(...)` в арифметиці не містить рівно одного елемента |
| `KPOL-LOWER-UNKNOWN-CONCEPT` | Звернення до неоголошеного концепту або невалідний `owner_cid`/`target_cid` у таблиці підписок |
| `KPOL-LOWER-UNSUPPORTED-OP` | Бінарний оператор поза підтримуваною трійкою `+`, `-`, `*` |
| `KPOL-LOWER-UNSUPPORTED-CST` | Вузол CST поза детермінованою підмножиною (`DefLayoutCST`, `GroupBoundsCST`, `ParamCST` тощо) |
| `KPOL-LOWER-EMPTY-SUB` | Порожній блок підписки `Src • {}` |
| `KPOL-LOWER-ASSIGN` | Виклик `Assign(...)` не має рівно двох аргументів `(DstConcept, Expr)` |
| `KPOL-LOWER-FANOUT` | Концепт має більше однієї підписки у фазі `KM_PHASE_POST_CHANGE` (`fan-out > 1` у `CME-RAW-1`) |
| `KPOL-LOWER-CYCLE` | Самопетля (`dst_cid == src_cid`), цикл `A -> ... -> A` або порушення рангу `dst_cid <= src_cid` у каскаді BRAM |

**Контракт CLI ([`Engineering/sw/kpol-auth/__main__.py`](../../sw/kpol-auth/__main__.py)):**

```bash
PYTHONPATH=Engineering/sw/kpol-auth python3 -m kpol_auth <input.kpol> \
    [--check] [--emit-bram <out.bram.bin>] [--emit-dogo <out.dogo.json|out.dogo.bin>]
# або прямий запуск пакета:
python3 Engineering/sw/kpol-auth <input.kpol> --check
```

* Виконує повну перевірку фронтенду й lowering у пам'яті **до** створення вихідних файлів: при будь-якій відмові файли `--emit-bram` і `--emit-dogo` не створюються.
* Якщо шлях `--emit-dogo` має розширення `.bin`, емітується упакований потік 32-бітних слів `<I` (`code_o`); інакше емітується детермінований JSON (`format: "kpol-auth-dogo-0.1.0"`, таблиці `concepts`, `subscriptions`, `code_o`, `code_o_hex`).
* Коди виходу процесу: `0` — успіх; `1` — помилка вводу-виводу (`KPOL-CLI-IO`); `2` — помилка фронтенду або точка невизначеності (`KPOL-AUTH-U01..U12`, `KPOL-AUTH-SYNTAX-*`, `KPOL-AUTH-LEX-*`); `3` — відмова lowering (`KPOL-LOWER-*`, зокрема `KPOL-LOWER-CYCLE`).

---

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-16 | Перша редакція специфікації підтримуваного підмножинного фронтенду та похідного lowering `KPOL-AUTH` (`Do/Go` + `CME-RAW-1`), трасування `KPOL-AUTH-01..08` до первинних джерел та `RFC-001–018`, розмежування `•`, контракту `_validate_bram_acyclic` (`KPOL-LOWER-CYCLE` для леми `P2`) і CLI ([#245](https://github.com/nick-fedchik/kuzmin-machine/issues/245), частина [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186) та [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8)). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| CID | Індекс концепту в таблиці слотів BRAM (`0..63`) |
| `CME-RAW-1` | 16-байтний двійковий дескриптор слота концепту ($4 \times 32$-бітні слова `W0..W3`) у конфігурації `CFG-P` |
| CST | Concrete Syntax Tree — дерево конкретного синтаксису зі збереженням токенів, дужок і байтових зміщень |
| DAG | Спрямований ациклічний граф каскадних підписок між концептами |
| `Do/Go` | 32-бітний байткод стекової віртуальної машини виконання ліній підписок (`km_mcu_fpga_bridge.c`) |
| `KPOL-AUTH` | Досліджуваний native-діалект мови KPOL за первинними матеріалами М. Ю. Кузьміна (ізольований від `KPOL-CME-1`/`KPOL-CME-2`) |
| RFC | Request for Comments — задокументований запит на уточнення семантики до Автора концепції |
| WP / NG | Work Product (результат роботи) у поточній структурі репозиторію Next Generation |
