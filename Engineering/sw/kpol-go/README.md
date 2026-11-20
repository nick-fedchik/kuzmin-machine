# Модуль `Engineering/sw/kpol-go`: компілятори й трансляція KPOL, EKPOL та KPOL-AUTH на Go

* **Версія:** 1.0.0
* **Дата:** 2026-11-20
* **Тип WP:** Guide
* **Відповідальний:** власник Микола Федчик; укладач — GitHub Copilot CLI.

## Призначення

Модуль містить інструментарій мов проєкту **на Go**: фронтенд і виконання KPOL, EKPOL та авторської нотації KPOL-AUTH, компілятори в образ `CME-RAW-1`, двосторонню трансляцію EKPOL ↔ KPOL, генератор C99 із сертифікатом безпеки Z3 та командний інтерфейс `kpolc`. Нормативні визначення мов — у [специфікаціях](../../specifications/kpol/README.md); посібники для програмістів — у [каталозі `Engineering/guides/`](../../guides/README.md).

Python-реалізація в [`Engineering/sw/kpol-ref/`](../kpol-ref/kpol_reference.py) і [`Engineering/sw/kpol-auth/`](../kpol-auth/__init__.py) залишається **еталоном** для диференційних перевірок: тести порівнюють Go-реалізацію з нею за результатами, кодами діагностик і байтами образів. Налагоджувач і емулятор — окремий модуль [`vmk-go`](../vmk-go/README.md).

Модуль не має зовнішніх залежностей (`go 1.22`, лише стандартна бібліотека). Для сертифіката безпеки потрібен виконуваний файл `z3`; без нього генерація C99 завершується помилкою, а не мовчки пропускає перевірку.

## Навігація чи використання

### Пакети

| Пакет | Зміст | Нормативне джерело |
| :--- | :--- | :--- |
| [`kpol/`](kpol/doc.go) | Лексер, парсер, статична семантика, інтерпретатор, перевірка `Proof`, профілі `KPOL-CME-1/2` → образ `CME-RAW-1`, перевірка ACL. | [KPOL](../../specifications/kpol/kpol-formal-specification.md) |
| [`ekpol/`](ekpol/types.go) | Обидві нотації EKPOL (символьна й ключова), профіль `EKPOL-B64`, вбудовані тести, трансляції `EKPOL ↔ KPOL`. | [EKPOL](../../specifications/kpol/ekpol-formal-specification.md) |
| [`kpolauth/`](kpolauth/lexer.go) | Лексер і CST лінійної нотації KPOL-AUTH, гейти `KPOL-AUTH-U01..U12`, зниження `KPOL-AUTH-L1` у команди `Do/Go` та образ маршрутизації, еталонна машина `Do/Go`. | [KPOL-AUTH](../../specifications/kpol/kpol-auth-formal-specification.md) |
| [`c99/`](c99/c99.go) | Детермінований генератор C99-автомата безпеки за таблицею дескрипторів, сертифікат Z3, еталонна модель рушія. | [Report #270](../../validation/kpol-cme/c99-emitter-270/report.md) |
| [`cmd/kpolc/`](cmd/kpolc/main.go) | Командний інтерфейс. | — |

### Команда `kpolc`

```bash
go build -C Engineering/sw/kpol-go -o kpolc ./cmd/kpolc

kpolc build SOURCE [IMAGE]      # .kpol / .ekpol -> 1024-байтний образ CME-RAW-1
kpolc build --profile KPOL-CME-2 --emit-ekpol out.ekpol --ekpol-style keyword SOURCE.kpol IMAGE
kpolc build SOURCE IMAGE --emit-c99 out.c --emit-z3-cert out.json --dump-concepts
kpolc check SOURCE              # розбір і статична перевірка
kpolc verify SOURCE             # Proof (.kpol) або вбудовані тести (.ekpol)
kpolc run SOURCE.kpol -e 'Buy(count=1)' -e 'Buy(count=Unknown)'
kpolc to-kpol SOURCE.ekpol      # EKPOL -> класичний KPOL (на stdout)
kpolc to-ekpol SOURCE.kpol      # KPOL або EKPOL -> EKPOL у стилі --ekpol-style symbolic|keyword
kpolc auth INPUT --check [--emit-bram OUT.bin] [--emit-dogo OUT.json]
kpolc auth-cst INPUT            # дерево розбору KPOL-AUTH
kpolc auth-run INPUT -w Concept=value ...   # запис у еталонну машину Do/Go
```

Коди виходу: `0` — успіх, `1` — перевірку не пройдено (`verify`; `auth` — помилка читання/запису файлу), `2` — помилка використання, введення-виведення або відхилений текст програми (`auth`: помилка розбору), `3` — відмова зниження KPOL-AUTH. `kpolc build` не перезаписує наявних файлів і не залишає часткового результату: якщо одну з вихідних операцій не виконано, створені файли видаляються. Покроковий розбір подій над образом виконує налагоджувач: `vmk --program IMAGE --trace-events SPEC`.

### Перевірка

```bash
(cd Engineering/sw/kpol-go && go vet ./... && go test ./...)     # офлайн; тести z3 і gcc пропускаються за їх відсутності
python3 -m pytest -q Engineering/sw/tests/test_kpol_go.py         # плюс диференціал kpolc проти Python-CLI і приклади посібників
```

Диференційні (золоті) файли [`testdata/*_golden.json.gz`](testdata/goldenio.py) створено еталонною Python-реалізацією: корпус усіх `.kpol` / `.ekpol` репозиторію, блоки з посібників, вектори додатків A специфікацій і систематичні мутації (від сотень до тисяч випадків на пакет). Кожен генератор детермінований: повторний запуск `python3 testdata/gen_<пакет>_golden.py` дає ті самі байти. Таблиці класів символів Unicode (`isalpha`, `isdigit`) зафіксовано з Python 3.14.4 (Unicode 16.0.0), щоб поведінка лексера не залежала від версії Go.

## Обмеження

1. **Відхилення від Python-еталона.** Скрізь, де еталон падає необробленим винятком, Go повертає помилку з окремим кодом: `KPOL-RT-*` (інтерпретатор, зокрема змішана арифметика `float`/`Decimal`), `EKPOL-INTERNAL`, `KPOL-AUTH-INT-01` і `KPOL-LOWER-INT-01` (не-десяткова цифра), `C99-PARSE`, `C99-Z3-TIMEOUT`. Глибина вкладення обмежена (`KPOL-PARSE-DEPTH` — 10000 для виразів KPOL, `KPOL-AUTH-LIMIT-01` — 1000 для KPOL-AUTH). Ліміт Python на 4300 цифр у цілому не відтворено. Машина `Do/Go` обчислює точно в `int64` і має ліміт кроків (`KPOL-AUTH-VM-STEPS`, 20000 за замовчуванням) замість нескінченного каскаду.
2. **Відомі розбіжності специфікацій (`D-K*`, `D-E*`, `D-A*`) відтворено**, а не виправлено: поведінка збігається з еталоном, доки власник не ухвалить рішення в Issue.
3. **Сертифікат безпеки.** Використовується лише `z3 -in -smt2`; Python-API `z3-solver` не портовано. Рядок `solver` у сертифікаті має вигляд `z3-cli (Z3 version …)`, заголовок `generator` зберігає ім'я еталонного генератора для збігу із закоміченими артефактами BMS.
4. **Не портовано** експериментальні й допоміжні засоби еталона, які специфікація KPOL (§0.2) не нормує: безпрофільне зниження і пасивний `compile_bram_image`, підписані образи, генератори Verilog/RTM/AXI/bare-metal, фальсифікаційний набір, `link_modules`. Їх лишено в [`kpol_reference.py`](../kpol-ref/kpol_reference.py).
5. **Трасування й TUI** не входять до `kpolc`: вони лишаються в `vmk`, який працює з образами `CME-RAW-1`. Власний, ширший за специфікацію фронтенд `vmk` (`internal/vmk/kpol_compiler.go`, `ekpol.go`) ще не переведено на цей модуль; його обмеження описано в реєстрах розбіжностей [`D-K8`](../../specifications/kpol/kpol-formal-specification.md) і [`D-A18`](../../specifications/kpol/kpol-auth-formal-specification.md).

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 1.0.0 | 2026-11-20 | Перший випуск: пакети `kpol`, `ekpol`, `kpolauth`, `c99`, команда `kpolc`, золоті файли, диференційні тести. |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| **Образ `CME-RAW-1`** | 1024 байти: 64 слоти по 16 байтів, які завантажуються в пам'ять виконавця концептів. |
| **Золотий файл** | Результати Python-еталона для корпусу вхідних текстів, з якими порівнюють Go-реалізацію. |
| **Диференційний тест** | Перевірка, що дві реалізації дають однакові результати на тих самих входах. |
| **L1** | `KPOL-AUTH-L1` — підмножина лінійної нотації KPOL-AUTH, для якої визначено зниження в команди й образ. |
| **WP** | Work Product — робочий продукт інженерного процесу. |
