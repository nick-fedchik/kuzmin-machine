#!/usr/bin/env python3
"""Compile a KPOL-CME-1 or KPOL-CME-2 program to a CME-RAW-1 BRAM image (and optional C99 / Z3 certificate)."""
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
        choices=("KPOL-CME-1", "KPOL-CME-2"),
        default="KPOL-CME-1",
        help="target CME profile (default: KPOL-CME-1)",
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
    parser.add_argument("image", type=Path, help="new output file (not overwritten)")
    args = parser.parse_args()
    prefix = "B3" if args.profile == "KPOL-CME-1" else "CME2"
    try:
        source = args.source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        parser.exit(2, f"{prefix}-IO: {args.source}: {error}\n")
    try:
        module = Parser(source).parse()
    except KpolError as error:
        parser.exit(2, f"{prefix}-SYNTAX: {args.source}: {error}\n")
    try:
        image = compile_concept_microcode_bram_image(module, profile=args.profile)
    except KpolError as error:
        parser.exit(2, f"{error}\n")

    c99_code = None
    z3_cert = None
    if args.emit_c99 is not None or args.emit_z3_cert is not None:
        try:
            descriptors = disassemble_concept_microcode(image)
            concept_names = [st.name for st in module.states]
            c99_code = emit_c99_safety_module(
                descriptors,
                profile=args.profile,
                module_name=module.name,
                concept_names=concept_names,
            )
            z3_cert = prove_c99_descriptor_safety_z3(
                descriptors,
                c99_source=c99_code,
                profile=args.profile,
                module_name=module.name,
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

    for out_path in (args.image, args.emit_c99, args.emit_z3_cert):
        if out_path is not None and out_path.exists():
            parser.exit(2, f"{prefix}-IO: {out_path}: File exists\n")

    created_paths: list[Path] = []
    try:
        with args.image.open("xb") as output:
            output.write(image)
        created_paths.append(args.image)

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
        concept_names = [st.name for st in module.states]
        dbg = KpolCascadeDebugger(
            image,
            profile=args.profile,
            module_name=module.name,
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
