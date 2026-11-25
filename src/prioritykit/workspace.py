"""Read and check a plain-text priorities file (TOML).

A person or an agent keeps goals, today's plan, and the P2 list in one TOML file under their own
version control, and the CLI or MCP server reads and checks it. See
``examples/priorities.toml`` for the format.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .matrix import Matrix
from .plan import (
    DEFAULT_COUNT,
    DEFAULT_WINDOW_DAYS,
    CoverageReport,
    DailyGoal,
    DayPlan,
    Goal,
    PlanReport,
    check_day_plan,
    check_goal_tree,
    slot_coverage,
)
from .review import DEFAULT_MAX_AGE_DAYS, P2Item, ReviewReport, review_p2


class WorkspaceError(ValueError):
    """The priorities file is malformed."""


@dataclass(frozen=True)
class Workspace:
    goals: tuple[Goal, ...]
    today: tuple[DailyGoal, ...] | None
    today_date: date | None
    p2: tuple[P2Item, ...]
    history: tuple[DayPlan, ...] = ()  # past day plans from [[day]] tables


def _date(value: Any, where: str) -> date:
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


def _daily_goals(entries: list[dict[str, Any]], where: str) -> tuple[DailyGoal, ...]:
    try:
        return tuple(
            DailyGoal(
                title=str(d["title"]),
                parent=d.get("parent"),
                p0=bool(d.get("p0", False)),
                displaces=d.get("displaces"),
            )
            for d in entries
        )
    except KeyError as exc:
        raise WorkspaceError(f"every goal in {where} needs a title; missing {exc}") from exc


def workspace_from_dict(data: dict[str, Any]) -> Workspace:
    try:
        goals = tuple(
            Goal(
                id=str(g["id"]),
                title=str(g["title"]),
                horizon=g["horizon"],
                parent=g.get("parent"),
                due=_date(g["due"], f"[[goal]] {g['id']!r} due") if "due" in g else None,
            )
            for g in data.get("goal", [])
        )
    except KeyError as exc:
        raise WorkspaceError(f"every [[goal]] needs id, title, and horizon; missing {exc}") from exc
    bad = [g.id for g in goals if g.horizon not in ("annual", "quarterly")]
    if bad:
        raise WorkspaceError(f"horizon must be 'annual' or 'quarterly' for goals {bad}")

    today = None
    today_date = None
    if "today" in data:
        t = data["today"]
        today_date = _date(t["date"], "[today] date") if "date" in t else None
        today = _daily_goals(t.get("goals", []), "[today]")

    history = []
    for d in data.get("day", []):
        if "date" not in d:
            raise WorkspaceError("every [[day]] needs a date")
        day = _date(d["date"], "[[day]] date")
        history.append(DayPlan(day, _daily_goals(d.get("goals", []), f"[[day]] {day}")))

    try:
        p2 = tuple(
            P2Item(
                title=str(i["title"]),
                added=_date(i["added"], f"[[p2]] {i.get('title')!r} added"),
                importance=i.get("importance"),
                urgency=i.get("urgency"),
                confirmed=_bool(i.get("confirmed", True), f"[[p2]] {i.get('title')!r} confirmed"),
            )
            for i in data.get("p2", [])
        )
    except KeyError as exc:
        raise WorkspaceError(f"every [[p2]] item needs title and added; missing {exc}") from exc
    return Workspace(goals, today, today_date, p2, tuple(history))


def load_workspace(path: str | Path) -> Workspace:
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
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
            out["today"] = self.today.to_dict()
        if self.p2_review is not None:
            out["p2_review"] = self.p2_review.to_dict()
        if self.coverage is not None:
            out["coverage"] = self.coverage.to_dict()
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
) -> WorkspaceReport:
    """Check the goal tree, today's plan, and the P2 list as of ``run_date``.

    P2 ages count from ``run_date``, never from the ``[today]`` date, so a file nobody updated
    still ages its list from the day the check runs. A ``[today]`` dated before ``run_date`` is
    a warning; a later date is fine, since a plan written the evening before carries tomorrow's
    date. A goal whose ``due`` date is before ``run_date`` is also a warning. When the file has
    ``[[day]]`` history, ``coverage`` lists goals with no slot in the ``window_days`` days ending
    on ``run_date``, counting the dated ``[today]`` plan as one of those days.
    """
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
    coverage = None
    if ws.history:
        plans = list(ws.history)
        if ws.today is not None and ws.today_date is not None:
            plans.append(DayPlan(ws.today_date, ws.today))
        coverage = slot_coverage(ws.goals, plans, run_date, window_days)
    return WorkspaceReport(
        run_date=run_date,
        goal_tree_errors=tuple(check_goal_tree(ws.goals)),
        annual_count=sum(g.horizon == "annual" for g in ws.goals),
        quarterly_count=sum(g.horizon == "quarterly" for g in ws.goals),
        today=check_day_plan(ws.today, ws.goals, count) if ws.today is not None else None,
        p2_review=(
            review_p2(ws.p2, run_date, max_age_days, departures_per_month, matrix)
            if ws.p2
            else None
        ),
        warnings=tuple(warnings),
        coverage=coverage,
    )
