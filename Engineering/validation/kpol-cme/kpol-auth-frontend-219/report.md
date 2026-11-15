# Звіт #219: Прототип фронтенду native-діалекту `KPOL-AUTH` (лексер/CST, точки невизначеності та корпус прикладів)

* **Версія:** 0.1.0
* **Дата:** 2026-11-15
* **Тип WP:** Report / Analysis
* **Issue:** [#219](https://github.com/nick-fedchik/kuzmin-machine/issues/219) (частина #186/#8; не закриває #186). **PR:** гілка `feat/219-kpol-auth-frontend`.
* **Виконавець:** GitHub Copilot CLI (`gemini-4-hydrogen`). **Рецензент:** незалежна рецензія не проведена.
* **Коміт, на якому виконано:** `56c9abd50f70dcb8318f66bfa26e7e73f4597e5b`. **Хост / плата:** Linux (`AORUS-5-SE`); фізична плата FPGA не залучалася. **Бітстрім (SHA-256):** не генерувався.
* **Критерії успіху (зафіксовано до виконання):** критерії приймання в описі [#219](https://github.com/nick-fedchik/kuzmin-machine/issues/219).

---

## 1. Що не вдалося і обмеження

* Усі перевірки виконано в хостовому інтерпретаторі Python 3 (`unittest`/`pytest`); генератор байт-коду або образу BRAM, семантичний обчислювач, RTL-симуляція та HIL на FPGA не реалізовувалися й не запускалися.
* Прототип фронтенду не розв'язує 12 відкритих питань (`RFC-009` п. 2–3, `RFC-015`, `RFC-016`, `RFC-017` п. 2–3, `RFC-018`) і не приписує Автору жодного правила понад дослівні відповіді. Усі 12 точок невизначеності (`KPOL-AUTH-U01`..`KPOL-AUTH-U12`) за замовчуванням працюють у режимі `fail-closed`.
* Первинні прогони тестів [`raw/kpol-auth-tests-01.log`](raw/kpol-auth-tests-01.log) та [`raw/kpol-auth-tests-02.log`](raw/kpol-auth-tests-02.log) виявили два дефекти: відносний імпорт у `kpol-auth/__init__.py` без `__package__` під час збирання `pytest` та неповну перевірку `SubscriptionSeqCST` у дужках (`Flag := (A • B)`) і токена `HASH_LEGACY` у режимі `record-diagnostic`. Обидва дефекти виправлено, а повторний прогін записано в новий файл [`raw/kpol-auth-tests-03.log`](raw/kpol-auth-tests-03.log).
* Чинний компілятор `kpol_reference.py`, профілі `KPOL-CME-1`/`KPOL-CME-2` та файли в `Engineering/hw/` не змінювалися.

## 2. Метод

1. **Окремий пакет [`Engineering/sw/kpol-auth/`](../../../sw/kpol-auth/__init__.py):**
   * [`uncertainty.py`](../../../sw/kpol-auth/uncertainty.py): єдиний реєстр `UNCERTAINTY_REGISTRY` (`KPOL-AUTH-U01`..`KPOL-AUTH-U12`) та єдине конфігураційне місце `AuthFrontendConfig` із політикою `fail-closed` за замовчуванням для кожної точки.
   * [`lexer.py`](../../../sw/kpol-auth/lexer.py): лексер парних дужок (`{}`, `()`, `[]`), текстових роздільників (`"..."`, `«...»`), операторів native-діалекту (`•` як `SUBSCRIPTION_SEQ`, `:=`, `:`, `@`, `_`, `!`, `¬`, `,`, арифметичні та порівняльні оператори). Символ `#` відхиляється як `KPOL-AUTH-U05`, екранування `\` всередині тексту — як `KPOL-AUTH-U06`.
   * [`cst.py`](../../../sw/kpol-auth/cst.py): побудова CST (`ProgramCST`, `BracketGroupCST`, `GroupBoundsCST`, `DefLayoutCST`, `SubscriptionSeqCST`, `CallOrConstructCST`, `AssignmentCST`, `BinaryExprCST`, `ParamCST`, `IdentifierCST`, `LiteralCST`, `UninitCST`). Реалізовано підтверджені правила Автора: `Min=1, Max=15` (`max_effective = Max + 1 = 16`), `Min=1, Max=0` (`max_effective = 1`), порядок бітів `Def` зліва молодший (`lsb_left_msb_right`), `OpenBracket`/`CloseBracket` як структурні заглушки, `A • B` як подія/послідовність підписки (з відхиленням унарного `• Flag` кодом `KPOL-AUTH-SYNTAX-03`).
   * [`corpus.py`](../../../sw/kpol-auth/corpus.py): корпус із 18 прикладів (`EX-01`..`EX-18`) із посиланнями на [первинні картки джерел](../../../../Research/sources/README.md) та `drafts@84812f6`, де випадки без відповіді Автора явно позначено як «поза межами джерела».
2. **Тестування та перевірки репозиторію:**
   * [`test_kpol_auth_frontend.py`](../../../sw/kpol-auth/tests/test_kpol_auth_frontend.py): перевірка всіх 18 прикладів корпусу, дефолтної політики `fail-closed` для всіх 12 точок, перемикання в єдиному конфігураційному місці та негативні тести для кожного правила й кожної точки невизначеності.
   * Повний прогін `python3 -m pytest -q`, `check_links.py`, `check_wp_documents.py`, `git diff --check` та перевірка нульового diff у `Engineering/hw` і `Engineering/sw/kpol-ref`.

## 3. Результати

* **Цільові тести `kpol-auth` ([`raw/kpol-auth-tests-03.log`](raw/kpol-auth-tests-03.log)):** `10 passed, 25 subtests passed in 0.08s`, `exit_code=0`.
* **Наскрізна перевірка репозиторію ([`raw/full-verification-01.log`](raw/full-verification-01.log)):** `python3 -m pytest -q` (`360 passed, 370 subtests passed`), `check_links.py`, `check_wp_documents.py`, `git diff --check` та перевірка відсутності змін у `Engineering/hw` і `Engineering/sw/kpol-ref` завершилися з `exit_code=0`.

### 3.1. Реєстр точок невизначеності (`fail-closed` за замовчуванням)

| Код | RFC | Предмет | Статус у джерелі |
| :--- | :--- | :--- | :--- |
| `KPOL-AUTH-U01` | RFC-009 п. 2 | Зв'язок `И` (Collection) / `ИЛИ` (Array) з `Min`/`Max` | Тимчасова репліка про запуски та `И`/`ИЛИ` без правила зв'язку з `Min`/`Max` |
| `KPOL-AUTH-U02` | RFC-009 п. 3 | Не-`Token` індекси та вихід за межі `Min`/`Max` | Поза межами джерела |
| `KPOL-AUTH-U03` | RFC-015 | Написання `CloseBracket` проти `CloseBracked` | Конфлікт слайда 5 і повідомлення Автора |
| `KPOL-AUTH-U04` | RFC-015 | Момент виконання `OpenBracket`/`CloseBracket` | Позначено Автором як заглушки («не придумал») |
| `KPOL-AUTH-U05` | RFC-016 п. 1 | Нова пара роздільників замість `#` та роль `#` | Поза межами джерела |
| `KPOL-AUTH-U06` | RFC-016 п. 2 | Запис закривального знака всередині `Text`/`Help` | Поза межами джерела |
| `KPOL-AUTH-U07` | RFC-016 п. 3 | Одиниця довжини `Name` (макс. 16) та `First`/`Length` | Поза межами джерела |
| `KPOL-AUTH-U08` | RFC-017 п. 2 | Булеве значення `•` (`true`/`false`) | Поза межами джерела |
| `KPOL-AUTH-U09` | RFC-017 п. 1 | Стан `busy` між читанням і записом в `A • B` | Не визначено в дослівних відповідях |
| `KPOL-AUTH-U10` | RFC-017 п. 3 | Читання `_` у виразах (`C := A + B`) | Поза межами джерела |
| `KPOL-AUTH-U11` | RFC-018 | Елемент `Child` та кількість бітів `Def` (7 vs 8) | Автор назвав `Child` «лишним» («При разработке уточним») |
| `KPOL-AUTH-U12` | RFC-018 / RFC-010 п. 3 | Розмежування `Def[i]=0` та присутності зі станом `_` | Поза межами джерела |

### 3.2. Перелік прикладів, які варто показати Автору

Нижче наведено приклади з [`corpus.py`](../../../sw/kpol-auth/corpus.py) (`show_to_author=True`), які ілюструють як уже зафіксовані правила, так і відкриті точки для уточнення (без надсилання нових RFC напряму — перелік передається власнику):

| ID | Приклад | Що перевіряє / яке питання ілюструє | Джерело |
| :--- | :--- | :--- | :--- |
| `EX-01` | `Collection(Letter)[Min=1, Max=15]` | Підтверджене правило `1..16` («На 1 больше») | [RFC-009](https://github.com/nick-fedchik/drafts/blob/84812f6/KuzminMachine/RFC/details/RFC-009-group-execution-bounds.md) |
| `EX-03` | `Def(1, 0, 1, 0, 0, 0, 0)` | Порядок бітів `Def` («слева младший-справа старший», 7 бітів без `Child`) | [RFC-018](https://github.com/nick-fedchik/drafts/blob/84812f6/KuzminMachine/RFC/details/RFC-018-def-bitmask-order-and-empty-vs-uninit.md) |
| `EX-04` | `Static(OpenBracket, ItemA, CloseBracket)` | `OpenBracket`/`CloseBracket` як структурні заглушки | [RFC-015](https://github.com/nick-fedchik/drafts/blob/84812f6/KuzminMachine/RFC/details/RFC-015-executable-brackets-in-static.md) |
| `EX-05` | `(A, B) • Do(A, B)` | Крок Евкліда: підписка після читання (`A • B`) | [RFC-017](https://github.com/nick-fedchik/drafts/blob/84812f6/KuzminMachine/RFC/details/RFC-017-busy-release-and-uninitialized-ops.md) |
| `EX-07` | `Collection(A, B, C)[Min=1, Max=2, Logic=AND]` | `U01`: як `И`/`ИЛИ` взаємодіють із `Min`/`Max` | [RFC-009](https://github.com/nick-fedchik/drafts/blob/84812f6/KuzminMachine/RFC/details/RFC-009-group-execution-bounds.md) |
| `EX-08` | `Array(A, B)[Min=Byte(1), Max=2]` | `U02`: не-`Token` індекси та вихід за межі | [RFC-009](https://github.com/nick-fedchik/drafts/blob/84812f6/KuzminMachine/RFC/details/RFC-009-group-execution-bounds.md) |
| `EX-09` | `Static(OpenBracket, A, CloseBracked)` | `U03`: канонічне написання `CloseBracket` vs `CloseBracked` | [RFC-015](https://github.com/nick-fedchik/drafts/blob/84812f6/KuzminMachine/RFC/details/RFC-015-executable-brackets-in-static.md) |
| `EX-11` | `#legacy_comment` | `U05`: яка нова пара знаків замінює `#` | [RFC-016](https://github.com/nick-fedchik/drafts/blob/84812f6/KuzminMachine/RFC/details/RFC-016-updated-delimiters-after-hash.md) |
| `EX-12` | `"text \" quote"` | `U06`: як записати закривальний знак усередині тексту | [RFC-016](https://github.com/nick-fedchik/drafts/blob/84812f6/KuzminMachine/RFC/details/RFC-016-updated-delimiters-after-hash.md) |
| `EX-13` | `Name("ПривітСвітДовгеІм")` | `U07`: одиниця вимірювання межі 16 для `Name` | [RFC-016](https://github.com/nick-fedchik/drafts/blob/84812f6/KuzminMachine/RFC/details/RFC-016-updated-delimiters-after-hash.md) |
| `EX-14` | `Flag := (A • B)` | `U08`: зміст булевого значення `•` | [RFC-017](https://github.com/nick-fedchik/drafts/blob/84812f6/KuzminMachine/RFC/details/RFC-017-busy-release-and-uninitialized-ops.md) |
| `EX-15` | `A • busy(A)` | `U09`: статус `busy` між читанням і записом | [RFC-017](https://github.com/nick-fedchik/drafts/blob/84812f6/KuzminMachine/RFC/details/RFC-017-busy-release-and-uninitialized-ops.md) |
| `EX-16` | `C := _ + B` | `U10`: читання стану `_` у виразі | [RFC-017](https://github.com/nick-fedchik/drafts/blob/84812f6/KuzminMachine/RFC/details/RFC-017-busy-release-and-uninitialized-ops.md) |
| `EX-17` | `Def(1, 0, 0, 0, 0, 0, 0, 1)` | `U11`: роль `Child` і кількість бітів `Def` | [RFC-018](https://github.com/nick-fedchik/drafts/blob/84812f6/KuzminMachine/RFC/details/RFC-018-def-bitmask-order-and-empty-vs-uninit.md) |
| `EX-18` | `Property(DefBit=1, Value=_)` | `U12`: різниця між `Def[i]=0` і станом `_` | [RFC-018](https://github.com/nick-fedchik/drafts/blob/84812f6/KuzminMachine/RFC/details/RFC-018-def-bitmask-order-and-empty-vs-uninit.md) |

## 4. Перевірка критеріїв

| Критерій (`#219`) | Очікувано | Отримано | Висновок |
| :--- | :--- | :--- | :--- |
| Прототип лексера й CST для `KPOL-AUTH` без зміни `kpol_reference.py` і `KPOL-CME-1/2` | Окремий пакет у `Engineering/sw/kpol-auth/`, `•` як послідовність підписки, НЕ `not` | Створено `lexer.py`, `cst.py`, `uncertainty.py`, `corpus.py`, `__init__.py`; `kpol_reference.py` і `Engineering/hw/` не змінено | Виконано |
| Реєстр точок невизначеності з одним конфігураційним місцем і `fail-closed` за замовчуванням | Усі відкриті питання `RFC-009, 015–018` мають явні коди і `fail-closed` | Зареєстровано `KPOL-AUTH-U01`..`KPOL-AUTH-U12` в `AuthFrontendConfig` | Виконано |
| Корпус прикладів із посиланнями на джерела Автора та позначкою «поза межами джерела» | 18 прикладів із джерелами і чіткими межами | `AUTHOR_CORPUS` (`EX-01`..`EX-18`) протестовано проти CST і діагностик | Виконано |
| Тести з негативними контролями для кожного правила й точки | Усі тести та регресія репозиторію зелені | `10 passed, 25 subtests passed` (`kpol-auth`), `360 passed, 370 subtests passed` (повний `pytest`), `check_links`, `check_wp_documents`, `git diff --check` — `exit_code=0` | Виконано |

## 5. Відтворення

```bash
python3 -m pytest Engineering/sw/kpol-auth/tests/test_kpol_auth_frontend.py -v
python3 -m pytest -q
KM_DRAFTS_REPO=/home/mfedchyk/GitHub/nick-fedchik/drafts python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
git diff --check
```

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-15 | Перша редакція звіту прототипу фронтенду `KPOL-AUTH` ([#219](https://github.com/nick-fedchik/kuzmin-machine/issues/219)). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| CST | Concrete Syntax Tree, конкретне синтаксичне дерево зі збереженням дужок і роздільників |
| `fail-closed` | Режим відхилення неоднозначної або невизначеної конструкції явною діагностикою замість припущення |
| WP | Work Product, результат роботи з визначеним призначенням |
