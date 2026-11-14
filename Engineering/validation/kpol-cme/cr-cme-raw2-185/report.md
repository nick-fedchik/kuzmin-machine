# Звіт #185: перевірка розрахунків проєкту `KPOL-SYS-02` і 32-байтного дескриптора `CME-RAW-2` (ADR B7)

* **Версія:** 0.1.0
* **Дата:** 2026-11-14
* **Тип WP:** Report / Analysis
* **Issue:** [#185](https://github.com/nick-fedchik/kuzmin-machine/issues/185) (sub-issue [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8)). **PR:** у гілці `docs/185-cr-kpol-sys02-cme-raw2`.
* **Виконавець:** GitHub Copilot CLI (Gemini 4 Carbon, `gemini-4-carbon`). **Рецензент:** незалежна рецензія не проведена.
* **Коміт бази (Шар 2 стеку, PR #188):** `103b5179166b5d94718f901e4efac327d4ab7fe2`. **Хост / плата:** Linux x86_64 (`AORUS-5-SE`); фізична плата FPGA не залучалася. **Бітстрім (SHA-256):** не генерувався.
* **Критерії успіху (зафіксовано до виконання):** критерії перевірки в описі [#185](https://github.com/nick-fedchik/kuzmin-machine/issues/185) (побітові таблиці варіантів 16 Б vs 32 Б, розрахунок місткості `BRAM36` для 64+ концептів, перевірка сумісності з 64-байтним HMAC-заголовком `Secure Boot` і протокол рішення без несанкціонованої зміни чинного RTL `CFG-P`).

---

## 1. Що не вдалося і обмеження

* Відповідно до меж задачі `type:change-request` ([#185](https://github.com/nick-fedchik/kuzmin-machine/issues/185)) жоден файл RTL або виконуваного коду чинної конфігурації `CFG-P` (`Engineering/hw/rtl/`, `Engineering/sw/kpol-ref/kpol_reference.py`) не змінювався; документ [`cme-raw2-kpol-sys02.md`](../../../decisions/cme-raw2-kpol-sys02.md) має статус `Proposed` до рішення власника.
* Синтезна перевірка двобанкової пам'яті `CME-RAW-2` (`2 × RAMB36E1`, 32-бітний Порт A + 64-бітний Порт B) виконана на рівні логічного синтезу відкритим інструментом `yosys synth_xilinx -family xc7` в ізольованому тимчасовому каталозі без розміщення й трасування (`nextpnr` / Vivado) і без HIL на платі PYNQ-Z1.
* Під час першого запуску `yosys` з прапорцем `-q` без явного перенаправлення виводу команди `stat` ([`raw/xc7-baseline-stat-01.log`](raw/xc7-baseline-stat-01.log)) таблиця примітивів була придушена тихим режимом; у повторному прогоні ([`raw/xc7-baseline-stat-02.log`](raw/xc7-baseline-stat-02.log)) вивід `stat` записано повністю через `tee -o /dev/stdout stat`.
* Правило поведінки складеного виразу при читанні неініціалізованого стану `_` (`W1.state_valid == 0`) залишається параметризованим бітом `REQUIRE_SELF_VALID` до отримання відповіді М. Ю. Кузьміна на відкритий запит `RFC-017` (`drafts` PR #4).

## 2. Метод

1. **Зняття точного ресурсного зрізу базового конвеєра `CFG-P` (`CME-RAW-1`):** виконано синтез `yosys synth_xilinx -family xc7 -top kpol_bram_pipeline_axi` для незмінної бази `103b5179166b5d94718f901e4efac327d4ab7fe2` ([`raw/xc7-baseline-stat-02.log`](raw/xc7-baseline-stat-02.log)).
2. **Емпірична перевірка відображення двобанкової пам'яті `CME-RAW-2` на примітиви Xilinx 7-Series:** синтезовано поведінкову модель парного/непарного банків (`bank_even` для `W0, W2, W4, W6` і `bank_odd` для `W1, W3, W5, W7` на 128 концептів = 4096 Б) із 32-бітним Портом A та 64-бітним Портом B у `yosys synth_xilinx -family xc7` ([`raw/dual-bank-xc7-probe-01.log`](raw/dual-bank-xc7-probe-01.log)), що підтвердило відображення в `2 × RAMB36E1` (оскільки `RAMB18E1` у режимі `TDP` обмежений шириною 18 бітів).
3. **Математична та програмна перевірка неперервності бітових розкладок і контейнера `Secure Boot`:** у фінальному прогоні ([`raw/final-verification-01.log`](raw/final-verification-01.log)) автоматизованим скриптом перевірено неперетин усіх бітових полів `W0..W7` (256 бітів без перекриттів і дірок), місткість `RAMB36E1` для $N \in \{64, 128, 256\}$ концептів, відсутність несанкціонованих змін у `Engineering/hw/` та `Engineering/sw/`, а також криптографічну цілісність розширення 64-байтного заголовка `HMAC-SHA256` (`FORMAT_VERSION = 0x0007`, `PAYLOAD_LEN = 2048`, загальний розмір `2112` байтів) із відмовою при невідповідності версії (`0x0006 != 0x0007`).
4. **Структурна та посилальна валідація:** запущено `check_links.py` (з `KM_DRAFTS_REPO`), `check_wp_documents.py`, `inspect_math_formatting.py`, перевірку `Project/registers/wp-index.json` та `pytest -q`.

## 3. Результати

* **Базовий синтез `CFG-P` ([`raw/xc7-baseline-stat-02.log`](raw/xc7-baseline-stat-02.log)):** повна ієрархія `kpol_bram_pipeline_axi` використовує `1 × RAMB36E1` (`0.71%` від 140 на `XC7Z020-1CLG400C`), `1743` примітивів `LUT2..LUT6` (`3.28%` від `53 200`), `1363` тригерів `FDCE`/`FDRE` (`1.28%` від `106 400`) та `111 × CARRY4`, `exit_code=0`.
* **Синтез двобанкової пам'яті `CME-RAW-2` ([`raw/dual-bank-xc7-probe-01.log`](raw/dual-bank-xc7-probe-01.log)):** модель на 128 концептів × 32 Б (4096 Б; придатна до 256 концептів = 8192 Б у тих самих примітивах `1024x36` TDP) синтезована у рівно `2 × RAMB36E1` (`1.43%` від 140 на `XC7Z020`), `2 × LUT2`, `32 × LUT3` і `1 × FDRE` на логіку комутації Порту A, `exit_code=0`. Це доводить збереження 8-тактового циклу транзакції (`80 нс` @ 100 МГц) та атомарного 1-тактового запису `{W1_new, W0_new}`.
* **Фінальна перевірка бітових таблиць, незмінності RTL/SW, посилань і тестів ([`raw/final-verification-01.log`](raw/final-verification-01.log)):**
  * усі 8 слів `W0..W7` (256 бітів) дескриптора `CME-RAW-2` покривають `[31:0]` без перекриттів;
  * `git diff --name-only origin/feat/184-kpol-cme2-profile -- Engineering/hw Engineering/sw` порожній (`0` змінених файлів коду/RTL);
  * `check_links.py` — `0` битих посилань (перевірено всі посилання на `drafts`);
  * `check_wp_documents.py` — `errors: []`;
  * `inspect_math_formatting.py` — `0` порушень;
  * `python3 -m pytest -q` — `349 passed, 328 subtests passed`, `exit_code=0`.

## 4. Перевірка критеріїв приймання

| Критерій (`#185`) | Очікувано | Отримано | Висновок |
| :--- | :--- | :--- | :--- |
| Побітові таблиці альтернатив (16 Б ущільнення vs 32 Б `CME-RAW-2`) і правила `valid`-біта `_` | Повні таблиці полів, обґрунтування відмови від 16 Б, таблиця переходів `state_valid` і межа `RFC-017` | Наведено у §2–3 [`cme-raw2-kpol-sys02.md`](../../../decisions/cme-raw2-kpol-sys02.md); бітове покриття 256 бітів перевірено програмно | Виконано |
| Розрахунок місткості `BRAM36` та LUT `XC7Z020` для 64+ концептів і впливу на AXI `B4` | Числові оцінки для 64, 128 і 256 концептів із підтвердженням примітивів Xilinx 7-Series | `1 × RAMB36E1` (`2a`) або `2 × RAMB36E1` (`1.43%`, `2b`, 8 тактів до 256 концептів), підтверджено синтезом `yosys` ([`raw/dual-bank-xc7-probe-01.log`](raw/dual-bank-xc7-probe-01.log)); AXI карта `0x000..0x02C` незмінна | Виконано |
| Перевірка сумісності з HMAC-заголовком `Secure Boot` | Збереження 64-байтного заголовка, `NONCE[16]` і `HMAC-SHA256` з fail-closed розмежуванням версій | `FORMAT_VERSION = 0x0007`, `PAYLOAD_LEN = 2048` (`2112` Б загалом), сумісність і відсікання версій перевірено ([`raw/final-verification-01.log`](raw/final-verification-01.log)) | Виконано |
| Протокол рішення власника без несанкціонованої зміни RTL `CFG-P` | 3 явні варіанти резолюції власника; `0` змін у `Engineering/hw/` та `Engineering/sw/` | Зафіксовано у §5 ADR B7; відсутність змін у RTL/SW перевірена `git diff` | Виконано |

## 5. Відтворення

```bash
KM_DRAFTS_REPO=/home/mfedchyk/GitHub/nick-fedchik/drafts python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
python3 -m pytest -q
```

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-14 | Перша редакція звіту перевірки проєкту архітектурного рішення B7 / CR [#185](https://github.com/nick-fedchik/kuzmin-machine/issues/185) (`KPOL-SYS-02` та `CME-RAW-2`). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| ADR / CR | Architecture Decision Record / Change Request |
| `CME-RAW-2` | Запропонований 32-байтний формат дескриптора концепту |
| HIL | Hardware-in-the-Loop (фізична плата FPGA; у цьому звіті не виконувався) |
| `KPOL-SYS-02` | Системна вимога окремого біта ініціалізації стану `_` |
| `RAMB36E1` | Примітив 36-кілобітної блокової пам'яті ПЛІС Xilinx 7-Series |
