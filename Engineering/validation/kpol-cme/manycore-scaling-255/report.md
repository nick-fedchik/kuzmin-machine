# Звіт MANYCORE-SCALING-255: Багатоядерне масштабування CFG-P (N = 1, 2, 4, 8), двоступенева конвеєризація міжбанкового комутатора (`PIPELINE_STAGES = 2`), межа анти-дедлоку черг та після-трасувальна оцінка F_max і LUT

* **Версія:** 0.2.0
* **Дата:** 2026-11-17
* **Тип WP:** Report
* **Issue:** [#255](https://github.com/nick-fedchik/kuzmin-machine/issues/255), [#263](https://github.com/nick-fedchik/kuzmin-machine/issues/263). **PR:** [#262](https://github.com/nick-fedchik/kuzmin-machine/pull/262) (`0.1.0`), поточне розширення у гілці `exp/263-pipelined-crossbar-100mhz`.
* **Виконавець:** GitHub Copilot CLI (`gemini-4-argon`); незалежна рецензія очікується за правилом `AGENTS.md §2.5` (`claude-sonnet-5.5`).
* **Коміт, на якому виконано:** `467cd4e` (`origin/main`). **Хост / плата:** `AORUS-5-SE`, `Linux 7.0.0-42-generic x86_64` (`OpenXC7 Yosys 0.69`, `nextpnr-himbaechel 1.0.0-41-g3e5c2cdd` з базою кристала `xc7z020clg400-1`, системні `Yosys 0.52`, `Z3 4.13.3`, `Verilator 5.032`, `Icarus Verilog 12.0`); підключення до фізичної плати `PYNQ-Z1` не виконувалося. **Бітстрім (SHA-256):** не записувався на залізо (`evidence_kind: openxc7_place_and_route_sta`, `not_physical_hil: true`).
* **Критерії успіху (зафіксовано до виконання):** розділ 2–3 в [#255](https://github.com/nick-fedchik/kuzmin-machine/issues/255) та [#263](https://github.com/nick-fedchik/kuzmin-machine/issues/263):
  1. Параметризований RTL кластера `km_manycore_cluster.sv` та комутатора `km_event_crossbar.sv` (`N = 1, 2, 4, 8`, `PIPELINE_STAGES = 1` за замовчуванням для зворотної сумісності з `#255` та `PIPELINE_STAGES = 2` для двоступеневого конвеєрного кросбара) без модифікації базових модулів одноядерного `CFG-P`;
  2. Формальна SMT-верифікація на `N = 2` для `PIPELINE_STAGES = 1` і `PIPELINE_STAGES = 2` (`MC1_event_conservation`, `MC2_rr_fairness`, `MC3_dag_progress`), конструктивна фіксація межі циклічного дедлока `Bank 0 <-> Bank 1` (`MC4_cyclic_deadlock_witness`) та `4` мутантні контролі з `.vcd` (включно з `M4_stage2_skid_overwrite`);
  3. Фізичне трасування (Place & Route) та статичний аналіз таймінгу (STA) у `OpenXC7` для `PIPELINE_STAGES = 1` (`N = 1, 2, 4, 8`) та `PIPELINE_STAGES = 2` (`N = 2, 4, 8`) на `xc7z020clg400-1` зі збереженням усіх блоків пам'яті (`RAMB36E1 == N`) і кількісним порівнянням `1-stage` проти `2-stage`;
  4. Потактове профілювання трафіку (`local`, `uniform`, `hotspot`, `many-to-one`, по `1 024` первинні події) для `N = 4` та `N = 8` у режимах `PIPELINE_STAGES = 1` та `PIPELINE_STAGES = 2` при `0` втрачених прийнятих подій.

---

## 1. Що не вдалося і обмеження

1. **Відсутність натурного запуску на платі `PYNQ-Z1` та вимірювань фізичного енергоспоживання (`HIL`):**
   * Усі результати отримані методами формальної SMT-верифікації (`yosys-smtbmc + Z3`), потактової RTL-симуляції (`Icarus Verilog`) та повного фізичного розміщення, трасування й статичного аналізу таймінгу `OpenXC7` (`yosys 0.69` + `nextpnr-himbaechel`) для кристала `xc7z020clg400-1`. Завантаження бітстріму на живу плату `PYNQ-Z1` та вимірювання споживаної потужності або температури кристала не проводилися (`not_physical_hil: true`).
2. **Часткове недосягнення порога `100.0 МГц` для `N = 8` у режимі `PIPELINE_STAGES = 2` (`91.89 МГц`, дефіцит `8.11 МГц`):**
   * У базовому одноступеневому режимі (`PIPELINE_STAGES = 1`, `#255`) поріг `100.0 МГц` виконувався лише для `N = 1` (`113.92 МГц`), тоді як при зростанні `N` частота знижувалася до `95.21 МГц` (`N = 2`, `10.503 нс`), `78.11 МГц` (`N = 4`, `12.803 нс`) та `50.81 МГц` (`N = 8`, `19.680 нс`).
   * Впровадження двоступеневої конвеєризації (`PIPELINE_STAGES = 2`, `#263`) повністю закрило цільовий таймінг `>= 100.0 МГц` для `N = 2` (`F_max = 133.89 МГц`, `7.469 нс`, `PASS @ 100 МГц`) і `N = 4` (`F_max = 103.73 МГц`, `9.640 нс`, `PASS @ 100 МГц`) та підвищило частоту 8-ядерного кластера у `1.81` раза — з `50.81 МГц` (`19.680 нс`) до `91.89 МГц` (`10.882 нс`, приріст `+41.08 МГц` або `+80.85%`). Водночас для `N = 8` при повнозв'язній топології `16 x 8` на кристалі `xc7z020clg400-1` залишається від'ємний запас `-882 пс` відносно періоду `10.000 нс` через фізичну довжину міжтайлових трас (`8.48 нс` маршрутизації з `10.88 нс` повного періоду); подолання порога `100.0 МГц` при `N >= 8` потребує ієрархічної кластеризації (2 локальні квадранти по 4 банки з міжквадрантним мостом) або 3-ступеневого конвеєра.
3. **Додаткова латентність конвеєрного комутатора при `PIPELINE_STAGES = 2` (`+1` такт на кожен міжбанковий перехід):**
   * Додавання проміжного регістрового ступеня Stage 1 збільшує мінімальну затримку проходження через комутатор із `1` до `2` тактів: на симуляції профілів трафіку середня потактова латентність транзакції зростає на `+5.02 .. +39.49` такту (`N = 8`), проте за рахунок підвищення тактової частоти з `78.11` до `103.73 МГц` (`N = 4`) та з `50.81` до `91.89 МГц` (`N = 8`) абсолютна пропускна здатність `MCPS @ F_max(N)` зростає на всіх чотирьох профілях на `+32.7%` (`N = 4`) та `+80.8% .. +82.6%` (`N = 8`).
4. **Формально доведена границя взаємного блокування (*deadlock*) на циклічних міжбанкових графах без віртуальних каналів:**
   * Конструктивний SMT-свідок [`MC4_cyclic_deadlock_witness.vcd`](raw/MC4_cyclic_deadlock_witness.vcd) (крок `20` від скидання) та індуктивна властивість `MC4_deadlock_permanence` показують, що при взаємній циклічній підписці `Bank 0 <-> Bank 1` і одночасному заповненні скінченних черг обох банків (`fifo_count == QUEUE_DEPTH`), конвеєрних зрізів кросбара та вихідних буферів у стані очікування `ST_WAIT_TX` виникає замкнений цикл залежності каналів (`rx_ready == 0, tx_ready == 0`), з якого кластер не виходить самостійно.
5. **Насичення пропускної здатності на незбалансованих профілях (`hotspot`, `many-to-one`) і параметричний масштаб SMT:**
   * Формальна SMT-верифікація `Z3` виконана на масштабованій конфігурації `NUM_CORES = 2, QUEUE_DEPTH = 4, NUM_CONCEPTS = 4` (`ADDR_WIDTH = 4`) для обох режимів `PIPELINE_STAGES = 1` та `PIPELINE_STAGES = 2`.
   * На профілях трафіку з концентрацією потоку на одному цільовому банку (`Bank N-1`) пропускна здатність усього кластера обмежується 8-тактовим циклом цього вузла-приймача: при `N = 8` і `PIPELINE_STAGES = 2` номінальна пропускна здатність @ `100 МГц` становить `16.942 MCPS` для `hotspot` і `23.429 MCPS` для `many-to-one` (проти `99.854 MCPS` на локальному профілі `local`).

---

## 2. Метод та архітектура

1. **Аналіз критичного шляху одноступеневого комутатора (`PIPELINE_STAGES = 1`, `#255`):**
   * Детальний розбір після-трасувальних звітів `nextpnr-himbaechel` ([`nextpnr_pnr_n2.log`](raw/nextpnr_pnr_n2.log), [`nextpnr_pnr_n4.log`](raw/nextpnr_pnr_n4.log), [`nextpnr_pnr_n8.log`](raw/nextpnr_pnr_n8.log)) виявив три послідовно з'єднані комбінаційні каскади, що формували критичний шлях `12.803 нс` (`N = 4`) та `19.680 нс` (`N = 8`):
     1. У вузлі-приймачі `km_cluster_node[j]` сигнал готовності черги `rx_ready_o` обчислювався комбінаційно через декодування `desc_w3_q -> sub_fire_w -> local_cascade_req` та 2-слайсовий суматор-компаратор `CARRY4` (`({1'b0, fifo_count_q} + rx_slots_needed) <= DEPTH_CNT`, комірка `$auto$alumacc` у `km_manycore_cluster.sv:217`) і безпосередньо надходив на вхід `dst_ready_i[j]` кросбара.
     2. У комутаторі `km_event_crossbar` при `PIPELINE_STAGES = 1` сигнал `dst_ready_i[j]` комбінаційно керував `pipe_can_accept_w = !pipe_valid_q[j] || dst_ready_i[j]` та `grant_fire_w` (`dut_cluster.xbar_inst.bank_accept_pulse[7]`, `13.90 нс` при `N = 8`), а цикл пріоритетного арбітражу `for (s = 0; s < 2*N; s++) if (!req_any && req_eff[s])` синтезувався у 16-рівневий послідовний ланцюжок LUT разом із `2N : 1` 38-бітним мультиплексором даних і 32-бітними суматорами телеметрії.
     3. Зворотний сигнал гранту `src_ready[s]` (`node_tx_ready`) повертався через кристал у вузол-відправник `km_cluster_node[s]`, де через `tx_buf_free_w = !tx_valid_q || tx_ready_i` керував мультиплексором станів `state_q` та дозволом тактування `.CE` 42-бітних регістрів `tx_*_q` / `hold_tx_*_q` (`19.680 нс` при `N = 8`).
2. **Двоступенева конвеєризація [`km_event_crossbar.sv`](../../../hw/rtl/cluster/km_event_crossbar.sv) та [`km_manycore_cluster.sv`](../../../hw/rtl/cluster/km_manycore_cluster.sv) (`PIPELINE_STAGES = 2`, `#263`):**
   * Параметр `parameter int PIPELINE_STAGES = 1` додано у `km_event_crossbar`, `km_cluster_node`, `km_manycore_cluster`, `km_manycore_synth_top` і `km_manycore_cluster_tb`. При `PIPELINE_STAGES == 1` виконується оригінальна гілка `#255` зі 100% збереженням потактової поведінки.
   * При `PIPELINE_STAGES == 2` на кожному цільовому банку `j` реалізовано двоступеневий конвеєр із двослотовим skid-буфером без комбінаційних петель `dst_ready_i -> src_ready`:
     * **Stage 1 (`s1_valid_q[j]`, `s1_cid_q`, `s1_param_q`, ієрархічний `4x4` round-robin арбітр):** джерела групуються по `4` входи (`gen_grp4`), де паралельно обчислюються локальні переможці груп `grp_ofs[gk]` та попередній `4:1` зріз даних `grp_cid[gk]`, `grp_param[gk]`, після чого глобальний арбітр груп обирає `win_grp`. Умова прийому в Stage 1 визначається виключно локальними тригерами `s1_can_accept_w = !s1_valid_q[j] || !pipe_valid_q[j]`, що повністю розриває комбінаційний зворотний зв'язок від `dst_ready_i[j]` до `int_ready_o` / `ext_ready_o`.
     * **Stage 2 (`pipe_valid_q[j]`, `pipe_cid_q[j]`, `pipe_param_q[j]`):** пересилає пакет із Stage 1 у вихідний регістр банку при `pipe_can_accept_w = !pipe_valid_q[j] || dst_ready_i[j]`. Якщо `pipe_valid_q[j] == 1` і цільовий банк виставляє `dst_ready_i[j] == 0`, пакет утримується у Stage 1 (`s1_valid_q[j] == 1`) як у skid-регістрі без втрати чи перезапису даних.
     * **Розрив комбінаційних шляхів у вузлах та телеметрії кластера при `PIPELINE_STAGES == 2`:** у `km_cluster_node` прапорці валідності та локальності підписника (`sub_valid_q`, `sub_local_q`) попередньо фіксуються на такті `ST_WAIT_GATE`, готовність вхідної черги `rx_ready_p2_w = !cascade_pending_valid_q && (state_q != ST_EVAL_GATE) && (fifo_count_q < DEPTH_CNT)` обчислюється в `1 LUT6` без ланцюжка `CARRY4` і розділяє в часі запис локального каскаду та зовнішнього пакета (усуваючи подвійний порт запису `wr_ptr_next1` на `608` тригерах FIFO кожного ядра), а умова `tx_buf_free_w = !tx_valid_q` і двоступеневе дерево регістрів суматорів телеметрії (`pair_*_q -> tot_*_q`) прибирають між'ядерні комбінаційні каскади.
3. **Інструментальні маршрути перевірки:**
   * **Статичний лінт:** `Verilator 5.032 --lint-only -Wall` для `NUM_CORES = 1, 2, 4, 8` при `PIPELINE_STAGES = 1` та `PIPELINE_STAGES = 2`.
   * **Формальний SMT-доказ (`N = 2`, `PIPELINE_STAGES = 1, 2`):** обгортка [`manycore_formal_props.sv`](scripts/manycore_formal_props.sv) та раннер [`run_manycore_formal.py`](scripts/run_manycore_formal.py) (`Yosys 0.52` + `yosys-smtbmc` + `Z3 4.13.3`, `0` операторів `assume` у блоці `FORMAL_INDUCTION`, `4` мутанти `M1..M4`).
   * **Синтез, Place & Route і STA (`OpenXC7` на `xc7z020clg400-1`):** обгортка [`km_manycore_synth_top.sv`](scripts/km_manycore_synth_top.sv), обмеження [`km_manycore_synth.xdc`](scripts/km_manycore_synth.xdc) та скрипт [`run_manycore_pnr.py`](scripts/run_manycore_pnr.py) (`--pipeline-stages 1` для `N = 1, 2, 4, 8` та `--pipeline-stages 2` для `N = 2, 4, 8`).
   * **Профілювання трафіку (`N = 4, 8`, `PIPELINE_STAGES = 1, 2`):** тестбенч [`km_manycore_cluster_tb.sv`](../../../hw/tests/km_manycore_cluster_tb.sv) та раннер [`run_manycore_traffic.py`](scripts/run_manycore_traffic.py) (`Icarus Verilog 12.0`, по `1 024` первинні події на профіль).

---

## 3. Результати

### 3.1. Формальна SMT-верифікація на `N = 2` (`yosys-smtbmc + Z3 4.13.3`) для `PIPELINE_STAGES = 1, 2` та мутантні тести `M1..M4`

Первинні дані: [`manycore_formal_results.csv`](raw/manycore_formal_results.csv), [`manycore_formal_provenance.json`](raw/manycore_formal_provenance.json), журнали `raw/formal_*.log`, `raw/M*.log`, свідок дедлока [`MC4_cyclic_deadlock_witness.vcd`](raw/MC4_cyclic_deadlock_witness.vcd) та контрприклади мутантів [`M1_fixed_priority_starvation.vcd`](raw/M1_fixed_priority_starvation.vcd), [`M2_drop_crossbar_backpressure.vcd`](raw/M2_drop_crossbar_backpressure.vcd), [`M3_duplicate_broadcast.vcd`](raw/M3_duplicate_broadcast.vcd), [`M4_stage2_skid_overwrite.vcd`](raw/M4_stage2_skid_overwrite.vcd).

| Модель / перевірка | Формальний режим (`yosys-smtbmc + Z3`) | Статус | Час (`с`) | Результат / артефакт |
|---|---|---|---:|---|
| `original (Cluster N=2, 1-stage)`: `MC1_MC4_base_bmc` | Конкретна 32-бітна база індукції `bmc t=4` | `PASSED` | `0.157` | [`formal_mc1_mc4_base_bmc.log`](raw/formal_mc1_mc4_base_bmc.log) |
| `original (Cluster N=2, 1-stage)`: `MC1_MC4_safety_ind` | Необмежена 32-бітна $k$-індукція `ind t=2` (без `cutpoint`) | `PASSED` | `12.253` | `MC1, MC2, MC3_rank, MC4_permanence` (`1-stage`); [`formal_mc1_mc4_ind.log`](raw/formal_mc1_mc4_ind.log) |
| `original (Cluster N=2, 2-stage)`: `MC1_MC4_base_bmc_p2` | Конкретна 32-бітна база індукції `bmc t=4` (`PIPELINE_STAGES=2`) | `PASSED` | `0.151` | [`formal_mc1_mc4_base_bmc_p2.log`](raw/formal_mc1_mc4_base_bmc_p2.log) |
| `original (Cluster N=2, 2-stage)`: `MC1_MC4_safety_ind_p2` | Необмежена 32-бітна $k$-індукція `ind t=2` (`PIPELINE_STAGES=2`) | `PASSED` | `14.585` | `MC1, MC2, MC3_rank, MC4_permanence` (`2-stage`); [`formal_mc1_mc4_ind_p2.log`](raw/formal_mc1_mc4_ind_p2.log) |
| `original (Cluster N=2, 1-stage)`: `MC3_dag_progress_bmc` | 45-тактовий `bmc t=45` дренування `Bank 0 -> Bank 1` | `PASSED` | `1.992` | Перехід у `!cluster_busy_o` (`idle`); [`formal_mc3_dag_bmc45.log`](raw/formal_mc3_dag_bmc45.log) |
| `original (Cluster N=2, 2-stage)`: `MC3_dag_progress_bmc_p2` | 49-тактовий `bmc t=49` дренування `Bank 0 -> Bank 1` (`2-stage`) | `PASSED` | `2.232` | Перехід у `!cluster_busy_o` та `s1_valid == 0, pipe_valid == 0`; [`formal_mc3_dag_bmc49_p2.log`](raw/formal_mc3_dag_bmc49_p2.log) |
| `original (Cluster N=2, 1-stage)`: `MC4_cyclic_deadlock_witness` | Конкретний 32-бітний `cover t=28` із записом `.vcd` | `PASSED` | `7.636` | Досягнуто на кроці `20`: [`MC4_cyclic_deadlock_witness.vcd`](raw/MC4_cyclic_deadlock_witness.vcd) |
| `original (Cluster N=2, 1-stage)`: `cover_dag_and_contention` | Конкретний 32-бітний `cover t=30` | `PASSED` | `16.039` | Досягнуто `C1` і `C2` (`1-stage`); [`formal_c1_c2_cover.log`](raw/formal_c1_c2_cover.log) |
| `original (Cluster N=2, 2-stage)`: `cover_dag_and_contention_p2` | Конкретний 32-бітний `cover t=32` (`PIPELINE_STAGES=2`) | `PASSED` | `14.122` | Досягнуто `C1` і `C2` (`2-stage`); [`formal_c1_c2_cover_p2.log`](raw/formal_c1_c2_cover_p2.log) |
| `M1_fixed_priority_starvation` | Конкретний `bmc t=8` | `FAILED` | `0.211` | Порушено `MC2_rr_fairness` ([`M1_fixed_priority_starvation.vcd`](raw/M1_fixed_priority_starvation.vcd)) |
| `M2_drop_crossbar_backpressure` | Конкретний `bmc t=12` | `FAILED` | `1.375` | Порушено `MC1_event_conservation` ([`M2_drop_crossbar_backpressure.vcd`](raw/M2_drop_crossbar_backpressure.vcd)) |
| `M3_duplicate_broadcast` | Конкретний `bmc t=6` | `FAILED` | `0.165` | Порушено `MC1_event_conservation` ([`M3_duplicate_broadcast.vcd`](raw/M3_duplicate_broadcast.vcd)) |
| `M4_stage2_skid_overwrite` | Конкретний `bmc t=12` (`PIPELINE_STAGES=2`) | `FAILED` | `1.975` | Порушено `MC1_event_conservation` ([`M4_stage2_skid_overwrite.vcd`](raw/M4_stage2_skid_overwrite.vcd)) |

* У режимі `PIPELINE_STAGES = 2` інваріант збереження подій `MC1_event_conservation` враховує суму пакетів на обох ступенях кросбара для кожного банку $j \in \{0, 1\}$ (`b_xbar_inflight = s1_valid_q[j] + pipe_valid_q[j]`). Мутант `M4_stage2_skid_overwrite` (ігнорування зайнятості Stage 1/Stage 2 при `s1_can_accept_w = 1'b1`) детерміновано спростовується солвером `Z3` на кроці `7` із записом траси [`M4_stage2_skid_overwrite.vcd`](raw/M4_stage2_skid_overwrite.vcd).

### 3.2. Фізичний синтез, Place & Route та STA (`OpenXC7` на `xc7z020clg400-1`): порівняння `1-stage` проти `2-stage`

Первинні дані `1-stage` (`#255`): [`manycore_pnr_scaling.csv`](raw/manycore_pnr_scaling.csv), [`manycore_pnr_summary.json`](raw/manycore_pnr_summary.json), `raw/nextpnr_report_n*.json`, `raw/yosys_synth_n*.log`, `raw/nextpnr_pnr_n*.log`.
Первинні дані `2-stage` (`#263`): [`manycore_pnr_scaling_p2.csv`](raw/manycore_pnr_scaling_p2.csv), [`manycore_pnr_summary_p2.json`](raw/manycore_pnr_summary_p2.json), [`nextpnr_report_p2_n2.json`](raw/nextpnr_report_p2_n2.json), [`nextpnr_report_p2_n4.json`](raw/nextpnr_report_p2_n4.json), [`nextpnr_report_p2_n8.json`](raw/nextpnr_report_p2_n8.json), [`yosys_synth_p2_n2.log`](raw/yosys_synth_p2_n2.log), [`yosys_synth_p2_n4.log`](raw/yosys_synth_p2_n4.log), [`yosys_synth_p2_n8.log`](raw/yosys_synth_p2_n8.log), [`yosys_xbar_only_p2_n2.log`](raw/yosys_xbar_only_p2_n2.log), [`yosys_xbar_only_p2_n4.log`](raw/yosys_xbar_only_p2_n4.log), [`yosys_xbar_only_p2_n8.log`](raw/yosys_xbar_only_p2_n8.log), [`nextpnr_pnr_p2_n2.log`](raw/nextpnr_pnr_p2_n2.log), [`nextpnr_pnr_p2_n4.log`](raw/nextpnr_pnr_p2_n4.log), [`nextpnr_pnr_p2_n8.log`](raw/nextpnr_pnr_p2_n8.log).

#### Таблиця 3.2.1. Базовий одноступеневий режим (`PIPELINE_STAGES = 1`, `#255`, `N = 1, 2, 4, 8`)

| Ядра `N` | `Yosys LCs` (увесь топ) | `Yosys LCs` (лише `xbar`) | `nextpnr SLICE_LUTX` (`%` від `106 400`) | `nextpnr SLICE_FFX` (`%` від `106 400`) | `CARRY4` | `RAMB36E1` (`%` від `140`) | `F_max^(1)(N)` (`МГц`) | Критичний шлях (`нс`) | Пік `MCPS` @ `100 МГц` | Пік `MCPS` @ `F_max^(1)(N)` |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `1` | `2 040` | `51` | `3 141` (`2.95%`) | `1 503` (`1.41%`) | `139` | `1` (`0.71%`) | `113.92` | `8.778` | `12.50` | `14.24` |
| `2` | `4 090` | `118` | `6 328` (`5.95%`) | `2 769` (`2.60%`) | `285` | `2` (`1.43%`) | `95.21` | `10.503` | `25.00` | `23.80` |
| `4` | `8 988` | `773` | `13 031` (`12.25%`) | `5 303` (`4.98%`) | `506` | `4` (`2.86%`) | `78.11` | `12.803` | `50.00` | `39.05` |
| `8` | `19 392` | `2 325` | `27 025` (`25.40%`) | `10 375` (`9.75%`) | `948` | `8` (`5.71%`) | `50.81` | `19.680` | `100.00` | `50.81` |

#### Таблиця 3.2.2. Двоступеневий конвеєрний режим (`PIPELINE_STAGES = 2`, `#263`, `N = 2, 4, 8`) та пряме порівняння з `1-stage`

| Ядра `N` | `SLICE_LUTX` `1-stage` -> `2-stage` ($\Delta\%$) | `SLICE_FFX` `1-stage` -> `2-stage` ($\Delta\%$) | `RAMB36E1` (`1-st` / `2-st`) | `F_max^(1)(N)` (`МГц`) | `F_max^(2)(N)` (`МГц`) | Приріст $\Delta F_{\max}$ (`%`) | Критичний шлях `1-st` -> `2-st` (`нс`) | Статус @ `100 МГц` (`2-stage`) | Пік `MCPS @ F_max` `1-st` -> `2-st` |
|---:|---|---|---:|---:|---:|---:|---|---|---|
| `2` | `6 328 -> 3 894` (`-38.46%`) | `2 769 -> 3 277` (`+18.35%`) | `2 / 2` | `95.21` | `133.89` | `+40.63%` | `10.503 -> 7.469` | `PASS` | `23.80 -> 33.47` (`+40.63%`) |
| `4` | `13 031 -> 8 225` (`-36.88%`) | `5 303 -> 6 095` (`+14.93%`) | `4 / 4` | `78.11` | `103.73` | `+32.80%` | `12.803 -> 9.640` | `PASS` | `39.05 -> 51.87` (`+32.83%`) |
| `8` | `27 025 -> 18 112` (`-32.98%`) | `10 375 -> 11 735` (`+13.11%`) | `8 / 8` | `50.81` | `91.89` | `+80.85%` | `19.680 -> 10.882` | `FAIL` (`-882 пс`) | `50.81 -> 91.89` (`+80.85%`) |

* **Аналіз фізичних змін у площі та частоті:**
  * Кількість тригерів `SLICE_FFX` у режимі `PIPELINE_STAGES = 2` закономірно зросла на `+508` (`N = 2`), `+792` (`N = 4`) та `+1 360` (`N = 8`) за рахунок регістрів першого ступеня комутатора (`s1_valid_q`, `s1_cid_q`, `s1_param_q`), регістрів телеметрії кросбара та двоступеневого дерева суматорів кластера (`pair_*_q`, `tot_*_q`).
  * Водночас загальна кількість таблиць істинності `SLICE_LUTX` усього кластера скоротилася на `32.98% .. 38.46%` (`27 025 -> 18 112` при `N = 8`), оскільки поділ у часі локального каскаду (`ST_EVAL_GATE`) та зовнішнього прийому (`rx_accept`) усунув другий динамічний порт запису `wr_ptr_next1` на `608` тригерах вхідного `FIFO` кожного ядра. Площа `SLICE_LUTX` при `PIPELINE_STAGES = 2` описується квадратичною моделлю $\widehat{\text{LUT}}^{(2)}(N) = 1\,846 \cdot N + 52.2619 \cdot N^2$ з відносною похибкою `<= 0.18%` (`3 901.0` для `N = 2`, `8 220.2` для `N = 4`, `18 112.8` для `N = 8`).

### 3.3. Потактове профілювання трафіку (`Icarus Verilog`) для `N = 4` та `N = 8` (`PIPELINE_STAGES = 1` проти `PIPELINE_STAGES = 2`)

Первинні дані (`evidence_kind: rtl_simulation_iverilog`, `not_physical_hil: true`):
* `PIPELINE_STAGES = 1` (`#255`): [`manycore_traffic_profiles.csv`](raw/manycore_traffic_profiles.csv), [`manycore_traffic_summary.json`](raw/manycore_traffic_summary.json), [`iverilog_traffic_n4.log`](raw/iverilog_traffic_n4.log), [`iverilog_traffic_n8.log`](raw/iverilog_traffic_n8.log).
* `PIPELINE_STAGES = 2` (`#263`): [`manycore_traffic_profiles_p2.csv`](raw/manycore_traffic_profiles_p2.csv), [`manycore_traffic_summary_p2.json`](raw/manycore_traffic_summary_p2.json), [`iverilog_traffic_p2_n4.log`](raw/iverilog_traffic_p2_n4.log), [`iverilog_traffic_p2_n8.log`](raw/iverilog_traffic_p2_n8.log).

У всіх `16` конфігураціях (`2` режими конвеєра $\times$ `2` масштаби $N \in \{4, 8\}$ $\times$ `4` профілі трафіку, по `1 024` первинні події) зафіксовано `0` втрачених прийнятих подій (`dropped_accepted_events = 0`) та `0` розбіжностей із незалежною еталонною таблицею `W0` (`w0_golden_mismatches = 0`).

| `N` | Профіль трафіку | Усього транзакцій | Активні такти `1-st` / `2-st` | `MCPS @ 100 МГц` `1-st` / `2-st` | Реальна пропускна здатність `MCPS @ F_max(N)` `1-stage` -> `2-stage` ($\Delta\%$) | Латентність сер. / макс. `1-st` (`такти`) | Латентність сер. / макс. `2-st` (`такти`) | Такти зворотного тиску `1-st` / `2-st` | Втрачено подій |
|---:|---|---:|---|---|---|---:|---:|---:|---:|
| `4` | `local` | `2 048` | `4 098 / 4 099` | `49.976 / 49.963` | `39.036 -> 51.827` (`+32.77%`) | `148.11 / 262` | `154.87 / 261` | `3 572 / 3 566` | `0 / 0` |
| `4` | `uniform` | `2 048` | `5 134 / 5 139` | `39.891 / 39.852` | `31.159 -> 41.339` (`+32.67%`) | `187.63 / 461` | `196.45 / 409` | `9 011 / 8 980` | `0 / 0` |
| `4` | `hotspot` | `1 280` | `7 938 / 7 939` | `16.125 / 16.123` | `12.595 -> 16.724` (`+32.78%`) | `135.57 / 206` | `140.95 / 213` | `7 699 / 7 693` | `0 / 0` |
| `4` | `many-to-one` | `1 792` | `8 194 / 8 195` | `21.870 / 21.867` | `17.082 -> 22.683` (`+32.79%`) | `345.43 / 582` | `360.20 / 613` | `25 946 / 25 924` | `0 / 0` |
| `8` | `local` | `2 048` | `2 050 / 2 051` | `99.902 / 99.854` | `50.760 -> 91.756` (`+80.76%`) | `143.25 / 262` | `149.83 / 261` | `1 708 / 1 710` | `0 / 0` |
| `8` | `uniform` | `2 048` | `2 632 / 2 607` | `77.812 / 78.558` | `39.536 -> 72.187` (`+82.59%`) | `147.46 / 645` | `186.95 / 545` | `6 389 / 6 479` | `0 / 0` |
| `8` | `hotspot` | `1 280` | `7 554 / 7 555` | `16.945 / 16.942` | `8.610 -> 15.568` (`+80.81%`) | `155.08 / 270` | `160.10 / 277` | `7 347 / 7 341` | `0 / 0` |
| `8` | `many-to-one` | `1 920` | `8 194 / 8 195` | `23.432 / 23.429` | `11.906 -> 21.529` (`+80.82%`) | `622.89 / 1 158` | `649.02 / 1 221` | `56 662 / 56 617` | `0 / 0` |

* Оскільки 8-тактовий цикл оцінки концепту у `km_cluster_node` є значно довшим за `2`-тактову затримку конвеєрного комутатора, кількість активних тактів виконання пакету з `1 024` первинних подій у режимі `PIPELINE_STAGES = 2` змінюється не більше ніж на `1..5` тактів (`<= 0.1%`), тоді як підвищення маршрутизованої частоти $F_{\max}^{(2)}(N)$ прямо конвертується у приріст реальної пропускної здатності `MCPS @ F_max(N)` (наприклад, на профілі `local` при `N = 8`: з `50.760` до `91.756 MCPS`, а на профілі `uniform` при `N = 8`: з `39.536` до `72.187 MCPS`).

---

## 4. Перевірка гіпотези / критеріїв

| Критерій ([#255](https://github.com/nick-fedchik/kuzmin-machine/issues/255), [#263](https://github.com/nick-fedchik/kuzmin-machine/issues/263)) | Очікувано | Отримано | Висновок |
| :--- | :--- | :--- | :--- |
| Параметр `PIPELINE_STAGES = 1, 2` у `km_event_crossbar.sv` та `km_manycore_cluster.sv` без зміни базових RTL `CFG-P` | `0` змін у базових RTL, чистий `verilator -Wall` для `PIPELINE_STAGES = 1, 2` | Базові SHA-256 незмінні; обидва режими проходять `verilator -Wall` та `yosys synth_xilinx` для `N = 1, 2, 4, 8` | Підтверджено |
| Формальний доказ `Z3` на `N = 2` для `PIPELINE_STAGES = 1, 2` + мутант `M4_stage2_skid_overwrite` | `PASSED` для `MC1..MC3` (`1-st` і `2-st`), `4/4` мутантів `M1..M4` відхилені з `.vcd` | `ind t=2` та `bmc t=49` доведені для `PIPELINE_STAGES = 2`; `M1..M4` відхилені солвером `Z3` із `.vcd` | Підтверджено |
| Фізичний Place & Route + STA `OpenXC7` для `PIPELINE_STAGES = 2` (`N = 2, 4, 8`) на `XC7Z020` | `RAMB36E1 == N`, підвищення $F_{\max}^{(2)}(N)$ відносно $F_{\max}^{(1)}(N)$ | `N = 2`: `95.21 -> 133.89 МГц` (`PASS`); `N = 4`: `78.11 -> 103.73 МГц` (`PASS`); `N = 8`: `50.81 -> 91.89 МГц` (`+80.85%`, дефіцит `8.11 МГц` до `100 МГц`) | Підтверджено (`PASS @ 100 МГц` для `N = 2, 4`; часткове покращення для `N = 8`) |
| Потактова симуляція 4 профілів трафіку при `PIPELINE_STAGES = 2` (`N = 4, 8`) | `0` втрат прийнятих подій, порівняння `MCPS @ F_max(N)` | По `1 024` первинні події, `0` втрат, `0` розбіжностей `W0`, приріст `MCPS @ F_max` на `+32.7%` (`N = 4`) і `+80.8%..+82.6%` (`N = 8`) | Підтверджено на рівні RTL |
| Натурне енерговимірювання та запуск бітстріму на живій платі `PYNQ-Z1` | Поза межами `#255` та `#263` | Не виконувалося (`not_physical_hil: true`) | Не перевірено на залізі |

---

## 5. Відтворення

```bash
# 1. Формальна SMT-верифікація Z3 на N = 2 для PIPELINE_STAGES = 1 та PIPELINE_STAGES = 2 + 4 мутанти M1..M4
python3 Engineering/validation/kpol-cme/manycore-scaling-255/scripts/run_manycore_formal.py

# 2. Повний синтез, Place & Route та STA у OpenXC7 (xc7z020clg400-1) для PIPELINE_STAGES = 1 (N = 1, 2, 4, 8) та PIPELINE_STAGES = 2 (N = 2, 4, 8)
python3 Engineering/validation/kpol-cme/manycore-scaling-255/scripts/run_manycore_pnr.py --pipeline-stages 1 --cores 1,2,4,8
python3 Engineering/validation/kpol-cme/manycore-scaling-255/scripts/run_manycore_pnr.py --pipeline-stages 2 --cores 2,4,8

# 3. Потактове профілювання 4 профілів трафіку в Icarus Verilog (N = 4, 8) для PIPELINE_STAGES = 1 та PIPELINE_STAGES = 2
python3 Engineering/validation/kpol-cme/manycore-scaling-255/scripts/run_manycore_traffic.py --pipeline-stages 1 --cores 4,8 --events-per-profile 1024
python3 Engineering/validation/kpol-cme/manycore-scaling-255/scripts/run_manycore_traffic.py --pipeline-stages 2 --cores 4,8 --events-per-profile 1024

# 4. Автоматизований набір тестів Issue #255 / #263 (включно з живими мутантними контролями 1-stage та 2-stage)
python3 -m pytest -v Engineering/hw/tests/test_manycore_scaling_255.py
```

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.2.0 | 2026-11-17 | Issue #263: додано двоступеневу конвеєризацію `PIPELINE_STAGES = 2` у `km_event_crossbar.sv` та `km_manycore_cluster.sv`, формальний доказ `Z3` на `N = 2` із мутантом `M4_stage2_skid_overwrite`, фізичний P&R + STA `OpenXC7` для `PIPELINE_STAGES = 2` (`N = 2, 4, 8`: `133.89 / 103.73 / 91.89 МГц`) та порівняння трафіку `1-stage` проти `2-stage`. |
| 0.1.0 | 2026-11-16 | Перша редакція звіту за Issue #255: RTL `km_event_crossbar` та `km_manycore_cluster`, формальний SMT-доказ `Z3` на `N = 2` зі свідком дедлока `MC4`, фізичний Place & Route + STA `OpenXC7` для `N = 1, 2, 4, 8` на `xc7z020clg400-1` та профілювання трафіку на `N = 4, 8`. |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| BMC | Bounded Model Checking — перевірка формальних властивостей на скінченній кількості тактів. |
| BRAM | Block RAM — вбудована двопортова синхронна блокова пам'ять ПЛІС (`RAMB36E1`). |
| CFG-P | Базова конфігурація програмованого конвеєра дескрипторів концептів Машини Кузьміна. |
| CME | Concept Micro-Engine — обчислювальне ядро оцінки предикатів, інваріантів і переходів концепту. |
| DAG | Directed Acyclic Graph — орієнтований ациклічний граф підписок між концептами та банками. |
| HIL | Hardware-in-the-Loop — натурні випробування на фізичній платі ПЛІС. |
| IOB | Input/Output Block — блок фізичного вводу-виводу кристала ПЛІС. |
| LC | Logic Cell — оцінна логічна комірка за до-трасувальним звітом `Yosys stat -tech xilinx`. |
| MCPS | Million Concept Evaluations Per Second — мільйонів оброблених транзакцій концептів за секунду. |
| P&R | Place and Route — фізичне розміщення комірок та маршрутизація міжз'єднань на кристалі ПЛІС. |
| SMT | Satisfiability Modulo Theories — розв'язання формул здійсненності в теорії бітових векторів. |
| STA | Static Timing Analysis — статичний аналіз затримок поширення сигналу та максимальної частоти `F_max`. |
| VCD | Value Change Dump — текстовий формат часових діаграм сигналів симуляції або контрприкладів. |
| WP | Work Product — робочий продукт проєкту з визначеним призначенням. |
