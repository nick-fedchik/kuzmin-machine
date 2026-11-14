# Звіт KPOL-SEC-164: усунення pre-auth nonce poisoning, детермінованого nonce та legacy-payload у Secure Boot

* **Версія:** 0.1.0
* **Дата:** 2026-11-14
* **Тип WP:** Report
* **Issue:** [#164](https://github.com/nick-fedchik/kuzmin-machine/issues/164).
* **Виконавець:** GitHub Copilot CLI (`gemini-4-carbon`). **Рецензент:** очікується незалежний агент іншої родини моделей (Claude).
* **Коміт, на якому виконано:** `e7e573e` (негативний контроль — `1d8359a`). **Хост / плата:** `AORUS-5-SE` (Linux x86_64, програмна верифікація Python 3.14.4 / pytest 9.0.2; апаратний HIL не охоплюється).
* **Критерії успіху (зафіксовано до виконання):** критерії приймання [#164](https://github.com/nick-fedchik/kuzmin-machine/issues/164).

---

## 1. Що не вдалося і обмеження

1. Перевірка є суто програмною верифікацією криптографічного пакувальника й верифікатора `compile_signed_bram_image` / `verify_bram_signature` у [`kpol_reference.py`](../../../sw/kpol-ref/kpol_reference.py). Вона **не є** апаратним Secure Boot на кристалі Zynq-7000 (`BootROM` / `FSBL` / eFUSE) і не вирішує задачі зберігання секретного ключа в захищеній пам'яті плати.
2. Поточна множина `seen_nonces: set[bytes]` є оперативною структурою в пам'яті процесу завантажувача; персистентне зберігання монотонного лічильника версій у енергонезалежній пам'яті не входить у межі #164.

## 2. Метод

1. **Негативний контроль до зміни реалізації (`1d8359ab351ddd041ad63598f157eefb8ff9dec4`):** до [`test_kpol_reference.py`](../../../sw/kpol-ref/tests/test_kpol_reference.py) додано три цільові тести (`test_issue164_pre_auth_nonce_poisoning_blocked`, `test_issue164_default_nonce_is_random_across_updates`, `test_issue164_module_payload_is_cme_raw_1`) та виконано прогін проти незміненого `kpol_reference.py` із записом у [`raw/negative-control-01.log`](raw/negative-control-01.log).
2. **Виправлення (`e7e573e`):**
   - у `verify_bram_signature()` обчислення та константно-часове порівняння `hmac.compare_digest(auth_tag, computed_tag)` перенесено **перед** перевіркою та модифікацією `seen_nonces`;
   - у `compile_signed_bram_image()` за `nonce=None` детермінований хеш замінено на криптостійкий випадковий `secrets.token_bytes(16)`;
   - за замовчуванням для входу типу `Module` ввімкнено кодогенерацію `CME-RAW-1` (`compile_concept_microcode_bram_image(module)`), сумісну з `km_concept_micro_engine.sv` (`payload_format="legacy"` збережено як явний опційний режим).
3. **Повна регресійна та структурна перевірка:** виконано повний набір `python3 -m pytest -v` ([`raw/full-pytest-01.log`](raw/full-pytest-01.log)), `check_links.py` і `check_wp_documents.py` ([`raw/structure-01.log`](raw/structure-01.log)).

## 3. Результати

* **Негативний контроль (`1d8359a`, [`raw/negative-control-01.log`](raw/negative-control-01.log)):** `3 failed, 55 deselected` (`exit_code=1`):
  - підроблений пакет зі зміненим 1 бітом у `auth_tag` записував `nonce` у `seen_nonces` (`len(seen_nonces) == 1`), блокуючи легітимний образ;
  - два послідовні підписані виклики для оновленого модуля `OtaModule` мали ідентичний 16-байтний `nonce` (`\xcdF\x7f...`);
  - payload підписаного `Module` містив legacy-таблицю замість `CME-RAW-1`.
* **Після виправлення (`e7e573e`, [`raw/full-pytest-01.log`](raw/full-pytest-01.log)):** `322 passed, 300 subtests passed` (`exit_code=0`).
* **Структурні перевірки WP та посилань ([`raw/structure-01.log`](raw/structure-01.log)):** `0 broken links`, `errors: []` (`exit_code=0`).

## 4. Перевірка гіпотези / критеріїв

| Критерій (#164) | Очікувано | Отримано | Висновок |
| :--- | :--- | :--- | :--- |
| Pre-auth захист `seen_nonces` | Підроблений `auth_tag` не змінює `seen_nonces`; справжній пакет після нього проходить | `len(seen_nonces) == 0` після підробки, `ok_legit == True` | Виконано |
| Свіжість стандартного `nonce` (`nonce=None`) | Два підписані оновлення одного `Module` мають різні 16-байтні `nonce` й обидва проходять | `img_v1[16:32] != img_v2[16:32]`, `ok1 == True`, `ok2 == True` | Виконано |
| Сумісність payload `Module` з `CME-RAW-1` | `signed_img[64:] == compile_concept_microcode_bram_image(module)` | Збіг 1024 байтів `CME-RAW-1`, `descriptors[0].current_state == 77` | Виконано |
| Негативний контроль + регресія | Зафіксоване падіння до фіксу та 100% зелений `pytest` після | `3 failed` до фіксу → `322 passed` після фіксу | Виконано |

## 5. Відтворення

```bash
python3 -m pytest Engineering/sw/kpol-ref/tests/test_kpol_reference.py -k issue164 -v
python3 -m pytest -q
python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
```

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-14 | Перша редакція звіту верифікації виправлень Secure Boot (#164). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| CME-RAW-1 | Бінарний формат 1024-байтного образу (64 дескриптори по 16 байтів) для ядра `km_concept_micro_engine`. |
| DoS | Denial of Service — відмова в обслуговуванні легітимних запитів. |
| HMAC-SHA256 | Код автентифікації повідомлень на базі хеш-функції SHA-256. |
| Nonce | Одноразове криптографічне число для захисту від повторного відтворення (replay). |
