---
name: prioritykit
description: Use when helping a person plan their day, triage a new task or request, decide whether something should interrupt their plan, or review a backlog, if they follow the importance-urgency, P0/P1/P2, three-goals-a-day system. Applies the rules through the prioritykit MCP tools or CLI.
---

# Prioritizing with prioritykit

The person decides what matters. You propose, explain, and apply the rules with the prioritykit
tools, so the result is the same every time. If the MCP server is not connected, run the
`prioritykit` CLI with `--json` instead.

## Scoring a task

1. Call `get_rubric` once per session to read the anchors and level actions.
2. Rate importance and urgency from 1 to 5. Quote the anchor you matched for each score and
   give a one-line reason, for example: "Importance 4 (directly advances the quarterly goal
   'Ship the design review'); urgency 2 (waiting a month costs little)."
3. Call `classify_task` and report the level and its action.
4. Ask the person to confirm or change the scores before you act on the level. If the person is
   not there to confirm (a scheduled or unattended run), record the scores as proposed
   (`confirmed = false` on a P2 item, or on a day plan you wrote) and leave the decision to them.
   Give a P2 item both scores or neither.

Importance takes precedence. Urgency alone never lifts work of importance 1 or 2 above P2, so
do not argue a low-importance task up the list because its deadline is close.

## P0 means interrupt

Never label work P0 on your own. `classify_task` returns `requires_confirmation: true` for P0,
and a P0 you propose stays a proposal until the person confirms it. When the person confirms a
P0, ask which of today's three goals it displaces, call `replan_for_p0`, and show the revised
plan.

## Each morning

1. Read the goal tree (from `priorities.toml` with `check_workspace`, or from the person). If
   `check_workspace` returns warnings, such as a stale `[today]` date or a past-due goal, tell the
   person first.
2. Propose exactly three goals for the day. Each one names the quarterly goal it advances.
   Word each so the person can tell at night whether it happened ("45-minute strength session"
   rather than "work on fitness").
3. Call `check_day_plan` and fix every error before you present the plan.
4. To say a goal has gone without a slot, call `check_week` with the past week's plans (the
   `[[day]]` entries in `priorities.toml`, or plans you saved) and quote `days_with_plans`.
   Without past plans, say nothing about unslotted goals. A slot in a plan with
   `confirmed = false` is a proposal; quote the `*_without_confirmed_slot` lists when you mean
   goals the person never committed time to.
5. When choosing the three, favor goals in `due_soon` whose `slot` is `"none"`, and quote
   `days_left`.

## Each evening

Ask the person how each of the day's three goals went, and record `done = "done"`, `"partial"`,
or `"missed"` on each goal as they report it. Do not guess an outcome they have not given.
`check_week` returns the counts for the window, and so does `check_workspace` once the file has
`[[day]]` history; only confirmed plans count. If nearly every goal is done week after week, ask
whether the goals are too easy; the person decides.

## Small, piled-up, and fun work

- A task that takes a few minutes: suggest doing it when it arrives instead of scoring and listing it.
- Many small items of one kind (small fixes, house maintenance): at review, score the pile as one
  item, since together they can reach P1 when none does alone.
- Reading, play, and side projects done for enjoyment sit outside the three goals and need no goal.

## P2 and the review

Treat P2 as work that will probably not happen. Do not bring up P2 items during normal planning.
At the person's periodic review, call `review_p2`, present the promote and delete candidates, and
let the person decide each one, marking items with `confirmed = false` as proposed scores. Items
in `confirm` are old and the person never confirmed them (`confirmed = false`): ask the person to
score or delete each one. A promoted item needs a dated slot in an upcoming day's three. A P2
item that blocks P1 work takes on that work's importance; rescore it instead of waiting for it to
age. If the person tracks how many items leave the P2 list each month, pass it to
`check_workspace` as `departures_per_month`; when it warns that the P2 wait is longer than the
review age, propose deletions toward the list size it names. At the weekly review, call
`check_week` to list the quarterly goals that got no slot.

## Work you generate

Score your own suggestions (research leads, refactors, new ideas) on the same two axes. If a
suggestion advances no goal, the rules put it at P2 or drop; say so instead of adding it to the
plan.

## Numbers

Quote counts, dates, and waits from tool results. Do not estimate them yourself.
