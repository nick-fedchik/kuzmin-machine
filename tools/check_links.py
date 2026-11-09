#!/usr/bin/env python3
"""Перевіряє, що відносні посилання в усіх .md репозиторію ведуть на наявні файли.

Посилання зі схемою `file:` заборонені: вони ведуть на локальні шляхи поза
репозиторієм і не працюють у клонах та на GitHub.
Інші зовнішні посилання (http, https, mailto) і якорі (#...) не перевіряються.
Код виходу 1, якщо є хоча б одне бите посилання або посилання `file:`.
"""
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^(```|~~~)")


def links(md: Path):
    in_code = False
    for n, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
        if FENCE.match(line.strip()):
            in_code = not in_code
            continue
        if in_code:
            continue
        for m in LINK.finditer(line):
            yield n, m.group(1)


def main() -> int:
    broken = []
    file_links = []
    for md in sorted(ROOT.rglob("*.md")):
        if ".git" in md.parts:
            continue
        rel = md.relative_to(ROOT)
        for n, target in links(md):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
                if target.lower().startswith("file:"):
                    file_links.append(f"{rel}:{n}: {target}")
                continue
            if target.startswith("#"):
                continue
            path = unquote(target.split("#", 1)[0])
            if not path:
                continue
            dest = (ROOT / path.lstrip("/")) if path.startswith("/") else (md.parent / path)
            if not dest.exists():
                broken.append(f"{rel}:{n}: {target}")
    for f in file_links:
        print(f"Заборонене посилання file: {f}")
    for b in broken:
        print(b)
    print(f"Битих посилань: {len(broken)}; посилань file:: {len(file_links)}")
    return 1 if broken or file_links else 0


if __name__ == "__main__":
    sys.exit(main())
