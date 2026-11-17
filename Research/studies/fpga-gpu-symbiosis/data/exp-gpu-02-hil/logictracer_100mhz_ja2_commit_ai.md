# Зведення автоматичного захвату LOGICTRACER_PICO_0.5.0 на 100 MS/s (10 нс) для EXP-GPU-02 (#253)

* **Версія:** 0.1.0
* **Дата:** 2026-11-17
* **Тип WP редакції NG:** Data

## Згенерований звіт `logictracer-cli --ai` (`100 MS/s`)

```json
{"hw_id":"0x4b504841","phases_only":true,"p1_e1_w0":0,"p1_e2_w0":1,"p2_e3_w0":1,"p2_e4_w0":2,"p4_e5_w0":3,"p4_e7_w0":4,"p4_e8_w0":4,"p4_e9_w0":5,"p4_e10_w0":501,"seq_mon":"0x00000008"}
```

- Device: `LOGICTRACER_PICO_0.5.0` (`/dev/ttyACM0`, `E66118604B78A622`) | GPIO map: `CH1=GP2`, `CH2=GP3`
- Setup: `dut.board=PYNQ-Z1`; `dut.design=kpol_bram_pipeline_pynq_z1_ha_top`; `dut.bitstream_sha256=b5f455aad296364ea66c2462cdbecf56e7b8657d220903ed83f173287cbd683b`
- Sample rate: `100 MHz` (period `10 ns`), `20000` samples, duration `200 us` | quantization `±1` sample (`±10 ns`)
- Trigger: `CH2` rising, `t = 0` at sample `1000`
- Visible range: samples `[0, 20000)` = `-10 us .. 190 us` (`20000` samples, `200 us`)

| Ch | Name | Idle | Final | Edges (rise/fall) | Pulses H/L | Frequency | Duty % | Min pulse | Max pulse | Glitches | Pin |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | JA1_TRIG | 1 | 1 | 0 (0/0) | 0/0 | - | - | - | - | 0 | GP2 |
| 2 | JA2_COMMIT | 0 | 0 | 14 (7/7) | 7/6 | 364.964 kHz | 3.6 | 100 ns | 4.82 us | 0 | GP3 |

### Повторюваний мотив переходів (`×7`, `14` фронтів)

`JA2_COMMIT↑ +10 JA2_COMMIT↓ +194[146..350] ↻` (`Δ` у відліках, `T = 10 ns`, ширина кожного з `7` імпульсів дорівнює рівно `10` відліків = `100.0 нс`).

```text
JA1_TRIG   |####################################################################################################|
JA2_COMMIT |_____|_|_|||||______________________________________________________________________________________|
           |-10 us .. 190 us | 1 column = 2 us
Legend: # high, _ low, | transition inside the column
```

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.1.0 | 2026-11-17 | Збережено автоматичний звіт `logictracer-cli capture --freq 100M --ai` для натурного прогону Фаз 1–4 `EXP-GPU-02` (#253). |

## Абревіатури та глосарій

| Термін | Значення |
|---|---|
| GP2 / GP3 | Вхідні канали `CH1` і `CH2` логічного аналізатора `LOGICTRACER_PICO_0.5.0` на базі `RP2040`. |
| JA2_COMMIT | Вихід `ja2` (`Y19`) плати `PYNQ-Z1` з розтягнутим імпульсом `hw_commit_pulse_o` (`100 нс` = `10` тактів @ `100 МГц`). |
| WP | Work Product, результат роботи з визначеним призначенням. |
