# Звіт KPOL-CME-169: синхронізація реєстрів, формального аналізу, архітектурних документів B1/S2 та паспорта TRL після PR #149–#174

* **Версія:** 0.1.0
* **Дата:** 2026-11-14
* **Тип WP:** Report
* **Issue:** [#169](https://github.com/nick-fedchik/kuzmin-machine/issues/169).
* **Виконавець:** GitHub Copilot CLI (`gemini-4-carbon`). **Рецензент:** очікується незалежний агент іншої родини моделей (Claude).
* **Коміт бази, на якому виконано:** `4a6d684` (верхній шар поверх стеку PR `#163`, `#170–#174`). **Хост:** `AORUS-5-SE` (Linux x86_64, Python 3.14.4 / pytest 9.0.2).
* **Критерії успіху (зафіксовано до виконання):** критерії приймання [#169](https://github.com/nick-fedchik/kuzmin-machine/issues/169).

---

## 1. Що не вдалося і обмеження

1. Робота виконує синхронізацію реєстрів, перехресних посилань і узгодження описів чинних контрактів (`B4 v2.2.0`, `B5 v2.2.0`, `RFC-008`, `CFG-R` vs `CFG-P`), а **не** нове фізичне вимірювання HIL або незалежний зовнішній аудит TRL 4.
2. Незмінні входи (`immutable_input: true` у [`migration-manifest.json`](../../../../Project/registers/migration-manifest.json) та історичні звіти `AV-04/07/08/10/11`, `S3-62`, `S4-07`) збережено побайтно без редагування.
3. Задачі відкритого стеку (`#151`, `#162`, `#164–#169`) відображені в [`open-work-items.md`](../../../../Project/registers/open-work-items.md) зі статусом `Open` / `In review`, оскільки рішення про рецензування та злиття в `main` належить виключно незалежному рецензенту й власнику проєкту.

## 2. Метод

1. **Перевірка фактичних станів GitHub Issues і PR:** звірено поточні стани Issues `#5`, `#8`, `#19`, `#20`, `#115`, `#120`, `#148`, `#150–#159`, `#151`, `#162`, `#164–#169` та злитих PR `#149–#161` у репозиторії `nick-fedchik/kuzmin-machine`.
2. **Точкова актуалізація документів та реєстрів (без зміни незмінних джерел):**
   - [`Project/registers/open-work-items.md`](../../../../Project/registers/open-work-items.md) (`v0.3.0`): збережено первинні знімки міграції, оновлено закриті `#148` ([PR #149](https://github.com/nick-fedchik/kuzmin-machine/pull/149)), `#115` ([PR #161](https://github.com/nick-fedchik/kuzmin-machine/pull/161)), `#5` (закрито в GitHub 2026-11-13 при чинному рішенні власника `Postponed` від 2026-11-12), злиті проміжні кроки `#8` (`PR #152–#160`) та додано таблицю відкритого стеку аудиту `#151/#162/#164–#169`;
   - [`Research/studies/author-semantics/formal-analysis.md`](../../../../Research/studies/author-semantics/formal-analysis.md) (`v0.3.1`): усунено категоричне твердження про повну відсутність будь-яких експериментальних зразків у автора; з прямим посиланням на [`Research/sources/author/rfc-2026-11-12.md`](../../../../Research/sources/author/rfc-2026-11-12.md) (`RFC-008`) розмежовано авторське свідчення про історичну демонстрацію макета з двох-трьох плат і фактичну відсутність переданого відтворюваного інженерного архіву (схем, прошивок, бітстрімів, RTL, протоколів вимірювань);
   - [`Engineering/design/system-boundary-allocation-b1.md`](../../../design/system-boundary-allocation-b1.md) (`v1.0.2`) та [`Engineering/design/s2-candidate-system.md`](../../../design/s2-candidate-system.md) (`v0.4.1`): узгоджено опис вхідної черги `B5 v2.2.0` (очікування без втрат за `valid && ready`, резервування слота під каскад і `cascade_pending_*_q` у `#151`, діагностичний облік втрат лише для незупинних джерел із W1C-очищенням `0x02C` при `busy == 0` у `#168`) та фазового контракту `B4 v2.2.0` (закриття 1-тактової гонитви `Load vs Run` та 2-FF CDC / антибрязкіт `btn[0]` у `pynq_z1_top`);
   - [`Project/assessments/trl/report.md`](../../../../Project/assessments/trl/report.md) (`v0.2.5`): у §3 явно відокремлено фізичний показник $p99 = 20.0\text{ нс}$ (2 такти @ 100 МГц ізольованої реактивної конфігурації `CFG-R` у `AV-10/AV-11`) від детермінованого 8-тактового циклу обробки однієї витягнутої з черги події ($80\text{ нс}$ @ 100 МГц без черги FIFO та CDC) програмованого BRAM-конвеєра `CFG-P`;
   - [`Project/registers/work-products.md`](../../../../Project/registers/work-products.md) (`v0.5.0`), [`Project/registers/goals-needs-work-items.md`](../../../../Project/registers/goals-needs-work-items.md) (`v0.9.0`), [`Engineering/validation/README.md`](../../README.md) (`v0.5.4`) та [`Project/registers/wp-index.json`](../../../../Project/registers/wp-index.json) (`v0.10.0`): зареєстровано всі нові звіти верифікації та синхронізовано файловий індекс WP з повним робочим деревом.
3. **Автоматизовані перевірки ([`raw/checks-01.log`](raw/checks-01.log)):** перевірено 1:1 відповідність `Project/registers/wp-index.json` повному набору файлів репозиторію, збереження всіх `immutable` входів, `check_links.py`, `check_wp_documents.py`, `git diff --check` та повний набір `python3 -m pytest -q`.

## 3. Результати

* **Повнота індексу `wp-index.json` ([`raw/checks-01.log`](raw/checks-01.log)):** усі відстежувані файли репозиторію проіндексовані без пропусків і дублікатів; жоден `immutable` вхід не змінено.
* **Перевірка посилань і конвертів WP ([`raw/checks-01.log`](raw/checks-01.log)):** `check_links.py` — `0 broken links`; `check_wp_documents.py` — `errors: []` (`immutable_checked: 108`).
* **Повний регресійний набір тестів ([`raw/checks-01.log`](raw/checks-01.log)):** `339 passed, 300 subtests passed` (`exit_code=0`).

## 4. Перевірка гіпотези / критеріїв

| Критерій (#169) | Очікувано | Отримано | Висновок |
| :--- | :--- | :--- | :--- |
| Актуалізація `open-work-items.md` | Закриті `#115` (PR #161) і `#148` (PR #149), стан `#5`/`#8`/`#120` та відкритий пакет `#151/#162/#164–#169` відображені без втрати історії | Оформлено у `v0.3.0` зі збереженням первинних знімків | Виконано |
| Уточнення `formal-analysis.md` за `RFC-008` | Відділено історичне авторське свідчення про макет із плат від відсутності переданого відтворюваного архіву | Оновлено у `v0.3.1` із прямим посиланням на `rfc-2026-11-12.md` | Виконано |
| Узгодження `system-boundary-allocation-b1.md` і `s2-candidate-system.md` | Опис B4 та B5 узгоджений із `v2.2.0` (`valid && ready`, резерв каскаду, W1C `0x02C`, `Load vs Run`) | Оновлено до `v1.0.2` та `v0.4.1` відповідно | Виконано |
| Розмежування латентності у `Project/assessments/trl/report.md` | Явно розділено `CFG-R` ($20.0\text{ нс}$) і `CFG-P` ($80\text{ нс}$ за 8 тактів без очікування в черзі) | Оновлено у `v0.2.5` | Виконано |
| Реєстри WP, `wp-index.json`, лінтери та тести | Нові звіти зареєстровані; `check_links.py`, `check_wp_documents.py` та `pytest` проходять чисто | `0 broken links`, `errors: []`, `339 passed` | Виконано |

## 5. Відтворення

```bash
KM_DRAFTS_REPO=/home/mfedchyk/GitHub/nick-fedchik/drafts python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
python3 -m pytest -q
```

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-14 | Перша редакція звіту синхронізації реєстрів і документації за результатами PR #149–#174 (#169). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| CFG-P / CFG-R | Конвеєрний BRAM-виконавець проєкту (8 тактів на подію) та окрема реактивна конфігурація транзакційного шлюзу S6 (`AV-10/AV-11`). |
| RFC | Request for Comments — редакційний запит на уточнення авторської семантики МК. |
| WP | Work Product — керований робочий продукт проєкту з власним типом і версією. |
