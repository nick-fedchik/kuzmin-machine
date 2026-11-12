# Реєстр вимог та двоспрямована матриця простежуваності Машини Кузьміна (ASPICE 4.0 / SWE.1–6 / HWE.1–4)

* **Версія:** 0.1.2
* **Перенесено з:** `drafts/KuzminMachine/Kuzmin-Machine-Requirements-UA.md` @ `a4738bc` (2026-11-09)

> **Історичний реєстр, не прийнята матриця S2.** Наведені нижче шляхи,
> позначки `PASS`, відсотки та твердження про рівні ASPICE не є
> підтвердженням поточного стану чи відповідності стандартам.
> [Огляд кожної вимоги і трасування (#114)](../docs/research/verification/requirements-trace-assessment-114.md)
> відокремлює наявні кандидати доказів від неперевірених тверджень.
> [Цілі, потреби та перший зріз WI (#118)](traceability/goals-needs-work-items.md)
> показують ширший контекст та відкриті прогалини.

**Проєкт:** Машина Кузьміна (Kuzmin Machine Architecture)  
**Репозиторій:** `nick-fedchik/drafts/KuzminMachine`  
**Стандарт:** Automotive SPICE v4.0 (PAM 4.0, VDA QMC 2023)  
**Рівень підтвердження (Capability Level):** CL 1 (Performed) / CL 2 (Managed)  
**Дата актуалізації:** 2026-11-09  

---

## 1. Системні вимоги (System Requirements — SYS.2 / SYS.5)

| ID вимоги | Назва та зміст вимоги | Архітектурний модуль | Реалізація | Протокол верифікації / Тест | Статус |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `REQ-SYS-001` | **Fail-Closed Hazard Mitigation:** Транзакційний шлюз відхиляє будь-яку транзакцію при виявленні небезпеки. | Transaction Gate | `02-engineering-hardware/rtl/kpol_txn_gate_v2.sv` | `04-verification-and-qa/test_km_concept_micro_engine.py` | PASS |
| `REQ-SYS-002` | **Autonomous Hardware Sequencing:** Автономна диспетчеризація подій у PL без участі процесора з часом реакції < 500 нс. | Autonomous Sequencer | `02-engineering-hardware/rtl/km_autonomous_sequencer.sv` | `04-verification-and-qa/test_km_autonomous_sequencer.py` | PASS |
| `REQ-SYS-003` | **Deterministic Execution Latency:** Детермінований час обчислення предикату та охоронця за фіксовану кількість тактів (0 джитер). | Concept Micro-Engine | `02-engineering-hardware/rtl/km_concept_micro_engine.sv` | `04-verification-and-qa/test_km_concept_micro_engine.py` | PASS |
| `REQ-SYS-004` | **Inter-Concept Hardware Rendezvous:** Підтримка каскадного переходу та рандеву між концептами через апаратну чергу FIFO. | Event FIFO & Sequencer | `02-engineering-hardware/rtl/km_autonomous_sequencer.sv` | `04-verification-and-qa/test_km_autonomous_sequencer.py` | PASS |
| `REQ-SYS-005` | **State Invariant Enforcement:** Апаратний контроль інваріанта стану концепту (захист від знакового переповнення). | Concept Micro-Engine | `02-engineering-hardware/rtl/km_concept_micro_engine.sv` | `04-verification-and-qa/test_km_concept_micro_engine.py` | PASS |
| `REQ-SYS-006` | **Fail-Closed on Unknown Hazard:** Відхилення транзакції при невизначеному статусі небезпеки (`FAIL_CLOSED_HAZARDS=1`). | Transaction Gate | `02-engineering-hardware/rtl/kpol_txn_gate_v2.sv` | `04-verification-and-qa/test_km_concept_micro_engine.py` | PASS |
| `REQ-SYS-007` | **Hardware Capability Access Control:** Розмежування прав доступу концептів через таблицю апаратних повноважень (ACL). | Security Controller | `03-engineering-software/kpol_reference.py` | `03-engineering-software/test_kpol_reference.py` | PASS |
| `REQ-SYS-008` | **Secure Boot & BRAM Signature:** Перевірка криптографічної автентичності бінарного образу BRAM алгоритмом HMAC-SHA256. | Security Controller | `03-engineering-software/kpol_reference.py` | `03-engineering-software/test_kpol_reference.py` | PASS |
| `REQ-SYS-009` | **Triad Formal Completeness:** Повна тріада (Problem / Solution / Proof) із криптографічним хешуванням та забороною mock-proofs. | Formal Triad Verifier | `03-engineering-software/kpol_reference.py` | `03-engineering-software/test_kpol_reference.py` | PASS |
| `REQ-SYS-010` | **Popperian Falsification Gate:** Обов'язкове мутаційне тестування зі 100% знищенням штучних мутантів (0 вижилих). | Popperian Auditor | `04-verification-and-qa/run_av07_mutation.py` | `04-verification-and-qa/Reports/AV-07_Mutation_Testing_Report_UA.md` | PASS |

---

## 2. Апаратні вимоги (Hardware Requirements — HWE.1 / HWE.4)

| ID вимоги | Назва та зміст вимоги | Архітектурний модуль | Реалізація | Протокол верифікації / Тест | Статус |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `REQ-HW-001` | **Universal Concept Micro-Engine:** Універсальне ядро обчислення концептів без жорстко закодованих FSM. | Concept Micro-Engine | `02-engineering-hardware/rtl/km_concept_micro_engine.sv` | `04-verification-and-qa/test_km_concept_micro_engine.py` | PASS |
| `REQ-HW-002` | **Predicate Micro-Opcodes:** Апаратне декодування предикатних опкодів (NOP, EQ, NEQ, GT, LT, RANGE, BITMASK). | Concept Micro-Engine | `02-engineering-hardware/rtl/km_concept_micro_engine.sv` | `04-verification-and-qa/test_km_concept_micro_engine.py` | PASS |
| `REQ-HW-003` | **Action Micro-Opcodes:** Апаратне формування кандидатного стану (ASSIGN, INC, DEC, ADD, SUB). | Concept Micro-Engine | `02-engineering-hardware/rtl/km_concept_micro_engine.sv` | `04-verification-and-qa/test_km_concept_micro_engine.py` | PASS |
| `REQ-HW-004` | **Big Dot Phase Inversion Logic:** Апаратна реалізація оператора Кузьміна `• = ¬` (інверсія охоронця). | Concept Micro-Engine | `02-engineering-hardware/rtl/km_concept_micro_engine.sv` | `04-verification-and-qa/test_km_concept_micro_engine.py` | PASS |
| `REQ-HW-005` | **Dual-Port BRAM Storage:** Двопортове збереження 64 дескрипторів концептів (16 байт на дескриптор = 1024 байти). | Concept BRAM Pool | `02-engineering-hardware/rtl/km_concept_bram.sv` | `04-verification-and-qa/test_km_bram_concepts.py` | PASS |
| `REQ-HW-006` | **Pipelined Synchronous BRAM Fetch:** 4-тактовий конвеєр завантаження 128-бітного дескриптора з компенсацією затримки BRAM. | Autonomous Sequencer | `02-engineering-hardware/rtl/km_autonomous_sequencer.sv` | `04-verification-and-qa/test_km_autonomous_sequencer.py` | PASS |
| `REQ-HW-007` | **Cascade Arbiter & Queue:** 16-елементна синхронна черга каскадних концептних подій без колізій. | Autonomous Sequencer | `02-engineering-hardware/rtl/km_autonomous_sequencer.sv` | `04-verification-and-qa/test_km_autonomous_sequencer.py` | PASS |
| `REQ-HW-008` | **AXI4-Lite Peripheral Bridge:** Апаратний міст для запису конфігурації BRAM та зчитування статусу секвенсера. | AXI4-Lite Bridge | `02-engineering-hardware/rtl/km_pynq_top.sv` | `04-verification-and-qa/test_kpol_direct_mmio.py` | PASS |
| `REQ-HW-009` | **FPGA Timing Closure:** Гарантована робоча частота ядер не нижче 50 МГц для топології до 32 концептів. | FPGA Interconnect | `02-engineering-hardware/rtl/km_stream_pipeline_engine.sv` | `04-verification-and-qa/Review_Reports/AV-08_Scaling_Review_Report_UA.md` | PASS |
| `REQ-HW-010` | **Glitch-Free Sequential FSM:** Повна відсутність проміжних засувок (latches) та висячих станів FSM. | Autonomous Sequencer | `02-engineering-hardware/rtl/km_autonomous_sequencer.sv` | `04-verification-and-qa/test_km_autonomous_sequencer.py` | PASS |

---

## 3. Програмні вимоги (Software Requirements — SWE.1 / SWE.6)

| ID вимоги | Назва та зміст вимоги | Архітектурний модуль | Реалізація | Протокол верифікації / Тест | Статус |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `REQ-SW-001` | **KPOL Microcode Compilation:** Компіляція високорівневого KPOL AST у 1024-байтний бінарний образ мікрокоду BRAM. | KPOL Toolchain | `03-engineering-software/kpol_reference.py` | `03-engineering-software/test_kpol_reference.py` | PASS |
| `REQ-SW-002` | **Predicate Extraction:** Автоматичне розпізнавання предикатів та операндів із блоку `when` правил KPOL. | KPOL Toolchain | `03-engineering-software/kpol_reference.py` | `03-engineering-software/test_kpol_reference.py` | PASS |
| `REQ-SW-003` | **Action Microcode Generation:** Трансляція виразів оператора `set` у мікрокоди дій (ASSIGN, INC, DEC, ADD, SUB). | KPOL Toolchain | `03-engineering-software/kpol_reference.py` | `03-engineering-software/test_kpol_reference.py` | PASS |
| `REQ-SW-004` | **Big Dot Phase Parsing:** Синтаксичний розбір оператора `•` або `not` із генерацією біта інверсії охоронця. | KPOL Toolchain | `03-engineering-software/kpol_reference.py` | `03-engineering-software/test_kpol_reference.py` | PASS |
| `REQ-SW-005` | **Cascade Mapping:** Формування ідентифікатора підписника (`subscriber_cid`) для міжконцептного рандеву. | KPOL Toolchain | `03-engineering-software/kpol_reference.py` | `03-engineering-software/test_kpol_reference.py` | PASS |
| `REQ-SW-006` | **HMAC-SHA256 Image Signing:** Генерація 1088-байтного захищеного образу з верифікацією підпису та nonce. | Secure Boot Compiler | `03-engineering-software/kpol_reference.py` | `03-engineering-software/test_kpol_reference.py` | PASS |
| `REQ-SW-007` | **Security ACL Static Verification:** Статична перевірка правил на відповідність таблиці повноважень перед збіркою. | Security Auditor | `03-engineering-software/kpol_reference.py` | `03-engineering-software/test_kpol_reference.py` | PASS |
| `REQ-SW-008` | **C99 Header & Baremetal Runtime:** Генерація сумісних C-структур та рантайму для мікроконтролерів (STM32/ESP32). | C Code Generator | `03-engineering-software/kpol_reference.py` | `03-engineering-software/test_kpol_reference.py` | PASS |
| `REQ-SW-009` | **Verilog Interconnect Generator:** Автоматична генерація апаратних шин та AXI-обгорток за моделлю KPOL. | Verilog Generator | `03-engineering-software/kpol_reference.py` | `03-engineering-software/test_kpol_reference.py` | PASS |
| `REQ-SW-010` | **Compliance RTM Synthesis:** Автоматична генерація звіту матриці простежуваності з коментарів та тегів KPOL. | RTM Compiler | `03-engineering-software/kpol_reference.py` | `03-engineering-software/test_kpol_reference.py` | PASS |

---

## 4. Результати аудиту відповідності (ASPICE 4.0 Lead Assessor Audit)

Аудит проведено автоматизованим верифікатором `scripts/aspice4_audit_tool.py`:
- **Загальна кількість вимог:** 30 (10 SYS + 10 HW + 10 SW)
- **Архітектурна алокація:** 100.0% $\to$ **F (Fully achieved: >85-100%)**
- **Покриття верифікацією:** 100.0% $\to$ **F (Fully achieved: >85-100%)**
- **Рівень успішного проходження тестів:** 100.0% $\to$ **F (Fully achieved: >85-100%)**
- **Невідслідковані / Фіктивні вимоги (Mock/Dummy):** 0

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.1.0 | 2026-11-09 | Перенесений історичний реєстр. |
| 0.1.1 | 2026-11-12 | Додано застереження і посилання на огляд #114; історичні рядки не змінено. |
| 0.1.2 | 2026-11-12 | Додано навігацію до першого зрізу наскрізного трасування (#118). |

## Абревіатури та глосарій

REQ — історичний ідентифікатор вимоги; RTM — матриця трасування вимог;
ASPICE — Automotive SPICE.
