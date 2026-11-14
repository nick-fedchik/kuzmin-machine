# Інженерні перевірки

* **Версія:** 0.5.3
* **Дата:** 2026-11-14
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
