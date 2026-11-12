#!/usr/bin/env python3
"""Compile a supported KPOL program to a CME BRAM image."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sw" / "kpol-ref"))
from kpol_reference import compile_concept_microcode_bram_image, parse_module  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("image", type=Path, help="new output file (not overwritten)")
    args = parser.parse_args()
    image = compile_concept_microcode_bram_image(
        parse_module(args.source.read_text(encoding="utf-8"))
    )
    with args.image.open("xb") as output:
        output.write(image)


if __name__ == "__main__":
    main()
