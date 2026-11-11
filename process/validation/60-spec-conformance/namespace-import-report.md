# #60: unresolved imports in KPOL v0.9

* **Version:** 0.1.0
* **Date:** 2026-11-11
* **Issue:** #60, partial finding; does not close S2.
* **Executor:** GitHub Copilot CLI, Auto; concrete model unavailable.
* **Independent review:** not performed.
* **Prerecorded criterion:** commit `03f47c039c684e7f421e0cc9985ff2ffd7561551`; [protocol](namespace-import-protocol.md).

## 1. Limits

This probe covers only rejection of an unresolved import in KPOL v0.9. It does
not verify successful namespace resolution, collision handling, cycle
detection, or full module linking. It says nothing about the Kuzmin Machine
concept or external standards compliance.

## 2. Result

KPOL v0.9 §3 defines namespace and import declarations. Section 4 requires
symbol collection and contract matching, including rejection of a solution
without its specified problem.

The preregistered input imports
`Avionics::FlightControl::MissingController`, which is absent from all three
triad inputs. `parse_triad_files` accepted it. The probe therefore exited 1
instead of the expected 0:

| Evidence | Result |
|---|---|
| Preregistration commit | `03f47c039c684e7f421e0cc9985ff2ffd7561551` |
| Implementation commit | `03f47c039c684e7f421e0cc9985ff2ffd7561551` |
| Implementation SHA-256 | `4c76a4914125a70e02812c3a690c7c6dfbe690ba00fac6d105f6a5ac5650f6bf` |
| Probe result | Expected exit 0; actual exit 1 |
| Raw output and metadata | [baseline.txt](raw-20261111-02/baseline.txt), [baseline.json](raw-20261111-02/baseline.json) |

The current implementation removes lines beginning with `namespace` or
`import` before parsing the concatenated files. The tested invalid import is
therefore silently discarded rather than resolved or rejected.

## 3. Disposition

This is a demonstrated mismatch between one normative KPOL v0.9 claim and our
reference implementation. Full namespace/import semantics would require more
than rejecting this single malformed input; no implementation change is
claimed here. Issue #60 remains open.

## Version history

| Version | Date | Change |
|---|---|---|
| 0.1.0 | 2026-11-11 | Record the preregistered unresolved-import counterexample. |

## Abbreviations and glossary

| Term | Meaning |
|---|---|
| FQCN | Fully qualified name, including namespace segments. |
| KPOL | The project's problem-oriented language and specifications. |
| Reference implementation | This repository's implementation under test, not an author-provided MK implementation. |
