# Звіт CME2-FORMAL-227: Формальна верифікація CFG-P та каскадів KPOL-CME-2

* **Тип WP:** Report
* **Версія:** 0.1.0
* **Дата:** 2026-11-15
* **Issue:** #227. **PR:** #— (очікує створення).
* **Виконавець:** `gemini-4-hydrogen`. **Рецензент:** не призначено.
* **Коміт, на якому виконано:** `3c89b4e`. **Хост / плата:** Linux x86_64 (`yosys 0.52`, `z3 4.13.3`; без апаратного прогону на платі).
* **Критерії успіху (зафіксовано до виконання):** Issue #227 (`P1` Fail-Closed збереження стану та відсутність каскаду при відхиленні; `P2` обмежене завершення ациклічних каскадів; `P3` детермінована затримка 8 тактів одиночної транзакції; невакуумність `cover`; виявлення >= 3 мутантів із `.vcd` контрприкладами).

---

## 1. Що не вдалося і обмеження

1. **Зменшена параметризація для SMT-трактабельності:** замість повної апаратної конфігурації `NUM_CONCEPTS = 64, QUEUE_DEPTH = 16, ADDR_WIDTH = 8` формальна модель інстанційована з параметрами `NUM_CONCEPTS = 4, QUEUE_DEPTH = 4, ADDR_WIDTH = 4` (`16` слів BRAM по `32` біти). Це зберігає логіку переповнення/арбітражу черги, повну 128-бітну структуру дескриптора `KPOL-CME-2` та ланцюжки каскадів довжиною до `4`, але не дає автоматичного доказу для `NUM_CONCEPTS > 4` без повторного запуску з більшими параметрами.
2. **Обмеження k-індукції та PDR:**
   - Необмежена `k`-індукція (`yosys-smtbmc -s z3 -i -t 5`) доведена для локальних інваріантів безпеки (`P1a_no_we_on_reject`, `P1b_no_we_during_reject`, `P1c_w0_preserved_on_reject`, `P1f_pulse_mutex`). Глобальна консервація подій (`P1d_no_cascade_on_reject`, `P1e_idle_after_isolated_reject`), яка використовує 32-бітні лічильники, а також властивості завершуваності/затримки (`P2`, `P3`) доведені методом Bounded Model Checking (BMC) від скидання на глибину `t=20` і `t=52` відповідно (`16` тактів ініціалізації BRAM через Порт A + до `36` активних тактів > `8 * 4 + 2 = 34`).
   - Рушій `yosys-abc pdr` не завершив доказ на повному дизайні за розумний час (> 120 с) через розмір простору станів BRAM + тіньового масиву (`1024` біти пам'яті).
   - Рушій `boolector` у зв'язці з `yosys-smtbmc` завершувався з `BrokenPipeError` при записі SMT2-потоку, тому всі фінальні перевірки виконано солвером `z3 4.13.3`.
3. **Не виконувалося:** апаратний прогін на PYNQ-Z1 (`HIL`) — задача обмежена формальною верифікацією RTL ядра `CFG-P`.

## 2. Метод

- **Об'єкт верифікації (реальний RTL без змін):**
  - `Engineering/hw/rtl/core/kpol_txn_gate_v2.sv`
  - `Engineering/hw/rtl/core/km_concept_micro_engine.sv`
  - `Engineering/hw/rtl/core/km_concept_bram.sv`
  - `Engineering/hw/rtl/core/km_autonomous_sequencer.sv`
- **Формальна обгортка та скрипт:** [cme2_formal_props.sv](scripts/cme2_formal_props.sv), [run_cme2_formal.py](scripts/run_cme2_formal.py).
- **Інструменти:** `Yosys 0.52`, `yosys-smtbmc`, `Z3 4.13.3`.
- **Групи властивостей:**
  - **P1 (Fail-Closed State Preservation & No Cascade on Reject):** `P1a_no_we_on_reject`, `P1b_no_we_during_reject`, `P1c_w0_preserved_on_reject`, `P1d_no_cascade_on_reject`, `P1e_idle_after_isolated_reject`, `P1f_pulse_mutex`.
  - **P2 (Bounded Acyclic Cascade Termination):** за ациклічної таблиці `KPOL-CME-2` (для кожного `cid` підписник вимкнений або `subscriber_cid > cid && subscriber_cid < 4`) та одного стартового зовнішнього тригера секвенсер переходить у `busy_o == 0` не пізніше `8 * NUM_CONCEPTS + 2 = 34` тактів (`P2_bounded_termination`).
  - **P3 (Exact Single-Transaction Latency):** від `ext_accept` у `ST_IDLE` за порожньої черги та вимкненого підписника імпульс `commit_pulse_o || reject_pulse_o` виставляється рівно на `8`-му такті (`P3a_exact_latency_pulse`, `P3b_no_early_pulse`), а `busy_o == 0` — на `9`-му такті (`P3c_idle_after_single`).
  - **Cover (Non-vacuity):** `C1_cascade_3_commits` (`committed_count_o >= 3`), `C2_reject_reached` (`reject_pulse_o == 1`), `C3_commit_and_idle`.
- **Мутантний негативний контроль (`AGENTS.md §4.1`):** інжектовано 3 мутанти у тимчасову копію `km_autonomous_sequencer.sv` (`M1_we_on_reject`, `M2_cascade_on_reject`, `M3_cyclic_cascade`).

## 3. Результати

Усі сирі журнали (`# cmd:`, `# timestamp:`) і `.vcd` траси збережені в `raw/`. Зведена таблиця результатів — [raw/cme2_results.csv](raw/cme2_results.csv), метадані та SHA-256 — [raw/cme2_provenance.json](raw/cme2_provenance.json).

| Дизайн / Перевірка | Рушій | Статус | Час (с) | Деталі / Артефакт |
| :--- | :--- | :--- | ---: | :--- |
| `original (CFG-P)` — `P1_safety_ind` | `smtbmc z3 ind t=5` | `PASSED` | 0.202 | [raw/orig_safety_ind.log](raw/orig_safety_ind.log) |
| `original (CFG-P)` — `P1_safety_bmc` | `smtbmc z3 bmc t=20` | `PASSED` | 21.479 | [raw/orig_safety_bmc.log](raw/orig_safety_bmc.log) |
| `original (CFG-P)` — `P2_P3_liveness_bmc` | `smtbmc z3 bmc t=52` | `PASSED` | 196.659 | [raw/orig_liveness_bmc.log](raw/orig_liveness_bmc.log) |
| `original (CFG-P)` — `cover_non_vacuity` | `smtbmc z3 cover t=45` | `PASSED` | 10.687 | Досягнуто `C1_cascade_3_commits`, `C2_reject_reached`, `C3_commit_and_idle`; [raw/orig_cover.log](raw/orig_cover.log) |
| `M1_we_on_reject` | `smtbmc z3 bmc t=20` | `FAILED` | 0.491 | Порушено `P1a_no_we_on_reject`; [raw/M1_we_on_reject.vcd](raw/M1_we_on_reject.vcd) |
| `M2_cascade_on_reject` | `smtbmc z3 bmc t=20` | `FAILED` | 1.001 | Порушено `P1e_idle_after_isolated_reject`; [raw/M2_cascade_on_reject.vcd](raw/M2_cascade_on_reject.vcd) |
| `M3_cyclic_cascade` | `smtbmc z3 bmc t=53` | `FAILED` | 280.492 | Порушено `P2_bounded_termination`; [raw/M3_cyclic_cascade.vcd](raw/M3_cyclic_cascade.vcd) |

## 4. Перевірка гіпотези / критеріїв

| Критерій | Очікувано | Отримано | Висновок |
| :--- | :--- | :--- | :--- |
| `P1` Fail-Closed збереження `W0` та заборона каскаду при reject | `PASSED` (k-індукція + BMC) | `PASSED` (`ind t=5` за 0.202 с, `bmc t=20` за 21.479 с) | Виконано |
| `P2` Обмежена завершуваність ациклічного каскаду (`<= 34` тактів) | `PASSED` (BMC `t=52`) | `PASSED` (196.659 с) | Виконано (в межах `NUM_CONCEPTS=4`) |
| `P3` Фіксована затримка одиночної транзакції (`8` тактів) | `PASSED` (BMC `t=52`) | `PASSED` (196.659 с) | Виконано |
| Невакуумність (`cover` >= 3 каскадних комітів та reject) | Усі 3 cover досягнуті | Досягнуто на кроках 24, 25, 41 | Виконано |
| Негативний контроль (>= 3 мутантів) | `FAILED` + `.vcd` для кожного | 3/3 мутантів спіймано з `.vcd` | Виконано |

## 5. Відтворення

```bash
python3 Engineering/validation/kpol-cme/cme2-formal-227/scripts/run_cme2_formal.py
python3 -m pytest -q Engineering/hw/tests/test_cme2_formal_227.py
```

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-15 | Перша редакція формальної верифікації CFG-P та каскадів KPOL-CME-2 (#227) |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| BMC | Bounded Model Checking — обмежена перевірка моделі на скінченну глибину тактів |
| BRAM | Block RAM — вбудована блокова пам'ять ПЛІС (FPGA) |
| CFG-P | Активна конфігурація апаратного конвеєра (`CME-RAW-1` + `KPOL-CME-1/2`) |
| CME | Concept Micro-Engine — мікроядро обчислення концепту |
| SVA | SystemVerilog Assertions — декларативні твердження формальної верифікації |
| WP | Work Product — робочий продукт із визначеним призначенням |
