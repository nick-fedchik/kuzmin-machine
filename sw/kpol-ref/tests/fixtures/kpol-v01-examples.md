# Регресійні приклади історичного KPOL v0.1

* **Версія:** 0.1.0 (версія набору fixtures)
* **Дата:** 2026-11-12
* **Джерело:** [kpol-0.1.0.md, редакція 0.1.2](https://github.com/nick-fedchik/kuzmin-machine/blob/727c19ecb08a6bd45cffea541a64db01acaab148/specs/kpol/kpol-0.1.0.md),
  три блоки `kpol` з §6, без зміни тексту.
* **WI:** [#19](https://github.com/nick-fedchik/kuzmin-machine/issues/19).

Це входи тестів Interpreter, **не** дозволені програми KPOL-CME-1.
Джерельні пояснення та походження збережено в Git-архіві.

## ReactorMonitor

```kpol
Problem ReactorMonitor {
    Assumptions {
        TempValid on Sample: Temp != Unknown and Temp >= -50 and Temp <= 300;
        PressureValid on Sample: Pressure != Unknown and Pressure >= 0 and Pressure <= 50;
    }
    Invariants {
        FaultImpliesTrip: SensorFault == false or Trip == true;
    }
    Hazards {
        CriticalCombination on Sample to Trip: Temp > 120 and Pressure > 15;
    }
    Goals {
        NormalInputClearsFault: SensorFault == false;
    }
}
Solution ReactorMonitor {
    event Sample(Temp: Float<degC>, Pressure: Float<bar>);
    state SensorFault: Bool = false;
    state Trip: Bool = false;
    rule trip_on_critical on Sample when Temp > 120 and Pressure > 15 covers CriticalCombination {
        set Trip := true;
        set SensorFault := false;
    }
    rule clear_trip on Sample when Temp <= 120 or Pressure <= 15 {
        set Trip := false;
        set SensorFault := false;
    }
    rule reject_sample on reject Sample {
        set SensorFault := true;
        set Trip := true;
    }
}
```

## EuclidGCD

```kpol
Problem EuclidGCD {
    Assumptions {
        PositiveOperands: A > 0 and B > 0;
    }
    Invariants {
        DivisorPreserved: gcd(A, B) == gcd(OriginalA, OriginalB);
    }
    Goals {
        CompletedWithGCD: Done == true and A == B and Result == A;
    }
}
Solution EuclidGCD {
    state A: U64 = 48;
    state B: U64 = 18;
    state OriginalA: U64 = 48;
    state OriginalB: U64 = 18;
    state Result: U64 = 0;
    state Done: Bool = false;
    rule reduce_a on change(A, B) when A > B {
        set A := A - B;
    }
    rule reduce_b on change(A, B) when B > A {
        set B := B - A;
    }
    rule finish on change(A, B) when A == B {
        set Result := A;
        set Done := true;
    }
}
```

## EnergyMeter

```kpol
Problem EnergyMeter {
    Assumptions {
        ValidSample on Sample: V != Unknown and I != Unknown and dt > 0;
    }
    Invariants {
        NonNegativeEnergy: EnergyJ >= 0;
    }
    Goals {
        EnergyIsNonNegative: EnergyJ >= 0;
    }
}
Solution EnergyMeter {
    event Sample(V: Float<V>, I: Float<A>, dt: Float<s>);
    state EnergyJ: Float<J> = 0;
    state SensorFault: Bool = false;
    rule integrate on Sample {
        set EnergyJ := EnergyJ + V * I * dt;
        set SensorFault := false;
    }
    rule reject_sample on reject Sample {
        set SensorFault := true;
    }
}
```

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.1.0 | 2026-11-12 | Незмінені приклади вилучено з залежності від живого тексту старої специфікації (#19). |

## Абревіатури та глосарій

Fixture — вхід тесту; Interpreter — еталонне програмне виконання,
не RTL або апаратний контролер.
