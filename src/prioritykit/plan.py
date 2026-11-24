"""Goal trees and the daily-three rule.

Annual goals sit at the root, quarterly goals point at an annual parent, and each of the day's
goals points at a quarterly goal. A day plan holds exactly ``count`` goals (three by default).
A P0 entry may stand in for a goal without a parent, because P0 work can be harm prevention
that advances no goal, but it must name the goal it displaced.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

Horizon = Literal["annual", "quarterly"]
DEFAULT_COUNT = 3


@dataclass(frozen=True)
class Goal:
    id: str
    title: str
    horizon: Horizon
    parent: str | None = None


@dataclass(frozen=True)
class DailyGoal:
    title: str
    parent: str | None = None  # id of a quarterly goal
    p0: bool = False
    displaces: str | None = None  # for a P0 entry: the title of the goal it replaced


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


def replan_for_p0(daily: Sequence[DailyGoal], p0_title: str, displaces: str) -> list[DailyGoal]:
    """Replace one of today's goals with a P0 entry that records what it displaced."""
    titles = [d.title for d in daily]
    if displaces not in titles:
        raise ValueError(f"{displaces!r} is not one of today's goals: {titles}")
    p0 = DailyGoal(title=p0_title, p0=True, displaces=displaces)
    return [p0 if d.title == displaces else replace(d) for d in daily]
