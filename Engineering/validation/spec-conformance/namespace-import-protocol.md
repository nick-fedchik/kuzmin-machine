# KPOL v0.9 Namespace/Import Conformance Protocol

* **Версія:** 1.0.1
* **Date:** 2026-11-11
* **Issue:** #60
* **Status:** Preregistered; baseline not yet run


* **Тип WP редакції NG:** Protocol
* **Укладач редакції NG:** GitHub Copilot CLI, Auto; конкретна модель не атестована.
* **Підстава редакції NG:** команда власника від 2026-11-12; локальне перенесення без legacy.
* **Походження:** [оригінал 1.0.0](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/process/validation/60-spec-conformance/namespace-import-protocol.md), `707fdba697d92ef9874c9013eb6f4f3cb2796d70`.
* **Стан редакції NG:** адаптовано до нової структури; незалежна рецензія не проведена.

> **Межі редакції NG.** Перенесення й оформлення не є новим експериментом,
> повторною науковою перевіркою або затвердженням baseline. Авторство,
> рішення, числа й рецензії нижче стосуються зазначених оригінальних
> об'єктів та версій, а не автоматично цієї локальної копії.

## Scope

Probe only the normative unresolved-import behavior in KPOL v0.9. The source is `Engineering/specifications/kpol/kpol-0.9.0.md`, §§2.1–2.3 and 3–5. In particular, §3 defines `import Namespace::TargetName`, and §4 requires contract matching and rejects a solution without its specified problem.

This probe does not test the complete namespace grammar, namespace collision handling, cycle detection, compiler backends, or standards compliance.

## Falsification criterion

The probe falsifies the tested conformance claim if `parse_triad_files` accepts an import whose fully qualified target is absent from the supplied problem/solution/proof inputs. A failure to reject is evidence of this implementation's behavior only; it is not evidence about the Kuzmin Machine concept.

## Frozen input

```text
problem_src:
namespace Avionics::FlightControl;
Problem PitchController {}

solution_src:
namespace Avionics::FlightControl;
import Avionics::FlightControl::MissingController;
Solution PitchController {
    event Tick();
    state PitchAngle: Int32 = 0;
}

proof_src:
namespace Avionics::FlightControl;
import Avionics::FlightControl::PitchController;
Proof PitchController {
    assert Holds on Tick {
        when true expect PitchAngle == 0;
    }
}
```

## Expected result

Reject the unresolved `MissingController` import with an explicit `KpolError` (or a more specific documented linker error). Accepting the input is a failure. No implementation change is part of this protocol.

## Reproduction command

```sh
python3 Engineering/validation/60-spec-conformance/namespace-import-probe.py
```

Exit status 0 means the unresolved import was rejected; nonzero means it was accepted or another unexpected error occurred.

## Version history

| Version | Date | Change |
|---|---|---|
| 1.0.1 | 2026-11-12 | Редакція NG: структура, навігація та оформлення WP; нових результатів не заявлено. |
| 1.0.0 | 2026-11-11 | Initial frozen probe for unresolved KPOL v0.9 imports. |

## Abbreviations and glossary

| Term | Meaning |
|---|---|
| FQCN | Fully qualified name, including its namespace segments. |
| Preregistered probe | A fixed input and expected result committed before execution. |
