# Пакет рішення: compiler → loader → BRAM/CME

* **Версія:** 0.2.0
* **Дата:** 2026-11-13
* **Тип WP:** Solution
* **Власник рішення:** Микола Федчик; укладач складу — GitHub Copilot CLI.
* **Стан:** опис локально перенесеного пакета; не релізна baseline.
* **Точний склад і походження:** [маніфест](../../Project/registers/migration-manifest.json).

## 1. Мета, межі та контракти

Реалізація системної межі [B1](../design/system-boundary-allocation-b1.md):
програма → підтримувана компіляція → 1024-байтний CME-образ → loader →
апаратний sequencer/CME/gate v2.
Підтримуваний контракт визначає [KPOL-CME-1](../specifications/kpol/kpol-cme-subset-0.1.0.md),
а не ширина граматики поточного парсера.

## 2. Склад і залежності

| Складник | Локатор | Залежність / інтерфейс |
|---|---|---|
| Референс і CME emitter | [Python](../sw/kpol-ref/kpol_reference.py) | Семантика та окремі двійкові формати. |
| CLI образу | [compile_kpol_bram_image.py](../hw/scripts/compile_kpol_bram_image.py) | Створює новий файл; не перезаписує існуючий. |
| Loader / HIL runner | [hil_kpol_bram_pipeline.py](../hw/boards/pynq-z1/hil/hil_kpol_bram_pipeline.py) | [Контракт B4](../specifications/hw/kpol-image-loader-pipeline-contract.md). |
| Ядро | [RTL core](../hw/rtl/core/) | BRAM, sequencer, CME, gate v2. |
| Інтеграція | [AXI](../hw/rtl/bus/kpol_bram_pipeline_axi.sv), [top](../hw/boards/pynq-z1/kpol_bram_pipeline_pynq_z1_top.v) | [B2](../design/bram-pipeline-event-integration.md), [B5](../specifications/hw/event-queue-ingress-specification.md). |
| Збірка | [build_bram_pipeline.sh](../hw/boards/pynq-z1/build_bram_pipeline.sh) | OpenXC7 та зовнішня chipdb; новий `BUILD_DIR`. |

## 3. Перевірки та відтворення

[Інтеграційний тест](../hw/tests/test_kpol_bram_pipeline.py) порівнює
стан із референсом, перевіряє direct/AXI-шлях і негативний випадок
переставлених образів. [S3](../validation/experiments/S3-62/report.md)
описує властивості gate v2; [S4](../validation/experiments/S4-07/report.md)
містить успадкований фізичний запис двох програм на одному бітстрімі.

Команди NG та межі симуляції — у [Validation](../validation/README.md).
Результати перенесення — у [звіті NG](../../Project/assessments/ng-migration/report.md).

## 4. Обмеження та стан прийняття

Наявність цих складників не доводить повного виконання профілю чи
MVP. Невідомі й відомі обмеження lowering не маскуються успішним
створенням образу. AV-10/11 не є апаратними тестами цього пакета.
Незалежної рецензії локальної редакції NG ще немає.
Новий [авторський Source #155](../../Research/sources/author/introduction-2026-11-13.md)
не є форматом цього пакета. Name/Help, Def/Class, native групи/адреси
та результат-метаподія `•` тут не реалізовані.
[Impact і майбутні кандидати](../../Research/studies/author-semantics/kpol-syntax-155-report.md)
не змінюють склад або прийняття чинного compiler/BRAM-рішення.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.2.0 | 2026-11-13 | #155: явна межа нового авторського представлення й поточного пакета. |
| 0.1.0 | 2026-11-12 | Явний склад актуального compiler/BRAM-рішення. |

## Абревіатури та глосарій

CME — Concept Micro-Engine; BRAM — блокова пам'ять; AXI — інтерфейс шини;
HIL — фізичний апаратний прогін; MVP — мінімальний цільовий продукт.
