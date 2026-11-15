# Сира відповідь сесії 02 (Q3-пілот #216)

* **Версія:** 0.1.0
* **Дата:** 2026-11-15
* **Тип WP:** Raw Data
* **Модель учасника:** `claude-sonnet-5.5`
* **Коміт SHA:** `56c9abd50f70dcb8318f66bfa26e7e73f4597e5b`
* **Ізоляція:** нульовий доступ до репозиторію; у промпті передано лише 3 специфікації (`kpol-cme-subset-0.1.0.md`, `kpol-cme2-profile-0.1.0.md`, `kpol-consolidated-0.1.0.md` §2–4) та формулювання 3 задач.

---

## Незмінна відповідь моделі

````markdown
**Завдання 1 (`KPOL-CME-1`)**

```kpol
Problem Counter1 {
    Invariants { NonNeg: S >= 0; }
}
Solution Counter1 {
    state S: Int32 = 5;
    event E(P: Int32);
    rule R on E when P < 10 {
        set S := S + 1;
    }
}
Proof Counter1 {
    scenario Check {
        step E(P = 4);
        expect S == 6;
        step E(P = 10);
        expect S == 6;
    }
}
```

**Завдання 2 (`KPOL-CME-2`)**

```kpol
Problem Dec2 {
    Invariants { NonNeg: S >= 0; }
}
Solution Dec2 {
    state S: Int32 = 1;
    event E(P: Int32);
    rule R on E when 0 <= P and P <= 100 {
        set S := S - 1;
    }
}
Proof Dec2 {
    scenario Check {
        step E(P = 50);
        expect S == 0;
        step E(P = 50);
        expect S == 0;
        step E(P = 101);
        expect S == 0;
    }
}
```

**Завдання 3 (`KPOL-CME-2`)**

```kpol
Problem Cascade2 {
    Invariants {
        NonNegA: A >= 0;
        NonNegB: B >= 0;
    }
}
Solution Cascade2 {
    state A: Int32 = 0;
    state B: Int32 = 0;
    event E(P: Int32);
    rule Ext on E when P >= 10 {
        set A := A + 1;
    }
    rule Casc on change(A) when A >= 2 {
        set B := B + 1;
    }
}
Proof Cascade2 {
    scenario Check {
        step E(P = 5);
        expect A == 0;
        expect B == 0;
        step E(P = 10);
        expect A == 1;
        expect B == 0;
        step E(P = 10);
        expect A == 2;
        expect B == 1;
    }
}
```

Я не компілював ці модулі, бо перевіряв їх лише за наданими специфікаціями.

Умови профілів, які задовольняє код:
- **Завдання 3:** `A` є видавцем каскаду і має крок `INC`, тому зміна стану гарантована. Охоронець каскаду `A >= 2` хибний на початковому `A = 0`, тому стартова узгодженість не порушується. Охоронці не потребують `W1` разом з `ADD`/`SUB`, тому колізії операндів немає.
- **Завдання 2:** на кроці 2 кандидат `-1` порушує інваріант, тому стан не змінюється. Межі `0` і `100` потрапляють у дозволений діапазон `[-32768, 32767]`.

Неоднозначності специфікацій:
- Специфікація 2 не наводить повної граматики. Я використав синтаксис фронтенду зі специфікації 3 (`state`, `event`, `rule`) і форму `P = integer` у `step`.
- Назви інваріантів (`NonNeg`, `NonNegA`) специфікації прямо не вимагають, але граматика фронтенду допускає їх.
````

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 0.1.0 | 2026-11-15 | Збереження сирої відповіді сесії 02 (`claude-sonnet-5.5`). |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| WP | Work Product, результат роботи з визначеним призначенням. |
| SHA | Ідентифікатор Git-коміту. |
