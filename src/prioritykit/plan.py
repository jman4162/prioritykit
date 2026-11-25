"""Goal trees and the daily-three rule.

Annual goals sit at the root, quarterly goals point at an annual parent, and each of the day's
goals points at a quarterly goal. A day plan holds exactly ``count`` goals (three by default).
A P0 entry may stand in for a goal without a parent, because P0 work can be harm prevention
that advances no goal, but it must name the goal it displaced. Past day plans, kept as a short
history, show which goals went without a slot over a window such as the last week.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Any, Literal

Horizon = Literal["annual", "quarterly"]
DEFAULT_COUNT = 3
DEFAULT_WINDOW_DAYS = 7


@dataclass(frozen=True)
class Goal:
    id: str
    title: str
    horizon: Horizon
    parent: str | None = None
    due: date | None = None


@dataclass(frozen=True)
class DailyGoal:
    title: str
    parent: str | None = None  # id of a quarterly goal
    p0: bool = False
    displaces: str | None = None  # for a P0 entry: the title of the goal it replaced


@dataclass(frozen=True)
class DayPlan:
    """One day's goals, kept so later checks can see which goals got a slot."""

    day: date
    goals: tuple[DailyGoal, ...]


@dataclass(frozen=True)
class PlanReport:
    ok: bool
    errors: tuple[str, ...]
    traces: tuple[tuple[str, ...], ...]  # daily title -> quarterly title -> annual title
    annual_without_slot: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "traces": [list(t) for t in self.traces],
            "annual_without_slot": list(self.annual_without_slot),
        }


def check_goal_tree(goals: Iterable[Goal]) -> list[str]:
    """Structural errors in a goal tree; an empty list means the tree is valid."""
    goals = list(goals)
    errors: list[str] = []
    by_id: dict[str, Goal] = {}
    for g in goals:
        if g.id in by_id:
            errors.append(f"duplicate goal id {g.id!r}")
        by_id[g.id] = g
    for g in goals:
        if g.horizon == "annual" and g.parent is not None:
            errors.append(f"annual goal {g.id!r} should have no parent")
        if g.horizon == "quarterly":
            if g.parent is None:
                errors.append(f"quarterly goal {g.id!r} needs an annual parent")
            elif g.parent not in by_id:
                errors.append(f"quarterly goal {g.id!r} points at unknown parent {g.parent!r}")
            elif by_id[g.parent].horizon != "annual":
                errors.append(f"quarterly goal {g.id!r} must point at an annual goal")
    return errors


def check_day_plan(
    daily: Sequence[DailyGoal], goals: Iterable[Goal], count: int = DEFAULT_COUNT
) -> PlanReport:
    """Check a day plan against the goal tree and the fixed count."""
    goals = list(goals)
    by_id = {g.id: g for g in goals}
    errors = check_goal_tree(goals)
    if len(daily) != count:
        errors.append(f"a day plan holds exactly {count} goals; this one has {len(daily)}")
    titles = [d.title.strip() for d in daily]
    if any(not t for t in titles):
        errors.append("every daily goal needs a title")
    if len(set(titles)) != len(titles):
        errors.append("daily goals must be distinct")

    traces: list[tuple[str, ...]] = []
    used_annual: set[str] = set()
    for d in daily:
        if d.p0:
            if not (d.displaces and d.displaces.strip()):
                errors.append(f"P0 entry {d.title!r} must name the goal it displaces")
            trace: tuple[str, ...] = (d.title, "P0 interrupt")
            if d.parent and d.parent in by_id:
                trace = (d.title, by_id[d.parent].title)
            traces.append(trace)
            continue
        if d.parent is None:
            errors.append(f"daily goal {d.title!r} must trace to a quarterly goal")
            traces.append((d.title,))
            continue
        q = by_id.get(d.parent)
        if q is None:
            errors.append(f"daily goal {d.title!r} points at unknown goal {d.parent!r}")
            traces.append((d.title,))
            continue
        if q.horizon != "quarterly":
            errors.append(f"daily goal {d.title!r} must point at a quarterly goal, not {q.id!r}")
            traces.append((d.title, q.title))
            continue
        a = by_id.get(q.parent) if q.parent else None
        traces.append((d.title, q.title, a.title) if a else (d.title, q.title))
        if a:
            used_annual.add(a.id)

    unslotted = tuple(g.title for g in goals if g.horizon == "annual" and g.id not in used_annual)
    return PlanReport(not errors, tuple(errors), tuple(traces), unslotted)


@dataclass(frozen=True)
class CoverageReport:
    """Goals that got no slot in any day plan inside a window ending on the run date."""

    window_start: date
    window_end: date
    days_with_plans: int
    quarterly_without_slot: tuple[str, ...]
    annual_without_slot: tuple[str, ...]

    @property
    def window_days(self) -> int:
        return (self.window_end - self.window_start).days + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "window_days": self.window_days,
            "days_with_plans": self.days_with_plans,
            "quarterly_without_slot": list(self.quarterly_without_slot),
            "annual_without_slot": list(self.annual_without_slot),
        }


def slot_coverage(
    goals: Iterable[Goal],
    days: Iterable[DayPlan],
    run_date: date,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> CoverageReport:
    """List the goals no day plan gave a slot in the ``window_days`` days ending on ``run_date``.

    A daily goal fills a slot for its quarterly parent and that goal's annual parent. Plans
    outside the window are ignored. ``days_with_plans`` counts the distinct dates in the window
    that have a plan, so a caller with two days of history cannot claim "no slot all week".
    """
    if window_days < 1:
        raise ValueError("window_days must be at least 1")
    goals = list(goals)
    by_id = {g.id: g for g in goals}
    start = run_date - timedelta(days=window_days - 1)
    dates: set[date] = set()
    slotted: set[str] = set()
    for plan in days:
        if not start <= plan.day <= run_date:
            continue
        dates.add(plan.day)
        for d in plan.goals:
            q = by_id.get(d.parent) if d.parent else None
            if q is None or q.horizon != "quarterly":
                continue
            slotted.add(q.id)
            if q.parent:
                slotted.add(q.parent)
    return CoverageReport(
        window_start=start,
        window_end=run_date,
        days_with_plans=len(dates),
        quarterly_without_slot=tuple(
            g.title for g in goals if g.horizon == "quarterly" and g.id not in slotted
        ),
        annual_without_slot=tuple(
            g.title for g in goals if g.horizon == "annual" and g.id not in slotted
        ),
    )


def replan_for_p0(daily: Sequence[DailyGoal], p0_title: str, displaces: str) -> list[DailyGoal]:
    """Replace one of today's goals with a P0 entry that records what it displaced."""
    titles = [d.title for d in daily]
    if displaces not in titles:
        raise ValueError(f"{displaces!r} is not one of today's goals: {titles}")
    p0 = DailyGoal(title=p0_title, p0=True, displaces=displaces)
    return [p0 if d.title == displaces else replace(d) for d in daily]
