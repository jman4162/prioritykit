from datetime import date
from pathlib import Path

import pytest

from prioritykit import (
    DailyGoal,
    Goal,
    P2Item,
    check_day_plan,
    check_goal_tree,
    littles_law_wait,
    load_workspace,
    replan_for_p0,
    review_p2,
)

GOALS = [
    Goal("lead", "Grow as a technical lead", "annual"),
    Goal("fit", "Stay strong and fit", "annual"),
    Goal("family", "Be present with my family", "annual"),
    Goal("mentor", "Mentor a junior scientist", "quarterly", "lead"),
    Goal("strength", "Strength train 3 times a week", "quarterly", "fit"),
    Goal("evenings", "Protect weekday evenings", "quarterly", "family"),
]
TODAY = [
    DailyGoal("Review a design doc", "mentor"),
    DailyGoal("Strength session", "strength"),
    DailyGoal("Dinner and bedtime", "evenings"),
]
EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "priorities.toml"


def test_valid_plan_traces_each_goal_to_an_annual_goal() -> None:
    report = check_day_plan(TODAY, GOALS)
    assert report.ok, report.errors
    assert report.traces[0] == (
        "Review a design doc",
        "Mentor a junior scientist",
        "Grow as a technical lead",
    )
    assert report.annual_without_slot == ()


@pytest.mark.parametrize("n", [2, 4])
def test_plan_must_hold_exactly_three(n: int) -> None:
    daily = (TODAY * 2)[:n]
    daily = [DailyGoal(f"{d.title} {k}", d.parent) for k, d in enumerate(daily)]
    report = check_day_plan(daily, GOALS)
    assert not report.ok
    assert any("exactly 3" in e for e in report.errors)


def test_count_is_configurable() -> None:
    assert check_day_plan(TODAY[:2], GOALS, count=2).ok


def test_daily_goal_needs_a_quarterly_parent() -> None:
    bad = [DailyGoal("Untraced"), DailyGoal("Points at annual", "lead"), TODAY[2]]
    errors = check_day_plan(bad, GOALS).errors
    assert any("must trace to a quarterly goal" in e for e in errors)
    assert any("must point at a quarterly goal" in e for e in errors)


def test_goal_tree_errors() -> None:
    goals = [
        Goal("a", "A", "annual", parent="x"),
        Goal("q1", "Q1", "quarterly"),
        Goal("q2", "Q2", "quarterly", "missing"),
        Goal("q3", "Q3", "quarterly", "q2"),
        Goal("a", "A again", "annual"),
    ]
    errors = check_goal_tree(goals)
    assert len(errors) == 5


def test_p0_replan_names_what_it_displaces() -> None:
    new = replan_for_p0(TODAY, "Restore the build server", "Review a design doc")
    assert new[0].p0 and new[0].displaces == "Review a design doc"
    report = check_day_plan(new, GOALS)
    assert report.ok, report.errors
    assert report.annual_without_slot == ("Grow as a technical lead",)
    with pytest.raises(ValueError):
        replan_for_p0(TODAY, "X", "not in the plan")


def test_p0_without_displaces_is_rejected() -> None:
    daily = [DailyGoal("Outage", p0=True), TODAY[1], TODAY[2]]
    assert any("must name the goal it displaces" in e for e in check_day_plan(daily, GOALS).errors)


def test_review_sorts_promote_delete_keep() -> None:
    items = [
        P2Item("old and low", date(2026, 1, 1), 2, 1),
        P2Item("now important", date(2026, 1, 1), 4, 2),
        P2Item("recent unscored", date(2026, 11, 1)),
        P2Item("old unscored", date(2025, 6, 1)),
    ]
    rep = review_p2(items, date(2026, 11, 24))
    assert [i.title for i, c in rep.promote] == ["now important"]
    assert rep.promote[0][1].level == "P1"
    assert [i.title for i in rep.delete] == ["old and low", "old unscored"]
    assert [i.title for i in rep.keep] == ["recent unscored"]
    assert rep.expected_wait_months is None


def test_littles_law() -> None:
    assert littles_law_wait(120, 3) == 40
    with pytest.raises(ValueError):
        littles_law_wait(10, 0)
    rep = review_p2([P2Item("a", date(2026, 11, 1))], date(2026, 11, 2), departures_per_month=0.5)
    assert rep.expected_wait_months == 2


def test_example_workspace_is_valid() -> None:
    ws = load_workspace(EXAMPLE)
    assert check_goal_tree(ws.goals) == []
    assert ws.today is not None
    report = check_day_plan(ws.today, ws.goals)
    assert report.ok, report.errors
    assert report.annual_without_slot == ("Publish technical writing",)
    rep = review_p2(ws.p2, date(2026, 11, 24))
    assert [i.title for i, _ in rep.promote] == ["Renew the passport before the spring trip"]
    assert [i.title for i in rep.delete] == ["Reorganize the photo library"]
