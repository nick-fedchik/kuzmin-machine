"""Synthetic cases for #75: changes, missing evidence and duplicate keys must fail."""

import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "process/validation/75-reproduce-av/compare.py"
spec = importlib.util.spec_from_file_location("av_comparison", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_numeric_format_and_row_order_are_not_differences():
    before = [{"id": "a", "value": "100.00"}, {"id": "b", "value": "32"}]
    after = [{"id": "b", "value": "32.0"}, {"id": "a", "value": "100"}]
    assert module.compare_rows(before, after, ["id"], ["value"]) == []


@pytest.mark.parametrize("after", [
    [{"id": "a", "value": "100.01"}],
    [{"id": "a", "value": "99.99"}],
    [{"id": "a"}],
    [],
    [{"id": "b", "value": "100"}],
    [{"id": "a", "value": "NaN"}],
])
def test_changed_missing_or_nonfinite_result_is_detected(after):
    assert module.compare_rows([{"id": "a", "value": "100"}], after, ["id"], ["value"])


def test_stage_difference_is_not_hidden_by_equal_score():
    assert module.compare_rows(
        [{"id": "mutant", "stage": "TIMEOUT"}],
        [{"id": "mutant", "stage": "SIMULATION_ASSERTION"}],
        ["id"], ["stage"],
    )


@pytest.mark.parametrize("left,right", [("NaN", "NaN"), ("Infinity", "Infinity"), (1, True)])
def test_invalid_numeric_equality_cannot_pass(left, right):
    assert not module.same_value(left, right)


def test_duplicate_or_empty_reference_is_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        module.compare_rows([{"id": "a"}, {"id": "a"}], [{"id": "a"}], ["id"], [])
    with pytest.raises(ValueError, match="empty"):
        module.compare_rows([], [], ["id"], [])
