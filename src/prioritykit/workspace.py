"""Read and check a plain-text priorities file (TOML, or JSON with the same layout).

A person or an agent keeps goals, today's plan, and the P2 list in one TOML file under their own
version control, and the CLI or MCP server reads and checks it. See
``examples/priorities.toml`` for the format. A file ending in ``.json`` is read as JSON, with
dates written as strings such as ``"2026-11-24"``.
"""

from __future__ import annotations

import json
import math
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, TypeVar

from .matrix import Matrix
from .plan import (
    DEFAULT_COUNT,
    DEFAULT_DUE_WITHIN_DAYS,
    DEFAULT_WINDOW_DAYS,
    CoverageReport,
    DailyGoal,
    DayPlan,
    DueGoal,
    Goal,
    PlanReport,
    check_day_plan,
    check_goal_tree,
    due_soon,
    slot_coverage,
)
from .review import DEFAULT_MAX_AGE_DAYS, P2Item, ReviewReport, review_p2

T = TypeVar("T")


class WorkspaceError(ValueError):
    """The priorities file is malformed."""


@dataclass(frozen=True)
class Workspace:
    goals: tuple[Goal, ...]
    today: tuple[DailyGoal, ...] | None
    today_date: date | None
    p2: tuple[P2Item, ...]
    history: tuple[DayPlan, ...] = ()  # past day plans from [[day]] tables
    today_confirmed: bool = True  # False: [today] is an agent's proposal, not yet confirmed


def _date(value: Any, where: str) -> date:
    if isinstance(value, datetime):  # a datetime is also a date, but cannot be compared to one
        raise WorkspaceError(f"{where}: expected a date like 2026-11-24, not a date and time")
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise WorkspaceError(f"{where}: expected a date like 2026-11-24, got {value!r}") from exc


def _bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise WorkspaceError(f"{where}: expected true or false, got {value!r}")
    return value


# JSON writers spell a missing optional field as null, so None reads the same as an absent key.


def _flag(d: dict[str, Any], key: str, default: bool, where: str) -> bool:
    value = d.get(key)
    return default if value is None else _bool(value, where)


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str):
        raise WorkspaceError(f"{where}: expected text, got {value!r}")
    return value


def _ident(value: Any, where: str) -> str:
    """A goal id or a reference to one. Whole numbers read as text, so ``parent = 1`` finds id 1."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise WorkspaceError(f'{where}: expected an id such as "mentor", got {value!r}')
    return str(value)


def _optional(value: Any, parse: Callable[[Any, str], T], where: str) -> T | None:
    return None if value is None else parse(value, where)


def _records(value: Any, where: str) -> list[dict[str, Any]]:
    """A list of tables; anything else is a malformed file, not a crash."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise WorkspaceError(f"{where} must be a list of tables")
    return value


def _require(d: dict[str, Any], keys: tuple[str, ...], message: str) -> None:
    for key in keys:
        if d.get(key) is None:
            raise WorkspaceError(f"{message}; missing {key!r}")


def _goal(g: dict[str, Any]) -> Goal:
    _require(g, ("id", "title", "horizon"), "every [[goal]] needs id, title, and horizon")
    gid = _ident(g["id"], "[[goal]] id")
    where = f"[[goal]] {gid!r}"
    return Goal(
        id=gid,
        title=_text(g["title"], f"{where} title"),
        horizon=g["horizon"],
        parent=_optional(g.get("parent"), _ident, f"{where} parent"),
        due=_optional(g.get("due"), _date, f"{where} due"),
    )


def _daily_goals(entries: Any, where: str) -> tuple[DailyGoal, ...]:
    out: list[DailyGoal] = []
    for d in _records(entries, f"goals in {where}"):
        _require(d, ("title",), f"every goal in {where} needs a title")
        title = _text(d["title"], f"a goal title in {where}")
        at = f"{where} goal {title!r}"
        try:
            out.append(
                DailyGoal(
                    title=title,
                    parent=_optional(d.get("parent"), _ident, f"{at} parent"),
                    p0=_flag(d, "p0", False, f"{at} p0"),
                    displaces=_optional(d.get("displaces"), _text, f"{at} displaces"),
                    done=d.get("done"),
                )
            )
        except WorkspaceError:
            raise
        except ValueError as exc:
            raise WorkspaceError(f"{where}: {exc}") from None
    return tuple(out)


def _p2_item(i: dict[str, Any]) -> P2Item:
    _require(i, ("title", "added"), "every [[p2]] item needs title and added")
    title = _text(i["title"], "[[p2]] title")
    added = _date(i["added"], f"[[p2]] {title!r} added")
    confirmed = _flag(i, "confirmed", True, f"[[p2]] {title!r} confirmed")
    try:
        return P2Item(title, added, i.get("importance"), i.get("urgency"), confirmed)
    except ValueError as exc:
        raise WorkspaceError(f"[[p2]] {exc}") from None


def workspace_from_dict(data: dict[str, Any]) -> Workspace:
    goals = tuple(_goal(g) for g in _records(data.get("goal"), "[[goal]]"))
    bad = [g.id for g in goals if g.horizon not in ("annual", "quarterly")]
    if bad:
        raise WorkspaceError(f"horizon must be 'annual' or 'quarterly' for goals {bad}")

    today = None
    today_date = None
    today_confirmed = True
    if data.get("today") is not None:
        t = data["today"]
        if not isinstance(t, dict):
            raise WorkspaceError("[today] must be a table")
        today_date = _optional(t.get("date"), _date, "[today] date")
        today = _daily_goals(t.get("goals"), "[today]")
        today_confirmed = _flag(t, "confirmed", True, "[today] confirmed")

    history: list[DayPlan] = []
    for d in _records(data.get("day"), "[[day]]"):
        if d.get("date") is None:
            raise WorkspaceError("every [[day]] needs a date")
        day = _date(d["date"], "[[day]] date")
        if any(p.day == day for p in history):
            raise WorkspaceError(f"[[day]] {day} appears more than once; keep one plan per date")
        history.append(
            DayPlan(
                day,
                _daily_goals(d.get("goals"), f"[[day]] {day}"),
                _flag(d, "confirmed", True, f"[[day]] {day} confirmed"),
            )
        )

    p2 = tuple(_p2_item(i) for i in _records(data.get("p2"), "[[p2]]"))
    return Workspace(goals, today, today_date, p2, tuple(history), today_confirmed)


def load_workspace(path: str | Path) -> Workspace:
    """Read a priorities file: JSON when the name ends in ``.json``, TOML otherwise."""
    text = Path(path).read_text(encoding="utf-8")
    if Path(path).suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise WorkspaceError(f"{path}: {exc}") from exc
        if not isinstance(data, dict):
            raise WorkspaceError(f"{path}: the top level must be an object")
    else:
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise WorkspaceError(f"{path}: {exc}") from exc
    return workspace_from_dict(data)


@dataclass(frozen=True)
class WorkspaceReport:
    """Errors break a rule and clear ``ok``. Warnings flag a file that may be out of date."""

    run_date: date
    goal_tree_errors: tuple[str, ...]
    annual_count: int
    quarterly_count: int
    today: PlanReport | None
    p2_review: ReviewReport | None
    warnings: tuple[str, ...]
    coverage: CoverageReport | None = None
    due_soon: tuple[DueGoal, ...] | None = None  # None when no goal has a due date
    today_confirmed: bool = True  # False: [today] is an agent's proposal, not yet confirmed

    @property
    def ok(self) -> bool:
        return not self.goal_tree_errors and (self.today is None or self.today.ok)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "run_date": self.run_date.isoformat(),
            "goal_tree_errors": list(self.goal_tree_errors),
            "goal_counts": {"annual": self.annual_count, "quarterly": self.quarterly_count},
        }
        if self.today is not None:
            out["today"] = {**self.today.to_dict(), "confirmed": self.today_confirmed}
        if self.p2_review is not None:
            out["p2_review"] = self.p2_review.to_dict()
        if self.coverage is not None:
            out["coverage"] = self.coverage.to_dict()
        if self.due_soon is not None:
            out["due_soon"] = [d.to_dict() for d in self.due_soon]
        out["warnings"] = list(self.warnings)
        out["ok"] = self.ok
        return out


def check_workspace(
    ws: Workspace,
    run_date: date,
    *,
    count: int = DEFAULT_COUNT,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    departures_per_month: float | None = None,
    matrix: Matrix | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    due_within_days: int = DEFAULT_DUE_WITHIN_DAYS,
) -> WorkspaceReport:
    """Check the goal tree, today's plan, and the P2 list as of ``run_date``.

    P2 ages count from ``run_date``, never from the ``[today]`` date, so a file nobody updated
    still ages its list from the day the check runs. A ``[today]`` dated before ``run_date`` is
    a warning; a later date is fine, since a plan written the evening before carries tomorrow's
    date. A goal whose ``due`` date is before ``run_date`` is also a warning. When the file has
    ``[[day]]`` history, ``coverage`` lists goals with no slot in the ``window_days`` days ending
    on ``run_date``, counting the dated ``[today]`` plan as one of those days; a ``[[day]]`` with
    the same date as ``[today]`` is left out, with a warning. When any goal has a ``due`` date,
    ``due_soon`` lists the goals due within ``due_within_days`` days and their slot in the window.
    A P2 item added more than a day after ``run_date`` is a warning. With
    ``departures_per_month``, a P2 list whose
    Little's-law wait is longer than ``max_age_days`` is a warning that names the size that fits.
    """
    if window_days < 1:
        raise ValueError(f"the window must be at least 1 day, got {window_days}")
    if due_within_days < 0:
        raise ValueError(f"the due-within look-ahead cannot be negative, got {due_within_days}")
    warnings: list[str] = []
    if ws.today is not None and ws.today_date is not None and ws.today_date < run_date:
        days = (run_date - ws.today_date).days
        warnings.append(
            f"[today] date {ws.today_date.isoformat()} is {days} day{'s' if days != 1 else ''} "
            f"before the run date {run_date.isoformat()}; the plan may be stale"
        )
    warnings += [
        f"goal {g.title!r} was due {g.due.isoformat()}; remove it or set a new due date"
        for g in ws.goals
        if g.due is not None and g.due < run_date
    ]
    # One day of slack, as for [today]: an item added in the evening may carry tomorrow's date.
    warnings += [
        f"[[p2]] {i.title!r} added {i.added.isoformat()} is after the run date "
        f"{run_date.isoformat()}; check the date"
        for i in ws.p2
        if (i.added - run_date).days > 1
    ]
    coverage = None
    plans: list[DayPlan] | None = None
    if ws.history:
        plans = list(ws.history)
        if ws.today is not None and ws.today_date is not None:
            if any(p.day == ws.today_date for p in plans):
                warnings.append(
                    f"[[day]] {ws.today_date.isoformat()} has the same date as [today]; "
                    "coverage uses [today]"
                )
                plans = [p for p in plans if p.day != ws.today_date]
            plans.append(DayPlan(ws.today_date, ws.today, ws.today_confirmed))
        coverage = slot_coverage(ws.goals, plans, run_date, window_days)
    due = None
    if any(g.due is not None for g in ws.goals):
        due = due_soon(ws.goals, run_date, due_within_days, plans, window_days)
    p2_review = (
        review_p2(ws.p2, run_date, max_age_days, departures_per_month, matrix) if ws.p2 else None
    )
    if p2_review is not None and departures_per_month is not None:
        warnings += _wait_warning(
            len(ws.p2), departures_per_month, p2_review.expected_wait_months, max_age_days
        )
    return WorkspaceReport(
        run_date=run_date,
        goal_tree_errors=tuple(check_goal_tree(ws.goals)),
        annual_count=sum(g.horizon == "annual" for g in ws.goals),
        quarterly_count=sum(g.horizon == "quarterly" for g in ws.goals),
        today=check_day_plan(ws.today, ws.goals, count) if ws.today is not None else None,
        p2_review=p2_review,
        warnings=tuple(warnings),
        coverage=coverage,
        due_soon=due,
        today_confirmed=ws.today_confirmed,
    )


DAYS_PER_MONTH = 365.25 / 12


def _wait_warning(
    size: int, departures_per_month: float, wait_months: float | None, max_age_days: int
) -> list[str]:
    """Warn when items wait longer than the review age, so most are deleted before they are done.

    By Little's law a list that clears within ``max_age_days`` holds about departures times that
    span, rounded down, which is the size the warning names.
    """
    if wait_months is None or wait_months <= max_age_days / DAYS_PER_MONTH:
        return []
    # Round down: a list cut to this size clears within the review age, so the warning stops.
    fits = math.floor(departures_per_month * max_age_days / DAYS_PER_MONTH)
    holds = f"at most {fits} item{'' if fits == 1 else 's'}" if fits >= 1 else "less than one item"
    items = f"{size} item{'' if size == 1 else 's'}"
    rate = f"{departures_per_month:g} departure{'' if departures_per_month == 1 else 's'}"
    return [
        f"P2 list: {items} at {rate} a month is a {wait_months:.1f}-month wait, longer than the "
        f"{max_age_days}-day review age; a list that clears in that time holds {holds}"
    ]
