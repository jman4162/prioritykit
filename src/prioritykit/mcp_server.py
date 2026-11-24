"""stdio MCP server for AI agents acting as a chief of staff.

Every tool is a pure function of its inputs (plus, for ``check_workspace``, one local file the
agent names). Nothing is stored. The human decides scores and commits the plan; the agent
proposes, and these tools apply the rules so the arithmetic is the same every time.

Set ``PRIORITYKIT_MATRIX`` to a JSON file to replace the default anchors and cells.
"""

from __future__ import annotations

import importlib
import os
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from . import plan as plan_mod
from .matrix import Matrix, check_matrix, classify, default_matrix, load_matrix
from .review import DEFAULT_MAX_AGE_DAYS, P2Item, littles_law_wait
from .review import review_p2 as review_p2_fn
from .workspace import load_workspace

INSTRUCTIONS = """prioritykit applies a prioritization system. You propose, and the human decides.

1. Scores: rate importance and urgency from 1 to 5 against the anchors from get_rubric, give a
   one-line reason for each score, and ask the human to confirm before you treat the level as
   settled. Importance takes precedence: urgency alone never lifts importance 1-2 work above P2.
2. P0 means interrupt. Never label work P0 on your own. A confirmed P0 replaces one of today's
   goals; call replan_for_p0 and have the human name the goal it displaces.
3. Each morning, propose exactly three goals for the day, each tied to a quarterly goal that
   ties to an annual goal. Call check_day_plan before you present them and fix any error.
4. Treat P2 as work that will probably not happen. Do not raise P2 items outside a review. At a
   review, call review_p2 and present the promote and delete candidates for the human to decide.
5. Score work you generate yourself (research leads, refactors, ideas) like any other task; if it
   advances no goal, the rules put it at P2 or drop.
6. Quote numbers from tool results. Do not invent counts, dates, or waits.
"""


class GoalIn(BaseModel):
    id: str
    title: str
    horizon: str = Field(description="'annual' or 'quarterly'")
    parent: str | None = Field(
        default=None, description="id of the annual parent, for quarterly goals"
    )


class DailyGoalIn(BaseModel):
    title: str
    parent: str | None = Field(default=None, description="id of the quarterly goal this advances")
    p0: bool = False
    displaces: str | None = Field(default=None, description="for a P0 entry: the goal it replaced")


class P2In(BaseModel):
    title: str
    added: str = Field(description="ISO date the item went on the list, e.g. 2026-11-24")
    importance: int | None = None
    urgency: int | None = None


def _matrix() -> Matrix:
    path = os.environ.get("PRIORITYKIT_MATRIX")
    return load_matrix(path) if path else default_matrix()


def _goals(goals: list[GoalIn]) -> list[plan_mod.Goal]:
    out = []
    for g in goals:
        if g.horizon not in ("annual", "quarterly"):
            raise ValueError(f"goal {g.id!r}: horizon must be 'annual' or 'quarterly'")
        out.append(plan_mod.Goal(g.id, g.title, g.horizon, g.parent))  # type: ignore[arg-type]
    return out


def _daily(today: list[DailyGoalIn]) -> list[plan_mod.DailyGoal]:
    return [plan_mod.DailyGoal(d.title, d.parent, d.p0, d.displaces) for d in today]


# Tool bodies are plain functions so tests and other programs can call them without a server.


def tool_get_rubric() -> dict[str, Any]:
    m = _matrix()
    report = check_matrix(m)
    return {
        **m.to_dict(),
        "counts": m.counts(),
        "matrix_warnings": list(report.warnings),
        "daily_goal_count": plan_mod.DEFAULT_COUNT,
        "p2_review_max_age_days": DEFAULT_MAX_AGE_DAYS,
    }


def tool_classify_task(importance: int, urgency: int, title: str | None = None) -> dict[str, Any]:
    result = classify(importance, urgency, _matrix()).to_dict()
    if title:
        result["title"] = title
    return result


def tool_check_day_plan(
    goals: list[GoalIn], today: list[DailyGoalIn], count: int = plan_mod.DEFAULT_COUNT
) -> dict[str, Any]:
    return plan_mod.check_day_plan(_daily(today), _goals(goals), count).to_dict()


def tool_replan_for_p0(
    goals: list[GoalIn], today: list[DailyGoalIn], p0_title: str, displaces: str
) -> dict[str, Any]:
    new = plan_mod.replan_for_p0(_daily(today), p0_title, displaces)
    report = plan_mod.check_day_plan(new, _goals(goals))
    return {
        "today": [
            {"title": d.title, "parent": d.parent, "p0": d.p0, "displaces": d.displaces}
            for d in new
        ],
        "check": report.to_dict(),
    }


def tool_review_p2(
    items: list[P2In],
    today: str,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    departures_per_month: float | None = None,
) -> dict[str, Any]:
    parsed = [P2Item(i.title, date.fromisoformat(i.added), i.importance, i.urgency) for i in items]
    rep = review_p2_fn(
        parsed, date.fromisoformat(today), max_age_days, departures_per_month, _matrix()
    )
    return rep.to_dict()


def tool_wait_estimate(backlog: int, departures_per_month: float) -> dict[str, Any]:
    months = littles_law_wait(backlog, departures_per_month)
    return {
        "backlog": backlog,
        "departures_per_month": departures_per_month,
        "expected_wait_months": months,
        "method": "Little's law, W = L / throughput, assuming steady state",
    }


def tool_check_workspace(path: str, today: str | None = None) -> dict[str, Any]:
    ws = load_workspace(path)
    on = date.fromisoformat(today) if today else (ws.today_date or date.today())
    out: dict[str, Any] = {"goal_tree_errors": plan_mod.check_goal_tree(ws.goals)}
    if ws.today is not None:
        out["today"] = plan_mod.check_day_plan(ws.today, ws.goals).to_dict()
    if ws.p2:
        out["p2_review"] = review_p2_fn(ws.p2, on, matrix=_matrix()).to_dict()
    return out


def _server_class() -> Any:
    """FastMCP in MCP SDK 1.x, MCPServer in 2.x; both take (name, instructions=...)."""
    for module, name in (("mcp.server.fastmcp", "FastMCP"), ("mcp.server", "MCPServer")):
        try:
            return getattr(importlib.import_module(module), name)
        except (ImportError, AttributeError):
            continue
    raise ImportError("the MCP server needs the mcp extra: pip install 'prioritykit[mcp]'")


def build_server() -> Any:
    server = _server_class()("prioritykit", instructions=INSTRUCTIONS)

    @server.tool()
    def get_rubric() -> dict[str, Any]:
        """The score anchors, level names and actions, the 5x5 grid, and the daily goal count."""
        return tool_get_rubric()

    @server.tool()
    def classify_task(importance: int, urgency: int, title: str | None = None) -> dict[str, Any]:
        """Map 1-5 importance and urgency scores to P0, P1, P2, or drop, with the action."""
        return tool_classify_task(importance, urgency, title)

    @server.tool()
    def check_day_plan(
        goals: list[GoalIn], today: list[DailyGoalIn], count: int = plan_mod.DEFAULT_COUNT
    ) -> dict[str, Any]:
        """Check that today holds exactly `count` goals, each traced to quarterly and annual."""
        return tool_check_day_plan(goals, today, count)

    @server.tool()
    def replan_for_p0(
        goals: list[GoalIn], today: list[DailyGoalIn], p0_title: str, displaces: str
    ) -> dict[str, Any]:
        """Replace the named goal in today's plan with a confirmed P0 item, and recheck the plan."""
        return tool_replan_for_p0(goals, today, p0_title, displaces)

    @server.tool()
    def review_p2(
        items: list[P2In],
        today: str,
        max_age_days: int = DEFAULT_MAX_AGE_DAYS,
        departures_per_month: float | None = None,
    ) -> dict[str, Any]:
        """Sort a P2 list into promote (rescored to P1 or P0), delete (old, still low), and keep."""
        return tool_review_p2(items, today, max_age_days, departures_per_month)

    @server.tool()
    def wait_estimate(backlog: int, departures_per_month: float) -> dict[str, Any]:
        """Expected months a new item waits on a list, by Little's law."""
        return tool_wait_estimate(backlog, departures_per_month)

    @server.tool()
    def check_workspace(path: str, today: str | None = None) -> dict[str, Any]:
        """Check a local priorities.toml file: goal tree, today's plan, and P2 review."""
        return tool_check_workspace(path, today)

    return server


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()
