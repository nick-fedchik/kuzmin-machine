"""Go toolchain (Engineering/sw/kpol-go): unit tests, differential check against the Python
reference CLI and the executable examples of the three programming guides.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GO_MODULE = REPO_ROOT / "Engineering" / "sw" / "kpol-go"
VMK_MODULE = REPO_ROOT / "Engineering" / "sw" / "vmk-go"
GUIDES = REPO_ROOT / "Engineering" / "guides"
PY_CLI = REPO_ROOT / "Engineering" / "hw" / "scripts" / "compile_kpol_bram_image.py"
EXAMPLES = VMK_MODULE / "examples"

pytestmark = pytest.mark.skipif(shutil.which("go") is None, reason="Go toolchain is not installed")


@contextmanager
def _scratch(prefix: str = "kpol_go"):
    base = REPO_ROOT / ".pytest_cache" / f"{prefix}_{uuid.uuid4().hex}"
    base.mkdir(parents=True, exist_ok=False)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _go_env() -> dict[str, str]:
    cache = REPO_ROOT / ".pytest_cache" / "go_cache"
    cache.mkdir(parents=True, exist_ok=True)
    return {**os.environ, "GOCACHE": str(cache)}


@pytest.fixture(scope="module")
def tools(tmp_path_factory):
    """Build kpolc and vmk once, exactly as the guides tell the reader to."""
    out = REPO_ROOT / ".pytest_cache" / f"kpol_go_bin_{uuid.uuid4().hex}"
    out.mkdir(parents=True)
    env = _go_env()
    subprocess.run(["go", "build", "-C", str(GO_MODULE), "-o", str(out / "kpolc"), "./cmd/kpolc"], check=True, env=env)
    subprocess.run(["go", "build", "-C", str(VMK_MODULE), "-o", str(out / "vmk"), "./cmd/vmk"], check=True, env=env)
    yield out
    shutil.rmtree(out, ignore_errors=True)


def _run(cmd, cwd=None, **kwargs):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, cwd=cwd, **kwargs)


def test_go_module_tests_pass():
    result = subprocess.run(
        ["go", "test", "-count=1", "./..."], cwd=GO_MODULE, capture_output=True, text=True, env=_go_env()
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _corpus() -> list[Path]:
    skipped = {".git", ".pytest_cache", "kpol-go", "__pycache__"}
    return sorted(
        p for p in REPO_ROOT.rglob("*") if p.suffix in (".kpol", ".ekpol") and not skipped & set(p.relative_to(REPO_ROOT).parts)
    )


def _build_cases():
    cases = []
    for path in _corpus():
        rel = path.relative_to(REPO_ROOT).as_posix()
        profiles = [[]] if path.suffix == ".ekpol" else [["--profile", "KPOL-CME-1"], ["--profile", "KPOL-CME-2"]]
        for profile in profiles:
            cases.append(pytest.param(path, profile, id=f"{rel}-{'-'.join(profile) or 'ekpol'}"))
    return cases


def _outputs(directory: Path) -> dict[str, bytes]:
    result = {}
    for item in sorted(directory.iterdir()):
        data = item.read_bytes()
        if item.name == "cert":
            document = json.loads(data)
            document.pop("solver", None)  # Python API vs z3 CLI banner; everything else is compared
            data = json.dumps(document, sort_keys=True).encode()
        result[item.name] = data
    return result


@pytest.mark.skipif(shutil.which("z3") is None, reason="z3 is required for the C99 safety certificate")
@pytest.mark.parametrize("path, profile", _build_cases())
def test_kpolc_build_matches_python_cli(tools, path, profile):
    """kpolc build must reproduce image, translations, C99 module and certificate of the Python CLI."""
    emit_variants = [
        ["--emit-c99", "c99", "--emit-z3-cert", "cert"],
        ["--emit-kpol", "kpol_out"] if path.suffix == ".ekpol" else ["--emit-ekpol", "ekpol_out"],
        ["--emit-ekpol", "ekpol_out", "--ekpol-style", "keyword"],
    ]
    for variant in emit_variants:
        observed = {}
        for name, base in (("python", [sys.executable, PY_CLI]), ("go", [tools / "kpolc", "build"])):
            with _scratch("cli") as work:
                args = list(base) + profile
                it = iter(variant)
                for flag in it:
                    if flag.startswith("--emit-") and flag != "--ekpol-style":
                        args += [flag, str(work / next(it))]
                    else:
                        args.append(flag)
                args += [str(path), str(work / "image")]
                done = _run(args, cwd=REPO_ROOT)
                stderr = done.stderr.replace(str(work), "WORK").strip().splitlines()
                observed[name] = (done.returncode, done.stdout.strip(), stderr[-1:] if stderr else [], _outputs(work))
        assert observed["go"] == observed["python"], (path, profile, variant)


def _auth_sources() -> list[tuple[str, str]]:
    spec = (REPO_ROOT / "Engineering" / "specifications" / "kpol" / "kpol-auth-formal-specification.md").read_text(encoding="utf-8")
    sources = [(f"ex-{m[1]}", m[2]) for m in re.finditer(r"^\| `(EX-\d\d)` \| `([^`]+)` \|", spec, re.M)]
    sources += [(f"a2-{i}", m[1]) for i, m in enumerate(re.finditer(r"^\| `(Concept\([^`]+)` \|", spec, re.M))]
    sources += [(f"neg-{i}", m[1]) for i, m in enumerate(re.finditer(r"`(Concept\([^`]+)` → `KPOL-", spec))]
    guide = (GUIDES / "kpol-auth-programming-guide.md").read_text(encoding="utf-8")
    sources += [(f"guide-{i}", block) for i, block in enumerate(re.findall(r"^```kpol-auth\n(.*?)^```$", guide, re.M | re.S))]
    sources += [("guide-group", "Collection(Letter)[Min=1, Max=15]\n"), ("empty", ""), ("garbage", "Concept(A, 0"), ("arrow", "← A")]
    return sources


@pytest.mark.parametrize("label, source", _auth_sources(), ids=lambda v: v if isinstance(v, str) and len(v) < 12 else None)
def test_kpolc_auth_matches_python_frontend(tools, label, source):
    """kpolc auth --check must give the Python frontend's verdict, message and exit code."""
    with _scratch("auth") as work:
        path = work / "input.auth"
        path.write_text(source, encoding="utf-8")
        python = _run([sys.executable, REPO_ROOT / "Engineering" / "sw" / "kpol-auth" / "__main__.py", path, "--check"])
        go = _run([tools / "kpolc", "auth", path, "--check"])
        assert (go.returncode, go.stdout, go.stderr) == (python.returncode, python.stdout, python.stderr), label


def _blocks(guide: str, lang: str) -> list[str]:
    text = (GUIDES / guide).read_text(encoding="utf-8")
    return re.findall(rf"^```{lang}\n(.*?)^```$", text, re.M | re.S)


def test_guides_publish_the_build_commands_and_catalog_links():
    catalog = (GUIDES / "README.md").read_text(encoding="utf-8")
    for guide in ("kpol-programming-guide.md", "ekpol-programming-guide.md", "kpol-auth-programming-guide.md"):
        text = (GUIDES / guide).read_text(encoding="utf-8")
        assert f"]({guide})" in catalog
        assert "go build -C Engineering/sw/kpol-go -o kpolc ./cmd/kpolc" in text
        assert "python3" not in text and "PYTHONPATH" not in text, f"{guide} must use the Go toolchain"
    for guide in ("kpol-programming-guide.md", "ekpol-programming-guide.md"):
        assert "go build -C Engineering/sw/vmk-go -o vmk ./cmd/vmk" in (GUIDES / guide).read_text(encoding="utf-8")


def test_kpol_guide_programs_behave_as_the_text_says(tools):
    tickets, pair, room, loans, _tally = _blocks("kpol-programming-guide.md", "kpol")
    kpolc = tools / "kpolc"
    with _scratch("guide") as work:
        for name, source, expected in (
            ("tickets", tickets, "Tickets: 2/2 checks passed"),
            ("pair", pair, "Pair: 2/2 checks passed"),
            ("room", room, "Room: 2/2 checks passed"),
            ("loans", loans, "Loans: 6/6 checks passed"),
        ):
            (work / f"{name}.kpol").write_text(source, encoding="utf-8")
            done = _run([kpolc, "verify", work / f"{name}.kpol"])
            assert done.returncode == 0 and expected in done.stdout, done.stdout + done.stderr

        # Opening example: the four decisions of the cash desk in the VMK trace of the built image.
        image = work / "tickets.bin"
        assert _run([kpolc, "build", "--profile", "KPOL-CME-1", work / "tickets.kpol", image]).returncode == 0
        trace = _run([tools / "vmk", "--program", image, "--trace-events", "0:5,0:1,0:1,0:1"]).stdout
        verdicts = re.findall(r"\| (REJECT_GUARD|COMMIT|REJECT_INVARIANT)", trace)
        assert verdicts == ["REJECT_GUARD", "COMMIT", "COMMIT", "REJECT_INVARIANT"]

        # "Change the program": a failing expectation stops both verify and build.
        broken = tickets.replace("expect Left == 1;\n    }", "expect Left == 1;\n        step Buy(count = 1);\n        expect Left == 1;\n    }")
        (work / "broken.kpol").write_text(broken, encoding="utf-8")
        done = _run([kpolc, "verify", work / "broken.kpol"])
        assert done.returncode == 1 and "Expectation failed at step 6" in done.stdout
        done = _run([kpolc, "build", "--profile", "KPOL-CME-1", work / "broken.kpol", work / "broken.bin"])
        assert done.returncode == 2 and done.stderr.startswith("B3-PROOF")

        # Snapshot semantics: conflicting writes are reported, nothing is written.
        (work / "conflict.kpol").write_text(pair.replace("set B := A;", "set A := A;"), encoding="utf-8")
        done = _run([kpolc, "run", work / "conflict.kpol", "-e", "Swap()"])
        assert "diagnostics: ConflictingWrites:A" in done.stdout and "state:       A=2 B=5" in done.stdout

        done = _run([kpolc, "run", work / "room.kpol", "-e", "Report(n=2)", "-e", "Report(n=4)"])
        assert "state:       Used=2 Free=1" in done.stdout and "InvariantViolation:Capacity" in done.stdout

        done = _run([kpolc, "run", work / "loans.kpol", "-e", "Take(n=2)", "-e", "Take(n=3)", "-e", "Take(n=2)", "-e", "Take(n=Unknown)"])
        out = done.stdout
        assert "alerts:      Large" in out and "diagnostics: InvariantViolation:Stock" in out
        assert "state:       Available=0 Review=false" in out and "goals:       Reserve" in out
        assert "rejected:    RejectedInput:Take" in out


def test_ekpol_guide_programs_behave_as_the_text_says(tools):
    (visits,) = _blocks("ekpol-programming-guide.md", "ekpol")[:1]
    (short_rule,) = _blocks("ekpol-programming-guide.md", "ekpol")[1:2]
    kpolc = tools / "kpolc"
    with _scratch("guide") as work:
        source = work / "visits.ekpol"
        source.write_text(visits, encoding="utf-8")
        done = _run([kpolc, "verify", source])
        assert done.returncode == 0 and "VisitsCard: 1 embedded tests passed" in done.stdout

        assert _run([kpolc, "build", source, work / "visits.bin"]).returncode == 0
        trace = _run([tools / "vmk", "--program", work / "visits.bin", "--trace-events", "0:1,0:0,0:1,0:1,0:1"]).stdout
        # (Visits, Badges): the badge is committed in the cascade of the third counted visit.
        assert "COMMIT *STATE_CHANGE(0->1)" in trace
        assert re.search(r"C01 \(Concept_1\).*param=3.*COMMIT \*STATE_CHANGE\(0->1\)", trace)
        assert trace.count("COMMIT *STATE_CHANGE") == 5

        ge = work / "ge.ekpol"
        ge.write_text(visits.replace("Visits == 3", "Visits >= 3"), encoding="utf-8")
        done = _run([kpolc, "verify", ge])
        assert done.returncode == 1 and "EKPOL-PROOF-ERR" in done.stderr

        short = work / "short.ekpol"
        short.write_text(visits.replace("on change(Visits) when Visits == 3 => Badges += 1 commit;", short_rule.strip()), encoding="utf-8")
        assert _run([kpolc, "verify", short]).returncode == 0
        assert "on change(Visits)" in _run([kpolc, "to-ekpol", "--ekpol-style", "keyword", source]).stdout


def test_auth_guide_programs_behave_as_the_text_says(tools):
    pages, marks, sheets = _blocks("kpol-auth-programming-guide.md", "kpol-auth")
    (group,) = [b for b in _blocks("kpol-auth-programming-guide.md", "text") if b.startswith("Collection")]
    kpolc = tools / "kpolc"
    with _scratch("guide") as work:
        for name, source in (("pages", pages), ("marks", marks), ("sheets", sheets), ("group", group)):
            (work / f"{name}.auth").write_text(source, encoding="utf-8")

        done = _run([kpolc, "auth", work / "pages.auth", "--check"])
        assert done.stdout.strip() == "OK: 2 concepts, 1 subscriptions, 5 Do/Go words, 1024 BRAM bytes"
        assert "Page=4 Next=5" in _run([kpolc, "auth-run", "-w", "Page=4", work / "pages.auth"]).stdout

        # The prediction table of the guide.
        done = _run([kpolc, "auth-run", "-w", "Mark=4", "-w", "Mark=4", "-w", "Mark=0", "-w", "Mark=6", work / "marks.auth"])
        rows = [line.split(None, 2)[2] for line in done.stdout.splitlines()[1:]]
        assert rows == [
            "Mark=4 Count=1 Points=2 Errors=0 Review=0",
            "Mark=4 Count=2 Points=4 Errors=0 Review=0",
            "Mark=0 Count=2 Points=4 Errors=0 Review=0",
            "Mark=0 Count=2 Points=4 Errors=1 Review=1",
        ]
        done = _run([kpolc, "auth-run", "-w", "Sheet=3", "-w", "Sheet=5", work / "sheets.auth"])
        assert "Sheet=3 LastPage=6 NextPage=7" in done.stdout and "Sheet=5 LastPage=10 NextPage=11" in done.stdout

        # Exercise 1: "changed" and "positive" differ on the repeated 4.
        changed = marks.replace("OnPositive(Mark)", "Mark")
        (work / "changed.auth").write_text(changed, encoding="utf-8")
        done = _run([kpolc, "auth-run", "-w", "Mark=4", "-w", "Mark=4", "-w", "Mark=0", work / "changed.auth"])
        counts = [line.split()[3] for line in done.stdout.splitlines()[1:]]
        assert counts == ["Count=1", "Count=1", "Count=2"]

        # Parse versus lower.
        assert "GroupBounds Min=1 Max=15 effective=1..16" in _run([kpolc, "auth-cst", work / "group.auth"]).stdout
        done = _run([kpolc, "auth", work / "group.auth", "--check"])
        assert done.returncode == 3 and done.stderr.startswith("KPOL-LOWER-UNSUPPORTED-CST")

        (work / "cycle.auth").write_text(pages.replace("Assign(Next", "Assign(Page"), encoding="utf-8")
        done = _run([kpolc, "auth", work / "cycle.auth", "--check"])
        assert done.returncode == 3 and done.stderr.startswith("KPOL-LOWER-CYCLE")

        out = work / "pages.json"
        assert _run([kpolc, "auth", work / "pages.auth", "--check", "--emit-dogo", out]).returncode == 0
        document = json.loads(out.read_text(encoding="utf-8"))
        (subscription,) = document["subscriptions"]
        assert (subscription["owner_cid"], subscription["target_cid"], subscription["line_start_pc"], subscription["line_len"]) == (0, 1, 0, 5)


def _table(guide: str) -> list[str]:
    (block,) = [b for b in _blocks(guide, "text") if b.startswith("CID")]
    return [line.rstrip() for line in block.strip().splitlines()]


def _lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.strip().splitlines()]


def test_kpol_compiler_chapter_matches_the_tool(tools):
    tally = _blocks("kpol-programming-guide.md", "kpol")[4]
    kpolc = tools / "kpolc"
    with _scratch("chapter") as work:
        source = work / "tally.kpol"
        source.write_text(tally, encoding="utf-8")
        assert _run([kpolc, "check", source]).stdout.strip() == "OK: Tally: 2 states, 1 events, 2 rules, with Proof"
        assert _run([kpolc, "verify", source]).stdout.strip() == "Tally: 2/2 checks passed"

        done = _run([kpolc, "build", source, work / "cme1.bin"])
        assert done.returncode == 2 and done.stderr.strip() == "B3-SHAPE: module Tally: expected exactly one state, event and rule"

        image = work / "tally.bin"
        done = _run([kpolc, "build", "--profile", "KPOL-CME-2", source, image, "--dump-concepts"])
        assert done.returncode == 0 and _lines(done.stdout) == _table("kpol-programming-guide.md")
        done = _run([kpolc, "build", "--profile", "KPOL-CME-2", source, image])
        assert done.returncode == 2 and done.stderr.strip() == f"CME2-IO: {image}: File exists"

        trace = _run([tools / "vmk", "--program", image, "--trace-events", "0:1,0:1,0:1"]).stdout
        verdicts = re.findall(r"\| (COMMIT|REJECT_GUARD)", trace)
        assert verdicts == ["COMMIT", "REJECT_GUARD", "COMMIT", "REJECT_GUARD", "COMMIT", "COMMIT"]

        done = _run([kpolc, "build", "--profile", "KPOL-CME-2", "--emit-ekpol", work / "t.ekpol", "--ekpol-style", "keyword", source, work / "t.bin"])
        assert done.returncode == 0 and "on change(Count) when Count >= 3 => Done += 1 commit;" in (work / "t.ekpol").read_text(encoding="utf-8")
        if shutil.which("z3"):
            done = _run([kpolc, "build", "--profile", "KPOL-CME-2", "--emit-c99", work / "t.c", "--emit-z3-cert", work / "t.json", source, work / "t2.bin"])
            assert done.returncode == 0 and json.loads((work / "t.json").read_text(encoding="utf-8"))["verdict"] == "VERIFIED"

        # The error table of the chapter.
        broken = work / "broken.kpol"
        broken.write_text(tally.replace("set Count := Count + 1;", "set Count := Count + 1"), encoding="utf-8")
        done = _run([kpolc, "build", "--profile", "KPOL-CME-2", broken, work / "b.bin"])
        assert done.returncode == 2 and re.fullmatch(r"CME2-SYNTAX: .*broken\.kpol: \d+:\d+: expected ';', got '\}'", done.stderr.strip())
        broken.write_text(tally.replace("Count >= 3 {", "Total >= 3 {"), encoding="utf-8")
        assert _run([kpolc, "check", broken]).stderr.strip().endswith("unresolved name 'Total'")
        broken.write_text(tally.replace("expect Done == 1;", "expect Done == 5;"), encoding="utf-8")
        done = _run([kpolc, "verify", broken])
        assert done.returncode == 1 and "FAIL ThreeAdds: Expectation failed at step 5:" in done.stdout
        done = _run([kpolc, "build", "--profile", "KPOL-CME-2", broken, work / "p.bin"])
        assert done.returncode == 2 and done.stderr.startswith("CME2-PROOF: module Tally: Proof failed")
        assert "unknown input event 'Nope'" in _run([kpolc, "run", source, "-e", "Nope(n=1)"]).stderr
        assert "payload for 'Add' must contain exactly n" in _run([kpolc, "run", source, "-e", "Add(m=1)"]).stderr


def test_ekpol_compiler_chapter_matches_the_tool(tools):
    visits = _blocks("ekpol-programming-guide.md", "ekpol")[0]
    kpolc = tools / "kpolc"
    with _scratch("chapter") as work:
        source = work / "visits.ekpol"
        source.write_text(visits, encoding="utf-8")
        assert _run([kpolc, "check", source]).stdout.strip() == "OK: VisitsCard: 2 concepts, 1 tests (EKPOL-B64)"
        done = _run([kpolc, "build", source, work / "visits.bin", "--dump-concepts"])
        assert done.returncode == 0 and _lines(done.stdout) == _table("ekpol-programming-guide.md")
        done = _run([kpolc, "build", source, work / "visits.bin"])
        assert done.returncode == 2 and done.stderr.strip() == f"EKPOL-IO: {work / 'visits.bin'}: File exists"

        cases = {
            "EKPOL-SYNTAX-ERR": ("=> Visits += 1 commit;", "Visits += 1 commit;", "is missing '=>' action arrow"),
            "EKPOL-TYPE-ERR": ("concept Badges: i32", "concept Badges: u64", "concept 'Badges' has type U64"),
            "EKPOL-CYCLE-ERR": ("on Visit(stamp) when stamp == 1 => Visits += 1", "on change(Badges) => Visits += 1", "(Visits -> Badges -> Visits)"),
            "EKPOL-COLLISION-ERR": ("Visits += 1 commit;\n}\n\nconcept Badges", "Visits += 2 commit;\n}\n\nconcept Badges", "shares one 32-bit W1 operand_val"),
        }
        for code, (old, new, fragment) in cases.items():
            assert old in visits, code
            mutant = work / f"{code}.ekpol"
            mutant.write_text(visits.replace(old, new, 1), encoding="utf-8")
            done = _run([kpolc, "build", mutant, work / f"{code}.bin"])
            assert done.returncode == 2 and done.stderr.startswith(code) and fragment in done.stderr, (code, done.stderr)
        proof = work / "proof.ekpol"
        proof.write_text(visits.replace("Visits == 3", "Visits >= 3"), encoding="utf-8")
        done = _run([kpolc, "verify", proof])
        assert done.returncode == 1 and done.stderr.startswith("EKPOL-PROOF-ERR: embedded test verification failed")

        concept = work / "sum.ekpol"
        concept.write_text("module Sum;\nconcept Sum: f64 = 0 {\n    -> => . Sum = 0\n}\n", encoding="utf-8")
        assert _run([kpolc, "check", concept]).stdout.strip() == "OK: Sum: 1 concepts (conceptual constructs; not compilable to EKPOL-B64)"
        done = _run([kpolc, "build", concept, work / "sum.bin"])
        assert done.stderr.strip() == "EKPOL-TYPE-ERR: concept 'Sum' has type Float, but CME-RAW-1 bram64 requires Int32 (i32/int32/Int32)"

        # Three notations, one image.
        done = _run([kpolc, "build", source, work / "a.bin", "--emit-kpol", work / "v.kpol", "--emit-ekpol", work / "v_kw.ekpol", "--ekpol-style", "keyword"])
        assert done.returncode == 0
        assert _run([kpolc, "build", "--profile", "KPOL-CME-2", work / "v.kpol", work / "b.bin"]).returncode == 0
        assert _run([kpolc, "build", work / "v_kw.ekpol", work / "c.bin"]).returncode == 0
        assert (work / "a.bin").read_bytes() == (work / "b.bin").read_bytes() == (work / "c.bin").read_bytes()


def test_auth_compiler_chapter_matches_the_tool(tools):
    pages = _blocks("kpol-auth-programming-guide.md", "kpol-auth")[0]
    kpolc = tools / "kpolc"
    with _scratch("chapter") as work:
        source = work / "pages.auth"
        source.write_text(pages, encoding="utf-8")
        plain = _run([kpolc, "auth", source])
        assert plain.returncode == 0 and plain.stdout.strip() == "OK: 2 concepts, 1 subscriptions, 5 Do/Go words, 1024 BRAM bytes"

        done = _run([kpolc, "auth", source, "--emit-dogo", work / "words.bin"])
        assert done.returncode == 0 and (work / "words.bin").stat().st_size == 20
        done = _run([kpolc, "auth", source, "--emit-bram", work / "pages.bin"])
        assert done.returncode == 0 and (work / "pages.bin").stat().st_size == 1024

        # An existing output blocks every output.
        done = _run([kpolc, "auth", source, "--emit-dogo", work / "new.json", "--emit-bram", work / "pages.bin"])
        assert done.returncode == 1 and done.stderr.startswith("KPOL-CLI-IO: [Errno 17] File exists:")
        assert not (work / "new.json").exists()
        done = _run([kpolc, "auth", work / "missing.auth", "--check"])
        assert done.returncode == 1 and done.stderr.startswith("KPOL-CLI-IO: [Errno 2] No such file or directory:")

        for text, code, expected in (
            ("Concept(Page, 0) ← Page\n", 2, "KPOL-AUTH-LEX-01"),
            ("Concept(Page, 0\n", 2, "KPOL-AUTH-SYNTAX-02"),
            ("Concept(A, -1)\n", 2, "KPOL-AUTH-SYNTAX-01"),
            ("Concept(A, 0) Concept(B, 0) C := _ + B\n", 2, "KPOL-AUTH-U10"),
            ("Concept(A, 0) A • Assign(B, 1)\n", 3, "KPOL-LOWER-UNKNOWN-CONCEPT"),
            ("Concept(A, 0) Concept(B, 0) A • Assign(B, A / 2)\n", 3, "KPOL-LOWER-UNSUPPORTED-OP"),
            ("Concept(A, 0) Concept(B, 0) Concept(C, 0) A • {Assign(B, 1), Assign(C, 2)}\n", 3, "KPOL-LOWER-FANOUT"),
            ("Concept(A, 0) A • Assign(A, 1)\n", 3, "KPOL-LOWER-CYCLE"),
        ):
            bad = work / "bad.auth"
            bad.write_text(text, encoding="utf-8")
            done = _run([kpolc, "auth", bad, "--check"])
            assert (done.returncode, re.match(r"[A-Z0-9-]+", done.stderr)[0]) == (code, expected), (text, done.stderr)
