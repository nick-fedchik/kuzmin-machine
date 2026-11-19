#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]] || [[ -z "${1:-}" ]]; then
  echo "Usage: $0 <dest_dir>" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(git -C "${SRC_DIR}" rev-parse --show-toplevel 2>/dev/null || (cd "${SRC_DIR}/../../.." && pwd))"
GUIDES_DIR="${GUIDES_DIR:-$(cd "${REPO_ROOT}/Engineering/guides" && pwd)}"
DEST_ARG="$1"

DEST_DIR="$(python3 -c 'import os, sys; print(os.path.abspath(sys.argv[1]))' "${DEST_ARG}")"

python3 - "${SRC_DIR}" "${GUIDES_DIR}" "${REPO_ROOT}" "${DEST_DIR}" <<'PY'
import os
from pathlib import Path
import re
import shutil
import stat
import sys

src_dir = Path(sys.argv[1]).resolve()
guides_dir = Path(sys.argv[2]).resolve()
repo_root = Path(sys.argv[3]).resolve()
dest_dir = Path(sys.argv[4]).resolve()
allowed_dist_root = (repo_root / "Engineering" / "sw" / "vmk-go" / "dist").resolve()
allowed_scratch_root = (repo_root / ".pytest_cache").resolve()
home_dir = Path.home().resolve()
marker_name = ".vmk-public-bundle"


def _is_rel(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


# Strict destination safety guards:
# 1. Never allow /, $HOME, or any ancestor of $HOME, repo_root, src_dir, or guides_dir.
if (
    dest_dir == Path("/")
    or dest_dir == home_dir
    or _is_rel(home_dir, dest_dir)
    or _is_rel(repo_root, dest_dir)
    or _is_rel(src_dir, dest_dir)
    or _is_rel(guides_dir, dest_dir)
):
    print(f"Refusing to export into unsafe ancestor/home destination: {dest_dir}", file=sys.stderr)
    raise SystemExit(2)

# 2. Never allow any path inside repo_root except git-ignored dist/<subdir> or .pytest_cache/<subdir>.
in_allowed_dist = dest_dir != allowed_dist_root and _is_rel(dest_dir, allowed_dist_root)
in_allowed_scratch = dest_dir != allowed_scratch_root and _is_rel(dest_dir, allowed_scratch_root)
if _is_rel(dest_dir, repo_root) and not (in_allowed_dist or in_allowed_scratch):
    print(
        f"Refusing to export inside repository outside {allowed_dist_root}/<bundle>: {dest_dir}",
        file=sys.stderr,
    )
    raise SystemExit(2)

# 3. Only clean an existing non-empty directory if it carries our explicit bundle marker.
if dest_dir.exists():
    if not dest_dir.is_dir():
        print(f"Destination exists and is not a directory: {dest_dir}", file=sys.stderr)
        raise SystemExit(2)
    existing_entries = list(dest_dir.iterdir())
    if existing_entries and not (dest_dir / marker_name).is_file():
        print(
            f"Refusing to overwrite non-empty directory without {marker_name} marker: {dest_dir}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    for child in existing_entries:
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
else:
    dest_dir.mkdir(parents=True, exist_ok=True)

(dest_dir / marker_name).write_text("vmk-public-bundle\n", encoding="utf-8")

(dest_dir / "cmd" / "vmk").mkdir(parents=True, exist_ok=True)
(dest_dir / "internal" / "vmk").mkdir(parents=True, exist_ok=True)
(dest_dir / "examples").mkdir(parents=True, exist_ok=True)
(dest_dir / "scripts").mkdir(parents=True, exist_ok=True)
(dest_dir / "docs").mkdir(parents=True, exist_ok=True)

# 1. Extract canonical Version from internal/vmk/version.go
ver_txt = (src_dir / "internal" / "vmk" / "version.go").read_text(encoding="utf-8")
m_ver = re.search(r'const\s+Version\s*=\s*"([^"]+)"', ver_txt)
if not m_ver:
    raise SystemExit("Failed to extract Version from internal/vmk/version.go")
vmk_version = m_ver.group(1)

# 2. Write standalone go.mod (module vmk, zero external dependencies)
(dest_dir / "go.mod").write_text("module vmk\n\ngo 1.22\n", encoding="utf-8")

# 3. Copy cmd/vmk/*.go rewriting canonical module path to standalone module vmk
canon_import = "github.com/nick-fedchik/kuzmin-machine/Engineering/sw/vmk-go/internal/vmk"
for go_file in sorted((src_dir / "cmd" / "vmk").glob("*.go")):
    txt = go_file.read_text(encoding="utf-8").replace(canon_import, "vmk/internal/vmk")
    (dest_dir / "cmd" / "vmk" / go_file.name).write_text(txt, encoding="utf-8")

# 4. Copy internal/vmk/*.go excluding private HIL drivers (pynq.go, pynq_test.go)
excluded_go = {"pynq.go", "pynq_test.go"}
for go_file in sorted((src_dir / "internal" / "vmk").glob("*.go")):
    if go_file.name in excluded_go:
        continue
    txt = go_file.read_text(encoding="utf-8")
    if go_file.name in {"pynq_public.go", "pynq_public_test.go"}:
        # Remove //go:build public so standalone `go build` & `go test` work without extra flags
        txt = re.sub(r"^//go:build\s+public\s*\n+", "", txt)
    # Strip internal repo filename mentions in comments if present
    txt = txt.replace(
        "matching km_concept_micro_engine.sv and kpol_debugger.py.",
        "matching the hardware Concept Micro-Engine.",
    )
    txt = txt.replace(" (`kpol_txn_gate_v2.sv`)", "")
    (dest_dir / "internal" / "vmk" / go_file.name).write_text(txt, encoding="utf-8")

# 5. Copy all examples/*.{ekpol,kpol}
for ex_file in sorted((src_dir / "examples").iterdir()):
    if ex_file.is_file() and ex_file.suffix in {".ekpol", ".kpol"}:
        shutil.copy2(ex_file, dest_dir / "examples" / ex_file.name)

# 6. Copy scripts/build_releases.sh
rel_script = (src_dir / "scripts" / "build_releases.sh").read_text(encoding="utf-8")
dest_rel_script = dest_dir / "scripts" / "build_releases.sh"
dest_rel_script.write_text(rel_script, encoding="utf-8")
dest_rel_script.chmod(dest_rel_script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def sanitize_doc(md_text: str, is_users_guide: bool) -> str:
    txt = md_text
    if is_users_guide:
        # Strip section 2.7.2 (PYNQ-Z1 SSH/MMIO live board section) up to section 2.7.3
        txt = re.sub(
            r"#### 2\. Підключення `vmk` до фізичної плати.*?#### 3\. ",
            "#### 2. Коди виходу процесу `vmk`\n\n",
            txt,
            flags=re.DOTALL,
        )
        # Remove private PYNQ environment variable rows
        txt = re.sub(r"^\| `(?:KM_PYNQ[12]_HOST|PYNQ_SUDO_PASS)` \|.*$\n?", "", txt, flags=re.MULTILINE)
        # Replace section 3 PYNQ limitation item with standalone sim-only item
        txt = re.sub(
            r"3\. \*\*Особливості роботи з фізичною платою `PYNQ-Z1`.*?(?=4\. \*\*Позиція щодо стандартів)",
            (
                "3. **Ізоляція автономного пакета (`--target sim`):**\n"
                "   * Автономний публічний пакет підтримує виключно локальний симулятор `--target sim` "
                "(за замовчуванням); для будь-якого іншого значення `--target` повертається "
                "`VMK-TARGET-IO` з кодом виходу `2`.\n"
            ),
            txt,
            flags=re.DOTALL,
        )

    # Rewrite relative links inside docs/ to standalone layout
    txt = re.sub(
        r"\[([^\]]+)\]\(\.\./sw/vmk-go/scripts/export_public_bundle\.sh\)",
        r"\1",
        txt,
    )
    txt = txt.replace("(../sw/vmk-go/README.md)", "(../README.md)")
    txt = txt.replace("(../sw/vmk-go/", "(../")
    txt = txt.replace("`Engineering/sw/vmk-go/examples/", "`examples/")
    txt = txt.replace("Engineering/sw/vmk-go/examples/", "examples/")
    txt = txt.replace("`Engineering/sw/vmk-go/`", "`vmk/`")
    txt = txt.replace("`Engineering/sw/vmk-go`", "`vmk`")
    txt = txt.replace("cd Engineering/sw/vmk-go", "cd vmk")
    txt = txt.replace("(cd Engineering/sw/vmk-go && ", "(")
    txt = txt.replace(
        "github.com/nick-fedchik/kuzmin-machine/Engineering/sw/vmk-go",
        "vmk",
    )
    txt = txt.replace(
        "../../validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol",
        "examples/bms_safety_cascade.kpol",
    )
    txt = txt.replace("(README.md)", "(../README.md)")

    # Replace private GitHub links and out-of-bundle relative links with clean text
    txt = re.sub(
        r"\[([^\]]+)\]\(https://github\.com/nick-fedchik/kuzmin-machine[^)]*\)",
        r"\1",
        txt,
    )
    txt = re.sub(
        r"\[([^\]]+)\]\((?:\.\./)+(?!(?:README\.md|go\.mod|cmd/|internal/|examples/|scripts/|docs/))[^)]+\)",
        r"\1",
        txt,
    )
    # Same-directory guides that are not exported (e.g. formal specifications) become plain text
    txt = re.sub(
        r"\[([^\]]+)\]\((?!(?:vmk-users-guide|kpol-ekpol-language-guide)\.md)[A-Za-z0-9_-]+\.md(?:#[^)]*)?\)",
        r"\1",
        txt,
    )

    # Remove lines invoking internal Python scripts/tests outside standalone Go bundle
    cleaned_lines = []
    skip_continuation = False
    for line in txt.splitlines():
        if skip_continuation:
            if not line.rstrip().endswith("\\"):
                skip_continuation = False
            continue
        if any(
            tok in line
            for tok in (
                "compile_kpol_bram_image.py",
                "pytest ",
                "rm -f bms.bin",
                "test_ekpol_278.py",
                "test_vmk_go_274.py",
            )
        ):
            if line.rstrip().endswith("\\"):
                skip_continuation = True
            continue
        # Scrub remaining internal path prefixes and lab target names
        line = re.sub(r"`?(?:Engineering|Research|Project)/[A-Za-z0-9_./*-]*`?", "`vmk`", line)
        line = line.replace("(`nick-fedchik/kuzmin-machine`)", "")
        line = line.replace("`AGENTS.md §6.1`", "правилами атрибуції проєкту")
        line = line.replace("`AGENTS.md §4 п. 1`", "дисципліною негативного контролю")
        line = line.replace("`AGENTS.md §2.3`", "правилами стенда")
        line = line.replace("AGENTS.md", "правил проєкту")
        line = line.replace("`sim | pynq1 | pynq2 | user@host`", "`sim`")
        line = line.replace("`--target pynq1 | pynq2`", "`--target sim`")
        line = line.replace("`--target pynq1 \\| pynq2`", "`--target sim`")
        line = line.replace("(`--target sim | pynq1 | pynq2`)", "(`--target sim`)")
        line = line.replace("--target pynq2", "--target sim")
        line = line.replace("pynq1", "sim")
        line = line.replace("pynq2", "sim")
        line = line.replace("/tmp/km-bench.lock", "bench.lock")
        line = line.replace("/dev/mem", "MMIO")
        line = line.replace("PYNQ_SUDO_PASS", "SUDO_PASS")
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines) + "\n"


users_src = (guides_dir / "vmk-users-guide.md").read_text(encoding="utf-8")
lang_src = (guides_dir / "kpol-ekpol-language-guide.md").read_text(encoding="utf-8")
(dest_dir / "docs" / "vmk-users-guide.md").write_text(
    sanitize_doc(users_src, is_users_guide=True), encoding="utf-8"
)
(dest_dir / "docs" / "kpol-ekpol-language-guide.md").write_text(
    sanitize_doc(lang_src, is_users_guide=False), encoding="utf-8"
)

# 7. Write standalone public README.md
standalone_readme = f"""# `VMK v{vmk_version}`: Самодостатній двомодовий емулятор, транспайлер `EKPOL <-> KPOL` і повноекранний TUI-дебагер Машини Кузьміна на Go

* **Версія пакета:** `{vmk_version}` (`SemVer 2.0.0`)
* **Мова та залежності:** `Go >= 1.22`, виключно стандартна бібліотека `std` (**`0` зовнішніх залежностей**, `CGO_ENABLED=0`)
* **Платформи:** `Linux` (`amd64`, `arm64`), `macOS` (`arm64`, `amd64`), `Windows` (`amd64`)

## Швидкий старт

```bash
go build -o vmk ./cmd/vmk
./vmk --version
go test -v ./...
./vmk --example all
./vmk --program examples/bms_safety_cascade.ekpol --tui
```

## Посібники та структура пакета

* [Посібник користувача VMK (`docs/vmk-users-guide.md`)](docs/vmk-users-guide.md)
* [Керівництво користувача та чистий код мов KPOL і EKPOL (`docs/kpol-ekpol-language-guide.md`)](docs/kpol-ekpol-language-guide.md)
* [`examples/`](examples/bms_safety_cascade.ekpol) — 9 програм `.ekpol` та 4 класичні відповідники `.kpol` (`bms_safety_cascade`, `cascade_4concept`, `increase`, `decrease`)
* [`scripts/build_releases.sh`](scripts/build_releases.sh) — крос-компіляція статичних бінарників (`linux`, `darwin`, `windows`) і `SHA256SUMS`

## Обмеження автономного пакета

1. Автор концепції Машини Кузьміна — **Михайло Ювеналійович Кузьмін**. Мова `EKPOL 0.1.0` та Go-емулятор `VMK v{vmk_version}` є похідною інженерною розробкою (Микола Федчик) і не приписуються Автору концепції.
2. Цей автономний публічний пакет підтримує виключно симуляційну ціль `--target sim`; при передачі будь-якого іншого `--target` повертається `VMK-TARGET-IO` з кодом виходу `2`.
"""
(dest_dir / "README.md").write_text(standalone_readme, encoding="utf-8")

# 8. Verify relative Markdown links inside exported bundle
link_re = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
for md_path in sorted(dest_dir.rglob("*.md")):
    in_fence = False
    for lineno, line in enumerate(md_path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for m in link_re.finditer(line):
            target = m.group(1).split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (md_path.parent / target).resolve()
            if not resolved.exists():
                raise SystemExit(
                    f"[export_public_bundle] Broken relative link in {md_path.relative_to(dest_dir)}:{lineno}: {target}"
                )

# 9. Audit exported bundle for absence of private hosts, IPs, credentials, and repo paths
forbidden_re = re.compile(
    r"192\.168|kuzmin-machine|PYNQ_SUDO_PASS|/dev/mem|km-bench\.lock|KM_PYNQ|pynq1|pynq2|xilinx@|Engineering/|Research/|Project/|AGENTS\.md"
)
leaks = []
for fpath in sorted(dest_dir.rglob("*")):
    if not fpath.is_file():
        continue
    rel = fpath.relative_to(dest_dir)
    if rel.parts[0] in {".gotmp", "dist"}:
        continue
    content = fpath.read_text(encoding="utf-8", errors="replace")
    for lineno, line in enumerate(content.splitlines(), 1):
        m = forbidden_re.search(line)
        if m:
            leaks.append(f"{rel}:{lineno}: forbidden marker {m.group(0)!r}")

if leaks:
    for item in leaks[:20]:
        print(f"[export_public_bundle] AUDIT FAILURE: {item}", file=sys.stderr)
    raise SystemExit(1)

print(f"[export_public_bundle] Exported clean bundle (VMK v{vmk_version}) to {dest_dir}")
PY

BUILD_TMP="${DEST_DIR}/.gotmp"
mkdir -p "${BUILD_TMP}"
trap 'rm -rf "${BUILD_TMP}"' EXIT
export GOTMPDIR="${GOTMPDIR:-${BUILD_TMP}}"
export TMPDIR="${TMPDIR:-${BUILD_TMP}}"

(
  cd "${DEST_DIR}"
  test -z "$(gofmt -l .)"
  go vet ./...
  go test -v ./...
)

rm -rf "${BUILD_TMP}"
echo "[export_public_bundle] Verification passed (gofmt + go vet + go test + zero private leaks)."
