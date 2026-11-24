import json

import pytest

from prioritykit import (
    LEVELS,
    MatrixError,
    check_matrix,
    classify,
    default_matrix,
    load_matrix,
    matrix_from_dict,
)
from prioritykit.matrix import RANK, SCORES


def stated(i: int, u: int) -> str:
    """The default rules exactly as the background post states them."""
    if i >= 4 and u == 5:
        return "P0"
    if i >= 4:
        return "P1"
    if i == 3:
        return "P1" if u >= 4 else "P2"
    return "P2" if u >= 4 else "drop"


def test_default_matches_stated_rules() -> None:
    m = default_matrix()
    for i in SCORES:
        for u in SCORES:
            assert m.level(i, u) == stated(i, u), (i, u)


def test_default_counts() -> None:
    assert default_matrix().counts() == {"P0": 2, "P1": 10, "P2": 7, "drop": 6}


def test_default_passes_check_with_no_warnings() -> None:
    report = check_matrix(default_matrix())
    assert report.ok
    assert report.warnings == ()


def test_importance_outranks_urgency() -> None:
    # Unlike an importance x urgency product (5 x 1 < 2 x 5).
    assert RANK[classify(5, 1).level] > RANK[classify(2, 5).level]


def test_classify_reports_anchors_and_summary() -> None:
    c = classify(5, 2)
    assert c.level == "P1"
    assert c.importance_anchor.startswith("Directly advances an annual goal")
    assert c.urgency_anchor == "Waiting a month costs little"
    assert c.describe().startswith("Importance 5, urgency 2: P1 (schedule).")
    assert classify(1, 1).describe().startswith("Importance 1, urgency 1: Drop.")


@pytest.mark.parametrize("bad", [0, 6, 2.5, "3", True, None])
def test_invalid_scores_raise(bad: object) -> None:
    with pytest.raises(ValueError):
        classify(bad, 3)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        classify(3, bad)  # type: ignore[arg-type]


def test_custom_matrix_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    data = default_matrix().to_dict()
    path = tmp_path / "m.json"
    path.write_text(json.dumps(data))
    assert load_matrix(path) == default_matrix()


def test_check_flags_non_monotone_and_urgency_only_lift() -> None:
    data = default_matrix().to_dict()
    data["grid"][4][0] = "drop"  # importance 5, urgency 1 below importance 4, urgency 1
    data["grid"][0][4] = "P1"  # importance 1, urgency 5 lifted above P2 by urgency alone
    report = check_matrix(matrix_from_dict(data))
    assert not report.ok
    assert any("raising importance from 4 to 5" in e for e in report.errors)
    assert any("urgency alone" in w for w in report.warnings)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("grid"),
        lambda d: d["grid"].pop(),
        lambda d: d["grid"][0].__setitem__(0, "P9"),
        lambda d: d["levels"].pop("drop"),
        lambda d: d["importance"].pop(),
        lambda d: d["urgency"][0].__setitem__("label", " "),
    ],
)
def test_malformed_matrix_raises(mutate) -> None:  # type: ignore[no-untyped-def]
    data = default_matrix().to_dict()
    mutate(data)
    with pytest.raises(MatrixError):
        matrix_from_dict(data)


def test_levels_constant() -> None:
    assert set(default_matrix().levels) == set(LEVELS)
