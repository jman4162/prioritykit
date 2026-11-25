"""Goal trees and the daily-three rule.

Annual goals sit at the root, quarterly goals point at an annual parent, and each of the day's
goals points at a quarterly goal. A day plan holds exactly ``count`` goals (three by default).
A P0 entry may stand in for a goal without a parent, because P0 work can be harm prevention
that advances no goal, but it must name the goal it displaced. Past day plans, kept as a short
history, show which goals went without a slot over a window such as the last week. A day plan
an agent proposed and the person has not confirmed counts separately from a committed one.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Any, Literal

Horizon = Literal["annual", "quarterly"]
Slot = Literal["confirmed", "proposed", "none"]
DEFAULT_COUNT = 3
DEFAULT_WINDOW_DAYS = 7
DEFAULT_DUE_WITHIN_DAYS = 28


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
    confirmed: bool = True  # False: an agent proposed the plan and the person has not confirmed


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
    """Goals that got no slot in the day plans inside a window ending on the run date.

    The ``*_without_slot`` fields count every plan. The ``*_without_confirmed_slot`` fields count
    only plans the person confirmed, so each lists the same goals or more.
    """

    window_start: date
    window_end: date
    days_with_plans: int
    quarterly_without_slot: tuple[str, ...]
    annual_without_slot: tuple[str, ...]
    days_with_confirmed_plans: int
    quarterly_without_confirmed_slot: tuple[str, ...]
    annual_without_confirmed_slot: tuple[str, ...]

    @property
    def window_days(self) -> int:
        return (self.window_end - self.window_start).days + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "window_days": self.window_days,
            "days_with_plans": self.days_with_plans,
            "days_with_confirmed_plans": self.days_with_confirmed_plans,
            "quarterly_without_slot": list(self.quarterly_without_slot),
            "annual_without_slot": list(self.annual_without_slot),
            "quarterly_without_confirmed_slot": list(self.quarterly_without_confirmed_slot),
            "annual_without_confirmed_slot": list(self.annual_without_confirmed_slot),
        }


def _add_days(d: date, n: int) -> date:
    """``d`` plus ``n`` days, clamped to the dates Python can represent."""
    try:
        return d + timedelta(days=n)
    except OverflowError:
        return date.max if n > 0 else date.min


def _window(
    days: Iterable[DayPlan], run_date: date, window_days: int, *, include_later: bool = False
) -> tuple[date, list[DayPlan]]:
    """The window's first date and the plans inside it. Rejects two plans on one date.

    ``include_later`` also keeps plans dated after ``run_date``, such as a plan for tomorrow.
    """
    if window_days < 1:
        raise ValueError("window_days must be at least 1")
    days = list(days)
    seen: set[date] = set()
    for plan in days:
        if plan.day in seen:
            raise ValueError(f"two day plans share the date {plan.day.isoformat()}; keep one")
        seen.add(plan.day)
    start = _add_days(run_date, -(window_days - 1))
    return start, [p for p in days if start <= p.day and (include_later or p.day <= run_date)]


def _slotted(by_id: dict[str, Goal], plans: Iterable[DayPlan]) -> set[str]:
    """Ids of the goals the plans gave a slot: each daily goal's quarterly goal and its annual."""
    slotted: set[str] = set()
    for plan in plans:
        for d in plan.goals:
            q = by_id.get(d.parent) if d.parent else None
            if q is None or q.horizon != "quarterly":
                continue
            slotted.add(q.id)
            if q.parent:
                slotted.add(q.parent)
    return slotted


def slot_coverage(
    goals: Iterable[Goal],
    days: Iterable[DayPlan],
    run_date: date,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> CoverageReport:
    """List the goals no day plan gave a slot in the ``window_days`` days ending on ``run_date``.

    A daily goal fills a slot for its quarterly parent and that goal's annual parent. Plans
    outside the window are ignored, and two plans on one date raise ``ValueError``.
    ``days_with_plans`` counts the dates in the window that have a plan, so a caller with two
    days of history cannot claim "no slot all week". The confirmed-only fields leave out plans
    with ``confirmed=False``.
    """
    goals = list(goals)
    by_id = {g.id: g for g in goals}
    start, window = _window(days, run_date, window_days)
    confirmed = [p for p in window if p.confirmed]
    any_slot = _slotted(by_id, window)
    confirmed_slot = _slotted(by_id, confirmed)

    def without(horizon: Horizon, slotted: set[str]) -> tuple[str, ...]:
        return tuple(g.title for g in goals if g.horizon == horizon and g.id not in slotted)

    return CoverageReport(
        window_start=start,
        window_end=run_date,
        days_with_plans=len(window),
        quarterly_without_slot=without("quarterly", any_slot),
        annual_without_slot=without("annual", any_slot),
        days_with_confirmed_plans=len(confirmed),
        quarterly_without_confirmed_slot=without("quarterly", confirmed_slot),
        annual_without_confirmed_slot=without("annual", confirmed_slot),
    )


@dataclass(frozen=True)
class DueGoal:
    """A goal whose due date falls within the look-ahead, with its slot in recent plans.

    ``slot`` is "confirmed" (a confirmed plan gave it a slot), "proposed" (only unconfirmed plans
    did), "none", or None when no plan falls in the window, so there is nothing to judge by.
    """

    title: str
    horizon: Horizon
    due: date
    days_left: int
    slot: Slot | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "horizon": self.horizon,
            "due": self.due.isoformat(),
            "days_left": self.days_left,
            "slot": self.slot,
        }


def due_soon(
    goals: Iterable[Goal],
    run_date: date,
    within_days: int = DEFAULT_DUE_WITHIN_DAYS,
    days: Iterable[DayPlan] | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> tuple[DueGoal, ...]:
    """Goals due from ``run_date`` through ``within_days`` days later, soonest first.

    Overdue goals are left out; ``check_workspace`` warns about them instead. Each entry says
    whether a plan gave the goal a slot, counting plans from the ``window_days`` days ending on
    ``run_date`` and any plan dated later (a plan written the evening before), so a caller can
    find goals that are due soon and have not been planned. With no plan in that range, ``slot``
    is None rather than "none".
    """
    if within_days < 0:
        raise ValueError("within_days cannot be negative")
    goals = list(goals)
    by_id = {g.id: g for g in goals}
    any_slot: set[str] | None = None
    confirmed_slot: set[str] = set()
    if days is not None:
        _, window = _window(days, run_date, window_days, include_later=True)
        if window:
            any_slot = _slotted(by_id, window)
            confirmed_slot = _slotted(by_id, [p for p in window if p.confirmed])

    last = _add_days(run_date, within_days)
    out: list[DueGoal] = []
    for g in goals:
        if g.due is None or not run_date <= g.due <= last:
            continue
        slot: Slot | None = None
        if any_slot is not None:
            if g.id in confirmed_slot:
                slot = "confirmed"
            elif g.id in any_slot:
                slot = "proposed"
            else:
                slot = "none"
        out.append(DueGoal(g.title, g.horizon, g.due, (g.due - run_date).days, slot))
    return tuple(sorted(out, key=lambda d: (d.due, d.title)))


def replan_for_p0(daily: Sequence[DailyGoal], p0_title: str, displaces: str) -> list[DailyGoal]:
    """Replace one of today's goals with a P0 entry that records what it displaced."""
    titles = [d.title for d in daily]
    if displaces not in titles:
        raise ValueError(f"{displaces!r} is not one of today's goals: {titles}")
    p0 = DailyGoal(title=p0_title, p0=True, displaces=displaces)
    return [p0 if d.title == displaces else replace(d) for d in daily]
