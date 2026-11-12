#!/usr/bin/env python3
"""Compile a KPOL-CME-1 program to a CME-RAW-1 BRAM image."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sw" / "kpol-ref"))
from kpol_reference import KpolError, Parser, compile_concept_microcode_bram_image  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("image", type=Path, help="new output file (not overwritten)")
    args = parser.parse_args()
    try:
        source = args.source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        parser.exit(2, f"B3-IO: {args.source}: {error}\n")
    try:
        module = Parser(source).parse()
    except KpolError as error:
        parser.exit(2, f"B3-SYNTAX: {args.source}: {error}\n")
    try:
        image = compile_concept_microcode_bram_image(module, profile="KPOL-CME-1")
    except KpolError as error:
        parser.exit(2, f"{error}\n")
    try:
        with args.image.open("xb") as output:
            output.write(image)
    except OSError as error:
        parser.exit(2, f"B3-IO: {args.image}: {error}\n")


if __name__ == "__main__":
    main()
