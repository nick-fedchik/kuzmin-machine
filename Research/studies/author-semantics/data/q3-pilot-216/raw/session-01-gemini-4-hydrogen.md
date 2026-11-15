# Сира відповідь сесії 01 (Q3-пілот #216)

* **Версія:** 0.1.0
* **Дата:** 2026-11-15
* **Тип WP:** Raw Data
* **Модель учасника:** `gemini-4-hydrogen`
* **Коміт SHA:** `56c9abd50f70dcb8318f66bfa26e7e73f4597e5b`
* **Ізоляція:** нульовий доступ до репозиторію; у промпті передано лише 3 специфікації (`kpol-cme-subset-0.1.0.md`, `kpol-cme2-profile-0.1.0.md`, `kpol-consolidated-0.1.0.md` §2–4) та формулювання 3 задач.

---

## Незмінна відповідь моделі

````markdown
### Задача 1 (профіль `KPOL-CME-1`)

```kpol
Problem Task1 {
    Invariants {
        NonNeg: S >= 0;
    }
}

Solution Task1 {
    state S: Int32 = 5;
    event E(P: Int32);

    rule R on E when P < 10 {
        set S := S + 1;
    }
}

Proof Task1 {
    scenario CheckIncrementAndGuard {
        step E(P = 4);
        expect S == 6;
        step E(P = 10);
        expect S == 6;
    }
}
```

---

### Задача 2 (профіль `KPOL-CME-2`)

```kpol
Problem Task2 {
    Invariants {
        NonNeg: S >= 0;
    }
}

Solution Task2 {
    state S: Int32 = 1;
    event E(P: Int32);

    rule R on E when 0 <= P and P <= 100 {
        set S := S - 1;
    }
}

Proof Task2 {
    scenario CheckRangeAndInvariant {
        step E(P = 50);
        expect S == 0;
        step E(P = 50);
        expect S == 0;
        step E(P = 101);
        expect S == 0;
    }
}
```

*Примітка:* дія `S - 1` компілюється в `CME_ACT_DEC (0x02)` і не використовує поле `W1 (operand_val)`, тому двосторонній інтервальний охоронець `0 <= P and P <= 100` (`RANGE`, межі в межах `[-32768, 32767]`) не створює колізії `CME2-OPERAND-COLLISION`.

---

### Задача 3 (профіль `KPOL-CME-2`)

```kpol
Problem Task3 {
    Invariants {
        NonNeg1: S1 >= 0;
        NonNeg2: S2 >= 0;
    }
}

Solution Task3 {
    state S1: Int32 = 0;
    state S2: Int32 = 0;
    event E(P: Int32);

    rule R1 on E when P >= 10 {
        set S1 := S1 + 1;
    }

    rule R2 on change(S1) when S1 >= 2 {
        set S2 := S2 + 1;
    }
}

Proof Task3 {
    scenario CheckAcyclicCascade {
        step E(P = 5);
        expect S1 == 0;
        expect S2 == 0;
        step E(P = 10);
        expect S1 == 1;
        expect S2 == 0;
        step E(P = 10);
        expect S1 == 2;
        expect S2 == 1;
    }
}
```

*Примітка:* умови `KPOL-CME-2` для каскаду виконані:
- на старті `Init(S1) = 0`, тому охоронець каскаду `S1 >= 2` дає `False` (стартова узгодженість);
- видавець `S1` використовує `INC` (`S1 + 1`), що гарантує зміну стану при коміті;
- `INC` не використовує `W1 (operand_val)`, тому колізії з охоронцями `>=` немає.
````

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-15 | Збереження сирої відповіді сесії 01 (`gemini-4-hydrogen`). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| WP | Work Product, результат роботи з визначеним призначенням. |
| SHA | Ідентифікатор Git-коміту. |
