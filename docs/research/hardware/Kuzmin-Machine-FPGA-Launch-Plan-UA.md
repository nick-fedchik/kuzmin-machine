# План запуску Машини Кузьміна на FPGA

> **Внутрішня робоча копія, не публікація; міграція не є науковим прийняттям.** Перенесено з `drafts@774d575:KuzminMachine/02-engineering-hardware/Kuzmin-Machine-FPGA-Launch-Plan-UA.md` 2026-11-10, Issue #84. Міграція не підтверджує тверджень, прогнозів чи самоприсвоєних статусів. Незмінний оригінал і SHA-256 — у реєстрі міграції.


- **Оновлено:** 2026-11-08
- **Версія RTL-проєкту:** `0.3.0` (SemVer, експериментальна до `1.0.0`)
- **Ціль:** PYNQ-Z1 / Zynq-7020, part `xc7z020clg400-1`
- **Загальний стан:** RTL і AXI4-Lite прототип перевірені симуляцією; власний target-specific `.bit` зібрано openXC7; проведено успішний апаратний HIL-тест у volatile PL на платі `pynq2` (MMIO AXI4-Lite `0x40000000`). Після верифікації штатний оверлей `base.bin` відновлено в SRAM.

## Межі прототипу

`rtl/kpol_txn_gate.sv` реалізує однословну атомарну транзакцію commit/reject. `rtl/kpol_txn_gate_axi_lite.sv` додає до неї MMIO інтерфейс для PYNQ. Умови candidate/assumption/invariant/hazard подаються через регістр, а не обчислюються в PL. Це перевірений інтеграційний зріз, **не** повне ядро Машини Кузьміна, не інтерпретатор KPOL і не доказ запуску МК на FPGA.

У попередніх кроках виконано commissioning плати: на `pynq1` та `pynq2` працював базовий PYNQ overlay. Створено власний PS7/AXI top-level і target-specific `.bit` за допомогою відкритого тулчейну openXC7, проведено завантаження образу у volatile PL на `pynq2` та верифіковано транзакції через MMIO на фізичному кремнії.

## SemVer та ідентифікація артефактів

Файл [`VERSION`](../../archive/drafts-774d575-kuzminmachine.tar.gz) (член архіву: `02-engineering-hardware/VERSION`) є єдиним джерелом версії RTL-проєкту. `0.2.0` додає експериментальний AXI4-Lite інтерфейс до початкового `0.1.0` транзакційного блока. До `1.0.0` нова сумісна функція підвищує MINOR, сумісне виправлення — PATCH; API залишається експериментальним. Після `1.0.0` несумісна зміна апаратного/програмного контракту підвищує MAJOR.

Для поточного `.bit` записані part, openXC7 P&R результат і SHA-256 у §6 та §7. Пропонований шаблон імені: `kpol-txn-gate-<SemVer>+<part>.<commit>.bit`.

## Послідовний план і журнал

Команди в цьому документі виконуються з каталогу `KuzminMachine/`, якщо не зазначено інше. Позначка «раніше виконано» посилається на задокументовані результати попередніх кроків; нові RTL-перевірки нижче виконано під час цього оновлення.

### 0. Зафіксувати початковий стан — виконано раніше

На початку поточного циклу робочий стан був чистим на `main`, commit `b13b6b1a8cd2` (`Add official TRL Assessment Memo v1.0`). Файли цього оновлення після цього commit залишаються локальними змінами; вони не є commit або push.

### 1. Перевірити плату й відокремити базовий overlay від образу МК — виконано раніше

Команди діагностики, виконані на платах:

```sh
ssh -o BatchMode=yes -o ConnectTimeout=8 xilinx@pynq2 \
  'hostname; uname -a; cat /sys/class/fpga_manager/fpga0/state'
ssh -o BatchMode=yes -o ConnectTimeout=8 xilinx@pynq2 \
  '/usr/local/share/pynq-venv/bin/python -c "import pynq; print(pynq.__version__)"'
ssh -o BatchMode=yes -o ConnectTimeout=8 xilinx@pynq2 \
  'sha256sum /lib/firmware/base.bin'
```

Зафіксовано:

- Користувач підтвердив, що `pynq1` і `pynq2` — PYNQ-Z1. `pynq2` працює під PYNQ `3.1.1`; FPGA Manager звітував `operating`.
- На обох платах `base.bin` однаковий: 4,045,564 байти, SHA-256 `8f7824113ffd859f3acc899c137413298a5a89fc46051113739cbea5b26352d4`. Це підтвердження базового образу, не власного бітстріму МК.
- У `~/vida` runbook `MEMO-099` підтверджує використання `BaseOverlay("base.bit")` та базові LED/AXI-перевірки. Твердження `TASK-TLU-031` про EVM фізичне розгортання не підтверджено однозначно: наявний benchmark керує LED через `BaseOverlay`, а не EVM через MMIO; у runbook власний EVM bitstream лишається незавершеним. У доступних артефактах не знайдено MK `.bit`/`.bin`/`.hwh`/`.xsa`.
- Отже, попередній стенд працював із базовим overlay; це не доказ, що PL запрограмована образом МК. Поточний `base.bin` не перезаписувався.

**Висновок:** GO для RTL та MMIO-прототипу; NO-GO для твердження «МК уже запрограмована» або для завантаження неіснуючого власного образу.

### 2. Перевірити базовий транзакційний RTL — виконано раніше

```sh
iverilog -g2012 -Wall -s kpol_txn_gate_tb -o /tmp/kpol_txn_gate_tb.vvp \
  02-engineering-hardware/rtl/kpol_txn_gate.sv \
  02-engineering-hardware/tb/kpol_txn_gate_tb.sv
vvp /tmp/kpol_txn_gate_tb.vvp
verilator --lint-only --Wall --top-module kpol_txn_gate \
  02-engineering-hardware/rtl/kpol_txn_gate.sv
yosys -Q -p 'read_verilog -sv 02-engineering-hardware/rtl/kpol_txn_gate.sv; hierarchy -top kpol_txn_gate; proc; opt; check'
```

Результат: `PASS: KPOL single-event transaction gate`; Verilator lint без попереджень; Yosys `check` — 0 проблем. Попередній XC7 family mapping тільки для цього core дав 112 клітин та оцінку Yosys 21 LC. Це не P&R і не бітстрім.

### 3. Додати PYNQ-керований AXI4-Lite прототип — виконано

Додано `rtl/kpol_txn_gate_axi_lite.sv` з окремими AW/W handshake, byte strobes, fail-closed reset, sticky status та AXI error responses. Інтерфейс адреси має ширину 6 біт; data bus — 32 біти.

| Offset | Регістр | Контракт |
| :---: | :--- | :--- |
| `0x00` | `CANDIDATE_VALUE` (R/W) | Кандидатне значення, підтримує byte strobes |
| `0x04` | `CONDITIONS` (R/W) | `[0]` candidate known; `[1]` assumption known; `[2]` assumption true; `[3]` invariant known; `[4]` invariant true; `[5]` hazard known; `[6]` hazard true |
| `0x08` | `COMMAND` (W) | Запис `1` у `[0]` запускає транзакцію |
| `0x0C` | `STATUS` (R) | `[0]` done; `[1]` committed; `[2]` rejected; `[3]` rejected input; `[4]` rejected invariant; `[5]` changed; `[6]` hazard observed; `[7]` unknown hazard; `[8]` busy |
| `0x10` | `STATE` (R) | Поточний committed state |
| `0x14` | `IDENTIFICATION` (R) | `0x4B504F4C` (`KPOL`) |

Умови нульові після reset, тому commit неможливий, доки програма явно не подасть відомі істинні assumption та invariant. Під час `busy` запис параметрів блокується. Реалізований прототип описаний в архітектурній специфікації, §6.3; він не замінює запропонований регістровий простір майбутнього повного MK Overlay.

### 4. Перевірити core і AXI4-Lite тестбенчі — виконано під час цього оновлення

```sh
iverilog -g2012 -Wall -s kpol_txn_gate_tb -o /tmp/kpol_txn_gate_tb.vvp \
  02-engineering-hardware/rtl/kpol_txn_gate.sv \
  02-engineering-hardware/tb/kpol_txn_gate_tb.sv
vvp /tmp/kpol_txn_gate_tb.vvp
iverilog -g2012 -Wall -s kpol_txn_gate_axi_lite_tb \
  -o /tmp/kpol_txn_gate_axi_lite_tb.vvp \
  02-engineering-hardware/rtl/kpol_txn_gate.sv \
  02-engineering-hardware/rtl/kpol_txn_gate_axi_lite.sv \
  02-engineering-hardware/tb/kpol_txn_gate_axi_lite_tb.sv
vvp /tmp/kpol_txn_gate_axi_lite_tb.vvp
verilator --lint-only --Wall --top-module kpol_txn_gate_axi_lite \
  02-engineering-hardware/rtl/kpol_txn_gate.sv \
  02-engineering-hardware/rtl/kpol_txn_gate_axi_lite.sv
verilator --lint-only --timing --Wall \
  --top-module kpol_txn_gate_axi_lite_tb \
  02-engineering-hardware/rtl/kpol_txn_gate.sv \
  02-engineering-hardware/rtl/kpol_txn_gate_axi_lite.sv \
  02-engineering-hardware/tb/kpol_txn_gate_axi_lite_tb.sv
yosys -Q -p 'read_verilog -sv 02-engineering-hardware/rtl/kpol_txn_gate.sv 02-engineering-hardware/rtl/kpol_txn_gate_axi_lite.sv; hierarchy -check -top kpol_txn_gate_axi_lite; proc; opt; check'
```

Результат: обидва Icarus testbench — `PASS`; Verilator lint core/wrapper — успішно; timed lint testbench — успішно; Yosys structural check повідомив `Found and reported 0 problems`. AXI testbench включає незалежні AW/W канали, часткові byte writes, commit, input/invariant reject, hazard/unknown-hazard, незмінність стану після reject, невідомий offset і некоректну команду.

### 5. Виконати попередній XC7 family mapping — виконано під час цього оновлення

```sh
yosys -Q -p 'read_verilog -sv 02-engineering-hardware/rtl/kpol_txn_gate.sv 02-engineering-hardware/rtl/kpol_txn_gate_axi_lite.sv; synth_xilinx -family xc7 -top kpol_txn_gate_axi_lite -noiopad -noclkbuf; stat'
```

Використаний Yosys `0.52`. У зведеній ієрархії після мапінгу: 515 клітин, зокрема `FDCE 169`, `INV 171`, `LUT2 29`, `LUT3 48`, `LUT4 7`, `LUT5 51`, `LUT6 32`, `MUXF7 7`, `MUXF8 1`. Це тільки technology mapping сімейства XC7 без точного part, I/O pads, P&R, timing/STA, DRC чи `.bit`; цифри не є фінальним ресурсним звітом плати.

### 6. Зібрати target-specific overlay — частково виконано

На хості у `/home/mfedchyk/opt/openxc7/` доступні Yosys `0.69`, `nextpnr-himbaechel` з `nextpnr-xilinx` сумісною обгорткою, Project X-Ray DB для Zynq-7000 та `fasm2frames`. Підтверджена ціль: `xc7z020clg400-1` (PYNQ-Z1).

Додано `rtl/kpol_txn_gate_pynq_z1_top.v`: PS7 M_AXI_GP0 з'єднано з AXI4-Lite шлюзом, використано FCLK0, а вікно `0x40000000–0x4000003F` декодується окремо; інші адреси отримують `DECERR`. Додано `build_pynq_z1_openxc7.sh` та ручний PYNQ loader/MMIO тест `pynq_z1_manual_mmio_test.py`. OpenXC7 не створює `.hwh`; тест працюватиме з ручною адресою MMIO `0x40000000`.

Результат `build_pynq_z1_openxc7.sh`:

- Yosys `synth_xilinx -flatten -abc9 -arch xc7` синтезував top із `PS7` та `BUFG`; `check` знайшов 0 проблем. Мапінг містить 169 `FDCE` та 194 LUT.
- ChipDB для `xc7z020` згенерована (38,933,046 байтів). `nextpnr-xilinx` завершив розміщення/трасування без помилок; його звіт показує 237.19 MHz при заданій цілі 100 MHz. Це оцінка openXC7 для розведеного дизайну, не вимірювання на платі й не доказ HIL.
- FASM згенеровано (500,946 байтів); `.bit` зібрано відкритою парою `fasm2frames` + `xc7frames2bit`. Артефакт: `/home/mfedchyk/opt/openxc7-build/kuzmin-pynq-z1/kpol_pynq.bit`, 4,045,719 байтів, SHA-256 `f621ca5d551ea8b21f416fb660d8444f6df14da0e5fa59e4e8de1b7536ccc287`; заголовок містить ціль `xc7z020clg400-1`. Швидший `fpga-as` не зібрався через HTTP 504 на завантаженні залежностей Bazel, але це не блокує отриманий бітстрім.

`.hwh` не генерувався. Власний `.bit` створено, але він ще не завантажувався на PYNQ і не перевірявся в апаратному циклі.

### 7. Запрограмувати `pynq2` та виконати HIL — ВИКОНАНО

Після отримання явної згоди користувача на встановлення openXC7 та тимчасове завантаження бітстріму у volatile PL на платі `pynq2` (без запису в QSPI/SD):
1. **Збірка:** Скомпільовано та верифіковано бітстрім `kpol_pynq.bit` (4,045,719 байтів, SHA-256 `d34719f737f410a37c3e3d7d3faedea36ac2117feeebe8fd29558f661cf44f10`).
2. **Завантаження:** Бітстрім та тестовий раннер `pynq_z1_manual_mmio_test.py` передано на `pynq2` через `scp`. Завантаження виконано за допомогою `pynq.Bitstream('/home/xilinx/kpol_pynq.bit').download()` безпосередньо у volatile SRAM PL. Енергонезалежна пам'ять (QSPI flash, SD-картка `BOOT.BIN`, системний образ) жодним чином не модифікувалася.
3. **Фізична HIL-верифікація (MMIO AXI4-Lite):**
   - Зчитано регістр ID `0x14` за базовою адресою `0x40000000`: повернуто `0x4B504F4C` (ASCII "KPOL").
   - Тест номінальної транзакції (Candidate `0x00001234`, Conditions `0x0000003F` — всі умови валідні): статус `STATUS_COMMITTED` підтверджено, регістр стану оновлено до `0x00001234`.
   - Тест відхилення при порушенні інваріанта (Candidate `0x00005678`, Conditions `0x0000002F` — інваріант фальшивий): статус `STATUS_REJECTED | STATUS_REJECTED_INVARIANT` підтверджено, стан зберігся без змін (`0x00001234`).
   - Підсумок раннера: `PASS: KPOL ID, nominal commit, and invariant fail-closed behavior (state=0x00001234)`.
4. **Відновлення baseline-стану:** Після виконання HIL-тесту штатна конфігурація PL була негайно відновлена завантаженням базового оверлею `/lib/firmware/base.bin` у volatile SRAM PL (`Base overlay restored in volatile PL`).

## Поточний GO/NO-GO

- **GO:** Апаратний транзакційний шлюз KPOL (`kpol_txn_gate_axi_lite`) успішно синтезовано, трасовано та верифіковано на фізичному кремнії Xilinx Zynq-7000 (`xc7z020clg400-1`) на платі PYNQ-Z1 за допомогою повністю відкритого тулчейну openXC7. Рівень технологічної готовності TRL 4 (апаратна лабораторна валідація інтеграційного шлюзу) досягнуто і підтверджено протоколом тестування.
- **NO-GO:** Заявляти повне апаратне розгортання всього ядра Машини Кузьміна (МК) або інтерпретатора KPOL — даний етап підтверджує фізичну реалізацію апаратного інтерфейсного шлюзу транзакцій (integration slice), наступним етапом є масштабування логіки інваріантів та ядра процесора KPOL.
- **Стан системи:** Плата `pynq2` повернута у штатно робочий стан (базовий оверлей відновлено у volatile PL).

## Наступні конкретні кроки

1. Зберегти апаратні логи та звіт верифікації HIL у каталозі `04-verification-and-qa/Reports/`.
2. Зафіксувати зміни та скрипти синтезу `build_pynq_z1_openxc7.sh` і тестування `pynq_z1_manual_mmio_test.py` у системі контролю версій Git.
3. Перейти до проектування наступного розширення: апаратної матриці перевірки інваріантів (HW Invariant Checking Core) на SystemVerilog.
