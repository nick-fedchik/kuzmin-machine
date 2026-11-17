# Зведення сегментованого захвату LOGICTRACER_PICO_0.5.0 (7 вікон @ 100 MS/s + 200 МГц blast-таймер) для EXP-GPU-02 (#253)

* **Версія:** 0.1.0
* **Дата:** 2026-11-17
* **Тип WP редакції NG:** Data

## Згенерований звіт `logictracer-cli --segments 7 --ai` (`100 MS/s` + `200 MHz` blast timestamps)

```json
{"hw_id":"0x4b504841","phases_only":true,"p1_e1_w0":0,"p1_e2_w0":1,"p2_e3_w0":1,"p2_e4_w0":2,"p4_e5_w0":3,"p4_e7_w0":4,"p4_e8_w0":4,"p4_e9_w0":5,"p4_e10_w0":501,"seq_mon":"0x00000008"}
```

- Segmented capture: **7 trigger windows** of `450` samples (`4.5 us`) at `100 MHz`; `50` pre-trigger samples before window 1 only
- Every window starts on: `CH2` rising (`GP3 = JA2_COMMIT`)
- Trigger-to-trigger spacing (`6` intervals, `trigger_time_resolution_ns = 5.0 ns` @ `200 MHz` blast clock): min `53.38 us`, median `55.56 us`, max `108.8 us`; window `1 .. 7` span `483.45 us` (`[0.0, 108.795, 164.36, 270.125, 376.41, 429.785, 483.45] us`)
- Device: `LOGICTRACER_PICO_0.5.0` (`/dev/ttyACM0`, `E66118604B78A622`)
- Setup `dut.board`: `PYNQ-Z1`; `dut.design`: `kpol_bram_pipeline_pynq_z1_ha_top`; `dut.bitstream_sha256`: `b5f455aad296364ea66c2462cdbecf56e7b8657d220903ed83f173287cbd683b`
- Windows needing attention: `0 of 7`

| Ch | Name | Edges | Rising | Falling | HIGH pulses | HIGH width (samples) | Freq in window |
|---|---|---|---|---|---|---|---|
| 1 | JA1_TRIG | 0 | 0 | 0 | 0 | - | - |
| 2 | JA2_COMMIT | 14 | 7 | 7 | 7 | 10..11 | - |

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.1.0 | 2026-11-17 | Збережено автоматичний звіт `logictracer-cli capture --freq 100M --segments 7 --ai` з апаратними мітками часу `200 МГц` (`5.0 нс`) для `EXP-GPU-02` (#253). |

## Абревіатури та глосарій

| Термін | Значення |
|---|---|
| Blast Clock | Апаратна частота `200 МГц` (`5.0 нс`) таймера міток часу між сегментами в `LOGICTRACER_PICO_0.5.0`. |
| JA2_COMMIT | Вихід `ja2` (`Y19`) плати `PYNQ-Z1` з розтягнутим імпульсом `hw_commit_pulse_o` (`100 нс` = `10` тактів @ `100 МГц`). |
| WP | Work Product, результат роботи з визначеним призначенням. |
