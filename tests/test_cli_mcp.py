import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from prioritykit import __version__, cli
from prioritykit import mcp_server as srv

EXAMPLE = str(Path(__file__).resolve().parents[1] / "examples" / "priorities.toml")
GOALS_TOML = (
    '[[goal]]\nid = "a"\ntitle = "A"\nhorizon = "annual"\n'
    '[[goal]]\nid = "q"\ntitle = "Q"\nhorizon = "quarterly"\nparent = "a"\n'
)


def plan_toml(day: str) -> str:
    entries = "".join(f'  {{ title = "T{k}", parent = "q" }},\n' for k in range(3))
    return f"[today]\ndate = {day}\ngoals = [\n{entries}]\n"


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = cli.main(list(argv))
    return code, capsys.readouterr().out


def test_cli_classify_text_and_json(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "classify", "-i", "5", "-u", "5")
    assert code == 0 and out.startswith("Importance 5, urgency 5: P0 (interrupt).")
    code, out = run(capsys, "classify", "-i", "2", "-u", "5", "--json")
    assert json.loads(out)["level"] == "P2" and json.loads(out)["requires_confirmation"] is False


def test_cli_and_mcp_classify_return_the_same_shape(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "classify", "-i", "4", "-u", "5", "--json")
    cli_result = json.loads(out)
    assert code == 0 and cli_result["requires_confirmation"] is True
    assert cli_result == srv.tool_classify_task(4, 5)


def test_cli_matrix_and_anchors(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "matrix")
    assert code == 0 and "cells: 2 P0, 10 P1, 7 P2, 6 drop" in out
    code, out = run(capsys, "anchors")
    assert code == 0 and "Waiting a quarter costs nothing" in out


def test_cli_check_example(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "check", EXAMPLE, "--today", "2026-11-24", "--departures", "3")
    assert code == 0, out
    assert out.startswith("goal tree: ok (4 annual, 4 quarterly)\n")
    assert "today (3 goals): ok" in out
    assert "warning" not in out
    assert "plans on 3 days (1 proposed)" in out
    assert "  quarterly goals slotted only in proposed plans: One post a month" in out
    assert (
        "  Mentor a junior scientist (due 2026-12-18, 24 days left; slotted in a confirmed plan)"
        in out
    )
    assert "promote: Renew the passport before the spring trip (P1, proposed)" in out
    assert "expected wait for a new item: 1.0 months" in out


def test_cli_check_confirm_list_due_within_and_duplicate_days(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "p.toml"
    path.write_text(
        GOALS_TOML.replace('parent = "a"\n', 'parent = "a"\ndue = 2027-01-03\n')
        + '[[day]]\ndate = 2026-11-23\nconfirmed = false\ngoals = [{ title = "T", parent = "q" }]\n'
        + '[[p2]]\ntitle = "Guess"\nadded = 2026-01-01\nimportance = 2\nurgency = 1\n'
        + "confirmed = false\n"
    )
    code, out = run(capsys, "check", str(path), "--today", "2026-11-24")
    assert code == 0, out
    assert "  confirm or delete (older than 90 days, not confirmed): Guess" in out
    assert "\n  delete (older" not in out
    assert "due within" not in out  # 40 days away
    code, out = run(capsys, "check", str(path), "--today", "2026-11-24", "--due-within", "45")
    assert "  Q (due 2027-01-03, 40 days left; slotted only in proposed plans" in out
    code, out = run(capsys, "check", str(path), "--today", "2026-11-24", "--json")
    data = json.loads(out)
    assert data["coverage"]["quarterly_without_confirmed_slot"] == ["Q"]
    assert data["due_soon"] == [] and [i["title"] for i in data["p2_review"]["confirm"]] == [
        "Guess"
    ]

    for flag, value, message in (
        ("--due-within", "-1", "cannot be negative"),
        ("--window", "0", "at least 1 day"),
    ):
        assert cli.main(["check", str(path), flag, value]) == 2
        assert message in capsys.readouterr().err

    path.write_text(GOALS_TOML + "[[day]]\ndate = 2026-11-23\n[[day]]\ndate = 2026-11-23\n")
    assert cli.main(["check", str(path)]) == 2
    assert "appears more than once" in capsys.readouterr().err


def test_cli_check_large_due_within_and_proposed_today(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "p.toml"
    path.write_text(
        GOALS_TOML.replace('parent = "a"\n', 'parent = "a"\ndue = 2027-01-03\n')
        + plan_toml("2026-11-24").replace("[today]\n", "[today]\nconfirmed = false\n")
    )
    code, out = run(capsys, "check", str(path), "--today", "2026-11-24", "--due-within", "3000000")
    assert code == 0, out
    assert "today (3 goals, proposed): ok" in out
    assert "  Q (due 2027-01-03, 40 days left)" in out  # no [[day]] history, so no slot claim
    code, out = run(capsys, "check", str(path), "--today", "2026-11-24", "--json")
    assert json.loads(out)["today"]["confirmed"] is False


def test_cli_check_counts_goals_that_share_a_title(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "p.toml"
    path.write_text(
        '[[goal]]\nid = "a"\ntitle = "A"\nhorizon = "annual"\n'
        '[[goal]]\nid = "q1"\ntitle = "Q"\nhorizon = "quarterly"\nparent = "a"\n'
        '[[goal]]\nid = "q2"\ntitle = "Q"\nhorizon = "quarterly"\nparent = "a"\n'
        '[[day]]\ndate = 2026-11-23\nconfirmed = false\ngoals = [{ title = "T", parent = "q1" }]\n'
    )
    code, out = run(capsys, "check", str(path), "--today", "2026-11-24")
    assert code == 0, out
    assert "  quarterly goals with no slot: Q\n" in out
    assert "  quarterly goals slotted only in proposed plans: Q\n" in out
    assert "every goal had a slot" not in out


def test_cli_check_reports_invalid_plan(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text(
        '[[goal]]\nid = "a"\ntitle = "A"\nhorizon = "annual"\n'
        '[today]\ngoals = [{ title = "Only one", parent = "a" }]\n'
    )
    code, out = run(capsys, "check", str(bad), "--json")
    assert code == 1
    errors = json.loads(out)["today"]["errors"]
    assert any("exactly 3" in e for e in errors)


def test_cli_check_stale_today_warns_and_ages_p2_from_run_date(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 90 days old on the [today] date, so kept; 104 days old on the run date, so deleted.
    path = tmp_path / "p.toml"
    path.write_text(
        GOALS_TOML + plan_toml("2026-11-10") + '[[p2]]\ntitle = "Old idea"\nadded = 2026-08-12\n'
    )
    code, out = run(capsys, "check", str(path), "--today", "2026-11-24", "--json")
    data = json.loads(out)
    assert code == 0 and data["ok"] and data["run_date"] == "2026-11-24"
    assert data["warnings"] == [
        "[today] date 2026-11-10 is 14 days before the run date 2026-11-24; the plan may be stale"
    ]
    assert [d["title"] for d in data["p2_review"]["delete"]] == ["Old idea"]

    code, out = run(capsys, "check", str(path), "--today", "2026-11-24")
    assert code == 0 and "warning: [today] date 2026-11-10 is 14 days before" in out
    code, _ = run(capsys, "check", str(path), "--today", "2026-11-24", "--strict")
    assert code == 1


def test_cli_check_plan_for_tomorrow_is_not_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "p.toml"
    path.write_text(GOALS_TOML + plan_toml("2026-11-25"))
    code, out = run(capsys, "check", str(path), "--today", "2026-11-24", "--strict", "--json")
    assert code == 0 and json.loads(out)["warnings"] == []


def test_cli_check_history_and_proposed_scores(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "p.toml"
    path.write_text(
        GOALS_TOML
        + '[[goal]]\nid = "q2"\ntitle = "Q2"\nhorizon = "quarterly"\nparent = "a"\n'
        + plan_toml("2026-11-24")
        + '[[day]]\ndate = 2026-11-23\ngoals = [{ title = "T", parent = "q" }]\n'
        + '[[day]]\ndate = 2026-11-01\ngoals = [{ title = "Old", parent = "q2" }]\n'
        + '[[p2]]\ntitle = "Guess"\nadded = 2026-11-20\nimportance = 4\nurgency = 1\n'
        + "confirmed = false\n"
    )
    code, out = run(capsys, "check", str(path), "--today", "2026-11-24")
    assert code == 0, out
    assert "last 7 days (2026-11-18 to 2026-11-24): plans on 2 days" in out
    assert "  quarterly goals with no slot: Q2" in out
    assert "  promote: Guess (P1, proposed)" in out


def test_cli_check_goal_tree_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "p.toml"
    path.write_text(GOALS_TOML)
    code, out = run(capsys, "check", str(path))
    assert code == 0 and out == "goal tree: ok (1 annual, 1 quarterly)\n"


def test_cli_validate_matrix(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = srv.tool_get_rubric()
    data["grid"][4][0] = "drop"
    path = tmp_path / "m.json"
    path.write_text(json.dumps({k: data[k] for k in ("importance", "urgency", "levels", "grid")}))
    code, out = run(capsys, "validate-matrix", str(path))
    assert code == 1 and "lowers the level" in out


def test_cli_reads_matrix_env(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    data = srv.tool_get_rubric()
    data["grid"][2][0] = "drop"
    path = tmp_path / "m.json"
    path.write_text(json.dumps({k: data[k] for k in ("importance", "urgency", "levels", "grid")}))
    monkeypatch.setenv("PRIORITYKIT_MATRIX", str(path))
    code, out = run(capsys, "classify", "-i", "3", "-u", "1", "--json")
    assert code == 0 and json.loads(out)["level"] == "drop"


def test_python_m_runs_cli() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "prioritykit", "--version"],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    assert proc.stdout.strip() == f"prioritykit {__version__}"


def test_cli_errors_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["check", "/nonexistent/priorities.toml"]) == 2


def test_tool_functions() -> None:
    p0 = srv.tool_classify_task(4, 5, "Outage")
    assert p0["level"] == "P0" and p0["requires_confirmation"] is True
    p1 = srv.tool_classify_task(4, 4)
    assert p1["level"] == "P1" and p1["requires_confirmation"] is False
    rubric = srv.tool_get_rubric()
    assert rubric["counts"] == {"P0": 2, "P1": 10, "P2": 7, "drop": 6}
    goals = [
        srv.GoalIn(id="a", title="A", horizon="annual"),
        srv.GoalIn(id="q", title="Q", horizon="quarterly", parent="a"),
    ]
    today = [srv.DailyGoalIn(title=f"T{k}", parent="q") for k in range(3)]
    assert srv.tool_check_day_plan(goals, today)["ok"]
    replanned = srv.tool_replan_for_p0(goals, today, "Fire", "T1")
    assert replanned["check"]["ok"] and replanned["today"][1]["p0"]
    rep = srv.tool_review_p2(
        [srv.P2In(title="x", added="2026-01-01", importance=4, urgency=1, confirmed=False)],
        "2026-11-24",
    )
    assert rep["promote"][0]["level"] == "P1" and rep["promote"][0]["confirmed"] is False
    days = [srv.DayIn(date=f"2026-11-{d}", goals=today) for d in (20, 21)]
    week = srv.tool_check_week(goals, days, "2026-11-24")
    assert week["days_with_plans"] == 2 and week["quarterly_without_slot"] == []
    assert week["due_soon"] == []
    due_goals = [
        goals[0],
        srv.GoalIn(id="q", title="Q", horizon="quarterly", parent="a", due="2026-12-01"),
    ]
    proposed = [srv.DayIn(date="2026-11-23", goals=today, confirmed=False)]
    week = srv.tool_check_week(due_goals, proposed, "2026-11-24")
    assert week["days_with_confirmed_plans"] == 0
    assert week["quarterly_without_slot"] == [] and week["quarterly_without_confirmed_slot"] == [
        "Q"
    ]
    assert week["due_soon"] == [
        {
            "title": "Q",
            "horizon": "quarterly",
            "due": "2026-12-01",
            "days_left": 7,
            "slot": "proposed",
        }
    ]
    with pytest.raises(ValueError, match="share the date"):
        srv.tool_check_week(goals, days + days[:1], "2026-11-24")
    assert srv.tool_wait_estimate(120, 3)["expected_wait_months"] == 40
    assert srv.tool_check_workspace(EXAMPLE)["today"]["ok"]
    ws = srv.tool_check_workspace(EXAMPLE, "2026-11-24", window_days=1, due_within_days=60)
    assert ws["coverage"]["window_days"] == 1 and ws["due_soon"][0]["days_left"] == 24
    assert srv.tool_check_week(goals, [], "2026-11-24")["days_with_plans"] == 0
    empty = srv.tool_check_week(due_goals, [], "2026-11-24")
    assert empty["due_soon"][0]["slot"] is None  # no plans, so no claim about slots


def test_custom_matrix_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = srv.tool_get_rubric()
    data["grid"][2][0] = "drop"
    path = tmp_path / "m.json"
    path.write_text(json.dumps({k: data[k] for k in ("importance", "urgency", "levels", "grid")}))
    monkeypatch.setenv("PRIORITYKIT_MATRIX", str(path))
    assert srv.tool_classify_task(3, 1)["level"] == "drop"


def test_server_registers_tools() -> None:
    pytest.importorskip("mcp")
    server = srv.build_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "get_rubric",
        "classify_task",
        "check_day_plan",
        "replan_for_p0",
        "review_p2",
        "check_week",
        "wait_estimate",
        "check_workspace",
    }


def test_server_reports_package_version() -> None:
    pytest.importorskip("mcp")
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        },
    }
    proc = subprocess.run(
        [sys.executable, "-m", "prioritykit.mcp_server"],
        input=json.dumps(request) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
    )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert lines, proc.stderr
    assert json.loads(lines[0])["result"]["serverInfo"]["version"] == __version__


def test_pure_tool_set_reads_no_files(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("mcp")
    monkeypatch.setenv("PRIORITYKIT_TOOLS", "pure")
    names = {t.name for t in asyncio.run(srv.build_server().list_tools())}
    assert "check_workspace" not in names and len(names) == 7
    monkeypatch.setenv("PRIORITYKIT_TOOLS", "everything")
    with pytest.raises(ValueError):
        srv.build_server()


def test_check_workspace_path_rules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inside, outside = tmp_path / "a", tmp_path / "b"
    inside.mkdir()
    outside.mkdir()
    for d in (inside, outside):
        (d / "p.toml").write_text(GOALS_TOML)
    (inside / "notes.txt").write_text(GOALS_TOML)
    (inside / "link.toml").symlink_to(outside / "p.toml")

    with pytest.raises(ValueError, match=r"only \.toml"):
        srv.tool_check_workspace(str(inside / "notes.txt"))

    monkeypatch.setenv("PRIORITYKIT_ROOT", str(inside))
    assert srv.tool_check_workspace(str(inside / "p.toml"))["ok"]
    for bad in (outside / "p.toml", inside / "link.toml", inside / ".." / "b" / "p.toml"):
        with pytest.raises(ValueError, match="outside PRIORITYKIT_ROOT"):
            srv.tool_check_workspace(str(bad))
