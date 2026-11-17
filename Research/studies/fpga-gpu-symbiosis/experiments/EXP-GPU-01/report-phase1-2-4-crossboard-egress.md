# Звіт EXP-GPU-01 (Фази 1–2, 4, Issue #226): Фізичний Place & Route `pipeline_egress.bit` (`101.67 МГц`), натурна верифікація на `PYNQ-Z1 + RP2040 PIO` та міжплатний контур `PYNQ-Z1 -> Jetson AGX Orin J501`

* **Версія:** 0.1.1
* **Дата:** 2026-11-17
* **Тип WP:** Report
* **Issue:** `Part of` [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226) (пов'язані передумови: [#230](https://github.com/nick-fedchik/kuzmin-machine/issues/230), [#234](https://github.com/nick-fedchik/kuzmin-machine/issues/234), [#241](https://github.com/nick-fedchik/kuzmin-machine/issues/241), [#247](https://github.com/nick-fedchik/kuzmin-machine/issues/247)). **PR:** [#268](https://github.com/nick-fedchik/kuzmin-machine/pull/268) у гілці `exp/226-egress-openxc7-and-crossboard-e2e`.
* **Виконавець:** GitHub Copilot CLI. **Рецензент `0.1.0`:** `claude-sonnet-5.5` у [PR #268](https://github.com/nick-fedchik/kuzmin-machine/pull/268#issuecomment-6950179505) (вердикт «Доопрацювати»; зауваження `F-1..F-9` повністю враховано у `0.1.1`).
* **Базовий коміт:** `9175b73` (`origin/main`; рецензований коміт `0.1.0` — `54fe8bc`). **Хости та фізичні плати:** хост збірки `Linux 7.0.0-42-generic x86_64` (`OpenXC7 Yosys 0.69`, `nextpnr-himbaechel` для `xc7z020clg400-1`); фізична плата ПЛІС `Digilent PYNQ-Z1` (`pynq2`, `xilinx@192.168.68.69`, `Xilinx Zynq-7000 XC7Z020-1CLG400C`); фізичний аналізатор `LOGICTRACER_PICO_0.5.0` (`/dev/ttyACM0`, прошивка `0.5.0`, утиліта `/tmp/kimi-k3/src/cli/logictracer-cli` версії `0.5.0`, зібрана з локального репозиторію `/home/mfedchyk/GitHub/nick-fedchik/logictracer` @ коміт `58caf0af5db45086556ec6c17d28bc1a7c799707`, `RP2040 PIO` @ `100 МГц`, крок `10 нс`); фізичний вузол GPU `Seeed Studio reServer Industrial J501` (`mfedchyk@192.168.68.68`, `NVIDIA Jetson AGX Orin 64GB`, `GA10B SM 8.7`, `CUDA 12.6 V12.6.68`).
* **Бітстрім (`pipeline_egress.bit`, `4 045 747` байтів, SHA-256):** `7bfd5f5742334a7f08f2a290d5dde0a241e5bd06ced64c39d82e70021f30bbce` ([`openxc7_egress_bitstream.sha256`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/openxc7_egress_bitstream.sha256)).
* **Критерії успіху та фальсифікації (зафіксовані до виконання):** розділи «Результат» і «Перевірка (Попперівський критерій фальсифікації)» в [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226) та [протокол EXP-GPU-01](protocol.md).

---

## 1. Що не вдалося і обмеження

1. **Попперівське спростування придатності програмного міжплатного контуру `UDP/GbE` через ядро Linux для порога `p99.9 <= 15 мкс`, `σ <= 2 мкс` (`F-3, F-4, F-5`):**
   * За критерієм фальсифікації [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226) (*«Якщо апаратно виміряний між двома платами `p99.9(T_e2e) > 15 мкс` або `σ > 2 мкс` через затримку системного GPCDMA / мережевого контролера на Orin, гіпотеза субмікросекундного/мікросекундного міжплатного контуру без PCIe вважається спростованою — у звіті фіксується потреба переходу на ПЛІС із PCIe (Artix-7 / Zynq UltraScale+) для GPUDirect RDMA»*):
   * На живій серії $R = 5 \times 1\,000$ ($5\,000$ подій між `pynq2 192.168.68.69` та `Jetson AGX Orin 192.168.68.68` у [`summary_crossboard_226.json`](../../data/exp-gpu-01-crossboard/summary_crossboard_226.json)) прямий вимір повного кругового циклу `T_rtt` (`CLOCK_MONOTONIC_RAW` на `PYNQ-Z1`) становить `min = 133.70 мкс`, `p50 = 675.38 мкс`, `p99 = 1183.32 мкс`, **`p99.9 = 3143.41 мкс`**, `max = 3213.37 мкс`, **`σ = 208.51 мкс`**, а розрахункова оцінка одностороннього часу доставки `T_oneway_est = T_pl_mmio + 0.5 * (T_rtt - T_pl_mmio - T_jetson_host) + T_jetson_host` (за припущення симетричної мережевої затримки, оскільки годинники `PYNQ-Z1` та `Jetson Orin` не синхронізовані через PTP, а `RP2040 PIO` у цьому прогоні підключений лише до `PYNQ-Z1`) становить: `min = 73.10 мкс`, `p50 = 344.78 мкс`, `p99 = 853.03 мкс`, **`p99.9 = 2808.53 мкс`** (`187.2×` вище порога `15.0 мкс`) та **`σ = 199.17 мкс`** (`99.6×` вище порога `2.0 мкс`).
   * **Розділення джерел медіанної затримки та хвоста розподілу (`F-3, F-4`):**
     * **На медіані (`p50`):** `95.89%` розрахункового одностороннього часу (`330.61 мкс` із `344.78 мкс`) складає мережевий переліт `T_net_oneway_est = (T_rtt - T_pl_mmio - T_jetson_host) / 2` (`min = 59.85 мкс`, `p50 = 330.61 мкс`, `p99 = 371.19 мкс`, `p99.9 = 443.50 мкс`, `max = 471.86 мкс`, `σ = 35.08 мкс`; для кругового `T_rtt - T_jetson_host` медіана становить `663.35 мкс`, `p99.9 = 889.08 мкс`, `max = 945.85 мкс`).
     * **У хвості розподілу (`p99`, `p99.9`, `max`, `σ`):** оскільки мережева складова `T_net_oneway_est` обмежена зверху значенням `max = 471.86 мкс`, **домінуючий внесок у багатотисячомікросекундний хвіст (`p99.9(T_oneway_est) = 2808.53 мкс`, `σ = 199.17 мкс`) дає системна хост-обробка ОС Linux / сокетний стек та очікування GPU на боці `Jetson AGX Orin` (`T_jetson_host`: `p50 = 12.06 мкс`, `p99 = 520.67 мкс`, `p99.9 = 2471.49 мкс`, `max = 2537.95 мкс`, `σ = 195.75 мкс`)**. Пояснення рідкісних піків `1.15..2.54 мс` у `r1, r2` витісненням контексту драйвера `nvgpu` TSG або планувальником ядра Linux на Orin є **інженерною гіпотезою** (без прямого трасування `ftrace` у цьому прогоні).
   * **Точні епістемічні межі висновку (`F-5`):** цей експеримент **спростовує гіпотезу досягнення `p99.9 <= 15 мкс` (`σ <= 2 мкс`) для програмного міжплатного контуру `UDP/GbE` через ядро Linux та ЦП**. Натомість перехід на ПЛІС із трансиверами PCIe (`Artix-7 / Zynq UltraScale+` для прямого `GPUDirect RDMA`), фізичний тракт `PMOD -> 1.8V J501` через буферизований перетворювач рівнів `SN74AVC8T245` та kernel-bypass `AF_XDP` у цьому експерименті **не вимірювалися** і фіксуються як необхідні, але експериментально ще не перевірені інженерні гіпотези / предмети подальшої перевірки в межах відкритої частини [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226).
2. **Відсутність розпаяного макета перетворювача рівнів `3.3V -> 1.8V` між `PMOD JB` та `J501` (`Part of #226`):**
   * Пряме підключення виводів `PMOD JB` (`3.3V LVCMOS`) до низьковольтного роз'єму розширення `Jetson AGX Orin J501` (`1.8V`) заборонене умовами безпеки [#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226) та [протоколу EXP-GPU-01](protocol.md). Оскільки фізичний монтаж буферизованого перетворювача рівнів `SN74AVC8T245` (або лабораторна перевірка `TXS0108E` з розтягнутим стробом за чеклістом [#247](https://github.com/nick-fedchik/kuzmin-machine/issues/247)) потребує окремих монтажних робіт власника стенда, задача `#226` залишається відкритою (`Part of #226`) для осцилографування змонтованого `SN74AVC8T245` та одночасного двоканального захвату `GP0 (EVENT_START) -> GP1 (GPU_DONE)` на `RP2040 PIO`.
3. **Аварійне завершення післязаписного кроку `&mfs` у підпроцесі `yosys-abc` (`return code 134`) під час синтезу `Yosys 0.69` та відсутність повторного запуску P&R у CI (`F-6, F-7`):**
   * У журналі синтезу [`openxc7_egress_yosys.log`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/openxc7_egress_yosys.log) (рядки `4556–4563`) підпроцес `yosys-abc` спочатку успішно оптимізує та записує вихідний граф у файл (`ABC: + &write -n <abc-temp-dir>/output.aig`), після чого на додатковому кроці `+ &mfs` падає з `Assertion Lit >= 0 failed ... return code 134`. Оскільки файл `output.aig` уже повністю записаний на диск до виклику `&mfs`, `Yosys 0.69` видає попередження `Warning: ABC: execution of command ... failed: return code 134`, зчитує готовий `output.aig` у `8.46.17.6. Executing AIGER frontend` і завершує `check` з `0 reported problems`.
   * Повторний контрольний прогін `build_bram_pipeline_egress.sh` із `--seed 3` підтвердив повну детермінованість синтезованого нетліста (`3 630 SLICE_LUTX`, `1 524 SLICE_FFX`, `1 RAMB36E1`), трасування (`wirelen solved`, `spread`, `legal`) та статичного таймінгу (`101.67 MHz PASS`); при цьому SHA-256 самого файлу `.bit` змінюється між запусками виключно через те, що утиліта `xc7frames2bit` записує поточну дату/час (`c\x00YYYY/MM/DD\x00d\x00HH:MM:SS`) і шлях збірки у 183-байтний заголовок Xilinx `.bit` перед маркером `e\x00`, тоді як 4 045 564 байти конфігураційних фреймів після `e\x00` залишаються ідентичними.
   * Автоматизований тест `test_openxc7_egress_pnr_and_sta_100mhz` у CI перевіряє цілісність і узгодженість збережених у репозиторії логів P&R та SHA-256 бітстріму, але **не виконує повторну збірку `OpenXC7` у CI** (оскільки тулчейн `~/opt/openxc7` із 1.2-ГБ базою `chipdb-xc7z020.bin` розгорнутий локально на стендовому хості).

---

## 2. Метод та постановка експерименту

1. **Фізичний синтез, Place & Route, STA @ 100 МГц та генерація бітстріму `pipeline_egress.bit` у відкритому стеку `OpenXC7`:**
   * Скрипт [`build_bram_pipeline_egress.sh`](../../../../../Engineering/hw/boards/pynq-z1/build_bram_pipeline_egress.sh) синтезує через `OpenXC7 Yosys 0.69` (`synth_xilinx -flatten -abc9 -arch xc7`) повний стек `CFG-P` (`kpol_txn_gate_v2.sv`, `km_concept_micro_engine.sv`, `km_concept_bram.sv`, `km_autonomous_sequencer.sv`, `kpol_bram_pipeline_axi.sv`) разом із серіалізатором [`km_pmod_event_egress.sv`](../../../../../Engineering/hw/rtl/io/km_pmod_event_egress.sv) та топом плати [`kpol_bram_pipeline_pynq_z1_egress_top.v`](../../../../../Engineering/hw/boards/pynq-z1/kpol_bram_pipeline_pynq_z1_egress_top.v).
   * Трасування виконується `nextpnr-himbaechel` із файлом обмежень [`kpol_bram_pipeline_egress.xdc`](../../../../../Engineering/hw/boards/pynq-z1/kpol_bram_pipeline_egress.xdc) (`--device xc7z020clg400-1 --router router2 --seed 3 --freq 100`), після чого `fasm2frames` + `xc7frames2bit` формують бітстрім `pipeline_egress.bit`.
2. **Натурна перевірка бітстріму `pipeline_egress.bit` у кремнії `PYNQ-Z1` (`pynq2`) та захват `LOGICTRACER_PICO_0.5.0` (`100 МГц`, `F-1, F-2, F-9`):**
   * Бітстрім `pipeline_egress.bit` перетворено у формат Zynq FPGA Manager (`pipeline_egress.bin`, `4 045 564` байти) та завантажено у `/sys/class/fpga_manager/fpga0/firmware` на живій платі `pynq2` (`192.168.68.69`, стан `operating`).
   * **Крок А (одиночний функціональний тест каскаду в кремнії):** запущено `/home/xilinx/test_bram_cascade_live.py`, який перевірив запис/читання 256 слів Block RAM, одиночний 4-концептний ендогенний каскад `C0 -> C1 -> C2 -> C3` (`+4` коміти) та `Fail-Closed` відхилення невалідного стимулу (`+1` reject) у [`pynq2_egress_silicon_cascade.log`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/pynq2_egress_silicon_cascade.log).
   * **Крок Б (пакетний генератор `burst_egress_trig.c` для цифрового захвату `LOGICTRACER_PICO_0.5.0`):** для реєстрації часової діаграми піна `JA2_COMMIT` зовнішнім логічним аналізатором на `pynq2` скомпільовано й запущено через `--on-armed` C99-генератор [`burst_egress_trig.c`](../../../../../Engineering/hw/boards/pynq-z1/hil/burst_egress_trig.c). Програма завантажує в Block RAM (`0x40000000`) дескриптори 4-концептного каскаду `C0 -> C1 -> C2 -> C3` (`W2 = 0x01001304` для `C0`, `0x01001303` для `C1..C2`, `0x00000303` для `C3`) і виконує щільний цикл `for (int i = 0; i < 200; ++i)` записів у програмні регістри MMIO `0x00C (REG_PARAM = 10)` та `0x010 (REG_TRIGGER = 1)` з активним очікуванням `while (pl[0x014 >> 2] != 0)`. Оскільки тригер подається програмно через регістр `0x010` шини AXI GP0, а не через зовнішній вхідний пін `JA1`, лінія `CH1 (JA1_STIM)` під час захвату залишається у стані спокою (`0` фронтів), а на `CH2 (JA2_COMMIT, GP3)` генерується рівно **`200` високих імпульсів** (`400` фронтів: `200` наростаючих і `200` спадаючих, розділених `199` низькими паузами тривалістю `250..300 нс`).
   * Захват виконано на свіжопрошитому `LOGICTRACER_PICO_0.5.0` (`/dev/ttyACM0`, утиліта `/tmp/kimi-k3/src/cli/logictracer-cli` версії `0.5.0` з git-коміту `58caf0af5db45086556ec6c17d28bc1a7c799707` репозиторію `/home/mfedchyk/GitHub/nick-fedchik/logictracer`, частота вибірки `100 МГц`, крок `10 нс`, вікно `32 000` відліків = `320 мкс`) і збережено у [`logictracer_egress_ja2_100mhz.log`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/logictracer_egress_ja2_100mhz.log), [`logictracer_egress_ja2_100mhz.json`](../../data/exp-gpu-01-crossboard/logictracer_egress_ja2_100mhz.json) та [`logictracer_egress_ja2_100mhz.vcd`](../../data/exp-gpu-01-crossboard/logictracer_egress_ja2_100mhz.vcd).
3. **Міжплатний контур `PYNQ-Z1 -> GbE -> Jetson AGX Orin J501 Event Mailbox -> 1024 GPU Subscribers` ($R = 5 \times 1\,000$ подій, `F-8`):**
   * **Передавач на `PYNQ-Z1` ([`crossboard_egress_client.c`](crossboard_egress_client.c)):** ініціює подію в апаратному конвеєрі PL (`0x40000000`), очікує завершення каскаду (`REG_STATUS_BUSY == 0`), зчитує оновлений стан листового концепту `C3` з Block RAM, формує 64-бітний кадр події за форматом `km_pmod_event_egress.sv` (`[63:56]=CRC-8 poly 0x07`, `[55:54]=2'b01`, `[53:48]=cid`, `[47:32]=mask16`, `[31:0]=state`) і відправляє його через UDP-сокет із `SO_BUSY_POLL` на `Jetson AGX Orin` (`192.168.68.68`). Перед початком кожної серії з `1 000` подій клієнт виконує одиничну живу перевірку відхилення пошкодженого кадра (інвертований біт `CRC-8` `[60]`, `status == 1`, `crc_drop_count == 1`), тоді як повне побітове мутантне покриття всіх 64 бітів, тегів і поліномів виконується в автоматизованих pytest-тестах (`test_crossboard_egress_226.py` та `test_km_pmod_event_egress.py`).
   * **Приймач і персистентний кернел на `Jetson AGX Orin` ([`crossboard_egress_server.cu`](crossboard_egress_server.cu)):** утримує в резидентному стані на GPU (`GA10B SM 8.7`) персистентний кернел `16 блоків × 64 нитки = 32 варпи = 1 024 підписники` (Q8 ПІД у регістрах SM, секціоновані 128-Б слоти `km_event_ingress_t[16]` та ізольовані 128-Б лінії `isolated_ack[16]` у `cudaHostAllocMapped` Unified Memory за [ADR B6](../../../../../Engineering/decisions/b6-gpu-persistent-kernel-subscribers.md)).
   * Після завершення всіх робіт на платах `pynq1` (`192.168.68.81`) та `pynq2` (`192.168.68.69`) відновлено штатний бітстрім `/lib/firmware/pipeline.bin` і пройдено регресійний HIL-тест `test_kpol_bram_cascade_hil.py` (`2 passed`).

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
| **Критичний шлях (`clk`)** | **`9.84 нс`** | `<= 10.00 нс` | **Запас `+0.164 нс`** | `1.25 нс` логіки + `8.59 нс` трасування (`--seed 3`) |
| **Максимальна частота $F_{\max}$** | **`101.67 МГц`** | `>= 100.00 МГц` | **`PASS @ 100.00 MHz`** | Точне значення в JSON: `101.667343 МГц` |

### 3.2. Натурна верифікація `pipeline_egress.bit` на `pynq2` та захват `LOGICTRACER_PICO_0.5.0` (`100 МГц`, `F-1, F-2`)

Первинні дані: [`pynq2_egress_silicon_cascade.log`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/pynq2_egress_silicon_cascade.log), [`logictracer_egress_ja2_100mhz.log`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/logictracer_egress_ja2_100mhz.log), [`logictracer_egress_ja2_100mhz.json`](../../data/exp-gpu-01-crossboard/logictracer_egress_ja2_100mhz.json) (SHA-256: `8b1232ccb600cb5f0bad449c6404197ea9abfe1d0bb965efa2589ed4b6689ffb`), [`logictracer_egress_ja2_100mhz.vcd`](../../data/exp-gpu-01-crossboard/logictracer_egress_ja2_100mhz.vcd) (SHA-256: `2f8df8be092b6bc6ffd084033af2970a799dd395b3a623e3d366df52f5006718`).

* **Одиночний функціональний прогін (`pynq2_egress_silicon_cascade.log`):** після програмування `pipeline_egress.bin` у `/sys/class/fpga_manager/fpga0/firmware` на `pynq2` (`192.168.68.69`) кристал перейшов у стан `operating`, повернув ідентифікатор `0x4B504D43 ('KPMC')`, пройшов 100% верифікацію 256 слів Block RAM, виконав автономний каскад `C0 -> C1 -> C2 -> C3` (`Events: +4, Commits: +4, Rejects: +0`) та заблокував невалідний стимул `p = 100 >= 50` (`Commits: +0, Rejects: +1`).
* **Пакетний захват `LOGICTRACER_PICO_0.5.0` (`logictracer_egress_ja2_100mhz.json` / `.vcd`, `100 МГц`, `32 000` вибірок = `320 мкс`) під час виконання `burst_egress_trig.c` (`200` ітерацій циклу):**
  * На каналі `CH2 (JA2_COMMIT, GP3)` зафіксовано **`200` високих імпульсів** (`pulse_count_high = 200`, `rising_edges = 200`, `falling_edges = 200`, `transitions = 400`) та **`199` низьких пауз між ними** (`pulse_count_low = 199`; у текстовій таблиці CLI стовпець `PULSES = 399` показує суму `pulse_count_high + pulse_count_low = 200 + 199`), при `0` глітчів (`glitch_detection.count = 0`).
  * **Висока фаза (`high_pulse_width_us`):** для всіх `200` каскадних імпульсів `min = mean = max = 0.340 мкс` (**`340 нс`** = `34` відліки по `10 нс`).
  * **Низька фаза (`low_pulse_width_us`) та період повторення:** пауза між сусідніми каскадами під час опитування `REG_BUSY` і запису `REG_TRIGGER` процесором ARM Cortex-A9 через AXI GP0 становить `min = 250 нс` (що відповідає стовпцю `MIN PW = 250 ns` у зведеному виводі CLI), `mean = 260.25 нс`, `max = 300 нс`; медіанний період повторення каскадів становить `median_period_ns = 600.0 нс` (`mean_frequency_hz = 1.66597 МГц`, загальна тривалість пачки з 200 каскадів — `last_edge_us = 119.79 мкс`).
  * **Узгодженість із потактовою моделлю розширювача `ja2` (`F-2`):** у топі `kpol_bram_pipeline_pynq_z1_egress_top.v` кожен однотактовий імпульс `hw_commit` перезавантажує 10-тактовий лічильник розширювача `ja_commit_cnt_q <= 4'd10` (`100 нс`). Оскільки в 4-концептному каскаді `C0 -> C1 -> C2 -> C3` чотири коміти відбуваються з інтервалом `8` тактів (`80 нс < 100 нс`), лічильник `ja_commit_cnt_q` перезавантажується на кожному з 4 комітів до свого обнулення, зливаючи 4 коміти в один суцільний високий імпульс розрахункової ширини $3 \times 80\text{ нс} + 100\text{ нс} = 340\text{ нс}$ (`34` такти @ `100 МГц`). Оскільки окремі 80-нс інтервали всередині злитого імпульсу на `JA2_COMMIT` напряму не розділяються, виміряна ширина `340 нс` (`min = max = 340 нс` на всіх 200 каскадах) інтерпретується як точне узгодження з потактовою RTL-моделлю `3 × 80 + 100 нс`.

### 3.3. Міжплатний контур `PYNQ-Z1 -> GbE -> Jetson AGX Orin J501 (1024 підписники)` ($R = 5 \times 1\,000 = 5\,000$ подій)

Первинні дані: [`run-01-crossboard-5x1000.log`](../../data/exp-gpu-01-crossboard/run-01-crossboard-5x1000.log), [`crossboard_r1.json`](../../data/exp-gpu-01-crossboard/crossboard_r1.json)..[`crossboard_r5.json`](../../data/exp-gpu-01-crossboard/crossboard_r5.json), [`summary_crossboard_226.json`](../../data/exp-gpu-01-crossboard/summary_crossboard_226.json), [`sha256sums.txt`](../../data/exp-gpu-01-crossboard/sha256sums.txt). Перцентилі `p50`, `p99`, `p99.9` обчислені методом *nearest-rank* ($\lceil (p/100) \cdot N \rceil - 1$) у [`crossboard_frame.py`](crossboard_frame.py).

#### Попрогонна таблиця ($R = 5$, по $1\,000$ подій у прогоні)

| Прогін (`Файл`) | Подій $N$ | Одиничний тест відхилення CRC-8 (`drop`) | Розбіжностей станів GPU vs CPU (`1024` підп.) | `GPU Math p50` (`%globaltimer`, нс) | `GPU SM E2E p50` (`%globaltimer`, нс) | `GPU SM E2E p99.9` (нс) | Оцінка `One-Way Est p50` (мкс) | Оцінка `One-Way Est p99` (мкс) | Оцінка `One-Way Est p99.9` (мкс) | Оцінка `One-Way Est σ` (мкс) | Вимір `RTT p50` (мкс) | Вимір `RTT p99.9` (мкс) |
| :--- | ---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `r1` ([`crossboard_r1.json`](../../data/exp-gpu-01-crossboard/crossboard_r1.json)) | `1 000` | `PASS (1)` | `0` | `64` | `2 048` | `1 152 992` | `344.95` | `838.93` | `2 827.23` | `196.44` | `675.75` | `3 160.13` |
| `r2` ([`crossboard_r2.json`](../../data/exp-gpu-01-crossboard/crossboard_r2.json)) | `1 000` | `PASS (1)` | `0` | `64` | `2 016` | `1 145 984` | `345.66` | `1 291.35` | `2 808.53` | `201.48` | `677.06` | `3 143.41` |
| `r3` ([`crossboard_r3.json`](../../data/exp-gpu-01-crossboard/crossboard_r3.json)) | `1 000` | `PASS (1)` | `0` | `64` | `1 952` | `2 944` | `345.07` | `847.96` | `2 660.00` | `186.61` | `676.06` | `2 989.89` |
| `r4` ([`crossboard_r4.json`](../../data/exp-gpu-01-crossboard/crossboard_r4.json)) | `1 000` | `PASS (1)` | `0` | `64` | `2 016` | `2 912` | `344.25` | `842.37` | `2 835.88` | `200.60` | `674.34` | `3 166.15` |
| `r5` ([`crossboard_r5.json`](../../data/exp-gpu-01-crossboard/crossboard_r5.json)) | `1 000` | `PASS (1)` | `0` | `64` | `1 952` | `2 944` | `343.95` | `1 364.04` | `2 876.77` | `210.35` | `673.54` | `3 213.37` |
| **Зведена вибірка (`5 000` подій)** | **`5 000`** | **`5/5 PASS`** | **`0 / 5 120 000`** | **`64`** | **`1 952..2 048`** | **`2 912..1 152 992`** | **`344.78`** | **`853.03`** | **`2 808.53`** | **`199.17`** | **`675.38`** | **`3 143.41`** |

#### По-подієва декомпозиція наскрізного бюджету часу ($N = 5\,000$ подій, `F-3, F-4, F-5`)

Усі рядки нижче обчислено строго по-подієво з `crossboard_r1..r5.json` скриптом [`crossboard_frame.py`](crossboard_frame.py) та збережено у [`summary_crossboard_226.json`](../../data/exp-gpu-01-crossboard/summary_crossboard_226.json). Сума середніх арифметичних складових точно дорівнює середньому повного часу:
$$\overline{T}_{\text{pl\_mmio}} + \overline{T}_{\text{net\_rtt}} + \overline{T}_{\text{jetson\_host}} = 2.1775 + 656.7101 + 32.6009 = 691.4885\ \mu\text{с} = \overline{T}_{\text{rtt}}.$$

| Етап контуру | Спосіб вимірювання / формула | `min` (мкс) | `p50` (мкс) | `p99` (мкс) | `p99.9` (мкс) | `max` (мкс) | `mean` (мкс) | `σ` (мкс) |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1. Ядро ПЛІС `CFG-P` (1 концепт / 4-концептний каскад) | Такти PL @ `100 МГц` + `RP2040 PIO` (`340 нс` з `100 нс` розширювачем) | `0.080 / 0.320` | **`0.080 / 0.320`** | `0.080 / 0.320` | `0.080 / 0.320` | `0.080 / 0.320` | `0.080 / 0.320` | `0.000` |
| 2. Серіалізація `km_pmod_event_egress` (`PAR8` / `SPI 50 МГц`) | Такти PL (`17` / `129` тактів @ `100 МГц`) | `0.170 / 1.290` | **`0.170 / 1.290`** | `0.170 / 1.290` | `0.170 / 1.290` | `0.170 / 1.290` | `0.170 / 1.290` | `0.000` |
| 3. Тригер MMIO `Cortex-A9 -> AXI GP0 -> PL каскад -> читання BRAM` (`T_pl_mmio`) | Прямий вимір `CLOCK_MONOTONIC_RAW` на `PYNQ-Z1` | `2.037` | **`2.148`** | `2.314` | `3.477` | `72.560` | `2.1775` | `1.1936` |
| 4. Регістрова математика `1 024` ПІД-підписників у `16 SM` GPU | Прямий вимір `%globaltimer` на `Jetson AGX Orin` | `0.064` | **`0.064`** | `0.064` | `0.096` | `0.096` | `0.0640` | `< 0.010` |
| 5. Повний цикл `16 SM` GPU (`L2 acquire -> 1024 підписники -> isolated_ack release`) | Прямий вимір `%globaltimer` на `Jetson AGX Orin` (`r3..r5` / `r1..r2`) | `1.888` | **`2.016`** | `2.752` | `2.944` (`r3..r5`) / `1 152.992` (`r1`) | `1 152.992` | — | — |
| 6. Хост-обробка на `Jetson Orin` (`CRC-8 + 16×stlr + очікування GPU + CPU-модель`, `T_jetson_host`) | Прямий вимір `CLOCK_MONOTONIC_RAW` на `Jetson Orin` | `9.792` | **`12.064`** | `520.672` | **`2 471.488`** | **`2 537.952`** | `32.6009` | **`195.7514`** |
| 7а. Круговий мережевий транспорт + MMIO PYNQ (`T_rtt - T_jetson_host`) | По-подієва різниця `samples_rtt_us - samples_jetson_host_us` | `121.872` | **`663.354`** | `744.445` | `889.081` | `945.851` | `658.8876` | `70.1825` |
| 7б. Чистий круговий мережевий транспорт `GbE` (`T_net_rtt`) | По-подієва різниця `T_rtt - T_pl_mmio - T_jetson_host` | `119.694` | **`661.213`** | `742.384` | `886.995` | `943.716` | `656.7101` | `70.1664` |
| 7в. Розрахункова оцінка мережі в один бік (`T_net_oneway_est`) | По-подієва оцінка `(T_rtt - T_pl_mmio - T_jetson_host) / 2` | `59.847` | **`330.6065`** | `371.192` | `443.4975` | `471.858` | `328.3550` | `35.0832` |
| **8. Розрахункова оцінка `One-Way Est` (`PYNQ-Z1 -> Jetson GPU ACK`)** | По-подієва оцінка `T_pl_mmio + T_net_oneway_est + T_jetson_host` | **`73.096`** | **`344.781`** | **`853.025`** | **`2 808.528`** | **`2 876.769`** | **`363.1332`** | **`199.1650`** |
| **9. Прямий вимір `RTT` (`PYNQ-Z1 -> Jetson GPU -> PYNQ-Z1`)** | Прямий вимір `CLOCK_MONOTONIC_RAW` на `PYNQ-Z1` ($N = 5\,000$) | **`133.704`** | **`675.384`** | **`1 183.317`** | **`3 143.409`** | **`3 213.366`** | **`691.4885`** | **`208.5090`** |

---

## 4. Перевірка гіпотези та Попперівського критерію фальсифікації (#226)

| Критерій ([#226](https://github.com/nick-fedchik/kuzmin-machine/issues/226), [протокол EXP-GPU-01](protocol.md)) | Поріг прийняття / фальсифікації | Експериментальний результат | Статус |
| :--- | :--- | :--- | :--- |
| 1. Фізичний Place & Route та STA `kpol_bram_pipeline_pynq_z1_egress_top` в `OpenXC7` | $F_{\max} \ge 100.0\text{ МГц}$, `0` помилок `check` | **`F_max = 101.67 МГц`** (`PASS @ 100.00 MHz`), `3 630 LUT`, `1 524 FF`, `1 RAMB36E1`, бітстрім `7bfd5f57...` | **Виконано** |
| 2. Жива перевірка `pipeline_egress.bit` на `PYNQ-Z1` + захват `RP2040 PIO` (`100 МГц`) | Робота каскаду в кремнії, стабільний імпульс `JA2_COMMIT`, `0` глітчів | Каскад `C0->C1->C2->C3` верифіковано (`+4` коміти), **`200` високих імпульсів** (`400` переходів) на `CH2`, `min = max = 340 нс` (узгоджується з моделлю `3 × 80 + 100 нс`), `0` глітчів | **Виконано** |
| 3. Цілісність 64-бітного кадра з `CRC-8` (`poly 0x07`) та побітова точність `1 024` підписників GPU | Відхилення пошкоджених кадрів (`neg_crc_test` + unit-мутанти), `0` розбіжностей GPU vs CPU | 5 одиничних пошкоджених кадрів у живому каналі відхилено (`status=1`) + убито всі 64 однобітові/тегові/поліноміальні мутанти в unit-тестах; **`0` розбіжностей** на `5 120 000` оновленнях станів | **Виконано** |
| 4. **Попперівський критерій фальсифікації програмного міжплатного контуру `UDP/GbE`** | Фальсифікується, якщо `p99.9(T_e2e) > 15.0 мкс` або `σ > 2.0 мкс` | **`p99.9(RTT) = 3143.41 мкс`**, **`p99.9(One-Way Est) = 2808.53 мкс > 15.0 мкс`** (`187.2×`), **`σ = 199.17 мкс > 2.0 мкс`** (`99.6×`) | **Гіпотезу на `UDP/GbE` спростовано** |

### Архітектурний висновок для [ADR B6](../../../../../Engineering/decisions/b6-gpu-persistent-kernel-subscribers.md) (`F-4, F-5`)

1. **Внутрішньокристальні обчислювачі вкладаються в мікросекундний бюджет:** `80 нс` на перехід у `CFG-P` на ПЛІС (`320 нс` на 4-концептний каскад) + `170 нс` паралельної видачі `PAR8` + `64 нс` регістрової математики на GPU (`2.02 мкс` медіани з урахуванням когерентної тканини `L2/SCF` для `1 024` підписників на 16 SM).
2. **Програмний міжплатний контур `UDP/GbE` через ядро Linux не задовольняє критерій `<= 15 мкс` ні за медіаною, ні за хвостом:**
   * **На медіані (`p50 = 344.78 мкс` для `One-Way Est` / `675.38 мкс` для `RTT`)** основну затримку створює мережевий тракт `GbE + сокетний стек ОС` (`T_net_oneway_est p50 = 330.61 мкс`, або `95.89%` медіани).
   * **У хвості розподілу (`p99.9 = 2808.53 мкс`, `σ = 199.17 мкс`)** основним джерелом викидів є системна хост-обробка та очікування на боці `Jetson AGX Orin` (`T_jetson_host`: `p99.9 = 2471.49 мкс`, `max = 2537.95 мкс`, `σ = 195.75 мкс`), тоді як мережева складова `T_net_oneway_est` має `max = 471.86 мкс`.
3. **Наступні кроки та неперевірені гіпотези:** оскільки `XC7Z020` не має трансиверів PCIe (`GTP/GTX`), перехід на ПЛІС із апаратним **PCIe (`Artix-7 / Zynq UltraScale+`) для прямого `GPUDirect RDMA`** (без участі хост-потоку Linux на Orin), а також прямий цифровий тракт `PMOD -> 1.8V J501` через `SN74AVC8T245` фіксуються як необхідні інженерні гіпотези для окремої експериментальної перевірки.

---

## 5. Відтворення та контрольні суми SHA-256

### 5.1. Команди відтворення

```bash
# 1. Збірка бітстріму pipeline_egress.bit у відкритому стеку OpenXC7 (локально за наявності ~/opt/openxc7):
BUILD_DIR=/home/mfedchyk/GitHub/nick-fedchik/km-wt-226-egress-e2e/.build_egress \
  bash Engineering/hw/boards/pynq-z1/build_bram_pipeline_egress.sh

# 2. Натурний захват пачки з 200 каскадів (burst_egress_trig.c) аналізатором LOGICTRACER_PICO_0.5.0 @ 100 МГц:
/tmp/kimi-k3/src/cli/logictracer-cli capture \
  --port /dev/ttyACM0 --no-session --freq 100M --samples 32k \
  --channels 1:JA1_STIM,2:JA2_COMMIT,3:JA3_REJECT,4:JA4_BUSY \
  --trigger 2:rising --timeout 5000 \
  --on-armed "sshpass -p xilinx ssh -o StrictHostKeyChecking=no xilinx@192.168.68.69 \"echo xilinx | sudo -S /home/xilinx/burst_egress_trig\"" \
  --out-json Engineering/validation/kpol-cme/pmod-event-egress-230/raw/logictracer_egress_ja2_100mhz.json \
  --out-vcd Engineering/validation/kpol-cme/pmod-event-egress-230/raw/logictracer_egress_ja2_100mhz.vcd \
  --summary

# 3. По-подієва агрегація статистики міжплатних прогонів R = 5 x 1000 та перевірка критерію Поппера:
python3 Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-01/crossboard_frame.py \
  --summarize Research/studies/fpga-gpu-symbiosis/data/exp-gpu-01-crossboard/crossboard_r*.json

# 4. Автоматизовані тести (включно з негативними мутантами CRC-8 та перевіркою артефактів):
python3 -m pytest -v \
  Engineering/hw/tests/test_km_pmod_event_egress.py \
  Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-01/tests/test_crossboard_egress_226.py
```

### 5.2. Реєстр первинних файлів і SHA-256

| Файл | SHA-256 | Призначення |
| :--- | :--- | :--- |
| `pipeline_egress.bit` ([`openxc7_egress_bitstream.sha256`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/openxc7_egress_bitstream.sha256)) | `7bfd5f5742334a7f08f2a290d5dde0a241e5bd06ced64c39d82e70021f30bbce` | Бітстрім `kpol_bram_pipeline_pynq_z1_egress_top` (`4 045 747` Б) |
| [`openxc7_egress_yosys.log`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/openxc7_egress_yosys.log) | `a79934e3dc8b14ed18c8054b423be83e67547d4e96cb84faad0f5b980fc16d23` | Журнал синтезу `OpenXC7 Yosys 0.69` |
| [`openxc7_egress_nextpnr.log`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/openxc7_egress_nextpnr.log) | `a7836f3b9a07666d99d4bc87f7bb3c2520b660f9bdd34cfc6e1371673ec67227` | Журнал P&R та STA `nextpnr-himbaechel` (`101.67 МГц PASS`) |
| [`openxc7_egress_nextpnr_report.json`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/openxc7_egress_nextpnr_report.json) | `4aa2770e14d46bb30ccd560e0cc3a155ea6beb7c43aaab02e0e3a48ad1fb3f54` | Машиночитний звіт ресурсів і таймінгу `nextpnr` |
| [`pynq2_egress_silicon_cascade.log`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/pynq2_egress_silicon_cascade.log) | `9bc430da62efe03cf3b3353bc6da930008cb611f285e93d3b97bd36c69578ea5` | Жива перевірка `pipeline_egress.bit` на кремнії `pynq2` |
| [`logictracer_egress_ja2_100mhz.log`](../../../../../Engineering/validation/kpol-cme/pmod-event-egress-230/raw/logictracer_egress_ja2_100mhz.log) | `d65710e2ed2b323e6e43779d1b65c67b37e6466d79f965a09a92aad3e8b1dc79` | Журнал захвату `LOGICTRACER_PICO_0.5.0` @ `100 МГц` (`58caf0af`) |
| [`logictracer_egress_ja2_100mhz.json`](../../data/exp-gpu-01-crossboard/logictracer_egress_ja2_100mhz.json) | `8b1232ccb600cb5f0bad449c6404197ea9abfe1d0bb965efa2589ed4b6689ffb` | Захват `LOGICTRACER_PICO_0.5.0` @ `100 МГц` (`200` імпульсів `JA2_COMMIT` по `340 нс`) |
| [`logictracer_egress_ja2_100mhz.vcd`](../../data/exp-gpu-01-crossboard/logictracer_egress_ja2_100mhz.vcd) | `2f8df8be092b6bc6ffd084033af2970a799dd395b3a623e3d366df52f5006718` | Хвильова діаграма VCD захвату `RP2040 PIO` (`100 МГц`) |
| [`run-01-crossboard-5x1000.log`](../../data/exp-gpu-01-crossboard/run-01-crossboard-5x1000.log) | `73bedc4553e40b2632d71a05566316c1e76297a3e5c5b76c9fe2006e7f6750e9` | Протокол виконання 5 міжплатних серій `PYNQ-Z1 -> Jetson Orin` |
| [`crossboard_r1.json`](../../data/exp-gpu-01-crossboard/crossboard_r1.json) | `35a4a9a8ff1ed5409fed22fd698240833635892ab9c8c69d8db5427c4f47e96e` | Сирі вимірювання серії `r1` (`1 000` подій) |
| [`crossboard_r2.json`](../../data/exp-gpu-01-crossboard/crossboard_r2.json) | `471a8c6e029bc798baa082a9f9c9a1bb576470df974d3aec139c2cd155c3c4d4` | Сирі вимірювання серії `r2` (`1 000` подій) |
| [`crossboard_r3.json`](../../data/exp-gpu-01-crossboard/crossboard_r3.json) | `ece7919075a5213611921b279934931f515e954db4be9f40e31f4b11efaa5316` | Сирі вимірювання серії `r3` (`1 000` подій) |
| [`crossboard_r4.json`](../../data/exp-gpu-01-crossboard/crossboard_r4.json) | `d726dcd4190ec5b7af836484b1d88ded364acc61f6b40c1aed59889c43370cc4` | Сирі вимірювання серії `r4` (`1 000` подій) |
| [`crossboard_r5.json`](../../data/exp-gpu-01-crossboard/crossboard_r5.json) | `671cddf79bd48aef8d662edd7f20cd65a2bf5831f467842d9bc43a738d3bc392` | Сирі вимірювання серії `r5` (`1 000` подій) |
| [`summary_crossboard_226.json`](../../data/exp-gpu-01-crossboard/summary_crossboard_226.json) | `a692236e282b2ebb7ab8e981be893ed4f0645d7fa7a00e83ffb0a6cf9f804c53` | Зведений статистичний звіт `R = 5 x 1 000` (з по-подієвою декомпозицією) та вердикт Поппера |

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.1 | 2026-11-17 | Враховано зауваження рецензії `claude-sonnet-5.5` у [PR #268](https://github.com/nick-fedchik/kuzmin-machine/pull/268#issuecomment-6950179505) (`F-1..F-9`): перезнято захват на оновленій прошивці `LOGICTRACER_PICO_0.5.0`, виправлено опис на **`200` високих імпульсів** (`400` переходів, `199` низьких пауз по `250..300 нс`) із додаванням C99-генератора [`burst_egress_trig.c`](../../../../../Engineering/hw/boards/pynq-z1/hil/burst_egress_trig.c); перераховано по-подієву декомпозицію (`T_net_oneway_est`: `p50 = 330.61 мкс`, `p99.9 = 443.50 мкс`, `max = 471.86 мкс`, `σ = 35.08 мкс`) і чітко відокремлено медіану мережі від хвоста `T_jetson_host` (`p99.9 = 2471.49 мкс`, `max = 2537.95 мкс`); явно позначено `One-Way Est` як розрахункову оцінку та звужено формулювання висновку до доведеного спростування програмного `UDP/GbE` контуру; задокументовано поведінку `&mfs` у `yosys-abc` (`return code 134` після запису `output.aig`), вилучено непідкріплені логами згадки про `seed 1/2` і зафіксовано коміт `logictracer-cli` (`58caf0af`). |
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
| TSG | Time Slice Group планувальника драйвера `nvgpu`. |
| WNS | Worst Negative Slack (найгірший часовий запас відносно періоду тактового сигналу). |
