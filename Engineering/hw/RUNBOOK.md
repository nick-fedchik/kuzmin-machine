# Відкрита перевірка поточного BRAM/CME-тракту

* **Версія:** 0.3.0
* **Дата:** 2026-11-12
* **Тип WP:** Guide
* **Укладач:** GitHub Copilot CLI, Auto; незалежної рецензії NG немає.
* **Походження:** [runbook 0.2.0](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/hw/RUNBOOK.md).

## 1. Мета та передумови

Локальна перевірка актуального compiler/loader/BRAM/CME/gate v2.
Потрібні Python 3/pytest, GCC, Icarus Verilog, Verilator, Yosys.
Формальні тести додатково потребують Z3, yosys-smtbmc, yosys-abc.
Відсутній інструмент може спричинити skip у pytest; це не успішна перевірка.
Фізичний стенд у цьому маршруті не використовується.

## 2. Порядок виконання

З кореня NG:

```bash
python3 -m pytest -q
bash Engineering/hw/scripts/run_open_flow.sh
```

Скрипт спочатку запускає наявні testbench та наскрізні тести.
Gate v2 і BRAM перевіряються строгим Verilator та XC7 logic synthesis.
Інтегрований `kpol_bram_pipeline_axi` лінтується з відомими
попередженнями як нефатальними, але синтаксичні/командні помилки
залишаються фатальними. Його синтез включає справжні залежності,
не вилучені демо-FSM.

Окремі формальні регресії містяться в
[Validation](../validation/README.md); їхні тестові виходи — тимчасові.
Прямі runners потребують нового `S3_OUT_DIR` або `AXI64_OUT_DIR`.

## 3. Цільова збірка та обладнання

Для окремого апаратного циклу використовуються тільки
[build_bram_pipeline.sh](boards/pynq-z1/build_bram_pipeline.sh),
актуальний [top](boards/pynq-z1/kpol_bram_pipeline_pynq_z1_top.v)
та його [XDC](boards/pynq-z1/kpol_bram_pipeline.xdc).
Скрипт потребує зовнішньої конфігурації OpenXC7 і нового `BUILD_DIR`.
Оточення описано у [toolchain](toolchain/xc7.md).
Loader і умови HIL — у [Solution](../solutions/compiler-bram-pipeline.md).
Перед доступом до плати потрібен файловий lock `/tmp/km-bench.lock`.

## 4. Обмеження та діагностика

Логічний синтез не є P&R, STA або готовим бітстрімом. Відкритий цикл
не підтверджує фізичної затримки, автономності чи працездатності всієї МК.
Старий gate v1, AXI-обгортка демо та iCE40-проксі вилучені з маршруту.
Числа старого runbook не переписані як результати нового pipeline.
Фактичний склад перенесення NG зафіксовано у
[реєстрі перенесення](../../Project/registers/migration.md).

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.3.0 | 2026-11-12 | Новий актуальний маршрут замість legacy gate/demo/iCE40. |

## Абревіатури та глосарій

RTL — опис логіки; P&R — розміщення й трасування; STA — статичний
часовий аналіз; HIL — фізичний апаратний прогін; CME — Concept Micro-Engine.
