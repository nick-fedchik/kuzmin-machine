# Звіт #219: Прототип фронтенду native-діалекту `KPOL-AUTH` (лексер/CST, точки невизначеності та корпус прикладів)

* **Версія:** 0.2.0
* **Дата:** 2026-11-16
* **Тип WP:** Report / Analysis
* **Issue:** [#219](https://github.com/nick-fedchik/kuzmin-machine/issues/219), [#224](https://github.com/nick-fedchik/kuzmin-machine/issues/224), [#233](https://github.com/nick-fedchik/kuzmin-machine/issues/233), [#243](https://github.com/nick-fedchik/kuzmin-machine/issues/243) (частина #8/#186; не закриває #8 або #186). **PR:** `feat/219-kpol-auth-frontend` (`0.1.0`), `fix/224-kpol-auth-review-fixes` (`0.1.1`), `feat/243-kpol-auth-utf8-dogo-lowering` (`0.2.0`).
* **Виконавець:** GitHub Copilot CLI (`gemini-4-hydrogen`). **Рецензент:** `claude-sonnet-5.5` (рецензії PR #222 для `0.1.0` та PR #231 для `0.1.1`); незалежна рецензія для `0.2.0` не проведена.
* **Коміт, на якому виконано:** `deb9434e09c681fe96f6d23446f105e026a1f8fe`. **Хост / плата:** Linux (`AORUS-5-SE`); фізична плата FPGA не залучалася (`KM_SKIP_LIVE_HIL=1`). **Бітстрім (SHA-256):** не генерувався.
* **Критерії успіху (зафіксовано до виконання):** критерії приймання в описах [#219](https://github.com/nick-fedchik/kuzmin-machine/issues/219), [#233](https://github.com/nick-fedchik/kuzmin-machine/issues/233) та [#243](https://github.com/nick-fedchik/kuzmin-machine/issues/243).

---

## 1. Що не вдалося і обмеження

* Усі перевірки виконано в хостовому інтерпретаторі Python 3 (`unittest`/`pytest`) та незалежному еталонному стековому інтерпретаторі `ReferenceDoGoVM`; компіляція C99-рантайму на фізичній платі PYNQ-Z1, RTL-симуляція та HIL на FPGA не запускалися (`KM_SKIP_LIVE_HIL=1`).
* Модуль [`lowering.py`](../../../sw/kpol-auth/lowering.py) є **похідною інженерною трансляцією** (`AGENTS.md §6.1`) детермінованої підмножини `KPOL-AUTH` у 32-бітний байткод `Do/Go` ([`km_mcu_fpga_bridge.c`](../../../sw/runtime/mcu/km_mcu_fpga_bridge.c)) та 1024-байтний образ BRAM `CME-RAW-1` ([`kpol-cme2-profile-0.1.0.md`](../../../specifications/kpol/kpol-cme2-profile-0.1.0.md)); це НЕ специфікація Автора (М. Ю. Кузьміна).
* Прототип фронтенду не розв'язує 12 відкритих питань (`RFC-009` п. 2–3, `RFC-015`, `RFC-016`, `RFC-017` п. 2–3, `RFC-018`) і не приписує Автору жодного правила понад дослівні відповіді. Усі 12 точок невизначеності (`KPOL-AUTH-U01`..`KPOL-AUTH-U12`) за замовчуванням працюють у режимі `fail-closed`.
* Первинні прогони тестів [`raw/kpol-auth-tests-01.log`](raw/kpol-auth-tests-01.log) та [`raw/kpol-auth-tests-02.log`](raw/kpol-auth-tests-02.log) виявили два дефекти: відносний імпорт у `kpol-auth/__init__.py` без `__package__` під час збирання `pytest` та неповну перевірку `SubscriptionSeqCST` у дужках (`Flag := (A • B)`) і токена `HASH_LEGACY` у режимі `record-diagnostic`. Обидва дефекти виправлено, а повторний прогін записано в новий файл [`raw/kpol-auth-tests-03.log`](raw/kpol-auth-tests-03.log).
* Історичні сирі логи [`raw/kpol-auth-tests-01.log`](raw/kpol-auth-tests-01.log)..[`raw/kpol-auth-tests-03.log`](raw/kpol-auth-tests-03.log) містять хвостові пробіли з виводу `pytest`, через які `git diff --check` на них повертав `rc=2`, а [`raw/full-verification-01.log`](raw/full-verification-01.log) мав порожній розділ `=== git diff --check ===` без зафіксованого `exit_code`. Згідно з `AGENTS.md §4.5` ці історичні файли збережено незмінними; для редакцій `0.1.1` і `0.2.0` записано нові чисті логи [`raw/revision-0.1.1-kpol-auth-tests.log`](raw/revision-0.1.1-kpol-auth-tests.log), [`raw/revision-0.1.1-full-verification.log`](raw/revision-0.1.1-full-verification.log), [`raw/revision-0.2.0-kpol-auth-tests.log`](raw/revision-0.2.0-kpol-auth-tests.log) та [`raw/revision-0.2.0-full-verification.log`](raw/revision-0.2.0-full-verification.log) (рядки очищено через `sed 's/[[:space:]]*$//'` із задокументованою командою на рядку 1).
* Чинний компілятор `kpol_reference.py`, `Engineering/sw/runtime/mcu/km_mcu_fpga_bridge.c`, `Project/registers/open-work-items.md` та файли в `Engineering/hw/` не змінювалися.

## 2. Метод

1. **Окремий пакет [`Engineering/sw/kpol-auth/`](../../../sw/kpol-auth/__init__.py):**
   * [`uncertainty.py`](../../../sw/kpol-auth/uncertainty.py): єдиний реєстр `UNCERTAINTY_REGISTRY` (`KPOL-AUTH-U01`..`KPOL-AUTH-U12`) та єдине конфігураційне місце `AuthFrontendConfig` із політикою `fail-closed` за замовчуванням для кожної точки та явно конфігурованою одиницею вимірювання довжини `Name` для `U07` (`name_length_unit`: `fail-closed` за замовчуванням — відхиляє рядок при перевищенні 16 у `codepoints` або `utf8_bytes`, включно з неоднозначними багатобайтовими рядками > 16 байтів UTF-8; або явні `codepoints` / `utf8_bytes`).
   * [`lexer.py`](../../../sw/kpol-auth/lexer.py): лексер парних дужок (`{}`, `()`, `[]`), текстових роздільників (`"..."`, `«...»`), операторів native-діалекту (`•` як `SUBSCRIPTION_SEQ`, `:=`, `:`, `@`, `_`, `!`, `¬`, `,`, арифметичні та порівняльні оператори). Символ `#` відхиляється як `KPOL-AUTH-U05`, екранування `\` всередині тексту — як `KPOL-AUTH-U06`.
   * [`cst.py`](../../../sw/kpol-auth/cst.py): побудова CST (`ProgramCST`, `BracketGroupCST`, `GroupBoundsCST`, `DefLayoutCST`, `SubscriptionSeqCST`, `CallOrConstructCST`, `AssignmentCST`, `BinaryExprCST`, `ParamCST`, `IdentifierCST`, `LiteralCST`, `UninitCST`). Реалізовано підтверджені правила Автора: `Min=1, Max=15` (`max_effective = Max + 1 = 16`), `Min=1, Max=0` (`max_effective = 1`), порядок бітів `Def` зліва молодший (`lsb_left_msb_right`), `OpenBracket`/`CloseBracket` як структурні заглушки, `A • B` як подія/послідовність підписки (з відхиленням унарного `• Flag` кодом `KPOL-AUTH-SYNTAX-03`). Ширина `Def(...)`, відмінна від `7` і `8` бітів, явно відхиляється з діагностикою `KPOL-AUTH-SYNTAX-04` (8-бітний `Def` із `Child` підпадає під `KPOL-AUTH-U11`).
   * [`corpus.py`](../../../sw/kpol-auth/corpus.py): корпус із 18 прикладів (`EX-01`..`EX-18`) із посиланнями на [первинні картки джерел](../../../../Research/sources/README.md), `drafts@84812f6` та явним прапорцем `in_source_scope` (`True` для `EX-01`..`EX-06`, `False` для `EX-07`..`EX-18`, де випадки без відповіді Автора позначено як «поза межами джерела»).
2. **Тестування та перевірки репозиторію:**
   * [`test_kpol_auth_frontend.py`](../../../sw/kpol-auth/tests/test_kpol_auth_frontend.py): перевірка всіх 18 прикладів корпусу (з перевіркою конкретних ID, непорожніх посилань і прапорця `in_source_scope`), дефолтної політики `fail-closed` і перемикання на `record-diagnostic` для всіх 12 точок `U01`..`U12`, 3 мутантних контролі (`•` як `not`, пропуск парності дужок, мовчазне ігнорування точки невизначеності), тест на кириличний рядок `Name` із 9 символів (18 байтів UTF-8), відхилення не-7/8-бітного `Def(...)` та негативні тести для кожного правила.
   * Повний прогін `python3 -m pytest -q`, `check_links.py`, `check_wp_documents.py`, `git diff --check origin/main..HEAD` та перевірка нульового diff у `Engineering/hw`, `Engineering/sw/kpol-ref` і `Project/registers/open-work-items.md`.

## 3. Результати

* **Цільові тести `kpol-auth` (редакція `0.2.0`, [`raw/revision-0.2.0-kpol-auth-tests.log`](raw/revision-0.2.0-kpol-auth-tests.log)):** `17 passed, 40 subtests passed in 0.09s`, `exit_code=0`.
* **Наскрізна перевірка репозиторію (редакція `0.2.0`, [`raw/revision-0.2.0-full-verification.log`](raw/revision-0.2.0-full-verification.log)):** `KM_SKIP_LIVE_HIL=1 python3 -m pytest -q` (`384 passed, 1 skipped, 385 subtests passed`), `check_links.py` (0 битих, 41 drafts-посилання перевірено), `check_wp_documents.py` (`153` документи, `errors: []`), `git diff --check origin/main..HEAD` (`exit_code=0`).
* **Редакція `0.1.1`:** [`raw/revision-0.1.1-kpol-auth-tests.log`](raw/revision-0.1.1-kpol-auth-tests.log) (`12 passed, 40 subtests passed`), [`raw/revision-0.1.1-full-verification.log`](raw/revision-0.1.1-full-verification.log) (`362 passed, 385 subtests passed`).
* **Історичні логи редакції `0.1.0`:** [`raw/kpol-auth-tests-03.log`](raw/kpol-auth-tests-03.log) (`10 passed, 25 subtests passed`) і [`raw/full-verification-01.log`](raw/full-verification-01.log) (`360 passed, 370 subtests passed`, але `git diff --check` на `raw/*-01..03.log` давав `rc=2` через хвостові пробіли `pytest`).

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
| Тести з негативними контролями та мутантами (`#224`) | Усі тести, мутантні контролі та регресія репозиторію зелені | `12 passed, 40 subtests passed` (`kpol-auth`), `362 passed, 385 subtests passed` (повний `pytest`), `check_links`, `check_wp_documents`, `git diff --check origin/main..HEAD` — `exit_code=0` | Виконано |

## 5. Відтворення

```bash
python3 -m pytest Engineering/sw/kpol-auth/tests/test_kpol_auth_frontend.py -v
python3 -m pytest -q
KM_DRAFTS_REPO=/home/mfedchyk/GitHub/nick-fedchik/drafts python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
git diff --check origin/main..HEAD
```

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.2.0 | 2026-11-16 | Закрито знахідки #233 (`G-1` логічний мутант парності дужок, `G-2` оновлено поле «Рецензент» із PR #222/#231, `G-3` чисті одиниці `utf8_bytes`/`codepoints` і граничні тести 16/17/18 байтів) та виконано #243: точні UTF-8 зміщення `Span` (`byte_offset`, `byte_end`, `end_line`, `end_column`), похідний модуль кодогенерації `lowering.py` у `Do/Go` байткод і 1024-байтний `CME-RAW-1` BRAM із верифікацією на `ReferenceDoGoVM` та мутантними контролями. |
| 0.1.1 | 2026-11-15 | Виправлення за рецензією PR #222 ([#224](https://github.com/nick-fedchik/kuzmin-machine/issues/224), `F-1..F-4`): уточнено примітку про історичні `raw/*-01..03.log` і додано чисті логи `revision-0.1.1-*.log`; замінено тавтологію в тесті корпусу через `in_source_scope`; додано `record-diagnostic` для всіх 12 точок `U01..U12` і 3 мутантні контролі; явне відхилення `Def` ширини != 7/8 (`KPOL-AUTH-SYNTAX-04`) та конфігурована одиниця довжини `Name` (`U07`). |
| 0.1.0 | 2026-11-15 | Перша редакція звіту прототипу фронтенду `KPOL-AUTH` ([#219](https://github.com/nick-fedchik/kuzmin-machine/issues/219)). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| CST | Concrete Syntax Tree, конкретне синтаксичне дерево зі збереженням дужок і роздільників |
| `fail-closed` | Режим відхилення неоднозначної або невизначеної конструкції явною діагностикою замість припущення |
| WP | Work Product, результат роботи з визначеним призначенням |
