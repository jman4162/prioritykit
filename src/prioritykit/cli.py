"""Command line interface. Standard library only."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from typing import Any

from . import __version__
from .matrix import (
    LEVELS,
    Matrix,
    MatrixError,
    check_matrix,
    classify,
    default_matrix,
    load_matrix,
)
from .plan import DEFAULT_COUNT, check_day_plan, check_goal_tree
from .review import DEFAULT_MAX_AGE_DAYS, review_p2
from .workspace import WorkspaceError, load_workspace


def _matrix(args: argparse.Namespace) -> Matrix:
    return load_matrix(args.matrix) if args.matrix else default_matrix()


def _print(obj: Any, as_json: bool, text: str) -> None:
    print(json.dumps(obj, indent=2) if as_json else text)


def cmd_classify(args: argparse.Namespace) -> int:
    c = classify(args.importance, args.urgency, _matrix(args))
    _print(c.to_dict(), args.json, c.describe())
    return 0


def cmd_matrix(args: argparse.Namespace) -> int:
    m = _matrix(args)
    lines = ["importance \\ urgency    1     2     3     4     5"]
    for i in range(5, 0, -1):
        lines.append(f"{i:>21}  " + " ".join(f"{m.level(i, u):>5}" for u in range(1, 6)))
    counts = m.counts()
    lines.append("cells: " + ", ".join(f"{counts[k]} {k}" for k in LEVELS))
    _print(m.to_dict(), args.json, "\n".join(lines))
    return 0


def cmd_anchors(args: argparse.Namespace) -> int:
    m = _matrix(args)
    lines = ["Importance (what it does for your goals):"]
    lines += [f"  {a.score}  {a.label}" for a in reversed(m.importance)]
    lines.append("Urgency (how fast waiting gets costly):")
    lines += [f"  {a.score}  {a.label}" for a in reversed(m.urgency)]
    lines.append("Levels:")
    lines += [f"  {k:<4}  {v.name}: {v.action}" for k, v in m.levels.items()]
    _print(m.to_dict(), args.json, "\n".join(lines))
    return 0


def cmd_validate_matrix(args: argparse.Namespace) -> int:
    report = check_matrix(load_matrix(args.file))
    out = {"ok": report.ok, "errors": list(report.errors), "warnings": list(report.warnings)}
    text = "\n".join(
        [f"error: {e}" for e in report.errors]
        + [f"warning: {w}" for w in report.warnings]
        + ["ok" if report.ok else "invalid"]
    )
    _print(out, args.json, text)
    return 0 if report.ok else 1


def cmd_check(args: argparse.Namespace) -> int:
    ws = load_workspace(args.file)
    today = date.fromisoformat(args.today) if args.today else (ws.today_date or date.today())
    out: dict[str, Any] = {"goal_tree_errors": check_goal_tree(ws.goals)}
    lines = [f"error: {e}" for e in out["goal_tree_errors"]]
    ok = not out["goal_tree_errors"]

    if ws.today is not None:
        plan = check_day_plan(ws.today, ws.goals, args.count)
        out["today"] = plan.to_dict()
        ok = ok and plan.ok
        lines.append(f"today ({len(ws.today)} goals): {'ok' if plan.ok else 'invalid'}")
        lines += [f"  error: {e}" for e in plan.errors if e not in out["goal_tree_errors"]]
        lines += ["  " + " <- ".join(t) for t in plan.traces]
        if plan.annual_without_slot:
            lines.append(
                "  annual goals with no slot today: " + "; ".join(plan.annual_without_slot)
            )

    if ws.p2:
        rep = review_p2(ws.p2, today, args.max_age, args.departures, _matrix(args))
        out["p2_review"] = rep.to_dict()
        lines.append(f"P2 list: {len(ws.p2)} items")
        lines += [f"  promote: {i.title} ({c.level})" for i, c in rep.promote]
        lines += [f"  delete (older than {args.max_age} days): {i.title}" for i in rep.delete]
        lines += [f"  keep: {i.title}" for i in rep.keep]
        if rep.expected_wait_months is not None:
            lines.append(f"  expected wait for a new item: {rep.expected_wait_months:.1f} months")

    out["ok"] = ok
    _print(out, args.json, "\n".join(lines))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="prioritykit",
        description="Importance-urgency scoring, P0/P1/P2 levels, and three daily goals.",
    )
    p.add_argument("--version", action="version", version=f"prioritykit {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--matrix", help="JSON file with your own anchors and cells")
        sp.add_argument("--json", action="store_true", help="print JSON")

    c = sub.add_parser("classify", help="map importance and urgency scores to a level")
    c.add_argument("-i", "--importance", type=int, required=True, choices=range(1, 6))
    c.add_argument("-u", "--urgency", type=int, required=True, choices=range(1, 6))
    common(c)
    c.set_defaults(func=cmd_classify)

    m = sub.add_parser("matrix", help="print the 5x5 grid")
    common(m)
    m.set_defaults(func=cmd_matrix)

    a = sub.add_parser("anchors", help="print the score anchors and level actions")
    common(a)
    a.set_defaults(func=cmd_anchors)

    v = sub.add_parser("validate-matrix", help="check a custom matrix file")
    v.add_argument("file")
    v.add_argument("--json", action="store_true")
    v.set_defaults(func=cmd_validate_matrix)

    k = sub.add_parser("check", help="check a priorities.toml file")
    k.add_argument("file")
    k.add_argument("--today", help="date for the P2 review (default: [today] date or today)")
    k.add_argument("--count", type=int, default=DEFAULT_COUNT, help="daily goal count (default 3)")
    k.add_argument(
        "--max-age",
        type=int,
        default=DEFAULT_MAX_AGE_DAYS,
        help="days before a P2 item is a deletion candidate",
    )
    k.add_argument(
        "--departures", type=float, help="items leaving the P2 list per month, for a wait estimate"
    )
    common(k)
    k.set_defaults(func=cmd_check)

    s = sub.add_parser("mcp", help="run the stdio MCP server (needs the mcp extra)")
    s.set_defaults(func=lambda _args: _run_mcp())
    return p


def _run_mcp() -> int:
    from .mcp_server import main as mcp_main

    mcp_main()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (MatrixError, WorkspaceError, ValueError, OSError) as exc:
        print(f"prioritykit: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
