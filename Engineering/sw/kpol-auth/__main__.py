"""CLI entry point for KPOL-AUTH frontend check and Do/Go + CME-RAW-1 lowering."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import struct
import sys


def _bootstrap_package():
    if __package__:
        return sys.modules[__package__]
    if "kpol_auth" in sys.modules:
        return sys.modules["kpol_auth"]
    pkg_dir = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "kpol_auth",
        pkg_dir / "__init__.py",
        submodule_search_locations=[str(pkg_dir)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kpol_auth"] = module
    spec.loader.exec_module(module)
    return module


def _format_span(span) -> str:
    if span is None:
        return ""
    return (
        f" [line {span.line}, col {span.column}, "
        f"bytes {span.byte_offset}..{span.byte_end}]"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kpol_auth",
        description=(
            "KPOL-AUTH native frontend & derived Do/Go + CME-RAW-1 lowering CLI "
            "(fail-closed on KPOL-AUTH-* and KPOL-LOWER-*)."
        ),
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to input KPOL-AUTH source file (UTF-8).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate KPOL-AUTH syntax, uncertainty gates, and lowering invariants.",
    )
    parser.add_argument(
        "--emit-bram",
        type=Path,
        default=None,
        metavar="PATH",
        help="Write 1024-byte CME-RAW-1 BRAM routing image (.bin).",
    )
    parser.add_argument(
        "--emit-dogo",
        type=Path,
        default=None,
        metavar="PATH",
        help="Write lowered Do/Go artifact (.json metadata+bytecode or packed 32-bit .bin).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    ka = _bootstrap_package()
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        source_text = args.input.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"KPOL-CLI-IO: {exc}", file=sys.stderr)
        return 1

    try:
        program = ka.parse_kpol_auth(source_text)
        artifact = ka.lower_document(program)
    except ka.KpolAuthError as exc:
        diag = exc.diagnostic
        loc = _format_span(diag.span)
        print(f"{diag.code}{loc}: {diag.message}", file=sys.stderr)
        return 2
    except ka.KpolAuthLoweringError as exc:
        loc = _format_span(exc.span)
        print(f"{exc.code}{loc}: {exc.message}", file=sys.stderr)
        return 3

    try:
        if args.emit_bram is not None:
            args.emit_bram.parent.mkdir(parents=True, exist_ok=True)
            args.emit_bram.write_bytes(artifact.bram_image)

        if args.emit_dogo is not None:
            args.emit_dogo.parent.mkdir(parents=True, exist_ok=True)
            if args.emit_dogo.suffix.lower() == ".bin":
                packed = b"".join(struct.pack("<I", w & 0xFFFFFFFF) for w in artifact.code_o)
                args.emit_dogo.write_bytes(packed)
            else:
                payload = {
                    "format": "kpol-auth-dogo-0.1.0",
                    "concepts": [asdict(c) for c in artifact.concepts],
                    "subscriptions": [asdict(s) for s in artifact.subscriptions],
                    "code_o": list(artifact.code_o),
                    "code_o_hex": [f"0x{w:08X}" for w in artifact.code_o],
                }
                args.emit_dogo.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
    except OSError as exc:
        print(f"KPOL-CLI-IO: {exc}", file=sys.stderr)
        return 1

    if args.check or (args.emit_bram is None and args.emit_dogo is None):
        print(
            f"OK: {len(artifact.concepts)} concepts, "
            f"{len(artifact.subscriptions)} subscriptions, "
            f"{len(artifact.code_o)} Do/Go words, "
            f"{len(artifact.bram_image)} BRAM bytes"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
