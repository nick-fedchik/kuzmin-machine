"""Тести перевірки посилань на `drafts@<sha>` у tools/check_links.py.

Тести не залежать від справжнього клону `drafts`: тимчасовий git-репозиторій
створюється в `tmp_path`, а шлях до нього передається через `KM_DRAFTS_REPO`.
"""
import importlib.util
import subprocess
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "check_links.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("check_links_under_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


@pytest.fixture()
def drafts(tmp_path):
    """Тимчасовий клон drafts з одним комітом і файлом docs/a.md."""
    repo = tmp_path / "drafts"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    (repo / "docs").mkdir()
    (repo / "docs" / "a.md").write_text("# a\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "init")
    return repo, git(repo, "rev-parse", "HEAD")


def make_root(tmp_path: Path, link: str) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "doc.md").write_text(f"[посилання]({link})\n", encoding="utf-8")
    return root


def drafts_url(sha: str, path: str, kind: str = "blob") -> str:
    return f"https://github.com/nick-fedchik/drafts/{kind}/{sha}/{path}"


def test_existing_blob_passes(tmp_path, drafts, monkeypatch):
    repo, sha = drafts
    monkeypatch.setenv("KM_DRAFTS_REPO", str(repo))
    root = make_root(tmp_path, drafts_url(sha, "docs/a.md"))
    assert load_tool().main(root) == 0


def test_existing_tree_passes(tmp_path, drafts, monkeypatch):
    repo, sha = drafts
    monkeypatch.setenv("KM_DRAFTS_REPO", str(repo))
    root = make_root(tmp_path, drafts_url(sha, "docs", kind="tree"))
    assert load_tool().main(root) == 0


def test_percent_encoded_path_is_unquoted(tmp_path, drafts, monkeypatch):
    repo, sha = drafts
    (repo / "docs" / "файл з пробілом.md").write_text("# b\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "add spaced")
    sha = git(repo, "rev-parse", "HEAD")
    monkeypatch.setenv("KM_DRAFTS_REPO", str(repo))
    root = make_root(tmp_path, drafts_url(sha, "docs/файл%20з%20пробілом.md"))
    assert load_tool().main(root) == 0


def test_missing_path_fails(tmp_path, drafts, monkeypatch, capsys):
    repo, sha = drafts
    monkeypatch.setenv("KM_DRAFTS_REPO", str(repo))
    root = make_root(tmp_path, drafts_url(sha, "docs/немає.md"))
    assert load_tool().main(root) == 1
    assert "docs/немає.md" in capsys.readouterr().out


def test_missing_sha_fails(tmp_path, drafts, monkeypatch):
    repo, _ = drafts
    monkeypatch.setenv("KM_DRAFTS_REPO", str(repo))
    root = make_root(tmp_path, drafts_url("0" * 40, "docs/a.md"))
    assert load_tool().main(root) == 1


def test_without_env_skips_with_warning(tmp_path, drafts, monkeypatch, capsys):
    _, sha = drafts
    monkeypatch.delenv("KM_DRAFTS_REPO", raising=False)
    root = make_root(tmp_path, drafts_url(sha, "docs/немає.md"))
    assert load_tool().main(root) == 0
    out = capsys.readouterr().out
    assert "не перевіряються" in out
    assert "перевірено 0, пропущено 1" in out


def test_non_git_repo_skips_with_warning(tmp_path, drafts, monkeypatch, capsys):
    _, sha = drafts
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    monkeypatch.setenv("KM_DRAFTS_REPO", str(not_a_repo))
    root = make_root(tmp_path, drafts_url(sha, "docs/a.md"))
    assert load_tool().main(root) == 0
    assert "не перевіряються" in capsys.readouterr().out


def test_broken_relative_link_still_fails(tmp_path, monkeypatch):
    monkeypatch.delenv("KM_DRAFTS_REPO", raising=False)
    root = make_root(tmp_path, "немає-такого-файлу.md")
    assert load_tool().main(root) == 1
