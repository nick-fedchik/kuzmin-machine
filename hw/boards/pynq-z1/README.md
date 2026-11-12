# Документація платформи Digilent PYNQ-Z1

* **Версія:** 0.1.0
* **Дата:** 2026-11-12

---

## 1. Офіційні джерела та документація

* **Офіційний Reference Manual (Digilent):**  
  [https://digilent.com/reference/programmable-logic/pynq-z1/reference-manual](https://digilent.com/reference/programmable-logic/pynq-z1/reference-manual)
* **Принципова електрична схема (Rev F.0):**  
  [hw/pynq-z1-sch-f0.pdf](../../pynq-z1-sch-f0.pdf) (локальна копія, Doc# 6003-500-017)
* **Master XDC Constraints:**  
  [pynq_z1.xdc](pynq_z1.xdc)
* **Стенд та закупівлі:**  
  [../bench-procurement.md](../bench-procurement.md)

---

## 2. Апаратні інтерфейси та призначення виводів (Pinout)

### 2.1. Pmod роз'єми (PMODA / PMODB, 3.3V LVCMOS)

Кожен роз'єм Pmod має 12 контактів (2 ряди по 6 отворів, крок 2,54 мм).
На сигнальних лініях встановлено заводські послідовні захисні резистори 200 Ом та захисні діоди.

#### Роз'єм PMODA (Pmod JA)

```
        Сигнальна сторона                           Сторона живлення
  +-------------------------------------------------------------------+
  |  [1] JA1_P (Y18)  [2] JA1_N (Y19)  [3] JA2_P (Y16)  [4] JA2_N (Y17)  |  [5] GND    [6] VCC 3.3V
  |  [7] JA3_P (U18)  [8] JA3_N (U19)  [9] JA4_P (W18) [10] JA4_N (W19)  | [11] GND   [12] VCC 3.3V
  +-------------------------------------------------------------------+
```

* **Визначення на платі:** Край, що продзвонюється на корпус USB — це **GND (піни 5, 11)**. Протилежний край — це **піни 1, 7 (JA1)**.

#### Роз'єм PMODB (Pmod JB)

```
        Сигнальна сторона                           Сторона живлення
  +-------------------------------------------------------------------+
  |  [1] JB1_P (W14)  [2] JB1_N (Y14)  [3] JB2_P (T11)  [4] JB2_N (T10)  |  [5] GND    [6] VCC 3.3V
  |  [7] JB3_P (V12)  [8] JB3_N (W13)  [9] JB4_P (V13) [10] JB4_N (U12)  | [11] GND   [12] VCC 3.3V
  +-------------------------------------------------------------------+
```

---

### 2.2. Користувацькі кнопки, перемикачі та світлодіоди

| Периферія | Шовкографія | Пін FPGA | Стандарт | Призначення в KPOL |
| :--- | :--- | :--- | :--- | :--- |
| Кнопка 0 | `BTN0` | `D19` | LVCMOS33 | Асинхронний тригер події (`ext_event_valid_i`) |
| Кнопка 1 | `BTN1` | `D20` | LVCMOS33 | Резерв |
| Кнопка 2 | `BTN2` | `L20` | LVCMOS33 | Резерв |
| Кнопка 3 | `BTN3` | `L19` | LVCMOS33 | Резерв |
| Перемикач 0 | `SW0` | `M20` | LVCMOS33 | Invariant status: 1 = OK, 0 = Fail-closed reject |
| Перемикач 1 | `SW1` | `M19` | LVCMOS33 | Assumption status: 1 = OK, 0 = Input reject |
| Світлодіод 0 | `LD0` (зелений) | `R14` | LVCMOS33 | Committed / Reactive out |
| Світлодіод 1 | `LD1` (зелений) | `P14` | LVCMOS33 | Rejected Invariant (Fail-Closed) |
| Світлодіод 2 | `LD2` (зелений) | `N16` | LVCMOS33 | Hazard Observed |
| Світлодіод 3 | `LD3` (зелений) | `M14` | LVCMOS33 | Rejected Input |
| RGB4 (Red) | `RGB4_R` | `V16` | LVCMOS33 | Invariant Reject Alert |
| RGB4 (Green)| `RGB4_G` | `F17` | LVCMOS33 | Transaction Committed |
| RGB4 (Blue) | `RGB4_B` | `M17` | LVCMOS33 | Input Reject / Hazard Alert |
| RGB5 (RGB) | `RGB5` | `W15, W16, Y17` | LVCMOS33 | Heartbeat Pulse (~1.5 Hz) |

---

## 3. Обмеження та застереження безпеки

> [!CAUTION]
> Усі лінії I/O на роз'ємах PMODA, PMODB та Arduino/ChipKIT працюють виключно з напругою **3,3 В (LVCMOS33)** і **НЕ є 5V-толерантними**! Підключення 5 В сигналів безпосередньо призведе до пошкодження мікросхеми FPGA Zynq-7020.
