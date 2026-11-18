# Посібник: Каталог практичних посібників користувача (`Engineering/guides/`)

* **Версія:** 1.0.0
* **Дата:** 2026-11-18
* **Тип WP:** Guide
* **Статус:** Чинний навігаційний покажчик інженерних посібників
* **Issue:** `Closes` [#284](https://github.com/nick-fedchik/kuzmin-machine/issues/284); пов'язані задачі [#280](https://github.com/nick-fedchik/kuzmin-machine/issues/280), [#278](https://github.com/nick-fedchik/kuzmin-machine/issues/278), [#276](https://github.com/nick-fedchik/kuzmin-machine/issues/276), [#274](https://github.com/nick-fedchik/kuzmin-machine/issues/274).
* **Відповідальний:** власник Микола Федчик; укладач — GitHub Copilot CLI (Lead Engineer / Documentation Engineer).

---

## Призначення

Цей каталог містить практичні посібники користувача (`Work Product: Guide`) для розробників програмного й апаратного забезпечення, дослідників та верифікаторів проєкту **Машини Кузьміна** (`nick-fedchik/kuzmin-machine`). На відміну від нормативних контрактів у [`Engineering/specifications/`](../specifications/kpol/README.md), документи в `Engineering/guides/` побудовані як покрокові навчально-практичні керівництва з живими прикладами коду, стандартами чистого кодування та інструкціями з налагодження.

---

## Навігація чи використання

### 1. Основні посібники в каталозі `Engineering/guides/`

| Посібник | Версія | Цільова аудиторія та зміст |
| :--- | :---: | :--- |
| **[Керівництво користувача та чистий код мов KPOL і EKPOL (`kpol-ekpol-language-guide.md`)](kpol-ekpol-language-guide.md)** | `1.0.1` | Фундаментальний підручник і стандарт кодування з мов **KPOL** (`KPOL-CME-1/2`, `KPOL-AUTH`) та **EKPOL (`0.1.0`)**, побудований за канонами **Браяна Кернігана і Денніса Рітчі (*K&R*)** та **Роберта Мартіна (*Clean Code*)**:<br>• **Частина I (K&R Tutorial):** від першої програми за 60 секунд («Hello, Concept!») через анатомію концепту, стан невизначеності `_` (`undef`), 4 види адресації, предикати `::`/`when`, дві ролі Великої Крапки (`.` / `commit` / `after`) та інваріанти `[>= 0]` до реактивних циклів (`Nod`, `Factorial`) і 4-рівневого каскаду BMS;<br>• **Частина II (Clean Code by Robert C. Martin):** 7 золотих правил чистого концептно-орієнтованого коду з парними прикладами «❌ Погано» vs «✅ Чисто» та каталогом рефакторингу запахів коду (`SMELL-01..07`);<br>• **Частина III (K&R Reference Manual):** повні таблиці взаємної відповідності конструкцій і 16-байтних дескрипторів BRAM `W0..W3`, кодів предикатів/дій/прапорців, кодів діагностики компілятора (`EKPOL-*`, `CME2-*`) та CLI-шпаргалка. |
| **[Посібник користувача VMK та повноекранного TUI-дебагера (`vmk-users-guide.md`)](vmk-users-guide.md)** | `1.2.1` | Практичний посібник зі збірки та використання виконуваного бінарника **`vmk` (`Virtual Machine of Kuzmin v0.3.0`)** у [`Engineering/sw/vmk-go/`](../sw/vmk-go/README.md):<br>• робота у двох режимах (`--mode bram64` для 64-слотового конвеєра `CME-RAW-1` та `--mode conceptual` для авторської семантики `RFC-001..018`);<br>• трифазна інспекція підключення `PRE-LOAD -> POST-LOAD -> RUNNING` із послотним `Diff`;<br>• повноекранний інтерактивний TUI-дебагер (`--tui`: навігація `↑/↓`, картка `Concept Inspector`, ручний конструктор подій `[e]`, мікро-хоп хвилі `[n/Space]`, редактор стану `[m]`);<br>• потоковий режим UNIX `STDIO` (`--stdio`) та робота з фізичною платою ПЛІС **`Digilent PYNQ-Z1`** (`--target pynq1 \| pynq2`). |

### 2. Пов'язані інженерні посібники та нормативні входи в інших каталогах

| Категорія | Документ | Призначення |
| :--- | :--- | :--- |
| **Нормативні специфікації мов** | [`Engineering/specifications/kpol/README.md`](../specifications/kpol/README.md) | Вхід до специфікацій [`ekpol-specification.md`](../specifications/kpol/ekpol-specification.md), [`kpol-cme-subset.md`](../specifications/kpol/kpol-cme-subset.md), [`kpol-cme2-profile.md`](../specifications/kpol/kpol-cme2-profile.md), [`kpol-auth-subset.md`](../specifications/kpol/kpol-auth-subset.md) та [`kpol-consolidated.md`](../specifications/kpol/kpol-consolidated.md). |
| **Специфікація емулятора VMK** | [`Engineering/specifications/sw/vmk-go-emulator-and-tui-debugger.md`](../specifications/sw/vmk-go-emulator-and-tui-debugger.md) | Архітектурна та програмна специфікація двомодового емулятора `VMK v0.3.0` і TUI-дебагера на Go. |
| **Апаратний стенд PYNQ-Z1** | [`Engineering/hw/boards/pynq-z1/README.md`](../hw/boards/pynq-z1/README.md), [`hil-bench-wiring-guide.md`](../hw/boards/pynq-z1/hil-bench-wiring-guide.md) | Профіль плати `Digilent PYNQ-Z1` (`Zynq-7020`) та посібник із фізичної комутації HIL-стенда (`PMOD JA/JB`, `RP2040 LogicTracer`, `Jetson AGX Orin`). |
| **Процесні посібники проєкту** | [`Project/guides/project-manual.md`](../../Project/guides/project-manual.md), [`AGENTS.md`](../../AGENTS.md) | Правила організації робіт, ролей, гілок, рецензування та верифікації без бутафорії. |

### 3. Рекомендований маршрут читання для нового інженера

1. Почніть із **[Частини I `kpol-ekpol-language-guide.md`](kpol-ekpol-language-guide.md#частина-i-вступний-курс-за-методом-кернігана-і-рітчі-a-tutorial-introduction)** і запустіть першу програму `examples/increase.ekpol` за 60 секунд.
2. Опануйте **[Частину II `kpol-ekpol-language-guide.md`](kpol-ekpol-language-guide.md#частина-ii-дисципліна-чистого-коду-в-kpol-та-ekpol-за-принципами-роберта-мартіна-clean-concept-oriented-code)** (7 правил чистого коду Мартіна та таблицю антипатернів `SMELL-01..07`).
3. Відкрийте **[`vmk-users-guide.md`](vmk-users-guide.md)** і пройдіть покрокове трасування хвилі подій у повноекранному TUI-дебагері (`vmk --program examples/bms_safety_cascade.ekpol --tui`).
4. Використовуйте **[Частину III `kpol-ekpol-language-guide.md`](kpol-ekpol-language-guide.md#частина-iii-довідник-мов-kpol-та-ekpol-kr-appendix-a--reference-manual)** та **[`ekpol-specification.md`](../specifications/kpol/ekpol-specification.md)** як довідник під час розробки й формальної верифікації власних модулів.

---

## Обмеження

1. Посібники в `Engineering/guides/` не замінюють нормативних специфікацій у [`Engineering/specifications/`](../specifications/kpol/README.md) та вимог у [`Engineering/requirements/`](../requirements/requirements.md); у разі розбіжностей пріоритет мають нормативні контракти та формальні докази `Z3` / `SymbiYosys`.
2. Атрибуція авторства концепції Машини Кузьміна (**М. Ю. Кузьмін**, первинні матеріали у [`Research/sources/`](../../Research/sources/README.md)) суворо відділена від похідних інженерних розробок проєкту (`EKPOL 0.1.0`, `VMK v0.3.0`, профілі `KPOL-CME-1/2`, генератор C99) згідно з `AGENTS.md §6.1`.

---

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 1.0.0 | 2026-11-18 | Перший випуск індексного посібника каталогу `Engineering/guides/README.md` з оглядом `kpol-ekpol-language-guide.md` (`1.0.1`), `vmk-users-guide.md` (`1.2.1`) та рекомендованим маршрутом навчання (Issue [#284](https://github.com/nick-fedchik/kuzmin-machine/issues/284)). |

---

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| **KPOL / EKPOL** | Класична (`KPOL`) та ергономічна двостильова ASCII/програмістська (`EKPOL 0.1.0`) концептно-орієнтовані мови програмування Машини Кузьміна. |
| **VMK** | Virtual Machine of Kuzmin (`v0.3.0`) — двомодовий емулятор, транспайлер і повноекранний TUI-дебагер МК (`Engineering/sw/vmk-go/`). |
| **TUI** | Text-based User Interface — інтерактивний термінальний інтерфейс покрокового налагодження каскадів подій. |
| **HIL** | Hardware-in-the-Loop — верифікація за участю фізичної плати ПЛІС `Digilent PYNQ-Z1`. |
| **WP** | Work Product — робочий продукт інженерного процесу за структурою проєкту. |
