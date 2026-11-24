import asyncio
import json
from pathlib import Path

import pytest

from prioritykit import cli
from prioritykit import mcp_server as srv

EXAMPLE = str(Path(__file__).resolve().parents[1] / "examples" / "priorities.toml")


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = cli.main(list(argv))
    return code, capsys.readouterr().out


def test_cli_classify_text_and_json(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "classify", "-i", "5", "-u", "5")
    assert code == 0 and out.startswith("Importance 5, urgency 5: P0 (interrupt).")
    code, out = run(capsys, "classify", "-i", "2", "-u", "5", "--json")
    assert json.loads(out)["level"] == "P2"


def test_cli_matrix_and_anchors(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "matrix")
    assert code == 0 and "cells: 2 P0, 10 P1, 7 P2, 6 drop" in out
    code, out = run(capsys, "anchors")
    assert code == 0 and "Waiting a quarter costs nothing" in out


def test_cli_check_example(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "check", EXAMPLE, "--departures", "3")
    assert code == 0, out
    assert "today (3 goals): ok" in out
    assert "promote: Renew the passport before the spring trip (P1)" in out
    assert "expected wait for a new item: 1.0 months" in out


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


def test_cli_validate_matrix(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = srv.tool_get_rubric()
    data["grid"][4][0] = "drop"
    path = tmp_path / "m.json"
    path.write_text(json.dumps({k: data[k] for k in ("importance", "urgency", "levels", "grid")}))
    code, out = run(capsys, "validate-matrix", str(path))
    assert code == 1 and "lowers the level" in out


def test_cli_errors_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["check", "/nonexistent/priorities.toml"]) == 2


def test_tool_functions() -> None:
    assert srv.tool_classify_task(4, 5, "Outage")["level"] == "P0"
    assert srv.tool_classify_task(4, 4)["level"] == "P1"
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
        [srv.P2In(title="x", added="2026-01-01", importance=4, urgency=1)], "2026-11-24"
    )
    assert rep["promote"][0]["level"] == "P1"
    assert srv.tool_wait_estimate(120, 3)["expected_wait_months"] == 40
    assert srv.tool_check_workspace(EXAMPLE)["today"]["ok"]


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
        "wait_estimate",
        "check_workspace",
    }
