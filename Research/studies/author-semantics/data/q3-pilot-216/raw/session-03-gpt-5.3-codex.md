# Сира відповідь сесії 03 (Q3-пілот #216)

* **Версія:** 0.1.0
* **Дата:** 2026-11-15
* **Тип WP:** Raw Data
* **Модель учасника:** `gpt-5.3-codex`
* **Коміт SHA:** `56c9abd50f70dcb8318f66bfa26e7e73f4597e5b`
* **Ізоляція:** нульовий доступ до репозиторію; у промпті передано лише 3 специфікації (`kpol-cme-subset-0.1.0.md`, `kpol-cme2-profile-0.1.0.md`, `kpol-consolidated-0.1.0.md` §2–4) та формулювання 3 задач.

---

## Незмінна відповідь моделі

````markdown
```kpol
Problem Cme1Counter {
    Invariants {
        NonNeg: Counter >= 0;
    }
}
Solution Cme1Counter {
    state Counter: Int32 = 5;
    event Tick(P: Int32);
    rule Step on Tick when P < 10 {
        set Counter := Counter + 1;
    }
}
Proof Cme1Counter {
    scenario Main {
        step Tick(P = 4);
        expect Counter == 6;
        step Tick(P = 10);
        expect Counter == 6;
    }
}
```

```kpol
Problem Cme2DecRange {
    Invariants {
        NonNeg: Counter >= 0;
    }
}
Solution Cme2DecRange {
    state Counter: Int32 = 1;
    event Pulse(P: Int32);

    rule DecOnRange on Pulse when 0 <= P and P <= 100 {
        set Counter := Counter - 1;
    }
}
Proof Cme2DecRange {
    scenario Main {
        step Pulse(P = 50);
        expect Counter == 0;

        step Pulse(P = 50);
        expect Counter == 0;

        step Pulse(P = 101);
        expect Counter == 0;
    }
}
```

```kpol
Problem Cme2Cascade {
    Invariants {
        SrcNonNeg: S1 >= 0;
        DstNonNeg: S2 >= 0;
    }
}
Solution Cme2Cascade {
    state S1: Int32 = 0;
    state S2: Int32 = 0;

    event Ev(P: Int32);

    rule ExternalStep on Ev when P >= 10 {
        set S1 := S1 + 1;
    }

    rule CascadeStep on change(S1) when S1 >= 2 {
        set S2 := S2 + 1;
    }
}
Proof Cme2Cascade {
    scenario Main {
        step Ev(P = 5);
        expect S1 == 0;
        expect S2 == 0;

        step Ev(P = 10);
        expect S1 == 1;
        expect S2 == 0;

        step Ev(P = 10);
        expect S1 == 2;
        expect S2 == 1;
    }
}
```
````

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-15 | Збереження сирої відповіді сесії 03 (`gpt-5.3-codex`). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| WP | Work Product, результат роботи з визначеним призначенням. |
| SHA | Ідентифікатор Git-коміту. |
