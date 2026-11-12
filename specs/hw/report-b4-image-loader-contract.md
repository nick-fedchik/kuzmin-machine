# Звіт про виконання задачі S2 / B4: Контракт завантаження та виконання образу KPOL

* **Тип Work Product:** `Report` (підтип `Analysis`)
* **Версія:** 1.0.0
* **Дата:** 2026-11-12
* **Автор:** Antigravity (agy)
* **Статус:** Подано на розгляд власника (Submitted)
* **ASPICE 4.0 процеси:** `SYS.3`, `HWE.1`, `SWE.1`, `MAN.3`
* **Work Item:** Задача [#133](https://github.com/nick-fedchik/kuzmin-machine/issues/133) (Parent: #5)
* **Пов'язані задачі:** S4 / [#7](https://github.com/nick-fedchik/kuzmin-machine/issues/7) (PR #137, виконання двох програм на одному бітстрімі), S2 / [#48](https://github.com/nick-fedchik/kuzmin-machine/issues/48) (PR #138, карта регістрів AXI)

---

## 1. Мета та виконана робота

На виконання задачі #133 формалізовано рішення **B4** із системної архітектури MVP ([`architecture/s2-candidate-system.md`, §7.1](../../architecture/s2-candidate-system.md#71-пять-рішень-для-погодження)):
1. Створено нормативну специфікацію [`kpol-image-loader-pipeline-contract.md`](kpol-image-loader-pipeline-contract.md), яка регламентує повний життєвий цикл бінарного образу KPOL та інтерфейс взаємодії між програмним завантажувачем (loader) на ARM Cortex-A9 та апаратним конвеєром PL.
2. Прийнято та обґрунтовано архітектурне рішення (Decision B4):
   - Розділені фази виконання (Load vs Run) обрано як базову архітектуру MVP, що виключає ризик розірваного запису (torn write) 128-бітних дескрипторів та забезпечує повний детермінізм;
   - Конкурентну «гарячу» модифікацію образу під час оброблення подій відкладено до майбутніх розширень (HA).
3. Сформовано однозначну матрицю дозволених та заборонених операцій шини AXI4-Lite для кожної фази життєвого циклу (`PHASE_RESET`, `PHASE_LOAD`, `PHASE_ARMED`, `PHASE_RUN`).
4. Зафіксовано формат та межі пам'яті образу: 1024 байти (64 концепти $\times$ 16 байтів), 32-бітний Little-Endian порядок слів, точна структура полів дескриптора.
5. Чітко розмежовано конвеєрну обгортку `kpol_bram_pipeline_axi.sv` (`CFG-P`) та ручну AXI-обгортку `kpol_txn_gate_axi_lite.sv` (`CFG-R`, #48).
6. Сформульовано 5 перевірних вимог (`REQ-SYS-015`, `REQ-SYS-016`, `REQ-HW-017`, `REQ-SW-011`, `REQ-SW-012`).
7. Узгоджено проєкт протоколу верифікації з фізично підтвердженими результатами S4 (Issue #7, PR #137) щодо виконання двох програм на незмінному бітстрімі.
8. Оновлено системну архітектуру [`s2-candidate-system.md`](../../architecture/s2-candidate-system.md) та каталог апаратних специфікацій [`README.md`](README.md).

---

## 2. Звірка з критеріями завершення Issue #133

| Критерій Issue #133 | Статус виконання | Доказ / Локатор у WP |
| :--- | :---: | :--- |
| **1. Зафіксовано варіанти B4, вибір, причини, наслідки** | **Виконано** | [`kpol-image-loader-pipeline-contract.md`, §2](kpol-image-loader-pipeline-contract.md#2-архітектурне-рішення-b4-decision-adr-b4) |
| **2. Однозначна таблиця фаз, операцій, переходів і спостережуваних результатів** | **Виконано** | [`kpol-image-loader-pipeline-contract.md`, §3.2](kpol-image-loader-pipeline-contract.md#32-матриця-операцій-за-фазами-життєвого-циклу) |
| **3. Точна конфігурація образу, межі пам'яті, порядок слів/байтів** | **Виконано** | [`kpol-image-loader-pipeline-contract.md`, §4](kpol-image-loader-pipeline-contract.md#4-контракт-формату-виконуваного-образу-format--memory-layout) |
| **4. Вимоги з ID, походженням, критерієм і методом** | **Виконано** | [`kpol-image-loader-pipeline-contract.md`, §5](kpol-image-loader-pipeline-contract.md#5-перевірні-вимоги-requirements--sys--hw--sw) |
| **5. Проєкт Protocol узгоджено з наявним критерієм #7 (2 програми, незмінний SHA-256)** | **Виконано** | [`kpol-image-loader-pipeline-contract.md`, §6](kpol-image-loader-pipeline-contract.md#6-проєкт-верифікаційного-протоколу-protocol) |
| **6. Обидві обгортки (CFG-P vs CFG-R) та межі #48 чітко розрізнені** | **Виконано** | [`kpol-image-loader-pipeline-contract.md`, §1.2](kpol-image-loader-pipeline-contract.md#12-межі-розрізнення-обгорток) |
| **7. Оновлено двоспрямоване трасування та записи SemVer** | **Виконано** | [`kpol-image-loader-pipeline-contract.md`, §7](kpol-image-loader-pipeline-contract.md#7-двоспрямоване-трасування-traceability-register) |
| **8. Є Report та незалежний Review Report** | **Виконано** | Цей звіт та [`reviews/review-b4-image-loader-contract.md`](reviews/review-b4-image-loader-contract.md) |

---

## 3. Висновок

Всі критерії задачі #133 виконано в повному обсязі. Результати готові до розгляду та прийняття власником проєкту.

## Історія версій

| Версія | Дата | Автор | Зміни |
| :--- | :--- | :--- | :--- |
| 1.0.0 | 2026-11-12 | Antigravity (agy) | Первинна редакція звіту за задачею #133. |
