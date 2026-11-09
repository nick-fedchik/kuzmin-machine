# Звіт з експерименту AV-07: Мутаційне тестування тестбенчів RTL

* **Версія:** 2.0.0 (виправлена редакція після незалежного аудиту та усунення тавтологій у тестбенчах).
* **Review Report:** `AV-07_Mutation_Testing_Review_Report_UA.md` у `Review_Reports/`.
* **Дата виконання:** 2026-11-09 09:12:27 UTC
* **Виконавець:** агент Gemini. Рецензент: Copilot.
* **Мета:** Об'єктивна фізична перевірка чутливості та повноти верифікаційного набору тестбенчів у `02-engineering-hardware/tb/` шляхом внесення навмисних дефектів (мутантів) згідно з [Kuzmin-Machine-Experiment-Plan-Available-Hardware-UA.md](../PLAN.md) (§4.2, AV-07).
* **Правило об'єктивності:** «Кожен тест має провалитися на навмисно зламаній версії (мутанті). Перевірку, яка не ловить жодного мутанта, доказом не вважають» (§2 п. 7).
* **Підсумковий результат:** **Mutation Score = 100.0% (22/22 мутантів спіймано: 20 через асерти симуляції, 2 через таймаут, 0 через компіляцію; 0 вижило)**.
* **Перенесено з:** `drafts/KuzminMachine/04-verification-and-qa/Reports/AV-07_Mutation_Testing_Report_UA.md` @ `a4738bc` (2026-11-09)

---

## 1. Зведена таблиця чутливості тестбенчів

| Модуль RTL | Файл тестбенчу | Всього мутантів | Спіймано (Killed) | Вижило (Survived) | Чутливість (Score) | Статус |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `kpol_txn_gate` | `kpol_txn_gate_tb.sv` | 4 | 4 | 0 | **100.0%** | **PASS** |
| `km_euclid_core` | `km_euclid_core_tb.sv` | 3 | 3 | 0 | **100.0%** | **PASS** |
| `km_concept_bram` | `km_concept_bram_tb.sv` | 3 | 3 | 0 | **100.0%** | **PASS** |
| `km_cascade_arbiter_engine` | `km_cascade_arbiter_engine_tb.sv` | 3 | 3 | 0 | **100.0%** | **PASS** |
| `km_rcfc_engine` | `km_rcfc_engine_tb.sv` | 3 | 3 | 0 | **100.0%** | **PASS** |
| `km_stream_pipeline_engine` | `km_stream_pipeline_engine_tb.sv` | 3 | 3 | 0 | **100.0%** | **PASS** |
| `km_io_trigger_engine` | `km_io_trigger_engine_tb.sv` | 3 | 3 | 0 | **100.0%** | **PASS** |

---

## 2. Детальний реєстр мутацій за модулями

### Модуль `kpol_txn_gate` (`kpol_txn_gate_tb.sv`)

| ID мутанта | Опис дефекту | Стадія детекції | Результат |
| :--- | :--- | :--- | :--- |
| `MUT-GATE-01` | Ігнорування перевірки assumption_known / assumption_true (fail-open) | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |
| `MUT-GATE-02` | Ігнорування інваріанту (завжди істинний, invariant_ok = 1'b1) | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |
| `MUT-GATE-03` | Занулення сигналу committed_o при успішному переході | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |
| `MUT-GATE-04` | Відсутність оновлення state_o при коміті | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |

### Модуль `km_euclid_core` (`km_euclid_core_tb.sv`)

| ID мутанта | Опис дефекту | Стадія детекції | Результат |
| :--- | :--- | :--- | :--- |
| `MUT-EUCLID-01` | Інверсія умови порівняння (reg_a_q < reg_b_q замість reg_a_q > reg_b_q) | `TIMEOUT` | **KILLED** (Тест спіймав дефект) |
| `MUT-EUCLID-02` | Помилка операції (додавання замість віднімання: reg_a_q + reg_b_q) | `TIMEOUT` | **KILLED** (Тест спіймав дефект) |
| `MUT-EUCLID-03` | Занулення результату НСД (result_q <= 32'd0) | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |

### Модуль `km_concept_bram` (`km_concept_bram_tb.sv`)

| ID мутанта | Опис дефекту | Стадія детекції | Результат |
| :--- | :--- | :--- | :--- |
| `MUT-BRAM-01` | Інверсія адреси читання порту A (~a_addr_i) | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |
| `MUT-BRAM-02` | Залипання даних читання порту B у 0 | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |
| `MUT-BRAM-03` | Ігнорування запису порту A (вимкнення WE) | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |

### Модуль `km_cascade_arbiter_engine` (`km_cascade_arbiter_engine_tb.sv`)

| ID мутанта | Опис дефекту | Стадія детекції | Результат |
| :--- | :--- | :--- | :--- |
| `MUT-ARBITER-01` | Блокування інкременту Int8 переповнення (int8_val_q не змінюється) | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |
| `MUT-ARBITER-02` | Помилка кроку U8 переповнення (+2 замість +1) | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |
| `MUT-ARBITER-03` | Спотворення байтового запису (0xAA замість 0x55) | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |

### Модуль `km_rcfc_engine` (`km_rcfc_engine_tb.sv`)

| ID мутанта | Опис дефекту | Стадія детекції | Результат |
| :--- | :--- | :--- | :--- |
| `MUT-RCFC-01` | Підміна стану слота Fallback на IDLE | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |
| `MUT-RCFC-02` | Занулення лічильника черги avalanche_enqueued_q | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |
| `MUT-RCFC-03` | Занулення результату обчислення TC-01 | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |

### Модуль `km_stream_pipeline_engine` (`km_stream_pipeline_engine_tb.sv`)

| ID мутанта | Опис дефекту | Стадія детекції | Результат |
| :--- | :--- | :--- | :--- |
| `MUT-PIPE-01` | Занулення обчислення EMA фільтра (ema_calc = 18'sd0) | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |
| `MUT-PIPE-02` | Занулення диференційного керування (u_raw = 18'sd0) | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |
| `MUT-PIPE-03` | Занулення контрольної суми (accum_sum_q <= 32'd0) | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |

### Модуль `km_io_trigger_engine` (`km_io_trigger_engine_tb.sv`)

| ID мутанта | Опис дефекту | Стадія детекції | Результат |
| :--- | :--- | :--- | :--- |
| `MUT-TRIGGER-01` | Занулення детекції вхідної події (evt_detected_q <= 1'b0) | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |
| `MUT-TRIGGER-02` | Інверсія прапорця проходження тесту pass_o | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |
| `MUT-TRIGGER-03` | Спотворення лічильника подій (trigger_count_o <= 32'd0) | `SIMULATION_ASSERTION` | **KILLED** (Тест спіймав дефект) |

---

## 3. Висновки

1. **Усунення тавтологій та бутафорії:**
   - У `km_cascade_arbiter_engine.sv` усунено тавтологічну внутрішню перевірку виразу замість регістра; FSM переведено на перевірку зафіксованих фізичних регістрів `int8_val_q`, `u8_val_q`, `strb_word_q` у наступних тактах.
   - У тестбенчі `km_cascade_arbiter_engine_tb.sv` додано пряму верифікацію вихідних шин `result0[7:0] == 8'h80` та `result1 == 32'hAABB55DD`. Усі мутанти арбітра (`MUT-ARBITER-01..03`) успішно спіймано.
   - У `km_rcfc_engine_tb.sv` додано моніторинг стану `slot_state` для слота 0 під час обробки відмови. Мутант `MUT-RCFC-01` (підміна `SLOT_FALLBACK` на `SLOT_IDLE`) надійно детектується.
   - Виправлено помилки підстановки пробілів у `MUT-RCFC-03` та `MUT-PIPE-03`; кількість незастосованих мутантів дорівнює **0**.
2. **Підсумковий показник:**
   - Загальний бал мутаційного покриття становить **100.0%** (22/22).
   - Жоден мутант не залишився непоміченим (0 вижилих мутантів).
3. **Сирі дані:**
   - JSON-звіт: [`04-verification-and-qa/Reports/raw/av07_mutation_results.json`](raw/av07_mutation_results.json).
