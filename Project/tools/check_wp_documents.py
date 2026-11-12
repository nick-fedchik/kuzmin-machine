#!/usr/bin/env python3
"""Check NG document envelopes and immutable inputs, not semantic acceptance."""

import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def check(root):
    root = Path(root)
    errors = []
    manifest = root / "Project/registers/migration-manifest.json"
    records = json.loads(manifest.read_text())["entries"] if manifest.exists() else []
    immutable = {row["destination"]: row for row in records if row["immutable"]}
    for relative, row in immutable.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"{relative}: missing immutable input")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != row["source_sha256"]:
            errors.append(f"{relative}: changed immutable input")
    checked = 0
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(root).as_posix()
        if relative in immutable or relative.startswith("Project/templates/"):
            continue
        if any(part in {".git", ".pytest_cache", "__pycache__"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        checked += 1
        fields = {
            "version": r"(?im)^\* \*\*(?:Версія|Version).*?:?\*\*:?\s+\d+\.\d+\.\d+",
            "date": r"(?im)^\* \*\*(?:Дата|Оновлено|Date|Updated).*?:?\*\*:?\s+\d{4}-\d{2}-\d{2}",
            "WP type": r"(?m)^\* \*\*Тип WP(?: редакції NG)?:\*\*\s+\S",
            "history": r"(?im)^## .*?(?:історія версій|version history)",
            "glossary": r"(?im)^## .*?(?:глосарій|словник термінів|glossary)",
        }
        for field, pattern in fields.items():
            if not re.search(pattern, text):
                errors.append(f"{relative}: missing {field}")
    if not checked:
        errors.append("no live WP Markdown documents found")
    for name in ("docs", "process", "architecture", "requirements", "specs",
                 "hw", "sw", "tools", "experiments", "archives"):
        if (root / name).exists():
            errors.append(f"{name}: obsolete root directory")
    if (root / "Engineering/hw/rtl/poc-demo").exists():
        errors.append("Engineering/hw/rtl/poc-demo: excluded implementation")
    return {"documents_checked": checked, "immutable_checked": len(immutable), "errors": errors}


if __name__ == "__main__":
    result = check(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result["errors"]))
