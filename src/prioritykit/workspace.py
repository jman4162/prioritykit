"""Read a plain-text priorities file (TOML).

prioritykit stores nothing. A person or an agent keeps goals, today's plan, and the P2 list in
one TOML file under their own version control, and the CLI or MCP server checks it. See
``examples/priorities.toml`` for the format.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .plan import DailyGoal, Goal
from .review import P2Item


class WorkspaceError(ValueError):
    """The priorities file is malformed."""


@dataclass(frozen=True)
class Workspace:
    goals: tuple[Goal, ...]
    today: tuple[DailyGoal, ...] | None
    today_date: date | None
    p2: tuple[P2Item, ...]


def _date(value: Any, where: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise WorkspaceError(f"{where}: expected a date like 2026-11-24, got {value!r}") from exc


def workspace_from_dict(data: dict[str, Any]) -> Workspace:
    try:
        goals = tuple(
            Goal(
                id=str(g["id"]),
                title=str(g["title"]),
                horizon=g["horizon"],
                parent=g.get("parent"),
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
        try:
            today = tuple(
                DailyGoal(
                    title=str(d["title"]),
                    parent=d.get("parent"),
                    p0=bool(d.get("p0", False)),
                    displaces=d.get("displaces"),
                )
                for d in t.get("goals", [])
            )
        except KeyError as exc:
            raise WorkspaceError(f"every goal in [today] needs a title; missing {exc}") from exc

    try:
        p2 = tuple(
            P2Item(
                title=str(i["title"]),
                added=_date(i["added"], f"[[p2]] {i.get('title')!r} added"),
                importance=i.get("importance"),
                urgency=i.get("urgency"),
            )
            for i in data.get("p2", [])
        )
    except KeyError as exc:
        raise WorkspaceError(f"every [[p2]] item needs title and added; missing {exc}") from exc
    return Workspace(goals, today, today_date, p2)


def load_workspace(path: str | Path) -> Workspace:
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise WorkspaceError(f"{path}: {exc}") from exc
    return workspace_from_dict(data)
