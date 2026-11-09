#!/usr/bin/env python3
"""Перевіряє посилання в усіх .md репозиторію.

1. Відносні посилання мають вести на наявні файли.
2. Посилання зі схемою `file:` заборонені: вони ведуть на локальні шляхи поза
   репозиторієм і не працюють у клонах та на GitHub.
3. Посилання на `drafts` виду
   `https://github.com/nick-fedchik/drafts/(blob|tree)/<sha>/<шлях>`
   перевіряються в локальному клоні `drafts`, шлях до якого задає змінна
   середовища `KM_DRAFTS_REPO`, командою `git cat-file -e <sha>:<шлях>`
   (якір відокремлюється перед `unquote`, кінцевий `/` прибирається).
   URL без SHA або шляху вважається битим незалежно від доступності клону.
   Якщо змінна не задана або
   це не git-репозиторій, такі посилання пропускаються з одним попередженням:
   у CI клону `drafts` немає.
Інші зовнішні посилання (http, https, mailto) і якорі (#...) не перевіряються.
Код виходу 1, якщо є хоча б одне бите посилання або посилання `file:`.
"""
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^(```|~~~)")
DRAFTS = re.compile(
    r"^https?://github\.com/nick-fedchik/drafts/(?:blob|tree)/([0-9a-f]{7,40})/(.+)$"
)
DRAFTS_ROUTE = re.compile(
    r"^https?://github\.com/nick-fedchik/drafts/(?:blob|tree)(?:/|$)"
)


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


def drafts_repo():
    """Локальний клон `drafts` зі змінної KM_DRAFTS_REPO або None."""
    path = os.environ.get("KM_DRAFTS_REPO")
    if not path:
        return None
    path = Path(path).expanduser()
    try:
        probe = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--git-dir"],
            capture_output=True,
        )
    except OSError:
        return None
    return path if probe.returncode == 0 else None


def drafts_exists(repo: Path, sha: str, path: str) -> bool:
    """Чи існує шлях у коміті sha локального клону drafts."""
    obj = f"{sha}:{path}" if path else sha
    probe = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", obj],
        capture_output=True,
    )
    return probe.returncode == 0


def main(root: Path | None = None) -> int:
    root = Path(root) if root is not None else ROOT
    repo = drafts_repo()
    broken = []
    file_links = []
    drafts_checked = 0
    drafts_skipped = 0
    for md in sorted(root.rglob("*.md")):
        if ".git" in md.parts:
            continue
        rel = md.relative_to(root)
        for n, target in links(md):
            target_without_anchor = target.split("#", 1)[0]
            if DRAFTS_ROUTE.match(target_without_anchor):
                drafts = DRAFTS.fullmatch(target_without_anchor)
                path = unquote(drafts.group(2)).rstrip("/") if drafts else ""
                if not drafts or not path:
                    broken.append(f"{rel}:{n}: {target} — некоректний SHA або відсутній шлях")
                    continue
                if repo is None:
                    drafts_skipped += 1
                    continue
                drafts_checked += 1
                if not drafts_exists(repo, drafts.group(1), path):
                    broken.append(f"{rel}:{n}: {target}")
                continue
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
                if target.lower().startswith("file:"):
                    file_links.append(f"{rel}:{n}: {target}")
                continue
            if target.startswith("#"):
                continue
            path = unquote(target.split("#", 1)[0])
            if not path:
                continue
            dest = (root / path.lstrip("/")) if path.startswith("/") else (md.parent / path)
            if not dest.exists():
                broken.append(f"{rel}:{n}: {target}")
    for f in file_links:
        print(f"Заборонене посилання file: {f}")
    for b in broken:
        print(b)
    if drafts_skipped:
        print(
            "Увага: KM_DRAFTS_REPO не задано або це не git-репозиторій — "
            f"посилання на drafts не перевіряються (пропущено {drafts_skipped})."
        )
    print(
        f"Битих посилань: {len(broken)}; посилань file:: {len(file_links)}; "
        f"посилань на drafts: перевірено {drafts_checked}, пропущено {drafts_skipped}"
    )
    return 1 if broken or file_links else 0


if __name__ == "__main__":
    sys.exit(main())
