#!/usr/bin/env python3
"""Compile a KPOL-CME-1, KPOL-CME-2, or EKPOL program to a CME-RAW-1 BRAM image (and optional C99 / Z3 certificate / KPOL<->EKPOL transpilation)."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sw" / "kpol-ref"))
from c99_emitter import (  # noqa: E402
    C99EmitterError,
    emit_c99_safety_module,
    prove_c99_descriptor_safety_z3,
)
from ekpol_frontend import (  # noqa: E402
    EkpolError,
    compile_ekpol_to_bram_image,
    parse_ekpol,
    transpile_ekpol_to_kpol,
    transpile_kpol_to_ekpol,
)
from kpol_reference import (  # noqa: E402
    KpolError,
    Parser,
    compile_concept_microcode_bram_image,
    disassemble_concept_microcode,
)
from kpol_debugger import (  # noqa: E402
    KpolCascadeDebugger,
    parse_trace_events_spec,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("KPOL-CME-1", "KPOL-CME-2", "EKPOL"),
        default=None,
        help="target profile: KPOL-CME-1, KPOL-CME-2, or EKPOL (default: auto-detect .ekpol or KPOL-CME-1)",
    )
    parser.add_argument(
        "--emit-kpol",
        dest="emit_kpol",
        type=Path,
        default=None,
        help="transpile input .ekpol to classic .kpol at this new path (not overwritten)",
    )
    parser.add_argument(
        "--emit-ekpol",
        dest="emit_ekpol",
        type=Path,
        default=None,
        help="transpile input .kpol to .ekpol at this new path (not overwritten)",
    )
    parser.add_argument(
        "--ekpol-style",
        dest="ekpol_style",
        choices=("symbolic", "keyword"),
        default="symbolic",
        help="formatting style when emitting .ekpol: 'symbolic' (<-, ~, ::, .) or 'keyword' (on write, on change, when, commit)",
    )
    parser.add_argument(
        "--emit-c99",
        dest="emit_c99",
        type=Path,
        default=None,
        help="new output C99 safety module path (not overwritten)",
    )
    parser.add_argument(
        "--emit-z3-cert",
        dest="emit_z3_cert",
        type=Path,
        default=None,
        help="new output Z3 SMT safety certificate JSON path (not overwritten)",
    )
    parser.add_argument(
        "--dump-concepts",
        action="store_true",
        help="print the compiled BRAM concept descriptor table (W0, Valid '_', W1, W2, W3)",
    )
    parser.add_argument(
        "--trace-events",
        dest="trace_events",
        type=str,
        default=None,
        help="optional event trace specification (e.g. '0:10,0:100,0:invalid') to debug after compilation",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "image",
        type=Path,
        nargs="?",
        default=None,
        help="new output 1024-byte BRAM image file (not overwritten; optional if only --emit-kpol/--emit-ekpol is used)",
    )
    args = parser.parse_args()

    is_ekpol_input = (args.profile == "EKPOL") or (
        args.profile is None and args.source.suffix.lower() == ".ekpol"
    )
    effective_profile = "EKPOL" if is_ekpol_input else (args.profile or "KPOL-CME-1")
    if args.image is None and args.emit_kpol is None and args.emit_ekpol is None:
        parser.error("the following arguments are required: image")

    prefix = "EKPOL" if is_ekpol_input else ("B3" if effective_profile == "KPOL-CME-1" else "CME2")
    try:
        source = args.source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        parser.exit(2, f"{prefix}-IO: {args.source}: {error}\n")

    emitted_kpol_text = None
    emitted_ekpol_text = None
    concept_names: list[str] = []
    module_name = args.source.stem

    if is_ekpol_input:
        try:
            ek_prog = parse_ekpol(source, default_module_name=args.source.stem)
            module_name = ek_prog.module_name
            concept_names = [c.name for c in ek_prog.concepts]
            image = compile_ekpol_to_bram_image(ek_prog)
            if args.emit_kpol is not None:
                emitted_kpol_text = transpile_ekpol_to_kpol(ek_prog)
            if args.emit_ekpol is not None:
                kpol_tmp = transpile_ekpol_to_kpol(ek_prog)
                emitted_ekpol_text = transpile_kpol_to_ekpol(kpol_tmp, style=args.ekpol_style)
        except (EkpolError, KpolError) as error:
            parser.exit(2, f"{error}\n")
    else:
        try:
            module = Parser(source).parse()
            module_name = module.name
            concept_names = [st.name for st in module.states]
        except KpolError as error:
            parser.exit(2, f"{prefix}-SYNTAX: {args.source}: {error}\n")
        try:
            if args.image is not None or args.emit_c99 is not None or args.emit_z3_cert is not None or args.dump_concepts or args.trace_events is not None:
                image = compile_concept_microcode_bram_image(module, profile=effective_profile)
            else:
                image = b""
            if args.emit_ekpol is not None:
                emitted_ekpol_text = transpile_kpol_to_ekpol(source, style=args.ekpol_style)
            if args.emit_kpol is not None:
                emitted_kpol_text = source
        except (EkpolError, KpolError) as error:
            parser.exit(2, f"{error}\n")

    c99_code = None
    z3_cert = None
    if args.emit_c99 is not None or args.emit_z3_cert is not None:
        c99_prof = "KPOL-CME-2" if is_ekpol_input else effective_profile
        try:
            descriptors = disassemble_concept_microcode(image)
            c99_code = emit_c99_safety_module(
                descriptors,
                profile=c99_prof,
                module_name=module_name,
                concept_names=concept_names,
            )
            z3_cert = prove_c99_descriptor_safety_z3(
                descriptors,
                c99_source=c99_code,
                profile=c99_prof,
                module_name=module_name,
                concept_names=concept_names,
            )
            if not z3_cert.get("passed", False):
                reasons = "; ".join(z3_cert.get("failures", ["Z3 verification failed"]))
                parser.exit(2, f"{prefix}-Z3: {reasons}\n")
        except (C99EmitterError, KpolError, RuntimeError) as error:
            parser.exit(2, f"{prefix}-C99: {error}\n")

    trace_events_list = None
    if args.trace_events is not None:
        try:
            trace_events_list = parse_trace_events_spec(args.trace_events)
        except KpolError as error:
            parser.exit(2, f"{prefix}-TRACE: {error}\n")

    for out_path in (args.image, args.emit_kpol, args.emit_ekpol, args.emit_c99, args.emit_z3_cert):
        if out_path is not None and out_path.exists():
            parser.exit(2, f"{prefix}-IO: {out_path}: File exists\n")

    created_paths: list[Path] = []
    try:
        if args.image is not None:
            with args.image.open("xb") as output:
                output.write(image)
            created_paths.append(args.image)

        if args.emit_kpol is not None and emitted_kpol_text is not None:
            with args.emit_kpol.open("x", encoding="utf-8") as k_out:
                k_out.write(emitted_kpol_text)
            created_paths.append(args.emit_kpol)

        if args.emit_ekpol is not None and emitted_ekpol_text is not None:
            with args.emit_ekpol.open("x", encoding="utf-8") as ek_out:
                ek_out.write(emitted_ekpol_text)
            created_paths.append(args.emit_ekpol)

        if args.emit_c99 is not None and c99_code is not None:
            with args.emit_c99.open("x", encoding="utf-8") as c_out:
                c_out.write(c99_code)
            created_paths.append(args.emit_c99)

        if args.emit_z3_cert is not None and z3_cert is not None:
            with args.emit_z3_cert.open("x", encoding="utf-8") as z_out:
                z_out.write(json.dumps(z3_cert, indent=2, ensure_ascii=False) + "\n")
            created_paths.append(args.emit_z3_cert)
    except OSError as error:
        for created in created_paths:
            try:
                created.unlink()
            except OSError:
                pass
        parser.exit(2, f"{prefix}-IO: {error}\n")

    if args.dump_concepts or trace_events_list is not None:
        dbg = KpolCascadeDebugger(
            image,
            profile=effective_profile,
            module_name=module_name,
            source_code=source,
            concept_names=concept_names,
            break_on_reject=True,
            watch_state_change=True,
        )
        if trace_events_list is not None:
            dbg.run_events(trace_events_list)
            print(dbg.format_full_4block_report())
        else:
            print(dbg.format_source_block())
            print()
            print(dbg.format_concepts_table())


if __name__ == "__main__":
    main()
