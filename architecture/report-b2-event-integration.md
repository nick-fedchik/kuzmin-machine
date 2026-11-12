# Звіт про виконання задачі S2 / B2: Інтеграція зовнішньої події з BRAM-конвеєром

* **Тип Work Product:** `Report` (підтип `Analysis`)
* **Версія:** 1.0.0
* **Дата:** 2026-11-12
* **Автор:** Antigravity (agy)
* **Статус:** Подано на розгляд власника (Submitted)
* **ASPICE 4.0 процеси:** `SYS.3`, `HWE.1`, `MAN.3`
* **Work Item:** Задача [#134](https://github.com/nick-fedchik/kuzmin-machine/issues/134) (Parent: #5)

---

## 1. Мета та виконана робота

На виконання задачі #134 формалізовано рішення **B2** із системної архітектури MVP ([`architecture/s2-candidate-system.md`, §7.1](s2-candidate-system.md#71-пять-рішень-для-погодження)):
1. Спроєктовано та задокументовано повний архітектурний наскрізний тракт у документі [`bram-pipeline-event-integration.md`](bram-pipeline-event-integration.md):
   $$\text{Зовнішній асинхронний вхід} \xrightarrow{\text{CDC 2-FF}} \text{Детектор фронту / Мапувальник} \xrightarrow{\text{hw\_trigger}} \text{FIFO 16} \xrightarrow{\text{Fetch 4W}} \text{CME} \xrightarrow{} \text{Gate v2} \xrightarrow{} \text{LED/PMOD}$$
2. Обґрунтовано архітектурний вибір (Варіант 2): інтеграція фізичного входу безпосередньо з конфігурацією конвеєра `CFG-P` (`kpol_bram_pipeline_pynq_z1_top.v`) із збереженням `CFG-R` як окремого фізичного результату S6 (AV-10/AV-11).
3. Сформульовано 5 атомарних перевірних вимог (`REQ-SYS-011`, `REQ-SYS-012`, `REQ-HW-011`, `REQ-HW-012`, `REQ-HW-013`) із зазначенням критеріїв успіху, методів верифікації та джерел походження.
4. Розроблено проєкт верифікаційного протоколу (Protocol) із 3 сценаріями: позитивний commit, негативний fail-closed reject та стрес-навантаження черги.
5. Забезпечено двоспрямовану матрицю простежуваності між вимогами, RTL, симуляційними тестбенчами та HIL-випробуваннями на стенді PYNQ-Z1.
6. Оновлено системну архітектуру [`s2-candidate-system.md`](s2-candidate-system.md).

---

## 2. Звірка з критеріями завершення Issue #134

| Критерій Issue #134 | Статус виконання | Доказ / Локатор у WP |
| :--- | :---: | :--- |
| **1. Записано варіанти B2, вибір, причини, наслідки** | **Виконано** | [`bram-pipeline-event-integration.md`, §2](bram-pipeline-event-integration.md#2-архітектурне-рішення-b2-decision-adr-b2) |
| **2. Design показує весь цільовий тракт і межі тактових доменів** | **Виконано** | [`bram-pipeline-event-integration.md`, §3](bram-pipeline-event-integration.md#3-склад-і-конструкція-наскрізного-тракту-design) |
| **3. Атомарні вимоги з ID, походженням, критерієм, методом** | **Виконано** | [`bram-pipeline-event-integration.md`, §4](bram-pipeline-event-integration.md#4-перевірні-вимоги-requirements--sys--hw) |
| **4. Protocol із версією об'єкта, стимулом, очікуванням, негативним контролем** | **Виконано** | [`bram-pipeline-event-integration.md`, §5](bram-pipeline-event-integration.md#5-проєкт-верифікаційного-протоколу-protocol) |
| **5. Не підмінено критерії #7/#9 і не запроваджено непогодженого часового порога** | **Виконано** | [`bram-pipeline-event-integration.md`, §1.2, §3.3](bram-pipeline-event-integration.md#33-часовий-бюджет-та-аналіз-латентності) (чітко застережено від переносу 60 нс) |
| **6. Оновлено обидва напрями трасування до #7/#8 та AV-10/11/S3-62** | **Виконано** | [`bram-pipeline-event-integration.md`, §6](bram-pipeline-event-integration.md#6-двоспрямоване-трасування-traceability-register) |
| **7. Змінені WP версіоновано за SemVer** | **Виконано** | Версія 1.0.0, історія версій у кожному зміненому документі |
| **8. Є Report та незалежний Review Report** | **Виконано** | Цей звіт та [`reviews/review-b2-event-integration.md`](reviews/review-b2-event-integration.md) |

---

## 3. Висновок

Всі критерії задачі #134 виконано в повному обсязі. Результати готові до розгляду та прийняття власником проєкту. Наступним кроком у ланцюжку S2 є задача [#135](https://github.com/nick-fedchik/kuzmin-machine/issues/135) (B5: визначення навантаження та політики черги FIFO).

## Історія версій

| Версія | Дата | Автор | Зміни |
| :--- | :--- | :--- | :--- |
| 1.0.0 | 2026-11-12 | Antigravity (agy) | Первинна редакція звіту за задачею #134. |
