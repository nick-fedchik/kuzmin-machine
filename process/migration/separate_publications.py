#!/usr/bin/env python3
"""Preserve the complete research snapshot before pruning the editorial tree."""
import argparse
import gzip
import hashlib
import json
import os
import re
import runpy
import subprocess
import tarfile
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "process/migration/publication-84"
TRANSLATION = "01-concepts-and-theory/Concepts_And_Concept-Oriented_Programming_UA.md"
FORMAL = "01-concepts-and-theory/Kuzmin-Machine-Formal-Analysis-UA.md"
LINK = re.compile(r"!?\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_archive(archive, entries):
    with tarfile.open(archive, "r:gz") as saved:
        members = {m.name: m for m in saved.getmembers() if m.isfile()}
        expected = {"KuzminMachine/" + e["source"] for e in entries}
        if set(members) != expected:
            raise ValueError("Archive member set differs from the inventory")
        for entry in entries:
            data = saved.extractfile(members["KuzminMachine/" + entry["source"]]).read()
            if digest(data) != entry["sha256"]:
                raise ValueError(f"Archive hash mismatch: {entry['source']}")


def verify_destinations(root, entries, relocations):
    destinations = {e["destination"] for e in entries if e["destination"]}
    unknown = relocations.keys() - destinations
    if unknown:
        raise ValueError(f"Relocation without migration destination: {sorted(unknown)}")
    current = [relocations.get(path, path) for path in destinations]
    if len(current) != len(set(current)):
        raise ValueError("Multiple migration destinations resolve to the same working copy")
    for path in current:
        if not (root / path).is_file():
            raise ValueError(f"Missing working copy: {path}")


def category(path):
    part = path.split("/")[0]
    return {
        ".github": "development-tool",
        "01-concepts-and-theory": "research",
        "02-engineering-hardware": "engineering",
        "03-engineering-software": "engineering",
        "04-verification-and-qa": "verification",
        "05-applications-and-guides": "application-research",
        "06-economic-model": "business-and-forecasts",
        "07-scientific-opposition": "research-review",
    }.get(part, "project-governance")


def readable_path(path):
    parts = path.split("/")
    if path.startswith(".github/"):
        return None
    if path.startswith("06-economic-model/"):
        return "docs/business/" + "/".join(parts[1:])
    if not path.endswith(".md") or parts[-1] == "README.md":
        return None
    if parts[-1].startswith("MEMO_KPOL_SOVEREIGN"):
        return "docs/strategy/" + parts[-1]
    if parts[-1].startswith("MEMO_CONTRIBUTIONS"):
        return "docs/governance/" + parts[-1]
    folder = {
        "01-concepts-and-theory": "theory",
        "02-engineering-hardware": "hardware",
        "03-engineering-software": "software",
        "04-verification-and-qa": "verification",
        "05-applications-and-guides": "applications",
        "07-scientific-opposition": "opposition",
    }.get(parts[0])
    return f"docs/research/{folder}/" + "/".join(parts[1:]) if folder else None


def normalize_markdown(text):
    result = []
    fenced = False
    for line in text.splitlines():
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
        hard_break = not fenced and bool(line.strip()) and line.endswith("  ")
        result.append(line.rstrip() + ("<br/>" if hard_break else ""))
    return "\n".join(result).rstrip() + "\n"


def rewrite(text, old, new, mapping, archive, sources, unresolved, source_repo, commit):
    def replace(match):
        label, target = match.groups()
        image = "!" if match.group(0).startswith("!") else ""
        path, sep, anchor = target.partition("#")
        suffix = sep + anchor
        if not path:
            return match.group(0)
        path = unquote(path)
        route = re.match(
            r"https?://github.com/nick-fedchik/drafts/(?:blob|tree)/[^/]+/KuzminMachine/(.*)",
            path,
        )
        if route:
            resolved = route.group(1).rstrip("/")
        elif path.startswith("file:"):
            resolved = path.split("/KuzminMachine/", 1)[-1] if "/KuzminMachine/" in path else None
        elif re.match(r"^[a-z][a-z0-9+.-]*:", path, re.I):
            return match.group(0)
        else:
            resolved = os.path.normpath(str(Path(old).parent / path))
        if resolved not in sources and resolved:
            candidates = [s for s in sources if Path(s).name == Path(resolved).name]
            if len(candidates) == 1:
                resolved = candidates[0]
        if resolved in mapping:
            rel = os.path.relpath(mapping[resolved], Path(new).parent)
            return f"{image}[{label}]({rel}{suffix})"
        if resolved in sources or (
            resolved and any(s.startswith(resolved.rstrip("/") + "/") for s in sources)
        ):
            rel = os.path.relpath(archive, Path(new).parent)
            return f"[{label}]({rel}) (член архіву: `{resolved}`)"
        if resolved and resolved.startswith("../"):
            outside = os.path.normpath("KuzminMachine/" + resolved)
            if not outside.startswith("../"):
                check = subprocess.run(
                    ["git", "-C", str(source_repo), "cat-file", "-e", f"{commit}:{outside}"],
                    capture_output=True,
                )
                if check.returncode == 0:
                    return f"[{label}](https://github.com/nick-fedchik/drafts/blob/{commit}/{outside}{suffix})"
        unresolved.append({"source": old, "target": target})
        return f"{label} (історичне посилання не розв’язано автоматично: `{target}`)"

    result = []
    fenced = False
    for line in text.splitlines(keepends=True):
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
        result.append(line if fenced else LINK.sub(replace, line))
    return normalize_markdown("".join(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_repo", type=Path)
    parser.add_argument("commit")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--prune-publications", action="store_true")
    args = parser.parse_args()
    source = args.source_repo.resolve()
    commit = git(source, "rev-parse", args.commit).decode().strip()
    archive_path = f"docs/archive/drafts-{commit[:7]}-kuzminmachine.tar.gz"
    if args.prune_publications or args.verify:
        data = json.loads((RECORD / "manifest.json").read_text())
        if data["source_commit"] != commit:
            raise ValueError("Unexpected source revision")
        if digest((ROOT / data["archive"]).read_bytes()) != data["archive_sha256"]:
            raise ValueError("Archive checksum differs from the migration record")
        verify_archive(ROOT / data["archive"], data["files"])
        previous = gzip.decompress((ROOT / data["previous_formal_archive"]).read_bytes())
        if digest(previous) != data["previous_formal_sha256"]:
            raise ValueError("Previous canonical analysis checksum mismatch")
        if args.verify:
            relocations = json.loads((RECORD / "relocations.json").read_text())
            verify_destinations(ROOT, data["files"], relocations)
            print(f"Verified {len(data['files'])} archived originals and all mapped destinations.")
            return
        for entry in data["files"]:
            path = source / "KuzminMachine" / entry["source"]
            if not path.is_file() or digest(path.read_bytes()) != entry["sha256"]:
                raise ValueError(f"Source changed before pruning: {path}")
        for entry in data["files"]:
            if entry["source"] != TRANSLATION:
                (source / "KuzminMachine" / entry["source"]).unlink()
        print("Pruned only inventoried files after verifying the complete private archive.")
        return
    if git(source, "status", "--porcelain", "--untracked-files=normal").strip():
        raise ValueError("Source worktree must be clean")
    if git(source, "rev-parse", "HEAD").decode().strip() != commit:
        raise ValueError("Source HEAD must match the pinned revision")
    if RECORD.exists():
        raise ValueError("Migration record already exists; refusing to overwrite")
    files = [
        p.removeprefix("KuzminMachine/")
        for p in git(source, "ls-files", "-z", "KuzminMachine").decode().split("\0") if p
    ]
    old_migration = runpy.run_path(str(ROOT / "process/migration/migrate_from_drafts.py"))
    known = old_migration["full_map"](source / "KuzminMachine")
    mapping = {s: d for s, d in known.items() if s in files and (ROOT / d).is_file()}
    imported = {}
    for path in files:
        if path not in mapping:
            dest = readable_path(path)
            if dest:
                if (ROOT / dest).exists():
                    raise ValueError(f"Refusing to overwrite: {dest}")
                imported[path] = dest
    mapping.update(imported)
    mapping[FORMAL] = "docs/theory/formal-analysis.md"
    archive = ROOT / archive_path
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(gzip.compress(git(source, "archive", "--format=tar", commit, "KuzminMachine"), mtime=0))
    entries = []
    for path in files:
        data = (source / "KuzminMachine" / path).read_bytes()
        entries.append({
            "source": path, "category": category(path), "sha256": digest(data),
            "bytes": len(data), "destination": mapping.get(path),
            "disposition": "imported-readable" if path in imported else
                "promoted-latest-analysis" if path == FORMAL else
                "existing-canonical-preserved" if path in mapping else "archive-only",
            "publication": "editorial-translation" if path == TRANSLATION else None,
        })
    verify_archive(archive, entries)
    RECORD.mkdir(parents=True)
    previous = ROOT / mapping[FORMAL]
    previous_bytes = previous.read_bytes()
    previous_archive = RECORD / "previous-formal-analysis.txt.gz"
    previous_archive.write_bytes(gzip.compress(previous_bytes, mtime=0))
    unresolved = []
    for old, new in {**imported, FORMAL: mapping[FORMAL]}.items():
        original = (source / "KuzminMachine" / old).read_bytes()
        dest = ROOT / new
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not old.endswith(".md"):
            dest.write_bytes(original)
            continue
        text = rewrite(
            original.decode(), old, new, mapping, archive_path,
            set(files), unresolved, source, commit,
        )
        notice = (
            "> **Внутрішня робоча копія, не публікація; міграція не є науковим прийняттям.** "
            f"Перенесено з `drafts@{commit[:7]}:KuzminMachine/{old}` 2026-11-10, Issue #84. "
            "Міграція не підтверджує тверджень, прогнозів чи самоприсвоєних статусів. "
            "Незмінний оригінал і SHA-256 — у реєстрі міграції.\n\n"
        )
        first, sep, rest = text.partition("\n")
        dest.write_text(first + sep + "\n" + notice + rest)
    manifest = {
        "version": "0.1.0", "issue": 84, "source_commit": commit,
        "private_base": git(ROOT, "rev-parse", "HEAD").decode().strip(),
        "archive": archive_path, "archive_sha256": digest(archive.read_bytes()),
        "previous_formal_archive": previous_archive.relative_to(ROOT).as_posix(),
        "previous_formal_sha256": digest(previous_bytes),
        "files": entries, "unresolved_historical_links": unresolved,
    }
    (RECORD / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "files": len(entries), "readable_imports": len(imported),
        "existing_canonicals": len(mapping) - len(imported),
        "archive_bytes": archive.stat().st_size,
        "unresolved_historical_links": len(unresolved),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
