# KPOL v0.9 Namespace/Import Conformance Protocol

* **Version:** 1.0.0
* **Date:** 2026-11-11
* **Issue:** #60
* **Status:** Preregistered; baseline not yet run

## Scope

Probe only the normative unresolved-import behavior in KPOL v0.9. The source is `specs/kpol/kpol-0.9.0.md`, §§2.1–2.3 and 3–5. In particular, §3 defines `import Namespace::TargetName`, and §4 requires contract matching and rejects a solution without its specified problem.

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
python3 process/validation/60-spec-conformance/namespace-import-probe.py
```

Exit status 0 means the unresolved import was rejected; nonzero means it was accepted or another unexpected error occurred.

## Version history

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-11-11 | Initial frozen probe for unresolved KPOL v0.9 imports. |

## Abbreviations and glossary

| Term | Meaning |
|---|---|
| FQCN | Fully qualified name, including its namespace segments. |
| Preregistered probe | A fixed input and expected result committed before execution. |
