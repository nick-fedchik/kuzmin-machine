"""Compare preregistered AV result fields without floating-point tolerances."""

import csv
from decimal import Decimal, InvalidOperation
import json


def same_value(left, right):
    try:
        a, b = Decimal(str(left)), Decimal(str(right))
        return a.is_finite() and b.is_finite() and a == b
    except InvalidOperation:
        return type(left) is type(right) and left == right


def compare_rows(expected, actual, keys, fields):
    def index(rows):
        result = {}
        for row in rows:
            key = tuple(str(row[field]) for field in keys)
            if key in result:
                raise ValueError(f"duplicate result key: {key}")
            result[key] = row
        return result

    before, after = index(expected), index(actual)
    if not before:
        raise ValueError("empty reference")
    differences = []
    for key in sorted(before.keys() | after.keys()):
        if key not in before or key not in after:
            differences.append({"key": key, "error": "missing or extra result"})
            continue
        for field in fields:
            if field not in before[key] or field not in after[key]:
                differences.append({"key": key, "field": field, "error": "missing field"})
                continue
            left, right = before[key][field], after[key][field]
            if field in ("reached_covers", "unreached_covers"):
                equal = set(left.split(";")) == set(right.split(";"))
            else:
                equal = same_value(left, right)
            if not equal:
                differences.append({"key": key, "field": field, "expected": left, "actual": right})
    return differences


def csv_rows(path):
    with open(path, newline="") as stream:
        return list(csv.DictReader(stream))


def mutation_rows(path):
    data = json.loads(path.read_text())
    rows = [{"id": "__totals__", **{
        key: data[key] for key in (
            "total_mutants", "killed_mutants", "survived_mutants", "mutation_score_pct"
        )
    }}]
    for suite in data["suites"]:
        for mutant in suite["mutants"]:
            rows.append({"id": mutant["id"], "status": mutant["status"], "stage": mutant["stage"]})
    return rows
