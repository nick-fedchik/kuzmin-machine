# Рецензія на інтеграцію фізичного тригера BRAM-конвеєра та політику черги FIFO (HWE.1..HWE.3)

* **Тип Work Product:** `Report` (підтип `Review`)
* **Версія:** 1.0.0 (рецензує версію `1.0.0` документа [`report-top-pmod-integration.md`](../report-top-pmod-integration.md) та пов'язані RTL/XDC/тестбенчі)
* **Дата:** 2026-11-12
* **Рецензент:** Antigravity (agy, Lead Systems & Hardware Engineer / Lead Assessor). **Конфлікт інтересів:** оцінювання виконано згідно з правилами незалежного аудиту ASPICE SUP.1 / VDA Scope.
* **Об'єкти перевірки:**
  - [`hw/boards/pynq-z1/report-top-pmod-integration.md`](../report-top-pmod-integration.md)
  - [`hw/boards/pynq-z1/kpol_bram_pipeline_pynq_z1_top.v`](../kpol_bram_pipeline_pynq_z1_top.v)
  - [`hw/boards/pynq-z1/kpol_bram_pipeline.xdc`](../kpol_bram_pipeline.xdc)
  - [`hw/rtl/core/km_autonomous_sequencer.sv`](../../../rtl/core/km_autonomous_sequencer.sv)
  - [`hw/rtl/bus/kpol_bram_pipeline_axi.sv`](../../../rtl/bus/kpol_bram_pipeline_axi.sv)
  - [`hw/tb/km_autonomous_sequencer_tb.sv`](../../../tb/km_autonomous_sequencer_tb.sv)
  - [`hw/tests/kpol_bram_pipeline_axi_tb.sv`](../../../tests/kpol_bram_pipeline_axi_tb.sv)
* **Вердикт:** **Прийнято (Pass)**. Усі вимоги рішень B2 та B5 реалізовано в RTL, підтверджено синтезом Yosys та повнофункціональними тестбенчами.

---

## 1. Що перевірено і як

1. **Відповідність нормативним архітектурним рішенням B2 та B5:**
   - **B2 (Інтеграція зовнішнього тригера):** перевірено наявність 2-ступеневого тригерного синхронізатора CDC (`REQ-HW-011`) та детектора фронту для лінії `ja1` і кнопки `btn[0]`. Перевірено формувачі імпульсів для виходів `ja2` (Commit) та `ja3` (Reject) тривалістю 10 тактів ($100\text{ нс}$), узгоджені з вимірювальним скриптом Raspberry Pi Pico (період $8\text{ нс}$).
   - **B5 (Політика черги FIFO):** перевірено параметризацію `QUEUE_DEPTH = 16`, роботу сигналів зворотного тиску `hw_trigger_ready_o`, немовчазне відкидання подій через прапорець `fifo_overflow_o` та лічильник `events_dropped_count_o`, а також абсолютний пріоритет внутрішніх каскадів підписників над зовнішніми тригерами (`REQ-SYS-014`).
2. **Перевірка синтезу:**
   - Виконано синтез топ-модуля `kpol_bram_pipeline_pynq_z1_top` через Yosys (`synth_xilinx -flatten -abc9 -arch xc7`). Жодних структурних або синтаксичних помилок не виявлено (`Found and reported 0 problems`). Оціночне використання логіки складає 1597 LC (< 3% XC7Z020).
3. **Цілісність XDC обмежень:**
   - Звірено розташування пінів `ja1`..`ja4`, `btn[0]`, `sw[1:0]`, `led[3:0]` з офіційним керівництвом PYNQ-Z1 Reference Manual та монтажною інструкцією [`hil-bench-wiring-guide.md`](../hil-bench-wiring-guide.md). Конфліктів стандартів введення/виведення (`LVCMOS33`) немає.
4. **Регресійне тестування:**
   - Усі 193 тести в системному наборі `pytest` виконано успішно.
   - Перевірено відносні посилання за допомогою `tools/check_links.py`: 0 broken links.

---

## 2. Знахідки

| ID | Серйозність | Факт | Доказ | Рекомендація |
| :--- | :--- | :--- | :--- | :--- |
| — | — | Знахідок блокувального чи суттєвого характеру не виявлено. | `report-top-pmod-integration.md` | Готово до злиття в `main` та генерації бітстріму. |

---

## 3. Що не перевірено

- Фізичне завантаження згенерованого бітстріму `.bit` у кристалічну пам'ять реальної плати PYNQ-Z1 та фізичне зчитування ліній PMOD JA осцилографом / платою Pico буде проведено на наступному етапі HIL-випробувань на зібраному стенді.

---

## Історія версій

| Версія | Дата | Автор | Зміни |
| :--- | :--- | :--- | :--- |
| **1.0.0** | 2026-11-12 | Antigravity (agy) | Первинна незалежна рецензія на інтеграцію фізичного тригера та черги FIFO (B2/B5). |
