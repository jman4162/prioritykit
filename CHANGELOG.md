# Changelog

## 0.3.0 (2026-11-24)

- Optional `[[day]]` history in the priorities file. `check` and the `check_workspace` tool list
  the quarterly and annual goals that got no slot in the last 7 days (`--window`), counting
  `[today]`, and how many of those days had a plan. The new MCP tool `check_week` and library
  function `slot_coverage` take past plans directly.
- Optional `confirmed = false` on P2 items marks scores an agent proposed. Review entries carry
  `confirmed`, and `check` prints "proposed" next to them. `classify_task` returns
  `requires_confirmation`, true for P0.
- Optional `due` date on goals; `check` warns once it has passed.
- The agent instructions and skill say to record proposed scores on unattended runs, to call
  `check_week` before saying a goal went without a slot, and to rescore a P2 item that blocks P1
  work.

## 0.2.1 (2026-11-24)

- `check` and the `check_workspace` tool count P2 ages from the run date (the current date, or
  `--today`) instead of the `[today]` date. A file nobody updated for two weeks used to age its P2
  list from two weeks ago.
- Both warn when `[today]` is dated before the run date, and `check --strict` exits 1 on any
  warning. JSON output adds `run_date`, `goal_counts`, and `warnings`, and the `check_workspace`
  tool now returns `ok` like the CLI.
- `check` prints a `goal tree:` line first, so a file with only goals no longer prints a blank line.
- `python -m prioritykit` runs the CLI.
- The MCP server reports the package version in `serverInfo` instead of an empty string.
- `check_workspace` reads only `.toml` files. `PRIORITYKIT_ROOT` limits it to one directory, and
  `PRIORITYKIT_TOOLS=pure` leaves it out of the server.
- The CLI reads `PRIORITYKIT_MATRIX` when `--matrix` is not given, as the MCP server does.
- New library function `check_workspace` and its `WorkspaceReport`.

## 0.2.0 (2026-11-24)

First release on PyPI.

- Default table: P0 now needs importance of at least 4 and urgency 5 (2 cells, down from 4), so
  work that grows costly within days goes into the next day's plan as P1 instead of interrupting
  today. Counts are 2 P0, 10 P1, 7 P2, 6 drop.
- The default P2 action names a weekly review.
- The agent skill covers tasks of a few minutes, piles of small items, and work done for enjoyment.

## 0.1.0 (GitHub only)

- Default 5 x 5 importance-urgency table with anchors and level actions; `classify` and
  `check_matrix` for custom tables.
- Goal-tree and daily-three checks with goal tracing, and a P0 replan that records what it
  displaced.
- P2 review (promote, delete, keep) and a Little's-law wait estimate.
- TOML priorities file, standard-library CLI, stdio MCP server, and an agent skill.
