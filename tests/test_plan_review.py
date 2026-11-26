import json
import re
import tomllib
from datetime import date, datetime
from pathlib import Path

import pytest

from prioritykit import (
    DailyGoal,
    DayPlan,
    Goal,
    P2Item,
    Workspace,
    WorkspaceError,
    check_day_plan,
    check_goal_tree,
    check_workspace,
    due_soon,
    littles_law_wait,
    load_workspace,
    replan_for_p0,
    review_p2,
    slot_coverage,
    workspace_from_dict,
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
    assert rep.confirm == ()
    assert rep.expected_wait_months is None


def test_review_asks_to_confirm_old_unconfirmed_items() -> None:
    old = date(2026, 1, 1)
    items = [
        P2Item("guessed low", old, 2, 1, confirmed=False),
        P2Item("confirmed low", old, 2, 1),
        P2Item("agent added, unscored", old, confirmed=False),
        P2Item("old unscored", old),
        P2Item("guessed high", old, 4, 2, confirmed=False),
        P2Item("recent guess", date(2026, 11, 20), 2, 1, confirmed=False),
    ]
    rep = review_p2(items, date(2026, 11, 24))
    assert [i.title for i in rep.confirm] == ["guessed low", "agent added, unscored"]
    assert [i.title for i in rep.delete] == ["confirmed low", "old unscored"]
    assert all(i.confirmed for i in rep.delete)
    assert [i.title for i, _ in rep.promote] == ["guessed high"]
    assert [i.title for i in rep.keep] == ["recent guess"]
    assert rep.to_dict()["confirm"][0] == {
        "title": "guessed low",
        "added": "2026-01-01",
        "confirmed": False,
    }


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


def test_slot_coverage_over_a_week() -> None:
    days = [DayPlan(date(2026, 11, d), (TODAY[0], TODAY[2])) for d in range(18, 25)]
    days.append(DayPlan(date(2026, 11, 17), (TODAY[1],)))  # outside the 7-day window
    cov = slot_coverage(GOALS, days, date(2026, 11, 24))
    assert cov.window_start == date(2026, 11, 18) and cov.window_days == 7
    assert cov.days_with_plans == 7
    assert cov.quarterly_without_slot == ("Strength train 3 times a week",)
    assert cov.annual_without_slot == ("Stay strong and fit",)


def test_slot_coverage_reports_how_much_history_it_had() -> None:
    p0 = DailyGoal("Outage", p0=True, displaces="Review a design doc")
    days = [
        DayPlan(date(2026, 11, 23), (p0, TODAY[1])),
        DayPlan(date(2026, 11, 24), (TODAY[1], TODAY[2])),
    ]
    cov = slot_coverage(GOALS, days, date(2026, 11, 24))
    assert cov.days_with_plans == 2
    assert cov.quarterly_without_slot == ("Mentor a junior scientist",)
    with pytest.raises(ValueError, match="at least 1"):
        slot_coverage(GOALS, days, date(2026, 11, 24), window_days=0)


def test_slot_coverage_rejects_two_plans_on_one_date() -> None:
    days = [DayPlan(date(2026, 11, 24), (TODAY[1],)), DayPlan(date(2026, 11, 24), (TODAY[2],))]
    with pytest.raises(ValueError, match="share the date 2026-11-24"):
        slot_coverage(GOALS, days, date(2026, 11, 24))


def test_slot_coverage_counts_proposed_plans_separately() -> None:
    days = [
        DayPlan(date(2026, 11, 23), (TODAY[0], TODAY[2])),
        DayPlan(date(2026, 11, 24), (TODAY[1],), confirmed=False),  # strength only proposed
    ]
    cov = slot_coverage(GOALS, days, date(2026, 11, 24))
    assert (cov.days_with_plans, cov.days_with_confirmed_plans) == (2, 1)
    assert cov.quarterly_without_slot == ()
    assert cov.quarterly_without_confirmed_slot == ("Strength train 3 times a week",)
    assert cov.annual_without_confirmed_slot == ("Stay strong and fit",)
    all_confirmed = slot_coverage(GOALS, days[:1], date(2026, 11, 24))
    assert all_confirmed.quarterly_without_slot == all_confirmed.quarterly_without_confirmed_slot
    assert all_confirmed.days_with_plans == all_confirmed.days_with_confirmed_plans == 1


def test_due_soon_crosses_due_dates_with_slots() -> None:
    goals = [
        *GOALS[:3],
        Goal("mentor", "Mentor a junior scientist", "quarterly", "lead", due=date(2026, 12, 4)),
        Goal("strength", "Strength train", "quarterly", "fit", due=date(2026, 11, 30)),
        Goal("evenings", "Protect evenings", "quarterly", "family", due=date(2027, 1, 3)),
        Goal("late", "Overdue goal", "quarterly", "lead", due=date(2026, 11, 1)),
    ]
    days = [
        DayPlan(date(2026, 11, 23), (TODAY[2],)),
        DayPlan(date(2026, 11, 24), (TODAY[1],), confirmed=False),
    ]
    run = date(2026, 11, 24)
    soon = due_soon(goals, run, 28, days)
    assert [(d.title, d.days_left, d.slot) for d in soon] == [
        ("Strength train", 6, "proposed"),
        ("Mentor a junior scientist", 10, "none"),
    ]
    assert [d.title for d in due_soon(goals, run, 45, days)][-1] == "Protect evenings"
    assert due_soon(goals, run, 45, days)[-1].slot == "confirmed"
    assert due_soon(goals, run, 28, days)[0].to_dict()["due"] == "2026-11-30"
    with pytest.raises(ValueError):
        due_soon(goals, run, -1)


def test_due_soon_makes_no_slot_claim_without_plans_in_range() -> None:
    goals = [GOALS[0], Goal("mentor", "M", "quarterly", "lead", due=date(2026, 11, 30))]
    run = date(2026, 11, 24)
    old_only = [DayPlan(date(2026, 11, 1), (TODAY[0],))]
    for days in (None, [], old_only):
        assert [d.slot for d in due_soon(goals, run, 28, days)] == [None]
    other = [DayPlan(date(2026, 11, 20), (TODAY[1],))]  # a plan in range, without mentor
    assert [d.slot for d in due_soon(goals, run, 28, other)] == ["none"]


def test_due_soon_counts_a_plan_for_tomorrow() -> None:
    goals = [GOALS[0], Goal("mentor", "M", "quarterly", "lead", due=date(2026, 11, 30))]
    tomorrow = [DayPlan(date(2026, 11, 25), (TODAY[0],))]
    assert due_soon(goals, date(2026, 11, 24), 28, tomorrow)[0].slot == "confirmed"
    cov = slot_coverage(goals, tomorrow, date(2026, 11, 24))
    assert cov.days_with_plans == 0  # coverage still ends on the run date


def test_large_windows_do_not_overflow() -> None:
    goals = [GOALS[0], Goal("mentor", "M", "quarterly", "lead", due=date(2026, 11, 30))]
    run = date(2026, 11, 24)
    days = [DayPlan(date(2026, 11, 23), (TODAY[0],))]
    assert due_soon(goals, run, 10**12, days, window_days=10**12)[0].slot == "confirmed"
    assert slot_coverage(goals, days, run, window_days=10**12).window_start == date.min


def test_workspace_due_soon_and_overdue() -> None:
    ws = workspace_from_dict(
        {
            "goal": [
                {"id": "a", "title": "A", "horizon": "annual"},
                {
                    "id": "q",
                    "title": "Q",
                    "horizon": "quarterly",
                    "parent": "a",
                    "due": "2026-12-04",
                },
                {
                    "id": "l",
                    "title": "L",
                    "horizon": "quarterly",
                    "parent": "a",
                    "due": "2026-11-01",
                },
            ]
        }
    )
    report = check_workspace(ws, date(2026, 11, 24))
    assert report.warnings == ("goal 'L' was due 2026-11-01; remove it or set a new due date",)
    assert report.to_dict()["due_soon"] == [
        {"title": "Q", "horizon": "quarterly", "due": "2026-12-04", "days_left": 10, "slot": None}
    ]
    no_due = workspace_from_dict({"goal": [{"id": "a", "title": "A", "horizon": "annual"}]})
    assert "due_soon" not in check_workspace(no_due, date(2026, 11, 24)).to_dict()


def test_workspace_today_overrides_day_with_same_date() -> None:
    ws = workspace_from_dict(
        {
            "goal": [
                {"id": "a", "title": "A", "horizon": "annual"},
                {"id": "q", "title": "Q", "horizon": "quarterly", "parent": "a"},
                {"id": "q2", "title": "Q2", "horizon": "quarterly", "parent": "a"},
            ],
            "today": {
                "date": "2026-11-24",
                "confirmed": False,
                "goals": [{"title": f"T{k}", "parent": "q"} for k in range(3)],
            },
            "day": [{"date": "2026-11-24", "goals": [{"title": "X", "parent": "q2"}]}],
        }
    )
    assert ws.today_confirmed is False
    report = check_workspace(ws, date(2026, 11, 24))
    assert report.warnings == (
        "[[day]] 2026-11-24 has the same date as [today]; coverage uses [today]",
    )
    cov = report.coverage
    assert cov is not None and cov.days_with_plans == 1 and cov.days_with_confirmed_plans == 0
    assert cov.quarterly_without_slot == ("Q2",)  # the [[day]] goal for Q2 did not count


def test_workspace_reads_history_due_dates_and_confirmed() -> None:
    ws = workspace_from_dict(
        {
            "goal": [
                {"id": "a", "title": "A", "horizon": "annual"},
                {
                    "id": "q",
                    "title": "Q",
                    "horizon": "quarterly",
                    "parent": "a",
                    "due": "2026-11-20",
                },
            ],
            "day": [{"date": "2026-11-23", "goals": [{"title": "T", "parent": "q"}]}],
            "p2": [{"title": "x", "added": "2026-11-01", "confirmed": False}],
        }
    )
    assert ws.history == (DayPlan(date(2026, 11, 23), (DailyGoal("T", "q"),)),)
    assert ws.goals[1].due == date(2026, 11, 20)
    assert ws.p2[0].confirmed is False
    report = check_workspace(ws, date(2026, 11, 24))
    assert report.warnings == ("goal 'Q' was due 2026-11-20; remove it or set a new due date",)
    assert report.coverage is not None and report.coverage.days_with_plans == 1
    assert check_workspace(ws, date(2026, 11, 20)).warnings == ()


@pytest.mark.parametrize(
    "data",
    [
        {"p2": [{"title": "x", "added": "2026-11-01", "confirmed": "false"}]},
        {"day": [{"goals": []}]},
        {"day": [{"date": "2026-11-23", "goals": [], "confirmed": "no"}]},
        {"today": {"goals": [], "confirmed": 0}},
        {"day": [{"date": "2026-11-23", "goals": []}, {"date": "2026-11-23", "goals": []}]},
        {"goal": [{"id": "a", "title": "A", "horizon": "annual", "due": datetime(2026, 12, 1, 9)}]},
        {"day": [{"date": datetime(2026, 11, 23, 8), "goals": []}]},
    ],
)
def test_workspace_rejects_bad_history_and_confirmed(data: dict[str, object]) -> None:
    with pytest.raises(WorkspaceError):
        workspace_from_dict(data)


def test_workspace_rejects_bad_window_settings_whatever_the_file_holds() -> None:
    ws = workspace_from_dict({"goal": [{"id": "a", "title": "A", "horizon": "annual"}]})
    with pytest.raises(ValueError, match="cannot be negative"):
        check_workspace(ws, date(2026, 11, 24), due_within_days=-1)
    with pytest.raises(ValueError, match="at least 1 day"):
        check_workspace(ws, date(2026, 11, 24), window_days=0)


def test_p2_item_needs_both_scores_or_neither() -> None:
    d = date(2026, 1, 1)
    with pytest.raises(ValueError, match="'half': give both importance and urgency, or neither"):
        P2Item("half", d, importance=5)
    with pytest.raises(ValueError, match="'high': importance must be an integer from 1 to 5"):
        P2Item("high", d, 7, 1)
    with pytest.raises(ValueError, match="'flag': importance must be"):
        P2Item("flag", d, True, 1)  # type: ignore[arg-type]
    assert P2Item("unscored", d).importance is None
    assert P2Item("scored", d, 2, 1).urgency == 1


@pytest.mark.parametrize(
    ("item", "message"),
    [
        ({"importance": 5}, "[[p2]] 'x': give both importance and urgency, or neither"),
        ({"importance": 7, "urgency": 1}, "[[p2]] 'x': importance must be an integer from 1 to 5"),
        ({"importance": 3, "urgency": "2"}, "[[p2]] 'x': urgency must be an integer from 1 to 5"),
        ({"importance": True, "urgency": 1}, "[[p2]] 'x': importance must be"),
    ],
)
def test_workspace_names_the_p2_item_with_bad_scores(item: dict[str, object], message: str) -> None:
    with pytest.raises(WorkspaceError, match=re.escape(message)):
        workspace_from_dict({"p2": [{"title": "x", "added": "2026-01-01", **item}]})


def test_p0_must_be_true_or_false() -> None:
    with pytest.raises(WorkspaceError, match=re.escape("[today] goal 'T' p0: expected true")):
        workspace_from_dict({"today": {"goals": [{"title": "T", "p0": "false"}]}})
    ws = workspace_from_dict({"today": {"goals": [{"title": "T", "p0": False}]}})
    assert ws.today is not None and ws.today[0].p0 is False


def test_outcomes_are_validated_and_counted() -> None:
    with pytest.raises(ValueError, match="daily goal 'T': done must be one of"):
        DailyGoal("T", "mentor", done="yes")  # type: ignore[arg-type]
    with pytest.raises(
        WorkspaceError, match=re.escape("[[day]] 2026-11-23: daily goal 'T': done must be")
    ):
        workspace_from_dict({"day": [{"date": "2026-11-23", "goals": [{"title": "T", "done": 1}]}]})

    def day(d: int, *outcomes: str | None, confirmed: bool = True) -> DayPlan:
        return DayPlan(
            date(2026, 11, d),
            tuple(DailyGoal(f"T{k}", "mentor", done=o) for k, o in enumerate(outcomes)),  # type: ignore[arg-type]
            confirmed,
        )

    days = [
        day(21, "done", "done", "missed"),
        day(22, "partial", None, None),
        day(23, "done", "done", "done", confirmed=False),  # a proposal: not counted
        day(24, "missed", None, None),  # the run date: only recorded outcomes count
        day(17, "done", "done", "done"),  # outside the 7-day window
    ]
    cov = slot_coverage(GOALS, days, date(2026, 11, 24))
    assert (cov.done, cov.partial, cov.missed, cov.not_recorded) == (2, 1, 2, 2)
    assert cov.to_dict()["outcomes"] == {"done": 2, "partial": 1, "missed": 2, "not_recorded": 2}
    ws = load_workspace(EXAMPLE)
    assert ws.history[1].goals[2].done == "partial"


def test_p2_item_added_after_the_run_date_warns() -> None:
    ws = workspace_from_dict(
        {
            "p2": [
                {"title": "typo", "added": "2027-03-01"},
                {"title": "added last evening, dated tomorrow", "added": "2026-11-26"},
            ]
        }
    )
    report = check_workspace(ws, date(2026, 11, 25))
    assert report.warnings == (
        "[[p2]] 'typo' added 2027-03-01 is after the run date 2026-11-25; check the date",
    )
    assert report.p2_review is not None and len(report.p2_review.keep) == 2


def test_p2_wait_longer_than_the_review_age_warns() -> None:
    def ws(n: int) -> Workspace:
        return workspace_from_dict(
            {"p2": [{"title": f"item {k}", "added": "2026-11-01"} for k in range(n)]}
        )

    run = date(2026, 11, 24)
    # 90 days is 2.96 months, and 3 departures a month clear 8.87 items in that time.
    assert check_workspace(ws(9), run, departures_per_month=3).warnings == (
        "P2 list: 9 items at 3 departures a month is a 3.0-month wait, longer than the 90-day "
        "review age; a list that clears in that time holds at most 8 items",
    )
    assert check_workspace(ws(8), run, departures_per_month=3).warnings == ()  # the named size
    one = check_workspace(ws(1), run, departures_per_month=0.1, max_age_days=30)
    assert one.warnings == (
        "P2 list: 1 item at 0.1 departures a month is a 10.0-month wait, longer than the 30-day "
        "review age; a list that clears in that time holds less than one item",
    )
    assert check_workspace(ws(30), run).warnings == ()  # no departures, no estimate
    with pytest.raises(ValueError, match="finite"):
        check_workspace(ws(3), run, departures_per_month=float("nan"))


def test_json_null_reads_as_absent_and_ids_may_be_numbers() -> None:
    ws = workspace_from_dict(
        {
            "goal": [
                {"id": 1, "title": "A", "horizon": "annual", "parent": None, "due": None},
                {"id": 2, "title": "Q", "horizon": "quarterly", "parent": 1},
            ],
            "today": {
                "date": None,
                "confirmed": None,
                "goals": [{"title": "T", "parent": 2, "p0": None, "displaces": None}],
            },
            "day": [{"date": "2026-11-23", "confirmed": None, "goals": None}],
            "p2": [{"title": "x", "added": "2026-11-01", "importance": None, "confirmed": None}],
        }
    )
    assert check_goal_tree(ws.goals) == []
    assert ws.today is not None and ws.today[0].parent == "2" and ws.today_date is None
    assert ws.today_confirmed is True and ws.history[0].confirmed is True
    assert ws.p2[0].importance is None and ws.p2[0].confirmed is True


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (
            {"today": {"goals": [{"title": "F", "p0": True, "displaces": 5}]}},
            "[today] goal 'F' displaces: expected text, got 5",
        ),
        ({"today": {"goals": [{"title": "T", "parent": ["q"]}]}}, "parent: expected an id"),
        ({"goal": [{"id": "q", "title": "Q", "horizon": "quarterly", "parent": True}]}, "an id"),
        ({"goal": [{"id": {"x": 1}, "title": "A", "horizon": "annual"}]}, "[[goal]] id"),
        ({"today": {"goals": [{"title": None}]}}, "needs a title; missing 'title'"),
        ({"today": {"goals": [{"title": 5}]}}, "a goal title in [today]: expected text, got 5"),
        ({"p2": [{"title": ["x"], "added": "2026-11-01"}]}, "[[p2]] title: expected text"),
    ],
)
def test_wrong_types_are_workspace_errors(data: dict[str, object], message: str) -> None:
    with pytest.raises(WorkspaceError, match=re.escape(message)):
        workspace_from_dict(data)


def test_json_file_matches_toml(tmp_path: Path) -> None:
    data = tomllib.loads(EXAMPLE.read_text(encoding="utf-8"))
    path = tmp_path / "priorities.json"
    path.write_text(json.dumps(data, default=str))  # dates become "2026-11-24" strings
    run = date(2026, 11, 24)
    as_json = check_workspace(load_workspace(path), run, departures_per_month=3).to_dict()
    as_toml = check_workspace(load_workspace(EXAMPLE), run, departures_per_month=3).to_dict()
    assert as_json == as_toml


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("{not json", "priorities.json: "),
        ("[1, 2]", "the top level must be an object"),
        ('{"goal": {"id": "a"}}', "[[goal]] must be a list of tables"),
        ('{"today": []}', "[today] must be a table"),
        ('{"day": [{"date": "2026-11-23", "goals": "T"}]}', "goals in [[day]] 2026-11-23 must"),
    ],
)
def test_malformed_json_is_a_workspace_error(tmp_path: Path, text: str, message: str) -> None:
    path = tmp_path / "priorities.json"
    path.write_text(text)
    with pytest.raises(WorkspaceError, match=re.escape(message)):
        load_workspace(path)
