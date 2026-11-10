import hashlib
import io
import runpy
import tarfile
from pathlib import Path

import pytest


MODULE = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "process/migration/separate_publications.py")
)


@pytest.mark.parametrize("defect", [None, "modified", "missing", "extra"])
def test_archive_checks_content_and_complete_member_set(tmp_path, defect):
    original = b"original research\n"
    entries = [{"source": "analysis.md", "sha256": hashlib.sha256(original).hexdigest()}]
    archive = tmp_path / "snapshot.tar.gz"
    with tarfile.open(archive, "w:gz") as saved:
        if defect != "missing":
            content = b"changed\n" if defect == "modified" else original
            member = tarfile.TarInfo("KuzminMachine/analysis.md")
            member.size = len(content)
            saved.addfile(member, io.BytesIO(content))
        if defect == "extra":
            member = tarfile.TarInfo("KuzminMachine/uninventoried.txt")
            saved.addfile(member, io.BytesIO(b""))
    if defect:
        with pytest.raises(ValueError):
            MODULE["verify_archive"](archive, entries)
    else:
        MODULE["verify_archive"](archive, entries)


def test_links_follow_canonical_files_but_do_not_rewrite_code(tmp_path):
    text = "[core](../core.sv)\n```text\n[example](../core.sv)\n```\n"
    result = MODULE["rewrite"](
        text, "old/a.md", "docs/research/a.md", {"core.sv": "hw/rtl/core.sv"},
        "docs/archive/snapshot.tar.gz", {"core.sv"}, [], tmp_path, "unused",
    )
    assert "[core](../../hw/rtl/core.sv)" in result
    assert "[example](../core.sv)" in result


def test_missing_historical_target_is_not_a_fabricated_link(tmp_path):
    unresolved = []
    result = MODULE["rewrite"](
        "[missing](absent.md)", "a.md", "docs/research/a.md", {},
        "docs/archive/snapshot.tar.gz", set(), unresolved, tmp_path, "unused",
    )
    assert "](absent.md)" not in result
    assert "`absent.md`" in result
    assert unresolved == [{"source": "a.md", "target": "absent.md"}]


def test_unique_moved_filename_and_archived_directory_are_resolved(tmp_path):
    unresolved = []
    result = MODULE["rewrite"](
        "[core](core.sv)\n[original directory](../02)\n",
        "old/a.md", "docs/research/a.md", {"02/rtl/core.sv": "hw/rtl/core.sv"},
        "docs/archive/snapshot.tar.gz", {"02/rtl/core.sv"}, unresolved, tmp_path, "unused",
    )
    assert "[core](../../hw/rtl/core.sv)" in result
    assert "[original directory](../archive/snapshot.tar.gz)" in result
    assert unresolved == []


def test_ambiguous_filename_is_not_guessed(tmp_path):
    unresolved = []
    result = MODULE["rewrite"](
        "[guide](guide.md)", "a.md", "docs/research/a.md",
        {"one/guide.md": "docs/one.md", "two/guide.md": "docs/two.md"},
        "docs/archive/snapshot.tar.gz", {"one/guide.md", "two/guide.md"},
        unresolved, tmp_path, "unused",
    )
    assert "docs/one.md" not in result and "docs/two.md" not in result
    assert unresolved == [{"source": "a.md", "target": "guide.md"}]
