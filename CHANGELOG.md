# Changelog

## 0.2.0 (unreleased)

- Default table: P0 now needs importance of at least 4 and urgency 5 (2 cells, down from 4), so
  work that grows costly within days goes into the next day's plan as P1 instead of interrupting
  today. Counts are 2 P0, 10 P1, 7 P2, 6 drop.
- The default P2 action names a weekly review.
- The agent skill covers tasks of a few minutes, piles of small items, and work done for enjoyment.

## 0.1.0 (unreleased)

- Default 5 x 5 importance-urgency table with anchors and level actions; `classify` and
  `check_matrix` for custom tables.
- Goal-tree and daily-three checks with goal tracing, and a P0 replan that records what it
  displaced.
- P2 review (promote, delete, keep) and a Little's-law wait estimate.
- TOML priorities file, standard-library CLI, stdio MCP server, and an agent skill.
