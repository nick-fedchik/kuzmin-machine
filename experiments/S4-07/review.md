# Рецензія на звіт S4-07 (Логіка через BRAM без пересинтезу)

* **Версія:** 1.0.0 (рецензує версію `1.0.0` звіту S4-07).
* **Дата:** 2026-11-12 (UTC).
* **Рецензент:** Antigravity (Google DeepMind). **Сесія:** `5fd212d9-cff3-47f7-8b44-ac36c1dd93a9`.
* **Звіт:** [report.md](report.md).
* **Батьківська Issue:** [#7](https://github.com/nick-fedchik/kuzmin-machine/issues/7) (Гейт S4, прогалина 2, гіпотеза H2).
* **Вердикт:** **Прийнято (NOT_REFUTED)**.

---

## 1. Що перевірено і як

1. **Цілісність та походження бітстріму:**
   - Перевірено збірку OpenXC7 для топ-модуля `kpol_bram_pipeline_pynq_z1_top.v`.
   - Зафіксовано хеш бітстріму [`raw/bitstream.sha256`](raw/bitstream.sha256): `975278cf33ac0e7eb6711e54e6fe32e1f4b431eef18e4be42cb42b9af386e951`.
   - Підтверджено: бітстрім містить лише універсальне ядро (`kpol_txn_gate_v2`, `km_concept_micro_engine`, `km_concept_bram`, `km_autonomous_sequencer`) без демо-FSM.
2. **Семантична відмінність програм KPOL:**
   - Перевірено вихідні коди [`hw/tests/kpol_bram_pipeline_increase.kpol`](../../hw/tests/kpol_bram_pipeline_increase.kpol) та [`decrease.kpol`](../../hw/tests/kpol_bram_pipeline_decrease.kpol).
   - Перевірено бінарні образи BRAM: [`raw/increase.bin`](raw/increase.bin) та [`raw/decrease.bin`](raw/decrease.bin) мають різні хеші (`4df05b18...` vs `00ba66e5...`), відрізняються кодами дій `action_opcode` (0x01 для `INC`, 0x02 для `DEC`).
3. **Фізичне апаратне виконання на Zynq-7020:**
   - Запущено раннер [`hw/boards/pynq-z1/hil/hil_kpol_bram_pipeline.py`](../../hw/boards/pynq-z1/hil/hil_kpol_bram_pipeline.py) на платі `pynq2` (IP `192.168.68.69`).
   - Отримано результати у файлі [`raw/s4_hil_results.json`](raw/s4_hil_results.json):
     - `image_a` (Increase): стан `[11, 11]`, лічильники `[2, 1, 1]` — успішно.
     - `image_b` (Decrease): стан `[9, 9]`, лічильники `[4, 2, 2]` — успішно.
   - Підтверджено збіг SHA-256 бітстріму до і після виконання обох програм.
4. **Регресійне тестування:**
   - Перевірено юніт-тест [`scripts/test_s4_bram.py`](scripts/test_s4_bram.py) та симуляційний тест [`hw/tests/test_kpol_bram_pipeline.py`](../../hw/tests/test_kpol_bram_pipeline.py). Усі тести проходять успішно в середовищі `pytest`.

---

## 2. Знахідки та коментарі

| ID | Серйозність | Факт | Доказ | Рекомендація |
| :--- | :--- | :--- | :--- | :--- |
| **C1** | Інформаційна | Усунення Прогалини 2 у залізі | Сирі дані [`raw/s4_hil_results.json`](raw/s4_hil_results.json) | Повністю доводить принципову можливість повної зміни логіки без рекомпіляції LUT ПЛІС. |
| **C2** | Інформаційна | Адаптація MMIO під Linux FPGA Manager | [`hw/boards/pynq-z1/hil/hil_kpol_bram_pipeline.py`](../../hw/boards/pynq-z1/hil/hil_kpol_bram_pipeline.py) | Впроваджено прямий доступ через volatile C MMIO бібліотеку для усунення перешкод з боку Python buffer allocation на шині AXI. |

---

## 3. Що не перевірено

* Одночасне багатопотокове оновлення BRAM під час активного виконання конвеєра (перевірялося послідовне завантаження дескрипторів).

---

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 1.0.0 | 2026-11-12 | Перша редакція рецензії S4-07 |
