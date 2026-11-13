# Апаратні специфікації (Hardware Specifications)

* **Версія:** 1.2.2
* **Дата:** 2026-11-13
* **ASPICE 4.0 процеси:** `HWE.1` (Hardware Requirements Analysis), `SYS.3` (System Architectural Design)

Цей каталог розділяє поточні контракти CFG-P та збережений контракт
CFG-R, потрібний для інтерпретації первинних записів AV-10/11.
Оригінальний статус Approved не є затвердженням локальної редакції NG.

| Документ | Цільовий RTL-модуль | Конфігурація | Опис | Статус |
| :--- | :--- | :--- | :--- | :--- |
| [`kpol-txn-gate-axi-lite-interface.md`](kpol-txn-gate-axi-lite-interface.md) | [`kpol_txn_gate_axi_lite.sv`](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/hw/rtl/bus/kpol_txn_gate_axi_lite.sv) | `CFG-R` | Специфікація інтерфейсу AXI4-Lite, повна карта регістрів CSR (0x00..0xC0), простір BRAM (0x1000..0x13FF), значення після скидання (`upper_bound_q = 0x7FFFFFFF`), правила DECERR/SLVERR та матриця трасування на TB і драйвери. | **Approved** |
| [`event-queue-ingress-specification.md`](event-queue-ingress-specification.md) | [`km_autonomous_sequencer.sv`](../../hw/rtl/core/km_autonomous_sequencer.sv), [`kpol_bram_pipeline_axi.sv`](../../hw/rtl/bus/kpol_bram_pipeline_axi.sv) | `CFG-P` | Специфікація приймання подій без втрат для керованих джерел (`valid && ready`), резервування слота каскадом, буфера full-каскаду `cascade_pending_*_q` та обліку порушень утримання незупинним джерелом (B5 v2.1.0, #135, #150, #151). | **Implemented in RTL (Pending Review)** |
| [`kpol-image-loader-pipeline-contract.md`](kpol-image-loader-pipeline-contract.md) | [`kpol_bram_pipeline_axi.sv`](../../hw/rtl/bus/kpol_bram_pipeline_axi.sv) | `CFG-P` | Специфікація контракту життєвого циклу образу, інтерфейсу loader ↔ PL, фазового розподілу (Load vs Run) та захисту пам'яті (B4, #133). | **Proposed** |


* **Тип WP редакції NG:** Guide
* **Укладач редакції NG:** GitHub Copilot CLI, Auto; конкретна модель не атестована.
* **Підстава редакції NG:** команда власника від 2026-11-12; локальне перенесення без legacy.
* **Походження:** [оригінал 1.0.0](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/specs/hw/README.md), `707fdba697d92ef9874c9013eb6f4f3cb2796d70`.
* **Стан редакції NG:** адаптовано до нової структури; незалежна рецензія не проведена.

> **Межі редакції NG.** Перенесення й оформлення не є новим експериментом,
> повторною науковою перевіркою або затвердженням baseline. Авторство,
> рішення, числа й рецензії нижче стосуються зазначених оригінальних
> об'єктів та версій, а не автоматично цієї локальної копії.

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 1.2.2 | 2026-11-13 | #151: оновлено опис і статус `event-queue-ingress-specification.md` (v2.1.0, утримання без втрат і арбітраж каскаду в RTL). |
| 1.2.1 | 2026-11-12 | Редакція NG: розділено актуальний CFG-P і контракт походження CFG-R; узгоджено версію з джерельною історією 1.2.0. |
| 1.0.0 | 2026-11-12 | Створення каталогу та індексація специфікації інтерфейсу AXI4-Lite (Issue #48). |
| 1.1.0 | 2026-11-12 | Додано специфікацію приймання подій та політики черги FIFO (Issue #135). |
| 1.2.0 | 2026-11-12 | Додано специфікацію контракту завантаження та життєвого циклу образу (Issue #133). |

## Абревіатури та глосарій

| Термін | Значення |
|---|---|
| WP | Work Product, результат роботи з визначеним призначенням. |
| NG | Нова структура локальної робочої копії; не нова доказова baseline. |
| SHA | Ідентифікатор Git-коміту або контрольна сума з указаним алгоритмом. |
