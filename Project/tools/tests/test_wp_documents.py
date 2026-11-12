import hashlib
import importlib.util
import json
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "check_wp_documents.py"
spec = importlib.util.spec_from_file_location("wp_documents", TOOL)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def test_missing_document_envelope_is_reported(tmp_path):
    (tmp_path / "README.md").write_text("# Missing metadata\n")
    result = tool.check(tmp_path)
    assert result["documents_checked"] == 1
    assert len(result["errors"]) == 5


def test_immutable_data_is_not_reformatted_but_changes_are_detected(tmp_path):
    source = tmp_path / "Research/sources/original.md"
    source.parent.mkdir(parents=True)
    source.write_text("Original source, not a WP form.\n")
    registry = tmp_path / "Project/registers"
    registry.mkdir(parents=True)
    (registry / "migration-manifest.json").write_text(json.dumps({"entries": [{
        "destination": source.relative_to(tmp_path).as_posix(),
        "immutable": True,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }]}))
    assert not any("original.md" in error for error in tool.check(tmp_path)["errors"])
    source.write_text("Changed original\n")
    assert any("changed immutable input" in error for error in tool.check(tmp_path)["errors"])
