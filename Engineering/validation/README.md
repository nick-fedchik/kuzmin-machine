# Інженерні перевірки

* **Версія:** 0.9.0
* **Дата:** 2026-11-18
* **Тип WP:** Guide

## Призначення та навігація

| Пакет | Об'єкт і межі |
|---|---|
| [S3-62](experiments/S3-62/report.md) | Gate v2, формальні властивості, cover і мутанти. |
| [S4-07](experiments/S4-07/report.md) | Успадкований HIL-запис двох програм на одному бітстрімі. |
| [AXI-64](experiments/AXI-64/report.md) | Згенерований slave, не ручна pipeline-обгортка. |
| [AV-10](experiments/AV-10/report.md), [AV-11](experiments/AV-11/report.md) | Записи CFG-R; збережені для межі доказів, не перенесення її властивостей на CFG-P. |
| [Fail-closed](fail-closed/report.md) | Окрема перевірка референсної реалізації за своїм протоколом. |
| [U32](spec-conformance/u32-report.md), [namespace/import](spec-conformance/namespace-import-report.md) | Контрприклади окремих контрактів; не повна перевірка мови. |
| [B3 raw](kpol-cme/raw/) | Первинні записи продовження KPOL-CME; походження в маніфесті. |
| [KPOL-CME-1 / #150](kpol-cme/profile-150/report.md) | Явний профільний compiler, негативний контроль і CLI/RTL-симуляційні регресії; не HIL. |
| [KPOL-CME-1 / B3-REQ-06 / #153](kpol-cme/behavior-153/report.md) | Стан після кожної події, signed guards, Int32 межі, W1–W3 і нульовий payload через direct/AXI; RTL-симуляція, не HIL. |
| [B5 v2.1 / черга подій / #151](kpol-cme/queue-retention-151/report.md) | Очікування без втрат для керованих джерел (`valid && ready`), резервування слота каскадом і `sw_trigger`, `cascade_pending_*_q`, глибини `4..32`, 6 мутантів і синтез XC7; RTL-симуляція, не HIL. |
| [Secure Boot / #164](kpol-cme/secure-boot-164/report.md) | Усунення pre-auth nonce poisoning, свіжі 16-байтні `nonce` за замовчуванням і `CME-RAW-1` payload у `compile_signed_bram_image` / `verify_bram_signature`; програмна перевірка, не апаратний Secure Boot. |
| [Семантика ядра CME / #167](kpol-cme/cme-semantics-167/report.md) | Каскад на `CID 0` (`guard_flags[4]`), по-концептний `state_changed_o`, знакове переповнення `INC/DEC/ADD/SUB`, знаковий `RANGE`, fail-closed відхилення невідомих `action_opcode > 0x04`, 6 мутантів і синтез XC7; RTL-симуляція, не HIL. |
| [AXI B4 / W1C / PYNQ-Z1 top / #168](kpol-cme/axi-b4-pynq-168/report.md) | Закриття 1-тактової гонитви `Load vs Run` у `kpol_bram_pipeline_axi.sv`, W1C-очищення `0x02C` при `busy == 0`, 2-FF CDC `sw[1:0]`, антибрязкіт `btn[0]` (1 мс) і `param = 1` у `kpol_bram_pipeline_pynq_z1_top.v`, 6 мутантів і синтез XC7; RTL-симуляція, не HIL. |
| [Синхронізація реєстрів і документації / #169](kpol-cme/docs-registers-169/report.md) | Синхронізація `open-work-items.md`, `formal-analysis.md` (RFC-008), `system-boundary-allocation-b1.md`, `s2-candidate-system.md`, `trl/report.md` (`CFG-R` 20 нс vs `CFG-P` 80 нс), `work-products.md`, `goals-needs-work-items.md` та індексу `wp-index.json`; структурна та посилальна перевірка. |
| [Верифікатор `Proof`, `change(...)` і базове CME-lowering / #183](kpol-cme/verifier-lowering-183/report.md) | Одноразовий початковий `change(...)` в `Interpreter`, відхилення вакуумних `Proof`, усунення інверсії охоронця за іменем правила, точне перенесення `>=`/`<=`/знакового `int16` `RANGE` у `km_concept_micro_engine.sv` та синхронізація `RFC-010`; RTL-симуляція (`iverilog`), не HIL. |
| [Профіль `KPOL-CME-2` / #184](kpol-cme/cme2-profile-184/report.md) | Багатоконцептна компіляція до 64 станів на `CME-RAW-1`, ациклічні каскади `on change(...)` (включно з `CID 0`), `ADD/SUB/ASSIGN`, `CME2-OPERAND-COLLISION` і побітова еквівалентність `Interpreter` з AXI RTL (`kpol_bram_pipeline_axi.sv`); RTL-симуляція (`iverilog`), не HIL. |
| [CR `KPOL-SYS-02` і дескриптор `CME-RAW-2` / #185](kpol-cme/cr-cme-raw2-185/report.md) | Синтез `yosys` двобанкової пам'яті `2 × RAMB36E1` (модель на 128 концептів із 64-бітним Портом B; 8 тактів до 256 концептів — проєктна ціль, не перевірено без RTL `CME-RAW-2`), перевірка 256-бітної розкладки `W0..W7` і поточного `Secure Boot` (`v0x0006` із відхиленням `0x0007`/`2048` Б) без зміни RTL `CFG-P`. |
| [Прототип фронтенду й lowering `KPOL-AUTH` / #219, #224, #233, #243, #245](kpol-cme/kpol-auth-frontend-219/report.md) | Контекстно-вільний лексер і CST з UTF-8 `Span`, 12 точок невизначеності `KPOL-AUTH-U01..U12` (`fail-closed`), корпус 18 прикладів, похідний lowering у `Do/Go` (`ReferenceDoGoVM`) і `CME-RAW-1` (`KPOL-LOWER-CYCLE`), CLI та мутанти; хостова перевірка, не HIL. |
| [Формальна верифікація `CFG-P` та каскадів `KPOL-CME-2` до $N=16$ / #227, #237, #242, #249](kpol-cme/cme2-formal-227/report.md) | BMC та композиційна $k$-індукція у `yosys-smtbmc + Z3` для $N=4$ і $N=16$ (`0` внутрішніх `assume` у `FORMAL_INDUCTION`): збереження `W0` при `Reject` (`P1`), монотонність рангу Ляпунова за передумови DAG компілятора (`P2`), точний 8-тактовий бюджет (`P3`), `cover` і 8 мутантів із `.vcd`. |
| [Модуль `km_pmod_event_egress.sv` та PYNQ-Z1 egress top / #230, #234, #241](kpol-cme/pmod-event-egress-230/report.md) | Формування 64-бітного кадра з `CRC-8` у режимах `SPI` (`50 МГц`, `1.29 мкс`) та 8-бітної паралельної шини `PAR8` (`170 нс`), інтеграція у `kpol_bram_pipeline_pynq_z1_egress_top.v`, 8 мутантів, `verilator` lint і синтез `yosys synth_xilinx`; симуляція, не фізичний HIL. |
| [Багатоядерне масштабування `CFG-P` ($N=1, 2, 4, 8$) / #255](kpol-cme/manycore-scaling-255/report.md) | Міжбанковий комутатор `km_event_crossbar.sv` та кластер `km_manycore_cluster.sv`, формальний SMT-доказ `Z3` на $N=2$ (`MC1..MC3`, свідок циклічного дедлока `MC4` і 3 мутанти), фізичний P&R та STA в `OpenXC7` (`nextpnr-himbaechel` на `xc7z020clg400-1`, $F_{\max} = 113.92..50.81\text{ МГц}$) і профілювання трафіку (`Icarus Verilog`); не фізичний HIL. |
| [Консолідована приймальна верифікація компілятора KPOL S5 / #8](kpol-cme/s5-compiler-8/report.md) | Наскрізна перевірка всіх трьох підтримуваних контурів S5 (`KPOL-CME-1` + `Secure Boot`, `KPOL-CME-2` на `CFG-P` і двобанковому `CFG-P-HA`, підмножина `KPOL-AUTH` у `Do/Go` + `CME-RAW-1`), 7 мутантних контролів `M1..M5` і фіксація відкритих меж `#186` та `ADR B7`. |
| [Генератор детермінованого C99 (`--emit-c99`) + Z3 Safety Certificate на кейсі BMS / #270](kpol-cme/c99-emitter-270/report.md) | Трансляція 4-рівневого каскаду BMS ([`bms_safety_cascade.kpol`](kpol-cme/c99-emitter-270/bms_safety_cascade.kpol)) у 1024-Б образ BRAM, MISRA-орієнтований C99-модуль із `valid_mask` та сертифікат `Z3` (`P1..P4`), верифікована на `x86_64`, `Icarus Verilog`, фізичному `ARM Cortex-A9` (`223.85..286.73 нс`) та кристалі `Zynq-7020 PL` (`pynq2`) з мутантами `M1..M4`; див. також [підсумковий аналіз](../../Research/studies/commercialization-and-final-conclusions.md). |
| [Покроковий дебагер-трасувальник каскадів МК (`--trace-events`, `--stdio`, `--tui`) та верифікація прикладів зі статей / #272](kpol-cme/debugger-trace-272/report.md) | 4-блоковий дебагер [`kpol_debugger.py`](../sw/kpol-ref/kpol_debugger.py), прапорці `--dump-concepts` і `--trace-events` у [`compile_kpol_bram_image.py`](../hw/scripts/compile_kpol_bram_image.py), потокове `STDIO` (`--stdio`), підключення TUI-дебагера до фізичної `PYNQ-Z1` (`pynq2`) зі знімками `PRE-LOAD` / `POST-LOAD` / `POST-RUN` (`1/64 -> 4/64` концепти), покрокова верифікація 5 груп прикладів зі статей (включно з `Nod(120, 6) = 6` проти `km_euclid_core.sv` у `iverilog`) і 5 мутантів `M1..M5` у [`test_kpol_debugger_272.py`](../sw/tests/test_kpol_debugger_272.py). |
| [Двомодовий Go-емулятор Віртуальної Машини Кузьміна (`VMK` v0.1.0: `bram64` + `conceptual`), `STDIO` та 4-панельний TUI-дебагер / #274](kpol-cme/vmk-go-274/report.md) | Самодостатній Go-модуль [`Engineering/sw/vmk-go/`](../sw/vmk-go/go.mod) (`std` only, [специфікація `vmk-go` `0.1.0`](../specifications/sw/vmk-go-emulator-and-tui-debugger-0.1.0.md)), два режими (`--mode bram64` з `Bank 0/1`, `CRC-8`, `FIFO 16` і підключенням до `pynq2`, та `--mode conceptual` за `RFC-001..018`), 10 вбудованих прикладів (`if`, `sum`, `nod`, `factorial`, `tachometer`, `bms`, `increase`, `decrease`, `cascade`, `auth`), перехресна звірка з Python/C99/`iverilog`/кремнієм `pynq2` та 5 мутантів Go-коду `M1..M5` у [`test_vmk_go_274.py`](../sw/tests/test_vmk_go_274.py). |

## Використання

З кореня NG:

```bash
python3 -m pytest -q
bash Engineering/hw/scripts/run_open_flow.sh
```

Формальні регресії пишуть у pytest `tmp_path`; аналіз AV-11 також
експортує CSV тільки в тимчасовий каталог. Аналізатори відмовляються
перезаписувати вже наявний експорт. Первинні записи не оновлюються тестами.
Для окремого повного формального прогону задають новий `S3_OUT_DIR`
або `AXI64_OUT_DIR`, не успадкований `raw/`.

CLI аналізаторів AV-10/11 тепер потребує явного нового `--output-dir`:

```bash
python3 Engineering/validation/experiments/AV-10/scripts/analyze_av10_burst.py --output-dir /tmp/ng-av10-derived-new
python3 Engineering/validation/experiments/AV-11/scripts/analyze_av11.py --output-dir /tmp/ng-av11-derived-new
```

Якщо каталог уже існує, прогін відмовляє до перезапису даних.
Це навмисна зміна NG для захисту первинних записів.

## Обмеження

Повторне читання LAC/JSON — не нове фізичне вимірювання.
Симуляція, формальний доказ і HIL мають різні області чинності.
Сусідні report provenance sidecar у вихідних пакетах відсутні;
їх не створюють заднім числом із припущень. Негативний структурний
результат такого перевіряльника не перетворюють на зелений S1.

Фактичні перевірки нової структури фіксуються у
[звіті перенесення](../../Project/assessments/ng-migration/report.md).

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.9.0 | 2026-11-18 | #274: зареєстровано пакет верифікації двомодового Go-емулятора VMK та 4-панельного TUI-дебагера (`kpol-cme/vmk-go-274/report.md`, `Engineering/sw/vmk-go/`, `test_vmk_go_274.py`) з натурною сесією на `pynq2` та 5 мутантами Go-коду `M1..M5`. |
| 0.8.0 | 2026-11-18 | #272: зареєстровано пакет верифікації покрокового дебагера каскадів МК (`kpol-cme/debugger-trace-272/report.md`, `kpol_debugger.py`, `test_kpol_debugger_272.py`) з натурною сесією на `pynq2` (`PRE-LOAD -> POST-LOAD -> POST-RUN`) та верифікацією прикладів зі статей. |
| 0.7.0 | 2026-11-17 | #270: зареєстровано пакет верифікації генератора `--emit-c99 + Z3` (`kpol-cme/c99-emitter-270/`, `test_c99_emitter_270.py`) та підсумковий висновок `commercialization-and-final-conclusions.md`. |
| 0.6.0 | 2026-11-17 | #8: зареєстровано звіти перевірок фронтенду й lowering `KPOL-AUTH` (`#219/#243/#245`), формальної $k$-індукції до $N=16$ (`#227/#237/#242/#249`), модуля `km_pmod_event_egress.sv` (`#230/#234/#241`), багатоядерного кластера `CFG-P` $N=1..8$ (`#255`) та консолідованої приймальної верифікації компілятора S5 (`s5-compiler-8/report.md`, `#8`). |
| 0.5.8 | 2026-11-14 | #192: у рядку про #185 «8 тактів» для `CME-RAW-2` позначено проєктною ціллю (не перевірено без RTL), уточнено межі перевірки `Secure Boot` (`v0x0006` із відхиленням `0x0007`/`2048` Б). Рядок історії додано в #198 (його пропущено в #192). |
| 0.5.7 | 2026-11-14 | Додано звіт синтезної та програмної перевірки проєкту ADR B7 (`KPOL-SYS-02` і 32-байтний дескриптор `CME-RAW-2`, #185). |
| 0.5.6 | 2026-11-14 | Додано пакет верифікації багатоконцептного профілю `KPOL-CME-2` та його AXI RTL-еквівалентності (#184). |
| 0.5.5 | 2026-11-14 | Додано пакет верифікації виправлень інтерпретатора, `verify_module` та базового CME-lowering у референсі KPOL (#183). |
| 0.5.4 | 2026-11-14 | Додано звіт структурної та посилальної перевірки синхронізації реєстрів і документації (#169). |
| 0.5.3 | 2026-11-14 | Додано пакет верифікації AXI B4 / W1C `0x02C` та модернізації `kpol_bram_pipeline_pynq_z1_top.v` (#168). |
| 0.5.2 | 2026-11-14 | Додано пакет верифікації семантики ядра `km_concept_micro_engine.sv` (#167). |
| 0.5.1 | 2026-11-14 | Додано програмну перевірку виправлень контейнера підпису Secure Boot (#164). |
| 0.5.0 | 2026-11-13 | Додано пакет верифікації черги подій та арбітражу каскаду B5 v2.1 (#151). |
| 0.4.0 | 2026-11-13 | Додано поведінкову матрицю профілю #153 і межі її висновків. |
| 0.3.1 | 2026-11-12 | Дослідницький HIL-пакет EXP-GPU-01 винесено до Research/studies/fpga-gpu-symbiosis/. |
| 0.2.0 | 2026-11-12 | Додано пакет перевірки профільного компілятора #150. |
| 0.1.0 | 2026-11-12 | Поточні перевірки замість застарілого журналу PLAN. |

## Абревіатури та глосарій

LAC — запис логічного аналізатора; CSV — табличний формат;
S1 — окремий процесний гейт, не код завершення структурного лінтера.
