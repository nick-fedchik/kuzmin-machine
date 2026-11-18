#!/usr/bin/env python3
"""Check NG document envelopes and immutable inputs, not semantic acceptance."""

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def _infer_direction(rel_path: str) -> str:
    if rel_path.startswith("Engineering/"):
        return "Engineering"
    if rel_path.startswith("Research/"):
        return "Research"
    if rel_path.startswith("Project/"):
        return "Project"
    return "technical-root"


def _infer_wp_type(path: Path, rel_path: str) -> str:
    if path.suffix.lower() == ".md":
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"(?m)^\* \*\*Тип WP(?: редакції NG)?:\*\*\s+(.+?)\s*$", text)
        if m:
            return m.group(1).strip().strip("`")
        return "Guide"
    if "/raw/" in f"/{rel_path}" or rel_path.endswith((".log", ".json", ".csv", ".hex", ".bin", ".lac")):
        if rel_path.endswith("go.mod"):
            return "Configuration"
        return "Data"
    if rel_path.endswith(("go.mod", ".yml", ".yaml", ".ini", ".gitignore")):
        return "Configuration"
    return "Source Code"


def write_wp_index(root: Path) -> None:
    index_path = root / "Project/registers/wp-index.json"
    existing_data = json.loads(index_path.read_text(encoding="utf-8"))
    by_path = {e["path"]: dict(e) for e in existing_data.get("entries", [])}

    added = 0
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in {".git", ".pytest_cache", "__pycache__"} for part in p.parts):
            continue
        rel = p.relative_to(root).as_posix()
        if rel not in by_path:
            by_path[rel] = {
                "path": rel,
                "direction": _infer_direction(rel),
                "wp_type": _infer_wp_type(p, rel),
                "immutable_input": False,
            }
            added += 1

    entries = [by_path[k] for k in sorted(by_path)]
    ver_parts = [int(x) for x in existing_data.get("version", "0.21.0").split(".")]
    if added > 0:
        ver_parts[1] += 1
        ver_parts[2] = 0
    new_obj = {
        "version": ".".join(str(x) for x in ver_parts),
        "date": datetime.date.today().isoformat(),
        "entries": entries,
    }
    index_path.write_text(json.dumps(new_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    parser = argparse.ArgumentParser(description="Check WP documents and optionally update wp-index.json")
    parser.add_argument("--write-index", action="store_true", help="update Project/registers/wp-index.json")
    args = parser.parse_args()
    if args.write_index:
        write_wp_index(ROOT)
    result = check(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result["errors"]))
