# Changelog

## 0.5.0 (2026-11-25)

- Optional `done = "done"`, `"partial"`, or `"missed"` on each daily goal records its outcome at
  the evening review. Coverage adds `outcomes` counts over the window's confirmed plans, with
  `not_recorded` for goals that have none (not counting the run date's own plan), and `check`
  prints them once any outcome is recorded. `check_week` accepts `done` and returns the counts.
- With `--departures`, `check` warns when the P2 list's Little's-law wait is longer than the
  review age (`--max-age`) and names the largest list that clears in that time. The MCP
  `check_workspace` tool takes `departures_per_month` and `max_age_days` for the same check.
- A P2 item whose `added` date is more than a day after the run date is a warning.
- `check` and `load_workspace` read a `.json` file with the same layout as the TOML file: dates
  as strings, `null` read as a missing field, ids as text or whole numbers. The MCP
  `check_workspace` tool still reads only `.toml` files.
- `prioritykit mcp` and `prioritykit-mcp` without the mcp extra print how to install it and exit
  2, instead of a traceback. `prioritykit-mcp` now runs through the CLI, so its other startup
  errors print one line as well. When the mcp package is installed but broken, the error says so
  instead of asking for the extra again.
- `--departures` must be a finite number.
- Python 3.14 in the classifiers and the CI matrix; a changelog link on the PyPI page; the README
  explains `--departures`.
- Behavior change: a P2 item with one score, or a score that is not an integer from 1 to 5, is an
  error that names the item. Before, a lone score counted as no score, so an old item could land
  on the delete list. `P2Item` checks this itself, so the library and MCP tools reject it too.
- Behavior change: `p0` must be `true` or `false`; `p0 = "false"` used to count as a P0. Titles
  and `displaces` must be text, and ids and `parent` text or whole numbers. A value of the wrong
  type or a table of the wrong shape is an error instead of a crash or a goal titled "None".
- The new warnings make `--strict` exit 1.

## 0.4.0 (2026-11-25)

- Optional `confirmed = false` on `[[day]]` and `[today]` marks a plan an agent proposed. Coverage
  adds `days_with_confirmed_plans`, `quarterly_without_confirmed_slot`, and
  `annual_without_confirmed_slot` beside the existing fields, which keep counting every plan.
  `check` prints how many days were proposed and the goals slotted only in proposals, and marks a
  proposed `[today]`; its JSON `today` entry carries `confirmed`.
- Goals due within 28 days of the run date (`check --due-within`) appear in a new `due_soon` list,
  each with `days_left` and `slot`: `confirmed`, `proposed`, or `none`, judged from the last 7
  days of plans plus any later plan such as tomorrow's `[today]`, or `null` when no plan falls in
  that range. `check_week` and `check_workspace` take `due_within_days`, `check_workspace` also
  takes `window_days`, and the library adds `due_soon` and `DueGoal`.
- `requires_confirmation` moved into the library's classification result, so `classify --json`
  and promoted P2 entries carry it as the `classify_task` tool does.
- Behavior change: an old P2 item with `confirmed = false` goes to a new `confirm` list instead of
  `delete`, so approving the delete list never removes an item no person has looked at.
- Behavior change: two `[[day]]` entries with one date are an error, and `slot_coverage` and
  `check_week` reject duplicate dates. A `[[day]]` with the same date as `[today]` is ignored for
  coverage, with a warning.
- A date field written as a TOML date and time, such as `due = 2026-12-01T09:00:00`, is a clear
  error instead of a crash. `check` rejects `--window` below 1 and a negative `--due-within`
  whatever the file holds.

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
