# Звіт CME2-FORMAL-227: Формальна верифікація CFG-P та каскадів KPOL-CME-2

* **Тип WP:** Report
* **Версія:** 0.2.0
* **Дата:** 2026-11-16
* **Issue:** #227, #237, #242. **PR:** #236 (v0.1.0); новий PR для v0.2.0 (очікує створення).
* **Виконавець:** `gemini-4-hydrogen`. **Рецензент:** не призначено.
* **Коміт, на якому виконано:** `deb9434` (v0.2.0; базовий `3c89b4e` для v0.1.0). **Хост / плата:** Linux x86_64 (`yosys 0.52`, `z3 4.13.3`; без апаратного прогону на платі).
* **Критерії успіху (зафіксовано до виконання):**
  - **#227 (v0.1.0, `N=4`):** `P1` Fail-Closed збереження стану та відсутність каскаду при відхиленні; `P2` обмежене завершення ациклічних каскадів; `P3` фіксована затримка 8 тактів одиночної транзакції; `cover`; >= 3 мутантів із `.vcd`.
  - **#237, #242 (v0.2.0, `N=16` композиційно):**
    1. `P1_n16_ind`: необмежена $k$-індукція (`yosys-smtbmc -s z3 -i`) для взаємовиключності Великої Крапки (`P_bigdot_mutex_pulse`, `P_bigdot_mutex_cme`) та `P1a..P1e` на `NUM_CONCEPTS = 16, QUEUE_DEPTH = 16, ADDR_WIDTH = 6`;
    2. `P2_rank_step_n16`: необмежена $k$-індукція спадання рангу Ляпунова $V(\text{cid}) = 15 - \text{cid}$ на кожному кроці каскаду для довільної DAG-таблиці на $N = 16$;
    3. `P3_liveness_n16_ind`: $k$-індукція точного 8-тактового бюджету як без підписника, так і з активним каскадом та двома зовнішніми тригерами у черзі;
    4. `cover_n16`: досяжність 4-ступеневого каскаду до `cid = 15`, `reject_pulse_o` та двох зовнішніх тригерів;
    5. Негативний контроль: >= 4 мутантів на $N = 16$ (включно з `M_bigdot_dual_pulse` та `M_rank_violation_self_sub`) із `.vcd`.

---

## 1. Що не вдалося і обмеження

1. **Межі композиційного доказу на `N = 16` проти повної конфігурації `N = 64`:**
   - Версія `0.2.0` масштабує формальну модель до **`NUM_CONCEPTS = 16, QUEUE_DEPTH = 16, ADDR_WIDTH = 6`** (`64` слова у BRAM по `32` біти) порівняно з `NUM_CONCEPTS = 4` у `0.1.0`, але все ще не покриває повну апаратну таблицю `NUM_CONCEPTS = 64, ADDR_WIDTH = 8` (`256` слів BRAM) одним монолітним прогоном.
   - Наївний монолітний BMC від скидання на $N = 16$ глибиною $> 130$ тактів є обчислювально нетрактабельним через експоненційне розгортання 32-бітних арифметичних шляхів `km_concept_micro_engine` та мультиплексорів BRAM/FIFO. Композиційне розбиття на необмежену $k$-індукцію безпеки (`P1_n16_ind`), крок рангу Ляпунова (`P2_rank_step_n16`) та 8-тактовий крок латентності (`P3_liveness_n16_ind`) усуває потребу в глибокому BMC для $N = 16$: математична композиція лем доводить завершення будь-якого ациклічного каскаду довжиною $\le 16$ за $\le 16 \times 8 = 128$ тактів обробки.
   - Для `P2_rank_step_n16` у режимі $k$-індукції ациклічність таблиці `KPOL-CME-2` (`sub_disabled || (subscriber_cid > active_cid_q && subscriber_cid < 16)`) припускається в момент захоплення слова `W3` (`ST_CAP_W3_STROBE`), що спирається на незмінність `W2/W3` під час `rst_n == 1` (`a_we_i == 0` і запис порту B лише в `W0`).
2. **Обмеження інструментів (`0.1.0` та `0.2.0`):**
   - Рушій `yosys-abc pdr` не завершує доказ на повному дизайні за розумний час (`> 120` с), а `boolector` падає з `BrokenPipeError`; усі фінальні результати отримано солвером `z3 4.13.3`.
   - Повний прогін `cover_n16` (~160 с) та `P3_liveness_n16_ind` (~54 с) виконуються окремим скриптом; у швидкому профілі CI (`pytest -q` з `--fast`) запускаються `P1_n16_ind`, `P2_rank_step_n16` та 4 мутанти (~112 с), а за відсутності `yosys`/`z3` у хмарному CI перевіряються зафіксовані сирі журнали, SHA-256 та `.vcd` контрприклади.
3. **Не виконувалося:** апаратний прогін на PYNQ-Z1 (`HIL`) — задача обмежена формальною верифікацією RTL-ядра `CFG-P`.

## 2. Метод

- **Об'єкт верифікації (реальний RTL без змін):**
  - `Engineering/hw/rtl/core/kpol_txn_gate_v2.sv`
  - `Engineering/hw/rtl/core/km_concept_micro_engine.sv`
  - `Engineering/hw/rtl/core/km_concept_bram.sv`
  - `Engineering/hw/rtl/core/km_autonomous_sequencer.sv`
- **Формальна обгортка та скрипти:**
  - `N = 4` (#227): [cme2_formal_props.sv](scripts/cme2_formal_props.sv), [run_cme2_formal.py](scripts/run_cme2_formal.py).
  - `N = 16` композиційно (#237, #242): [cme2_formal_n16_props.sv](scripts/cme2_formal_n16_props.sv), [run_cme2_formal_n16.py](scripts/run_cme2_formal_n16.py). Внутрішні сигнали секвенсера (`state_q`, `fifo_count_q`, `fifo_wr_ptr_q`, `fifo_rd_ptr_q`, `cme_event_valid`, `cme_committed`, `cme_rejected`, `cme_trigger_subscriber`, `cme_subscriber_cid`, `cascade_req`, `active_cid_q`, `cascade_pending_valid_q`, `cascade_pending_cid_q`, `desc_w2_q`) прив'язуються після `flatten` командою Yosys `connect -set` без зміни RTL.
- **Інструменти:** `Yosys 0.52`, `yosys-smtbmc`, `Z3 4.13.3`.
- **Групи властивостей (`N = 16`, v0.2.0):**
  - **`P1_n16_ind` (`k`-індукція `t=5`):** допоміжні індуктивні інваріанти досяжних станів (`state_q <= 7`, `fifo_count_q <= 16`, узгодженість `rd_ptr + count[3:0] == wr_ptr`, `bram_b_we_o == p_commit_pulse`) + докази `P_bigdot_mutex_pulse`, `P_bigdot_mutex_cme`, `P1a_no_we_on_reject`, `P1b_no_we_during_reject`, `P1c_w0_preserved_on_reject` (усі `16` слів `W0`), `P1d_no_cascade_on_reject`, `P1e_idle_after_isolated_reject`.
  - **`P2_rank_step_n16` (`k`-індукція `t=10`):** для довільної DAG-таблиці `KPOL-CME-2` на `N = 16` будь-яка завершена транзакція або не породжує каскаду, або виставляє `cme_subscriber_cid > active_cid_q` зі строгим спаданням рангу Ляпунова $V(\text{cid}) = 15 - \text{cid}$.
  - **`P3_liveness_n16_ind` (`k`-індукція `t=12`, закриття #237):** точний 8-тактовий цикл транзакції (`P3_first_tx_exact_8`, `P3_first_tx_no_early`), перехід у `!busy_o` на 9-му такті без каскаду (`P3_no_cascade_idle_9`) та миттєвий старт наступного циклу на 9–10 тактах при каскаді або другому зовнішньому тригері (`P3_cascade_or_2nd_trigger_zero_bubble`, `P3_next_tx_starts_at_10`).
  - **`cover_n16` (`t=42`):** досяжність 4-ступеневого каскаду до `cid = 15` (`C1_n16_cascade_4_commits`), відмови (`C2_n16_reject_reached`) та двох зовнішніх тригерів у черзі (`C3_n16_two_ext_triggers`).
- **Мутантний негативний контроль (`AGENTS.md §4.1`):** 3 мутанти на `N = 4` (`0.1.0`) і 4 мутанти на `N = 16` (`0.2.0`: `M_bigdot_dual_pulse`, `M_we_on_reject`, `M_cascade_on_reject`, `M_rank_violation_self_sub`).

## 3. Результати

### 3.1. Базовий прогін `N = 4` (v0.1.0, #227)

Усі сирі журнали (`# cmd:`, `# timestamp:`) і `.vcd` траси збережені в `raw/` ([raw/cme2_results.csv](raw/cme2_results.csv), [raw/cme2_provenance.json](raw/cme2_provenance.json)).

| Дизайн / Перевірка | Рушій | Статус | Час (с) | Деталі / Артефакт |
| :--- | :--- | :--- | ---: | :--- |
| `original (CFG-P)` — `P1_safety_ind` | `smtbmc z3 ind t=5` | `PASSED` | 0.202 | [raw/orig_safety_ind.log](raw/orig_safety_ind.log) |
| `original (CFG-P)` — `P1_safety_bmc` | `smtbmc z3 bmc t=20` | `PASSED` | 21.479 | [raw/orig_safety_bmc.log](raw/orig_safety_bmc.log) |
| `original (CFG-P)` — `P2_P3_liveness_bmc` | `smtbmc z3 bmc t=52` | `PASSED` | 196.659 | [raw/orig_liveness_bmc.log](raw/orig_liveness_bmc.log) |
| `original (CFG-P)` — `cover_non_vacuity` | `smtbmc z3 cover t=45` | `PASSED` | 10.687 | Досягнуто `C1_cascade_3_commits`, `C2_reject_reached`, `C3_commit_and_idle`; [raw/orig_cover.log](raw/orig_cover.log) |
| `M1_we_on_reject` | `smtbmc z3 bmc t=20` | `FAILED` | 0.491 | Порушено `P1a_no_we_on_reject`; [raw/M1_we_on_reject.vcd](raw/M1_we_on_reject.vcd) |
| `M2_cascade_on_reject` | `smtbmc z3 bmc t=20` | `FAILED` | 1.001 | Порушено `P1e_idle_after_isolated_reject`; [raw/M2_cascade_on_reject.vcd](raw/M2_cascade_on_reject.vcd) |
| `M3_cyclic_cascade` | `smtbmc z3 bmc t=53` | `FAILED` | 280.492 | Порушено `P2_bounded_termination`; [raw/M3_cyclic_cascade.vcd](raw/M3_cyclic_cascade.vcd) |

### 3.2. Композиційний прогін `N = 16` (v0.2.0, #237, #242)

Усі сирі журнали та `.vcd` траси збережені в `raw/n16_compositional/` ([cme2_n16_results.csv](raw/n16_compositional/cme2_n16_results.csv), [cme2_n16_provenance.json](raw/n16_compositional/cme2_n16_provenance.json)).

| Дизайн / Перевірка | Рушій | Статус | Час (с) | Деталі / Артефакт |
| :--- | :--- | :--- | ---: | :--- |
| `original (CFG-P N=16)` — `P1_n16_ind` | `smtbmc z3 ind t=5` | `PASSED` | 1.103 | [orig_n16_safety_ind.log](raw/n16_compositional/orig_n16_safety_ind.log) |
| `original (CFG-P N=16)` — `P2_rank_step_n16` | `smtbmc z3 ind t=10` | `PASSED` | 0.172 | [orig_n16_rank_ind.log](raw/n16_compositional/orig_n16_rank_ind.log) |
| `original (CFG-P N=16)` — `P3_liveness_n16_ind` | `smtbmc z3 ind t=12` | `PASSED` | 54.011 | [orig_n16_liveness_ind.log](raw/n16_compositional/orig_n16_liveness_ind.log) |
| `original (CFG-P N=16)` — `cover_n16` | `smtbmc z3 cover t=42` | `PASSED` | 160.037 | `C2` крок 15, `C3` крок 24, `C1` крок 39; [orig_n16_cover.log](raw/n16_compositional/orig_n16_cover.log) |
| `M_bigdot_dual_pulse` | `smtbmc z3 bmc t=15` | `FAILED` | 38.488 | Порушено `P_bigdot_mutex_pulse`; [M_bigdot_dual_pulse.vcd](raw/n16_compositional/M_bigdot_dual_pulse.vcd) |
| `M_we_on_reject` | `smtbmc z3 bmc t=15` | `FAILED` | 23.797 | Порушено `P1a_no_we_on_reject`; [M_we_on_reject.vcd](raw/n16_compositional/M_we_on_reject.vcd) |
| `M_cascade_on_reject` | `smtbmc z3 bmc t=15` | `FAILED` | 31.109 | Порушено `P1d_no_cascade_on_reject`; [M_cascade_on_reject.vcd](raw/n16_compositional/M_cascade_on_reject.vcd) |
| `M_rank_violation_self_sub` | `smtbmc z3 bmc t=15` | `FAILED` | 17.544 | Порушено `P2_rank_step_n16`; [M_rank_violation_self_sub.vcd](raw/n16_compositional/M_rank_violation_self_sub.vcd) |

## 4. Перевірка гіпотези / критеріїв

| Критерій | Очікувано | Отримано | Висновок |
| :--- | :--- | :--- | :--- |
| `P1_n16_ind` (Велика Крапка `•` vs `¬` + `P1a..P1e` на `N=16`) | `PASSED` (необмежена $k$-індукція) | `PASSED` (`ind t=5` за 1.103 с) | Виконано |
| `P2_rank_step_n16` (монотонність $V=15-\text{cid}$ на `N=16`) | `PASSED` (необмежена $k$-індукція) | `PASSED` (`ind t=10` за 0.172 с) | Виконано |
| `P3_liveness_n16_ind` (8-тактовий крок з/без каскаду та 2 тригерами) | `PASSED` ($k$-індукція `t=12`) | `PASSED` (54.011 с) | Виконано (#237) |
| `cover_n16` (4 коміти до `cid=15`, `reject`, 2 тригери) | Усі 3 cover досягнуті | Досягнуто на кроках 15, 24, 39 (160.037 с) | Виконано |
| Негативний контроль на `N=16` (>= 4 мутантів) | `FAILED` + `.vcd` для кожного | 4/4 мутантів спіймано з `.vcd` | Виконано |

## 5. Відтворення

```bash
python3 Engineering/validation/kpol-cme/cme2-formal-227/scripts/run_cme2_formal.py
python3 Engineering/validation/kpol-cme/cme2-formal-227/scripts/run_cme2_formal_n16.py
python3 -m pytest -q Engineering/hw/tests/test_cme2_formal_227.py
```

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.2.0 | 2026-11-16 | Композиційна $k$-індукція на `NUM_CONCEPTS = 16`, взаємовиключність Великої Крапки, лема рангу Ляпунова, 4 мутанти на `N = 16`, закриття #237 і #242 |
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
