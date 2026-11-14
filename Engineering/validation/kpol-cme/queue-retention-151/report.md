# Звіт #151: очікування без втрат і арбітраж ready/cascade черги B5

* **Версія:** 0.1.1
* **Дата:** 2026-11-13
* **Тип WP:** Report / Analysis
* **Issue:** [#151](https://github.com/nick-fedchik/kuzmin-machine/issues/151) (реалізація B5 v2 після [#135](https://github.com/nick-fedchik/kuzmin-machine/issues/135) та [#150](https://github.com/nick-fedchik/kuzmin-machine/issues/150)); PR — пов'язана публікація в цій Issue.
* **Виконавець:** GitHub Copilot CLI (модель: `gemini-4-carbon`).
* **Рецензент:** незалежна рецензія не проведена; автор не приймає власну роботу.
* **Код:** база `89618b447bf96b07a38eebd618627d4336991d62`; тести до виправлення `94654b00595a8833060c7521a432f675e04382b5` та `836bde7`, після виправлення RTL і специфікації — `d7ae62af96073777373ad46cbca602f0fb0c4fc7`. Повні SHA та SHA-256 дев'яти source-файлів — у `raw/`.
* **Хост:** Linux, `AORUS-5-SE`; фізична плата PYNQ-Z1 не підключалася, бітстрім не генерувався.
* **Критерії до виконання:** [#151](https://github.com/nick-fedchik/kuzmin-machine/issues/151), [`event-queue-ingress-specification.md` (v2.1.0)](../../../specifications/hw/event-queue-ingress-specification.md), [`KPOL-SYS-04`](../../../requirements/kpol.md).

## 1. Що не вдалося і обмеження

1. **Негативний контроль на базовому RTL та уточнення тестбенча до виправлення:**
   - На базовому RTL (`89618b4`) приймальні тести B5 v2 очікувано впали на всіх 6 перевірках ([`baseline-queue-01.log`](raw/baseline-queue-01.log), [`baseline-queue-02.log`](raw/baseline-queue-02.log), `exit_code=1`): у сценарії 5A штатне утримання `hw_trigger_valid_i=1` за `hw_trigger_ready_o=0` протягом 7 тактів хибно пораховано як 7 втрачених подій (`drop=7, ovf=1`), а в AXI-обгортці `kpol_bram_pipeline_axi.sv` під час однотактового `sw_trigger` сигнал `hw_trigger_ready_o` залишався рівним `1`, через що одночасний зовнішній тригер губився при формально активному `valid && ready`.
   - Під час початкової підготовки тестів виявлено й усунено дві технічні вади самих перевірок та сумісності інструментів:
     - у помічнику `prepare_cascade_collision` (`km_autonomous_sequencer_tb.sv`) на такті `ST_EVAL_GATE` шина BRAM утримує адресу останнього прочитаного слова дескриптора `Word 3` (`{cid, 2'b11}`), а не `Word 0` (`{cid, 2'b00}`); перевірку скориговано на `bram_b_addr[7:2] === 6'd0` у тестовому коміті `836bde7` до зміни RTL;
     - під час додавання мутаційного контролю `double-eval-full-cascade` з'ясувалося, що повторне перебування у `ST_EVAL_GATE` дає хибний `reject` (`rej_count + 1`, `events_processed + 1`), бо `committed_o` із `kpol_txn_gate_v2` є однотактовим імпульсом; до контрольних точок 5A–6 додано сувору перевірку `events_count` та `rej_count`;
     - Verilator 5.032 видавав внутрішню помилку `V3Delayed.cpp:937` при виклику функції всередині індексу масиву на лівій стороні `<=`; індексацію замінено на комбінаційні сигнали `rd_ptr_next1`, `wr_ptr_next1`, `wr_ptr_next2`, що чисто проходить Icarus Verilog 12, Verilator `-Wall` і Yosys `synth_xilinx`.
   - Проміжні повні прогони `pytest` ([`full-tests-01.log`](raw/full-tests-01.log), [`full-tests-02.log`](raw/full-tests-02.log)) зафіксували очікуване спрацювання `test_check_links.py` до фактичної появи всіх цільових файлів звіту й журналів на диску; після формування повного набору файлів фінальний прогін записано у новий файл [`full-tests-03.log`](raw/full-tests-03.log) без перезапису попередніх журналів.
   - Перший прогін `check_wp_documents.py` ([`structure-01.log`](raw/structure-01.log)) виявив зовнішній блокер CI у `main` (`9af9c08`): файл `Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-01/j501-hardware-interface.md` не мав заголовків `Історія версій` і `Абревіатури та глосарій`. Оформлено знахідку [#162](https://github.com/nick-fedchik/kuzmin-machine/issues/162) і виправлено конверт документа за правилом `PROJECT-MANUAL §2.2 п. 3`, після чого записано чистий прогін [`structure-02.log`](raw/structure-02.log).

2. **Межі чинності доказів:**
   - Результати отримано в потактовій RTL-симуляції (`iverilog`/`vvp`), статичному аналізі (`verilator --lint-only -Wall`) та логічному синтезі під Xilinx 7-Series (`yosys synth_xilinx -top kpol_bram_pipeline_axi`). Розміщення й трасування у Vivado (`Fmax`, таймінги, споживання енергії), формальний доказ властивостей секвенсера в SymbiYosys та фізичні прогони HIL на PYNQ-Z1 у межах #151 не виконувалися.
   - Фізичний вхід `ja1 | btn[0]` у `kpol_bram_pipeline_pynq_z1_top.v` формує однотактовий фронт `ext_hw_trig_pulse` без зовнішнього зворотного сигналу `ready` та без вхідного skid-буфера, тому залишається **фізично незупинним джерелом**: за зайнятого входу (`ready=0`) подія не утримується джерелом, а явно обліковується у `fifo_overflow_o` та `events_dropped_count_o` без псування черги чи BRAM.
   - Глибина за замовчуванням `QUEUE_DEPTH = 16` збережена параметризованою (`4, 8, 16, 32`); вибір глибини під конкретний промисловий профіль навантаження вимагає окремого розрахунку інтенсивності подій.

## 2. Метод

1. **Реалізована архітектура черги (`km_autonomous_sequencer.sv` та `kpol_bram_pipeline_axi.sv`):**
   - **Арбітражно-узгоджений `hw_trigger_ready_o`:** обчислюється комбінаційно без залежності від `hw_trigger_valid_i` (відсутня комбінаційна петля `valid -> ready`):
     `hw_trigger_ready_o = !cascade_pending_valid_q && ((fifo_count_q + (cascade_req ? 2 : 1)) <= QUEUE_DEPTH)`,
     а в AXI-обгортці `kpol_bram_pipeline_axi.sv` додатково маскується `&& !sw_trigger`, щоб під час однотактового програмного запуску зовнішній тригер утримувався до наступного такту.
   - **Однослотовий буфер full-каскаду (`cascade_pending_{valid,cid,param}_q`):** якщо каскад виникає на такті `ST_EVAL_GATE` при `fifo_count_q == QUEUE_DEPTH`, поточна транзакція виконує одиничний запис `W0` у BRAM і переходить у `ST_IDLE` (повторний `commit` неможливий), а каскад зберігається в `cascade_pending_*_q` при `busy_o == 1` та `hw_trigger_ready_o == 0`. На наступному ж такті `ST_IDLE` умова `dequeue_req = (state_q == ST_IDLE) && (fifo_count_q > 0)` звільняє слот і переносить `cascade_pending` у FIFO без зупинки автомата-споживача.
   - **Відокремлення штатного очікування від втрат незупинного джерела (`stalled_ext_q`, `ext_sw_stalled_q`):** утримання `valid=1` зі стабільними `{cid, param}` за `ready=0` дає `0` втрат (`fifo_overflow_o == 0`, `events_dropped_count_o == 0`). Лише зняття `valid` до появи `ready == 1` або зміна `{cid, param}` під час очікування фіксує фактичну втрату (`fifo_overflow_o <= 1`, `events_dropped_count_o += 1`).

2. **Сценарії верифікації та негативні контролі:**
   - У `km_autonomous_sequencer_tb.sv` перевірено сценарії **5A** (`full/empty`, утримання `param = 0`), **5B** (колізія за 2 вільних слотів), **5C** (колізія за 1 вільного слота з від'ємним `param = -42`, `fifo_full=0` і `ready=0`), **5D** (`full-каскад` у `cascade_pending_*_q` та одночасні `cascade_pending + external + dequeue`), **5E** (керована пачка `3 * QUEUE_DEPTH` із каскадами) та **6** (три навмисні порушення утримання незупинним джерелом). На кожному кроці звіряються `W0`, незмінність `W1..W3`, `events_processed_count`, `committed_count`, `rejected_count`, лічильник записів порту B BRAM та відсутність записів поза `W0`.
   - У `test_kpol_bram_pipeline.py` додано:
     1) параметризований прогін `QUEUE_DEPTH` $\in \{4, 8, 16, 32\}$;
     2) наскрізний AXI-тест `+hw_burst` (пачка з 40 зовнішніх подій із каскадом `CID 0 -> CID 1`, `param = 0`, `param = -7` та одночасним зіткненням `sw_trigger + ext_hw_trigger`);
     3) **6 постійних мутаційних негативних контролів** (`SEQUENCER_MUTANTS`): ігнорування резерву каскаду в `ready_o`, підрахунок `stall` як втрати, подвійне додавання при прийнятті, втрата full-каскаду, повторне оцінювання у `ST_EVAL_GATE` на full-каскаді та повторний запис у BRAM при розвантаженні `cascade_pending`.

## 3. Результати

| Прогін | Факт / raw | Межа |
|---|---|---|
| До виправлення RTL (коміти тестів `94654b0`, `836bde7`) | 6 failed, 142 deselected, `exit_code=1`; [`baseline-queue-01.log`](raw/baseline-queue-01.log), [`baseline-queue-02.log`](raw/baseline-queue-02.log). | Незмінений базовий RTL `89618b4`: викрито `drop=7, ovf=1` під `stall` та `ready=1` під час `sw_trigger`. |
| Цільові тести черги, AXI burst і 6 мутантів (`d7ae62a`) | 12 passed, `exit_code=0`; [`queue-retention-01.log`](raw/queue-retention-01.log). | Охоплює `QUEUE_DEPTH=4,8,16,32`, AXI `+hw_burst` і падіння всіх 6 мутантів RTL. |
| Проміжні повні `pytest` до появи всіх raw-файлів | 1 failed (`test_check_links.py`), 318 passed; [`full-tests-01.log`](raw/full-tests-01.log), [`full-tests-02.log`](raw/full-tests-02.log). | Збережено без змін: фіксують перевірку посилань до запису всіх цільових файлів на диск. |
| Фінальний повний `pytest` | 319 passed, 300 subtests passed, `exit_code=0`; [`full-tests-03.log`](raw/full-tests-03.log). | Регресії всього репозиторію (SW + HW + інструменти NG), не HIL. |
| Open EDA flow (`iverilog`, `verilator -Wall`, `yosys synth_xilinx`) | 154 passed; Verilator lint завершився **без помилок** (`exit_code=0`), але **з непослідовними попередженнями** (`PINCONNECTEMPTY`, `UNUSEDPARAM`, `UNUSEDSIGNAL`) та Yosys resize/replace warnings — «чистий» стосується відсутності помилок і провалів, не відсутності попереджень; успішний синтез XC7; [`open-flow-01.log`](raw/open-flow-01.log). | Синтезовано `kpol_bram_pipeline_axi`: 629 FDCE, 956 LUT, `check` — 0 помилок; без Vivado P&R і плати. |
| Перевірка посилань, WP-документів та індексу | До виправлення #162: [`structure-01.log`](raw/structure-01.log) (`exit_code=1` на `j501-hardware-interface.md`); після: `exit_code=0`, 0 битих посилань, 0 помилок `check_wp_documents.py` у [`structure-02.log`](raw/structure-02.log). | Структурна валідність і незмінність імпортованих джерел, не незалежна рецензія. |

## 4. Перевірка критеріїв

| Критерій (#151 / B5 v2.1) | Очікувано | Отримано / висновок |
|---|---|---|
| 1. Специфікація тактового контракту (`REQ-SYS-013`, `REQ-HW-014`) | Однозначні правила `valid/ready`, утримання при повній черзі та резервування слота каскадом. | Оформлено у [`event-queue-ingress-specification.md` v2.1.0](../../../specifications/hw/event-queue-ingress-specification.md) та узгоджено з RTL. |
| 2. Резервування слота каскадом і `sw_trigger` (`REQ-HW-014`) | При 1 вільному слоті та каскаді (або при `sw_trigger` в AXI) `ready=0` до фронту; утримана подія не губиться й не дублюється. | Підтверджено у сценаріях 5B, 5C (`param=-42`), AXI `+hw_burst` та мутанті `ready-ignores-cascade-slot`. |
| 3. Відсутність дедлоків і повторного `commit` при full-каскаді (`REQ-SYS-014`) | Повна черга не зупиняє споживача, каскад зберігається в `cascade_pending_*_q` з рівно одним `commit`. | Підтверджено у сценарії 5D та мутантах `drop-full-cascade`, `double-eval-full-cascade`, `duplicate-bram-write-pending`. |
| 4. Межі черги, параметризація та відокремлення незупинного джерела (`REQ-HW-015`, `REQ-HW-016`) | Перевірено `full/empty`, `param=0`, пачки `3*QUEUE_DEPTH` на глибинах `4,8,16,32` і точний облік порушень утримання. | Підтверджено у сценаріях 5A (`param=0`), 5E, 6 (`drop=3, ovf=1`) на всіх 4 глибинах без жодного псування `W1..W3`. |
| 5. Відтворюваний негативний контроль і повні регресії | Падіння до виправлення, зелені `pytest`, `check_links.py`, `check_wp_documents.py`, `run_open_flow.sh`. | Baseline впав на `89618b4`; після `d7ae62a` усі 319 тестів, лінтери та синтез пройшли з `exit_code=0`. |

## 5. Відтворення

З кореня worktree:

```bash
python3 -m pytest -v -p no:cacheprovider Engineering/hw/tests/test_testbenches.py Engineering/hw/tests/test_kpol_bram_pipeline.py -k "autonomous_sequencer or queue_retention or axi_hw_trigger" -rP
python3 -m pytest -q -p no:cacheprovider
bash Engineering/hw/scripts/run_open_flow.sh
KM_DRAFTS_REPO=/path/to/drafts python3 Project/tools/check_links.py
python3 Project/tools/check_wp_documents.py
```

Для відтворення падіння до виправлення достатньо перейти на тестовий коміт `836bde7` (де production RTL ідентичний `89618b4`) і запустити першу команду; крім того, 6 постійних мутаційних контролів `test_sequencer_queue_retention_mutant_controls` автоматично перевіряють чутливість тестбенча під час кожного прогону `pytest`.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.1.1 | 2026-11-14 | #179 (рецензія PR #163 F1): уточнено формулювання «чистий Verilator lint» — розмежовано «без помилок» (`exit_code=0`) і «з неблокуючими попередженнями» (`PINCONNECTEMPTY`/`UNUSEDPARAM`/`UNUSEDSIGNAL`, Yosys resize/replace), дані `raw/open-flow-01.log` без змін. |
| 0.1.0 | 2026-11-13 | Первинний звіт верифікації B5 v2.1 (#151): очікування без втрат, арбітраж `ready/cascade`, `cascade_pending_*_q`, AXI `+hw_burst`, 6 мутантів та відкритий EDA-потік. |

## Абревіатури та глосарій

FIFO — черга «першим прийшов — першим вийшов»; CME — Concept Micro-Engine;
BRAM — блокова пам'ять FPGA; AXI / MMIO — шинний і регістровий інтерфейс PS↔PL;
RTL — опис цифрової схеми на рівні регістрових передач; HIL — перевірка на фізичному обладнанні;
WP — результат роботи (Work Product); raw — незмінний первинний журнал конкретного прогону.
