# Апаратні специфікації (Hardware Specifications)

* **Версія:** 1.0.0
* **Дата:** 2026-11-12
* **ASPICE 4.0 процеси:** `HWE.1` (Hardware Requirements Analysis), `SYS.3` (System Architectural Design)

Цей каталог містить нормативні специфікації апаратних модулів, шинних інтерфейсів та карт регістрів Машини Кузьміна.

| Документ | Цільовий RTL-модуль | Конфігурація | Опис | Статус |
| :--- | :--- | :--- | :--- | :--- |
| [`kpol-txn-gate-axi-lite-interface.md`](kpol-txn-gate-axi-lite-interface.md) | [`kpol_txn_gate_axi_lite.sv`](../../hw/rtl/bus/kpol_txn_gate_axi_lite.sv) | `CFG-R` | Специфікація інтерфейсу AXI4-Lite, повна карта регістрів CSR (0x00..0xC0), простір BRAM (0x1000..0x13FF), значення після скидання (`upper_bound_q = 0x7FFFFFFF`), правила DECERR/SLVERR та матриця трасування на TB і драйвери. | **Approved** |
| [`event-queue-ingress-specification.md`](event-queue-ingress-specification.md) | [`km_autonomous_sequencer.sv`](../../hw/rtl/core/km_autonomous_sequencer.sv) | `CFG-P` | Специфікація приймання подій, арбітражу (пріоритет каскаду), політики черги FIFO (handshake backpressure + явний облік втрат) та обґрунтування ресурсу черги (B5, #135). | **Proposed** |
| [`kpol-image-loader-pipeline-contract.md`](kpol-image-loader-pipeline-contract.md) | [`kpol_bram_pipeline_axi.sv`](../../hw/rtl/bus/kpol_bram_pipeline_axi.sv) | `CFG-P` | Специфікація контракту життєвого циклу образу, інтерфейсу loader ↔ PL, фазового розподілу (Load vs Run) та захисту пам'яті (B4, #133). | **Proposed** |

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 1.0.0 | 2026-11-12 | Створення каталогу та індексація специфікації інтерфейсу AXI4-Lite (Issue #48). |
| 1.1.0 | 2026-11-12 | Додано специфікацію приймання подій та політики черги FIFO (Issue #135). |
| 1.2.0 | 2026-11-12 | Додано специфікацію контракту завантаження та життєвого циклу образу (Issue #133). |
