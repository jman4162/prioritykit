# prioritykit

[![CI](https://github.com/jman4162/prioritykit/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jman4162/prioritykit/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/prioritykit)](https://pypi.org/project/prioritykit/)
[![Python versions](https://img.shields.io/pypi/pyversions/prioritykit)](https://pypi.org/project/prioritykit/)
[![License](https://img.shields.io/github/license/jman4162/prioritykit)](https://github.com/jman4162/prioritykit/blob/main/LICENSE)

prioritykit applies one prioritization system the same way for a person at a terminal and for an
AI agent acting as a chief of staff. You rate each task from 1 to 5 on importance and urgency, a
5 × 5 table maps the pair to P0, P1, P2, or drop, and each day holds exactly three goals that
trace to quarterly and annual goals. The background, the evidence, and the figures are in
[Why P2 work rarely gets done, and how I pick three goals a day](https://john-hodge.com/blog/why-p2-work-rarely-gets-done/).

Each function computes its result from its arguments, and your goals, today's plan, and P2 list
live in a plain TOML file that you keep under your own version control. The core library and the
command line interface (CLI) use only the Python standard library, and an optional Model Context
Protocol (MCP) server exposes the same functions to agents.

## Install

Python 3.11 or later.

```bash
uv tool install "prioritykit[mcp]"
# or
pip install "prioritykit[mcp]"
```

Drop `[mcp]` if you only want the CLI and library.

## The rules

Importance is defined by your goals, and urgency by how fast the cost of waiting grows:

| Score | Importance: what it does for your goals | Urgency: how fast waiting gets costly |
| --- | --- | --- |
| 5 | Directly advances an annual goal, or prevents serious harm to health, family, or a commitment others depend on | Cost rises within hours; start today |
| 4 | Directly advances a quarterly goal | Cost rises within days; this week |
| 3 | Supports a goal indirectly, or meets an obligation with moderate consequences | Cost rises within weeks |
| 2 | Small benefit; no goal moves | Waiting a month costs little |
| 1 | No effect on any goal | Waiting a quarter costs nothing |

The default table gives importance precedence over urgency:

```text
importance \ urgency    1     2     3     4     5
                    5     P1    P1    P1    P1    P0
                    4     P1    P1    P1    P1    P0
                    3     P2    P2    P2    P1    P1
                    2   drop  drop  drop    P2    P2
                    1   drop  drop  drop    P2    P2
cells: 2 P0, 10 P1, 7 P2, 6 drop
```

| Level | Action |
| --- | --- |
| P0, interrupt | Rewrite today's three goals around it, and name the goal it displaces. |
| P1, schedule | Give it a slot in one of the next few days' three goals. |
| P2, list | Put it on the P2 list and plan as if it will not happen. The weekly review promotes it to P1 or deletes it. |
| drop | Decline it or delete it now. |

P0 needs importance of at least 4 and urgency 5, so work that grows costly within days waits for
the next morning's plan instead of interrupting today. Urgency alone never lifts work of importance
1 or 2 above P2. Multiplying the two scores, as a
risk matrix does, would rank a very important task with no deadline (5 × 1 = 5) below an
unimportant urgent one (2 × 5 = 10).

A P2 task that blocks P1 work takes on the importance of the work it blocks, so rescore it instead
of waiting for the review to notice.

## CLI

```bash
prioritykit classify -i 5 -u 2          # Importance 5, urgency 2: P1 (schedule). ...
prioritykit matrix                      # the 5 x 5 grid
prioritykit anchors                     # anchors and level actions
prioritykit check examples/priorities.toml --today 2026-11-24 --departures 3
prioritykit validate-matrix my-matrix.json
```

Every command takes `--json`. `check` exits with status 1 when the goal tree or today's plan
breaks a rule, so it can run in a pre-commit hook or a scheduled job. It counts P2 ages from the
run date, which is the current date unless you pass `--today`, and warns when `[today]` is dated
before the run date; `--strict` exits 1 on warnings too. `python -m prioritykit` runs the same CLI
when the console script is not on your PATH. Output for the example:

```text
goal tree: ok (4 annual, 4 quarterly)
today (3 goals): ok
  Review a design doc with a teammate <- Mentor a junior scientist <- Grow as a technical lead
  Dinner and bedtime, phone in another room <- Protect weekday evenings <- Be present with my family
  45-minute strength session <- Strength train 3 times a week <- Stay strong and fit
  annual goals with no slot today: Publish technical writing
last 7 days (2026-11-18 to 2026-11-24): plans on 3 days
  every goal had a slot
P2 list: 3 items
  promote: Renew the passport before the spring trip (P1, proposed)
  delete (older than 90 days): Reorganize the photo library
  keep: Try a new note-taking app
  expected wait for a new item: 1.0 months
```

## The priorities file

```toml
[[goal]]
id = "fit"
title = "Stay strong and fit"
horizon = "annual"

[[goal]]
id = "strength"
title = "Strength train 3 times a week"
horizon = "quarterly"
parent = "fit"
due = 2026-12-31   # optional; check warns once the date has passed

[today]
date = 2026-11-24
goals = [
  { title = "45-minute strength session", parent = "strength" },
  # ... exactly three entries; a P0 entry is { title = "...", p0 = true, displaces = "..." }
]

[[day]]          # optional history: each morning, move yesterday's [today] here
date = 2026-11-23
goals = [
  { title = "45-minute strength session", parent = "strength" },
  # ...
]

[[p2]]
title = "Reorganize the photo library"
added = 2026-05-02
importance = 2   # optional; rescored items that now map to P1 or P0 are promotion candidates
urgency = 1
confirmed = false   # optional; scores an agent proposed and you have not confirmed
```

[`examples/priorities.toml`](https://github.com/jman4162/prioritykit/blob/main/examples/priorities.toml) is a complete file. A P2 item older than
90 days that still scores P2 or lower, or was never scored, is a deletion candidate; change the
threshold with `--max-age`. With `[[day]]` history, `check` lists the quarterly and annual goals
that no plan gave a slot in the last 7 days (`--window`), counting `[today]`, and says how many of
those days had a plan.

Goal titles can name employer-internal projects or private matters, so keep your priorities file
in a private repository, not a public one.

## MCP server for agents

The server speaks stdio and exposes eight tools. All but `check_workspace` are pure functions:

| Tool | What it returns |
| --- | --- |
| `get_rubric` | anchors, level actions, the grid, and the daily goal count |
| `classify_task` | the level and action for an importance and urgency pair, and `requires_confirmation` (true for P0) |
| `check_day_plan` | whether today holds exactly three goals, each traced to quarterly and annual goals |
| `replan_for_p0` | today's plan with one goal replaced by a confirmed P0, rechecked |
| `check_week` | goals no day plan gave a slot over the last N days, and how many days had a plan |
| `review_p2` | promote, delete, and keep lists for a P2 review |
| `wait_estimate` | expected months on a list, by Little's law |
| `check_workspace` | all of the above for a local `priorities.toml`, plus warnings such as a stale `[today]` date |

Claude Code:

```bash
claude mcp add --transport stdio --scope user prioritykit -- prioritykit-mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{ "mcpServers": { "prioritykit": { "command": "prioritykit-mcp" } } }
```

The server's instructions tell the agent to propose scores with a reason for each and wait for
the human to confirm, or record them as proposed (`confirmed = false`) when no human is present;
never to label work P0 on its own; to call `check_day_plan` before presenting a day's three goals
and `check_week` before saying a goal has gone without a slot; and to raise P2 items only during
a review. Work the agent
generates for itself is scored like any other task. The same protocol is written out as an agent
skill in [`skills/prioritykit/SKILL.md`](https://github.com/jman4162/prioritykit/blob/main/skills/prioritykit/SKILL.md); copy it into
`~/.claude/skills/` or adapt it for an `AGENTS.md` file.

`check_workspace` is the only tool that reads a file. It runs with your permissions and reads
only paths that end in `.toml` once symlinks are resolved. For an agent that also reads untrusted
content such as email, where a prompt injection could choose the path, narrow it further:

- `PRIORITYKIT_ROOT=/path/to/dir` refuses files outside that directory.
- `PRIORITYKIT_TOOLS=pure` leaves `check_workspace` out, so no tool reads a file. A script reads
  the file and passes the goal tree and plan to the other tools.

## Your own table

Start from `prioritykit matrix --json > my-matrix.json` or a copy of
[`src/prioritykit/data/default_matrix.json`](https://github.com/jman4162/prioritykit/blob/main/src/prioritykit/data/default_matrix.json),
change the anchors, cells, or level names and actions, and pass it with `--matrix`. Set
`PRIORITYKIT_MATRIX` to use it everywhere: the CLI reads it when `--matrix` is absent and the MCP
server always reads it, so a script and an agent classify with the same table. The four levels
(P0, P1, P2, drop) are fixed, because the agent instructions and the P2 review depend on what each
one means, and the MCP server has no tool that changes the table. `prioritykit validate-matrix` rejects a table in which raising a score lowers the level,
and warns when urgency alone lifts low-importance work above P2, when P0 cells fall outside the
top-right corner, or when more than 4 cells are P0.

## Limits

The scores are ordinal judgments. Two people can score the same task differently, and ordinal
risk matrices are known to compress very different risks into one rating (Cox, 2008). The number
three is an operating rule from experience; the research behind the surrounding practices
(specific goals, if-then plans, written progress checks) is summarized in the background post.

## Development

```bash
uv sync --group dev
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

## License

Apache-2.0.
