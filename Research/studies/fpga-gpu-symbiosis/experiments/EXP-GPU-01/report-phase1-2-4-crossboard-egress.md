# Звіт EXP-GPU-01 (Фази 1–2, 4, Issue #226): Фізичний Place & Route `pipeline_egress.bit` (`101.67 МГц`), натурна верифікація на `PYNQ-Z1 + RP2040 PIO` та міжплатний контур `PYNQ-Z1 -> Jetson AGX Orin J501`

* **Версія:** 0.1.0
* **Дата:** 2026-11-17
* **Тип WP:** Report
* **Issue:** `Part of` [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226) (пов'язані передумови: [#230](https://github.com/nick-fedchik/kuzmin-machine/issues/230), [#234](https://github.com/nick-fedchik/kuzmin-machine/issues/234), [#241](https://github.com/nick-fedchik/kuzmin-machine/issues/241), [#247](https://github.com/nick-fedchik/kuzmin-machine/issues/247)). **PR:** у гілці `exp/226-egress-openxc7-and-crossboard-e2e`.
* **Виконавець:** GitHub Copilot CLI. **Рецензент:** очікує перехресної рецензії незалежною моделлю іншої родини.
* **Базовий коміт:** `9175b73` (`origin/main`). **Хости та фізичні плати:** хост збірки `Linux 7.0.0-42-generic x86_64` (`OpenXC7 Yosys 0.69`, `nextpnr-himbaechel` для `xc7z020clg400-1`); фізична плата ПЛІС `Digilent PYNQ-Z1` (`pynq2`, `xilinx@192.168.68.69`, `Xilinx Zynq-7000 XC7Z020-1CLG400C`); фізичний аналізатор `LOGICTRACER_PICO_0.5.0` (`/dev/ttyACM0`, `RP2040 PIO` @ `100 МГц`, крок `10 нс`); фізичний вузол GPU `Seeed Studio reServer Industrial J501` (`mfedchyk@192.168.68.68`, `NVIDIA Jetson AGX Orin 64GB`, `GA10B SM 8.7`, `CUDA 12.6 V12.6.68`).
* **Бітстрім (`pipeline_egress.bit`, `4 045 747` байтів, SHA-256):** `7bfd5f5742334a7f08f2a290d5dde0a241e5bd06ced64c39d82e70021f30bbce` ([`openxc7_egress_bitstream.sha256`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/openxc7_egress_bitstream.sha256)).
* **Критерії успіху та фальсифікації (зафіксовані до виконання):** розділи «Результат» і «Перевірка (Попперівський критерій фальсифікації)» в [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226) та [протокол EXP-GPU-01](protocol.md).

---

## 1. Що не вдалося і обмеження

1. **Попперівське спростування гіпотези суб-15-мкс міжплатного контуру без PCIe через мережевий/системний стек (`p99.9 > 15 мкс`, `σ > 2 мкс`):**
   * За критерієм фальсифікації [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226) (*«Якщо апаратно виміряний між двома платами `p99.9(T_e2e) > 15 мкс` або `σ > 2 мкс` через затримку системного GPCDMA / мережевого контролера на Orin, гіпотеза субмікросекундного/мікросекундного міжплатного контуру без PCIe вважається спростованою — у звіті фіксується потреба переходу на ПЛІС із PCIe (Artix-7 / Zynq UltraScale+) для GPUDirect RDMA»*):
   * На живій серії $R = 5 \times 1\,000$ ($5\,000$ подій між `pynq2 192.168.68.69` та `Jetson AGX Orin 192.168.68.68` у [`summary_crossboard_226.json`](../../data/exp-gpu-01-crossboard/summary_crossboard_226.json)) виміряний односторонній час доставки `T_crossboard_oneway_est` становить: `min = 73.10 мкс`, `p50 = 344.78 мкс`, `p99 = 853.03 мкс`, **`p99.9 = 2808.53 мкс`** (у `187.2×` вище порога `15.0 мкс`), **`σ = 199.17 мкс`** (у `99.6×` вище порога `2.0 мкс`), а повний круговий цикл `T_crossboard_rtt` — `p50 = 675.38 мкс`, `p99.9 = 3143.41 мкс`, `σ = 208.51 мкс`.
   * Отже, гіпотеза досягнення `< 15 мкс` (`σ <= 2 мкс`) між двома фізично окремими платами через стандартний мережевий тракт GbE без прямого апаратного доступу PCIe (`GPUDirect RDMA`) **емпірично спростована**. Попри те що обчислення в кремнії ПЛІС (`80 нс` на концепт) і в персистентному кернелі GPU (`64 нс` регістрової математики / `2.02 мкс` з L2 `Event Mailbox` для `1 024` підписників) сумарно займають лише **`~2.10 мкс` (`< 0.6%` часу контуру)**, понад **`99.4%`** затримки (`~342 мкс` на медіані) поглинається мережевими контролерами MAC/PHY, перериваннями та сокетним стеком ОС між Zynq-7020 PS і Orin.
2. **Відсутність розпаяного макета перетворювача рівнів `3.3V -> 1.8V` між `PMOD JB` та `J501` (`Part of #226`):**
   * Пряме підключення виводів `PMOD JB` (`3.3V LVCMOS`) до низьковольтного роз'єму розширення `Jetson AGX Orin J501` (`1.8V`) заборонене умовами безпеки [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226) та [протоколу EXP-GPU-01](protocol.md). Оскільки фізичний монтаж буферизованого перетворювача рівнів `SN74AVC8T245` (або лабораторна перевірка `TXS0108E` з розтягнутим стробом за чеклістом [#247](https://github.com/nick-fedchik/kuzmin-machine/issues/247)) потребує окремих монтажних робіт власника стенда, у цій роботі виконано передбачений п. 2 [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226) натурний міжплатний контур через GbE у `cudaHostAllocMapped` `Event Mailbox` разом із живою перевіркою бітстріму `pipeline_egress.bit` на `PYNQ-Z1` та захватом `JA2_COMMIT` на `RP2040 PIO` (`LOGICTRACER_PICO_0.5.0`). Задача `#226` залишається відкритою (`Part of #226`) для можливого осцилографування змонтованого `SN74AVC8T245`.
3. **Залежність закриття таймінгу `100 МГц` у `nextpnr-himbaechel` від зерна розміщення (`--seed 3`):**
   * При трасуванні топа [`kpol_bram_pipeline_pynq_z1_egress_top.v`](../../../../../Engineering/hw/boards/pynq-z1/kpol_bram_pipeline_pynq_z1_egress_top.v) у `nextpnr-himbaechel` (`router2`, `xc7z020clg400-1`) зерна `--seed 1` та `--seed 2` зупинилися на межі `96.84 МГц` (`WNS = -0.326 нс`) і `93.12 МГц`, тоді як `--seed 3` досягає **`F_max = 101.67 МГц` (`PASS at 100.00 MHz`, `WNS = +0.164 нс`)**. У скрипті [`build_bram_pipeline_egress.sh`](../../../../../Engineering/hw/boards/pynq-z1/build_bram_pipeline_egress.sh) зафіксовано детерміноване зерно `NEXTPNR_SEED=3`.

---

## 2. Метод та постановка експерименту

1. **Фізичний синтез, Place & Route, STA @ 100 МГц та генерація бітстріму `pipeline_egress.bit` у відкритому стеку `OpenXC7`:**
   * Скрипт [`build_bram_pipeline_egress.sh`](../../../../../Engineering/hw/boards/pynq-z1/build_bram_pipeline_egress.sh) синтезує через `OpenXC7 Yosys 0.69` (`synth_xilinx -flatten -abc9 -arch xc7`) повний стек `CFG-P` (`kpol_txn_gate_v2.sv`, `km_concept_micro_engine.sv`, `km_concept_bram.sv`, `km_autonomous_sequencer.sv`, `kpol_bram_pipeline_axi.sv`) разом із серіалізатором [`km_pmod_event_egress.sv`](../../../../../Engineering/hw/rtl/io/km_pmod_event_egress.sv) та топом плати [`kpol_bram_pipeline_pynq_z1_egress_top.v`](../../../../../Engineering/hw/boards/pynq-z1/kpol_bram_pipeline_pynq_z1_egress_top.v).
   * Трасування виконується `nextpnr-himbaechel` із файлом обмежень [`kpol_bram_pipeline_egress.xdc`](../../../../../Engineering/hw/boards/pynq-z1/kpol_bram_pipeline_egress.xdc) (`--device xc7z020clg400-1 --router router2 --seed 3 --freq 100`), після чого `fasm2frames` + `xc7frames2bit` формують бітстрім `pipeline_egress.bit`.
2. **Натурна перевірка бітстріму `pipeline_egress.bit` у кремнії `PYNQ-Z1` (`pynq2`) та захват `LOGICTRACER_PICO_0.5.0` (`100 МГц`):**
   * Бітстрім `pipeline_egress.bit` перетворено у формат Zynq FPGA Manager (`pipeline_egress.bin`, `4 045 564` байти) та завантажено у `/sys/class/fpga_manager/fpga0/firmware` на живій платі `pynq2` (`192.168.68.69`, стан `operating`).
   * Проведено побітову верифікацію 256 слів Block RAM, 4-концептного ендогенного каскаду `C0 -> C1 -> C2 -> C3` (`+4` коміти) та `Fail-Closed` відхилення невалідного стимулу (`+1` reject) у [`pynq2_egress_silicon_cascade.log`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/pynq2_egress_silicon_cascade.log).
   * Зовнішнім цифровим логічним аналізатором `LOGICTRACER_PICO_0.5.0` (`/dev/ttyACM0`, частота вибірки `100 МГц`, крок `10 нс`, вікно `32 000` відліків = `320 мкс`) захоплено серію імпульсів `JA2_COMMIT` під час пакетної генерації 4-концептних каскадів на `pynq2` ([`logictracer_egress_ja2_100mhz.json`](../../data/exp-gpu-01-crossboard/logictracer_egress_ja2_100mhz.json), [`logictracer_egress_ja2_100mhz.vcd`](../../data/exp-gpu-01-crossboard/logictracer_egress_ja2_100mhz.vcd)).
3. **Міжплатний контур `PYNQ-Z1 -> GbE -> Jetson AGX Orin J501 Event Mailbox -> 1024 GPU Subscribers` ($R = 5 \times 1\,000$ подій):**
   * **Передавач на `PYNQ-Z1` ([`crossboard_egress_client.c`](crossboard_egress_client.c)):** ініціює подію в апаратному конвеєрі PL (`0x40000000`), очікує завершення 8-тактового каскаду (`REG_STATUS_BUSY == 0`), зчитує оновлений стан листового концепту `C3` з Block RAM, формує 64-бітний кадр події за форматом `km_pmod_event_egress.sv` (`[63:56]=CRC-8 poly 0x07`, `[55:54]=2'b01`, `[53:48]=cid`, `[47:32]=mask16`, `[31:0]=state`) і відправляє його через UDP-сокет із `SO_BUSY_POLL` на `Jetson AGX Orin` (`192.168.68.68`). Перед початком кожної серії з `1 000` подій клієнт обов'язково відправляє 1 навмисно пошкоджений кадр із інвертованим бітом `CRC-8` (`[60]`) і перевіряє, що сервер Jetson відхиляє його (`status == 1`, `crc_drop_count == 1`) без публікації в `Event Mailbox`.
   * **Приймач і персистентний кернел на `Jetson AGX Orin` ([`crossboard_egress_server.cu`](crossboard_egress_server.cu)):** утримує в резидентному стані на GPU (`GA10B SM 8.7`) персистентний кернел `16 блоків × 64 нитки = 32 варпи = 1 024 підписники` (Q8 ПІД у регістрах SM, секціоновані 128-Б слоти `km_event_ingress_t[16]` та ізольовані 128-Б лінії `isolated_ack[16]` у `cudaHostAllocMapped` Unified Memory за [ADR B6](../../../../../Engineering/decisions/b6-gpu-persistent-kernel-subscribers.md)). При надходженні пакета сервер перевіряє `CRC-8` і тег `2'b01`, записує подію в 16 кеш-ліній `Event Mailbox` із бар'єром `release` (`stlr`), очікує `isolated_ack[0..15] == cur_seq` від усіх 16 SM (які паралельно фіксують апаратні мітки `%globaltimer` у device-local буфері `telemetry`), звіряє всі `1 024` стани підписників із еталонною моделлю CPU і відправляє пакет підтвердження назад на `PYNQ-Z1`.
   * Після завершення експерименту на обох платах `pynq1` (`192.168.68.81`) та `pynq2` (`192.168.68.69`) відновлено штатний бітстрім `/lib/firmware/pipeline.bin` і пройдено регресійний HIL-тест `test_kpol_bram_cascade_hil.py` (`2 passed`).

---

## 3. Результати

### 3.1. Фізичний Place & Route та STA @ 100 МГц топа `kpol_bram_pipeline_pynq_z1_egress_top` (`OpenXC7`)

Первинні дані: [`openxc7_egress_yosys.log`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/openxc7_egress_yosys.log), [`openxc7_egress_nextpnr.log`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/openxc7_egress_nextpnr.log), [`openxc7_egress_nextpnr_report.json`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/openxc7_egress_nextpnr_report.json), [`openxc7_egress_bitstream.sha256`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/openxc7_egress_bitstream.sha256).

| Ресурс / Метрика (`xc7z020clg400-1`) | Використано (`egress_top`) | Доступно на кристалі | Утилізація | Примітка |
| :--- | ---: | ---: | ---: | :--- |
| `SLICE_LUTX` | `3 630` | `106 400` | `3.41%` | Включно з `km_pmod_event_egress` (CRC-8, SPI/PAR8 FSM) |
| `SLICE_FFX` | `1 524` | `106 400` | `1.43%` | `914 FDCE + 2 FDPE + 608 FDRE` у Yosys `0.69` |
| `RAMB36E1` | `1` | `140` | `0.71%` | Однобанкова таблиця 64 концептів `CFG-P` (`256 × 32b`) |
| `CARRY4` | `155` | `13 300` | `1.17%` | Арифметика CME + лічильники `tx_count_o` / `drop_count_o` |
| `SELMUX2_1` (`MUXF7/F8`) | `16` | `40 700` | `0.04%` | `11 MUXF7 + 5 MUXF8` |
| `PAD` (`IOB33_INBUF_EN` + `IOB33_OUTBUF`) | `26` (`8 + 18`) | `392` | `6.63%` | `JA1..4, JA7..10`, `JB[7:0]`, `BTN[3:0]`, `SW[1:0]`, `LED[3:0]` |
| `BUFGCTRL` / `PS7` | `1` / `1` | `32` / `1` | `3.13%` / `100%` | Тактова сітка `FCLKCLK[0]` (`100 МГц`) та міст `MAXIGP0` |
| **Критичний шлях (`clk`)** | **`9.84 нс`** | `<= 10.00 нс` | **Запас `+0.164 нс`** | `1.25 нс` логіки + `8.59 нс` трасування (`seed 3`) |
| **Максимальна частота $F_{\max}$** | **`101.67 МГц`** | `>= 100.00 МГц` | **`PASS @ 100.00 MHz`** | Точне значення в JSON: `101.667343 МГц` |

### 3.2. Натурна верифікація `pipeline_egress.bit` на `pynq2` та захват `LOGICTRACER_PICO_0.5.0` (`100 МГц`)

Первинні дані: [`pynq2_egress_silicon_cascade.log`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/pynq2_egress_silicon_cascade.log), [`logictracer_egress_ja2_100mhz.log`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/logictracer_egress_ja2_100mhz.log), [`logictracer_egress_ja2_100mhz.json`](../../data/exp-gpu-01-crossboard/logictracer_egress_ja2_100mhz.json) (SHA-256: `7508e6a32b591f38a5a5d11aba40efeae46b49727a844f2d02fe50cb04973ba6`), [`logictracer_egress_ja2_100mhz.vcd`](../../data/exp-gpu-01-crossboard/logictracer_egress_ja2_100mhz.vcd) (SHA-256: `2f8df8be092b6bc6ffd084033af2970a799dd395b3a623e3d366df52f5006718`).

* Після програмування `pipeline_egress.bin` у `/sys/class/fpga_manager/fpga0/firmware` на `pynq2` (`192.168.68.69`) кристал перейшов у стан `operating`, повернув ідентифікатор `0x4B504D43 ('KPMC')`, пройшов 100% верифікацію 256 слів Block RAM, виконав автономний каскад `C0 -> C1 -> C2 -> C3` (`Events: +4, Commits: +4, Rejects: +0`) та заблокував невалідний стимул `p = 100 >= 50` (`Commits: +0, Rejects: +1`).
* Цифровий захват `LOGICTRACER_PICO_0.5.0` (`/dev/ttyACM0`, `100 МГц`, `32 000` вибірок = `320 мкс`) на каналі `CH2 (JA2_COMMIT)` зафіксував **`400` фронтів (`399` повних імпульсів, `0` глітчів)** із максимальною тривалістю імпульсу **`MAX PW = 340 нс`** (`34` відліки по `10 нс`).
* **Фізична інтерпретація ширини імпульсу `340 нс`:** у топі `kpol_bram_pipeline_pynq_z1_egress_top.v` кожен імпульс `hw_commit` перезавантажує 10-тактовий розширювач `ja_commit_cnt_q <= 4'd10` (`100 нс`). Оскільки в 4-концептному каскаді `C0 -> C1 -> C2 -> C3` чотири коміти відбуваються з інтервалом рівно `8` тактів (`80 нс` у моменти $t_0, t_0+80\text{ нс}, t_0+160\text{ нс}, t_0+240\text{ нс}$), лічильник `ja_commit_cnt_q` перезавантажується на кожному з 4 комітів до свого обнулення, утворюючи суцільний високий імпульс тривалістю:
  $$T_{\text{JA2\_cascade}} = 3 \times 80\text{ нс} + 100\text{ нс} = 340\text{ нс}\ (34\text{ такти @ }100\text{ МГц}),$$
  що з точністю до `0 нс` (`0 LSB`) збігається з виміряним на `LOGICTRACER_PICO_0.5.0` значенням `340 нс`.

### 3.3. Міжплатний контур `PYNQ-Z1 -> GbE -> Jetson AGX Orin J501 (1024 підписники)` ($R = 5 \times 1\,000 = 5\,000$ подій)

Первинні дані: [`run-01-crossboard-5x1000.log`](../../data/exp-gpu-01-crossboard/run-01-crossboard-5x1000.log), [`crossboard_r1.json`](../../data/exp-gpu-01-crossboard/crossboard_r1.json)..[`crossboard_r5.json`](../../data/exp-gpu-01-crossboard/crossboard_r5.json), [`summary_crossboard_226.json`](../../data/exp-gpu-01-crossboard/summary_crossboard_226.json), [`sha256sums.txt`](../../data/exp-gpu-01-crossboard/sha256sums.txt).

#### Попрогонна таблиця ($R = 5$, по $1\,000$ подій у прогоні)

| Прогін (`Файл`) | Подій $N$ | Негативний тест CRC-8 (`drop`) | Розбіжностей станів GPU vs CPU (`1024` підп.) | `GPU Math p50` (`%globaltimer`, нс) | `GPU SM E2E p50` (`%globaltimer`, нс) | `GPU SM E2E p99.9` (нс) | `One-Way p50` (мкс) | `One-Way p99` (мкс) | `One-Way p99.9` (мкс) | `One-Way σ` (мкс) | `RTT p50` (мкс) | `RTT p99.9` (мкс) |
| :--- | ---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `r1` ([`crossboard_r1.json`](../../data/exp-gpu-01-crossboard/crossboard_r1.json)) | `1 000` | `PASS (1)` | `0` | `64` | `2 048` | `1 152 992` | `344.95` | `838.93` | `2 827.23` | `196.44` | `675.75` | `3 160.13` |
| `r2` ([`crossboard_r2.json`](../../data/exp-gpu-01-crossboard/crossboard_r2.json)) | `1 000` | `PASS (1)` | `0` | `64` | `2 016` | `1 145 984` | `345.66` | `1 291.35` | `2 808.53` | `201.48` | `677.06` | `3 143.41` |
| `r3` ([`crossboard_r3.json`](../../data/exp-gpu-01-crossboard/crossboard_r3.json)) | `1 000` | `PASS (1)` | `0` | `64` | `1 952` | `2 944` | `345.07` | `847.96` | `2 660.00` | `186.61` | `676.06` | `2 989.89` |
| `r4` ([`crossboard_r4.json`](../../data/exp-gpu-01-crossboard/crossboard_r4.json)) | `1 000` | `PASS (1)` | `0` | `64` | `2 016` | `2 912` | `344.25` | `842.37` | `2 835.88` | `200.60` | `674.34` | `3 166.15` |
| `r5` ([`crossboard_r5.json`](../../data/exp-gpu-01-crossboard/crossboard_r5.json)) | `1 000` | `PASS (1)` | `0` | `64` | `1 952` | `2 944` | `343.95` | `1 364.04` | `2 876.77` | `210.35` | `673.54` | `3 213.37` |
| **Зведена вибірка (`5 000` подій)** | **`5 000`** | **`5/5 PASS`** | **`0 / 5 120 000`** | **`64`** | **`1 952..2 048`** | **`2 912..1 152 992`** | **`344.78`** | **`853.03`** | **`2 808.53`** | **`199.17`** | **`675.38`** | **`3 143.41`** |

#### Декомпозиція наскрізного бюджету часу (обчислення в кремнії проти міжплатного транспорту)

| Етап контуру | Спосіб вимірювання | `min` | `p50` (медіана) | `p99` | `p99.9` | `σ` (СКВ) | Частка від медіани `One-Way` (`344.78 мкс`) |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1. Ядро ПЛІС `CFG-P` (1 концепт / 4-концептний каскад) | Такти PL @ `100 МГц` + `RP2040 PIO` | `0.080 / 0.320 мкс` | **`0.080 / 0.320 мкс`** | `0.080 / 0.320 мкс` | `0.080 / 0.320 мкс` | `0.000 мкс` | `0.02% / 0.09%` |
| 2. Серіалізація `km_pmod_event_egress` (`PAR8` / `SPI 50 МГц`) | Такти PL (`17` / `129` тактів) | `0.170 / 1.290 мкс` | **`0.170 / 1.290 мкс`** | `0.170 / 1.290 мкс` | `0.170 / 1.290 мкс` | `0.000 мкс` | `0.05% / 0.37%` |
| 3. Тригер MMIO `Cortex-A9 -> AXI GP0 -> PL каскад -> читання BRAM` | `CLOCK_MONOTONIC_RAW` на `PYNQ-Z1` | `2.037 мкс` | **`2.148 мкс`** | `2.314 мкс` | `3.477 мкс` | `1.194 мкс` | `0.62%` |
| 4. Регістрова математика `1 024` ПІД-підписників у `16 SM` GPU | `%globaltimer` на `Jetson AGX Orin` | `0.064 мкс` | **`0.064 мкс`** | `0.064 мкс` | `0.096 мкс` | `< 0.010 мкс` | `0.02%` |
| 5. Повний цикл `16 SM` GPU (`L2 acquire -> 1024 підписники -> isolated_ack release`) | `%globaltimer` на `Jetson AGX Orin` | `1.888 мкс` | **`2.016 мкс`** | `2.752 мкс` | `2.944 мкс` (`r3..r5`) | — | `0.58%` |
| 6. Хост-обробка на `Jetson Orin` (`CRC-8 + 16×stlr + очікування GPU + CPU-модель`) | `CLOCK_MONOTONIC_RAW` на `Jetson Orin` | `9.792 мкс` | **`12.064 мкс`** | `520.672 мкс` | `2 471.488 мкс` | `195.751 мкс` | `3.50%` |
| 7. Мережевий транспорт `GbE MAC/PHY + Linux UDP socket` (в один бік) | Декомпозиція `(RTT - T_pl - T_jetson) / 2` | `61.27 мкс` | **`330.57 мкс`** | `645.10 мкс` | `1 180.00 мкс` | `~68.0 мкс` | **`95.88%`** |
| **Разом: Міжплатний `One-Way` (`PYNQ-Z1 -> Jetson GPU ACK`)** | `CLOCK_MONOTONIC_RAW` ($N = 5\,000$) | **`73.096 мкс`** | **`344.781 мкс`** | **`853.025 мкс`** | **`2 808.528 мкс`** | **`199.165 мкс`** | **`100.00%`** |
| **Разом: Міжплатний `RTT` (`PYNQ-Z1 -> Jetson GPU -> PYNQ-Z1`)** | `CLOCK_MONOTONIC_RAW` ($N = 5\,000$) | **`133.704 мкс`** | **`675.384 мкс`** | **`1 183.317 мкс`** | **`3 143.409 мкс`** | **`208.509 мкс`** | — |

---

## 4. Перевірка гіпотези та Попперівського критерію фальсифікації (#226)

| Критерій ([#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226), [протокол EXP-GPU-01](protocol.md)) | Поріг прийняття / фальсифікації | Експериментальний результат | Статус |
| :--- | :--- | :--- | :--- |
| 1. Фізичний Place & Route та STA `kpol_bram_pipeline_pynq_z1_egress_top` в `OpenXC7` | $F_{\max} \ge 100.0\text{ МГц}$, `0` помилок DRC/check | **`F_max = 101.67 МГц`** (`PASS @ 100.00 MHz`), `3 630 LUT`, `1 524 FF`, `1 RAMB36E1`, бітстрім `7bfd5f57...` | **Виконано** |
| 2. Жива перевірка `pipeline_egress.bit` на `PYNQ-Z1` + захват `RP2040 PIO` (`100 МГц`) | Робота каскаду в кремнії, стабільний імпульс `JA2_COMMIT`, `0` глітчів | Каскад `C0->C1->C2->C3` верифіковано (`+4` коміти), `399` імпульсів на `CH2`, `MAX PW = 340 нс` (`34` такти @ `100 МГц`), `0` глітчів | **Виконано** |
| 3. Цілісність 64-бітного кадра з `CRC-8` (`poly 0x07`) та побітова точність `1 024` підписників GPU | Відхилення 100% пошкоджених кадрів (`neg_crc_test`), `0` розбіжностей GPU vs CPU | `5/5` негативних мутантів CRC-8 відхилено (`status=1`), **`0` розбіжностей** на `5 000 × 1 024 = 5 120 000` оновленнях станів | **Виконано** |
| 4. **Попперівський критерій фальсифікації міжплатного контуру без PCIe** | Фальсифікується, якщо `p99.9(T_e2e) > 15.0 мкс` або `σ > 2.0 мкс` | **`p99.9(One-Way) = 2808.53 мкс > 15.0 мкс`** (`187.2×`), **`σ = 199.17 мкс > 2.0 мкс`** (`99.6×`) | **Гіпотезу спростовано (потреба в PCIe GPUDirect RDMA доведена)** |

### Архітектурний висновок для [ADR B6](../../../../../Engineering/decisions/b6-gpu-persistent-kernel-subscribers.md)

Натурний експеримент замкнув обидві половини рівняння гетерогенного симбіозу ПЛІС+GPU:
1. **Внутрішньокристальні обчислювачі повністю вкладаються в мікросекундний бюджет:** `80 нс` на перехід у `CFG-P` на ПЛІС + `170 нс` паралельної видачі `PAR8` + `64 нс` регістрової математики на GPU (`2.02 мкс` з урахуванням когерентної тканини `L2/SCF` для `1 024` підписників на 16 SM).
2. **Транспорт без PCIe є головним обмежувачем (`> 99.4%` затримки):** оскільки кристал `XC7Z020` на платі `PYNQ-Z1` не має високошвидкісних трансиверів PCIe (`GTP/GTX`), будь-яка передача через мережевий контролер GbE та процесорне ядро супроводжується медіанною затримкою `~345 мкс` і хвостом `p99.9 = 2.81 мс` (через латентність MAC/PHY, сокетного стека ОС та рідкісні витіснення контексту драйвера `nvgpu` TSG `~1.15..2.47 мс`).
3. **Обов'язкова умова для промислового суб-15-мкс контуру:** для реалізації потенціалу наносекундного ядра МК та персистентного кернела GPU без участі CPU та мережевого стека необхідний перехід на сімейство ПЛІС із апаратними трансиверами **PCIe (`Xilinx Artix-7 XC7A50T/100T` з GTP або `Zynq UltraScale+` з GTH)** для прямого запису подій через **PCIe BAR1 / GPUDirect RDMA** (або когерентний PCIe C2C на Orin Industrial) безпосередньо в 128-байтні лінії `Event Mailbox` GPU.

---

## 5. Відтворення та контрольні суми SHA-256

### 5.1. Команди відтворення

```bash
# 1. Збірка бітстріму pipeline_egress.bit у відкритому стеку OpenXC7:
BUILD_DIR=/home/mfedchyk/GitHub/nick-fedchik/km-wt-226-egress-e2e/.build_egress \
  bash Engineering/hw/boards/pynq-z1/build_bram_pipeline_egress.sh

# 2. Агрегація статистики міжплатних прогонів R = 5 x 1000 та перевірка критерію Поппера:
python3 Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-01/crossboard_frame.py \
  --summarize Research/studies/fpga-gpu-symbiosis/data/exp-gpu-01-crossboard/crossboard_r*.json

# 3. Автоматизовані тести (включно з негативними мутантами CRC-8 та перевіркою артефактів):
python3 -m pytest -v \
  Engineering/hw/tests/test_km_pmod_event_egress.py \
  Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-01/tests/test_crossboard_egress_226.py
```

### 5.2. Реєстр первинних файлів і SHA-256

| Файл | SHA-256 | Призначення |
| :--- | :--- | :--- |
| `pipeline_egress.bit` ([`openxc7_egress_bitstream.sha256`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/openxc7_egress_bitstream.sha256)) | `7bfd5f5742334a7f08f2a290d5dde0a241e5bd06ced64c39d82e70021f30bbce` | Бітстрім `kpol_bram_pipeline_pynq_z1_egress_top` (`4 045 747` Б) |
| [`openxc7_egress_yosys.log`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/openxc7_egress_yosys.log) | `1e6581a15e0ddd5913f2e648028691d9a1cecb913150ff61f189777275deba65` | Журнал синтезу `OpenXC7 Yosys 0.69` |
| [`openxc7_egress_nextpnr.log`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/openxc7_egress_nextpnr.log) | `d56a91bdd61d55a0b4cbaa861a62e522b48a37c5da1c9c4843b6aa195b32486d` | Журнал P&R та STA `nextpnr-himbaechel` (`101.67 МГц PASS`) |
| [`openxc7_egress_nextpnr_report.json`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/openxc7_egress_nextpnr_report.json) | `4aa2770e14d46bb30ccd560e0cc3a155ea6beb7c43aaab02e0e3a48ad1fb3f54` | Машиночитний звіт ресурсів і таймінгу `nextpnr` |
| [`pynq2_egress_silicon_cascade.log`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/pynq2_egress_silicon_cascade.log) | `9bc430da62efe03cf3b3353bc6da930008cb611f285e93d3b97bd36c69578ea5` | Жива перевірка `pipeline_egress.bit` на кремнії `pynq2` |
| [`logictracer_egress_ja2_100mhz.json`](../../data/exp-gpu-01-crossboard/logictracer_egress_ja2_100mhz.json) | `7508e6a32b591f38a5a5d11aba40efeae46b49727a844f2d02fe50cb04973ba6` | Захват `LOGICTRACER_PICO_0.5.0` @ `100 МГц` (`399` імпульсів `JA2_COMMIT`) |
| [`logictracer_egress_ja2_100mhz.vcd`](../../data/exp-gpu-01-crossboard/logictracer_egress_ja2_100mhz.vcd) | `2f8df8be092b6bc6ffd084033af2970a799dd395b3a623e3d366df52f5006718` | Хвильова діаграма VCD захвату `RP2040 PIO` (`100 МГц`) |
| [`run-01-crossboard-5x1000.log`](../../data/exp-gpu-01-crossboard/run-01-crossboard-5x1000.log) | `73bedc4553e40b2632d71a05566316c1e76297a3e5c5b76c9fe2006e7f6750e9` | Протокол виконання 5 міжплатних серій `PYNQ-Z1 -> Jetson Orin` |
| [`crossboard_r1.json`](../../data/exp-gpu-01-crossboard/crossboard_r1.json) | `35a4a9a8ff1ed5409fed22fd698240833635892ab9c8c69d8db5427c4f47e96e` | Сирі вимірювання серії `r1` (`1 000` подій) |
| [`crossboard_r2.json`](../../data/exp-gpu-01-crossboard/crossboard_r2.json) | `471a8c6e029bc798baa082a9f9c9a1bb576470df974d3aec139c2cd155c3c4d4` | Сирі вимірювання серії `r2` (`1 000` подій) |
| [`crossboard_r3.json`](../../data/exp-gpu-01-crossboard/crossboard_r3.json) | `ece7919075a5213611921b279934931f515e954db4be9f40e31f4b11efaa5316` | Сирі вимірювання серії `r3` (`1 000` подій) |
| [`crossboard_r4.json`](../../data/exp-gpu-01-crossboard/crossboard_r4.json) | `d726dcd4190ec5b7af836484b1d88ded364acc61f6b40c1aed59889c43370cc4` | Сирі вимірювання серії `r4` (`1 000` подій) |
| [`crossboard_r5.json`](../../data/exp-gpu-01-crossboard/crossboard_r5.json) | `671cddf79bd48aef8d662edd7f20cd65a2bf5831f467842d9bc43a738d3bc392` | Сирі вимірювання серії `r5` (`1 000` подій) |
| [`summary_crossboard_226.json`](../../data/exp-gpu-01-crossboard/summary_crossboard_226.json) | `267454a479629fa9bb99fca65d5b4993643e8a4e162750eec682614c563d4be3` | Зведений статистичний звіт `R = 5 x 1 000` та вердикт Поппера |

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-17 | Перша редакція звіту (#226): фізичний P&R та STA @ `100 МГц` бітстріму `pipeline_egress.bit` (`101.67 МГц PASS`), натурна перевірка на `pynq2` із захватом `LOGICTRACER_PICO_0.5.0` (`340 нс` на 4-концептний каскад) та міжплатний експеримент `PYNQ-Z1 -> GbE -> Jetson AGX Orin J501` ($R = 5 \times 1\,000$ подій, `1 024` підписники) з перевіркою Попперівського критерію фальсифікації. |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| CRC-8 | 8-бітна циклічна контрольна сума (поліном `0x07`, ініціалізація `0x00`). |
| Event Mailbox | Вирівняна по 128 байтах системно-когерентна область пам'яті (`cudaHostAllocMapped`) для передачі подій у персистентний кернел GPU через `L2`. |
| GPUDirect RDMA | Прямий доступ периферійних пристроїв PCIe до пам'яті GPU без участі CPU та мережевого стека ОС. |
| HIL | Hardware-in-the-Loop (натурне тестування на фізичних платах `PYNQ-Z1`, `Jetson AGX Orin` та `RP2040 PIO`). |
| PAR8 | 8-бітний джерельно-синхронний паралельний режим модуля `km_pmod_event_egress` (`17` тактів = `170 нс` на 64-бітний кадр). |
| RTT | Round-Trip Time (повний круговий час передачі події та отримання підтвердження). |
| STA | Static Timing Analysis (статичний аналіз часових затримок після трасування ПЛІС). |
