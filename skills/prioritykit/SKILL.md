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
4. Ask the person to confirm or change the scores before you act on the level.

Importance takes precedence. Urgency alone never lifts work of importance 1 or 2 above P2, so
do not argue a low-importance task up the list because its deadline is close.

## P0 means interrupt

Never label work P0 on your own. When the person confirms a P0, ask which of today's three goals
it displaces, call `replan_for_p0`, and show the revised plan.

## Each morning

1. Read the goal tree (from `priorities.toml` with `check_workspace`, or from the person).
2. Propose exactly three goals for the day. Each one names the quarterly goal it advances.
   Prefer outcomes ("45-minute strength session") to activities ("work on fitness").
3. Call `check_day_plan` and fix every error before you present the plan.
4. Mention annual goals with no slot today only if one has gone without a slot all week.

## P2 and the review

Treat P2 as work that will probably not happen. Do not bring up P2 items during normal planning.
At the person's periodic review, call `review_p2`, present the promote and delete candidates, and
let the person decide each one. A promoted item needs a dated slot in an upcoming day's three.

## Work you generate

Score your own suggestions (research leads, refactors, new ideas) on the same two axes. If a
suggestion advances no goal, the rules put it at P2 or drop; say so instead of adding it to the
plan.

## Numbers

Quote counts, dates, and waits from tool results. Do not estimate them yourself.
