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
            z3_cert = prove_c99_descriptor_safety_z3(
                descriptors,
                profile=args.profile,
                module_name=module.name,
                concept_names=concept_names,
            )
            if not z3_cert.get("passed", False):
                reasons = "; ".join(z3_cert.get("failures", ["Z3 verification failed"]))
                parser.exit(2, f"{prefix}-Z3: {reasons}\n")
            if args.emit_c99 is not None:
                c99_code = emit_c99_safety_module(
                    descriptors,
                    profile=args.profile,
                    module_name=module.name,
                    concept_names=concept_names,
                    z3_certificate=z3_cert,
                )
        except (C99EmitterError, KpolError) as error:
            parser.exit(2, f"{prefix}-C99: {error}\n")

    for out_path in (args.image, args.emit_c99, args.emit_z3_cert):
        if out_path is not None and out_path.exists():
            parser.exit(2, f"{prefix}-IO: {out_path}: File exists\n")

    try:
        with args.image.open("xb") as output:
            output.write(image)
    except OSError as error:
        parser.exit(2, f"{prefix}-IO: {args.image}: {error}\n")

    if args.emit_c99 is not None and c99_code is not None:
        try:
            with args.emit_c99.open("x", encoding="utf-8") as c_out:
                c_out.write(c99_code)
        except OSError as error:
            parser.exit(2, f"{prefix}-IO: {args.emit_c99}: {error}\n")

    if args.emit_z3_cert is not None and z3_cert is not None:
        try:
            with args.emit_z3_cert.open("x", encoding="utf-8") as z_out:
                z_out.write(json.dumps(z3_cert, indent=2, ensure_ascii=False) + "\n")
        except OSError as error:
            parser.exit(2, f"{prefix}-IO: {args.emit_z3_cert}: {error}\n")


if __name__ == "__main__":
    main()
