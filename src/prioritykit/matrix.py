"""The importance-urgency matrix and the classifier that reads it.

A matrix holds anchors for the two 1-5 scales, a name and action for each level, and a 5x5
grid where ``grid[i - 1][u - 1]`` is the level for importance ``i`` and urgency ``u``. The
default matrix ships in ``data/default_matrix.json``. Any JSON file with the same shape can
replace it, and :func:`check_matrix` reports whether the replacement keeps the properties
the default was built around.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Literal, cast

Level = Literal["P0", "P1", "P2", "drop"]
LEVELS: tuple[Level, ...] = ("P0", "P1", "P2", "drop")
# Higher rank means sooner attention.
RANK: dict[Level, int] = {"drop": 0, "P2": 1, "P1": 2, "P0": 3}
SCORES = (1, 2, 3, 4, 5)


class MatrixError(ValueError):
    """A matrix file has the wrong shape or contents."""


@dataclass(frozen=True)
class Anchor:
    score: int
    label: str


@dataclass(frozen=True)
class LevelInfo:
    name: str
    action: str


@dataclass(frozen=True)
class Classification:
    importance: int
    urgency: int
    level: Level
    name: str
    action: str
    importance_anchor: str
    urgency_anchor: str

    @property
    def requires_confirmation(self) -> bool:
        """P0 interrupts the day's plan, so an agent may propose it but a person must confirm."""
        return self.level == "P0"

    def describe(self) -> str:
        label = "Drop" if self.level == "drop" else f"{self.level} ({self.name})"
        return f"Importance {self.importance}, urgency {self.urgency}: {label}. {self.action}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "importance": self.importance,
            "urgency": self.urgency,
            "level": self.level,
            "name": self.name,
            "action": self.action,
            "importance_anchor": self.importance_anchor,
            "urgency_anchor": self.urgency_anchor,
            "requires_confirmation": self.requires_confirmation,
            "summary": self.describe(),
        }


@dataclass(frozen=True)
class MatrixReport:
    """Errors make a matrix unusable. Warnings flag a departure from the default design."""

    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class Matrix:
    importance: tuple[Anchor, ...]
    urgency: tuple[Anchor, ...]
    levels: dict[Level, LevelInfo]
    grid: tuple[tuple[Level, ...], ...]

    def level(self, importance: int, urgency: int) -> Level:
        _require_score("importance", importance)
        _require_score("urgency", urgency)
        return self.grid[importance - 1][urgency - 1]

    def counts(self) -> dict[Level, int]:
        counts: dict[Level, int] = dict.fromkeys(LEVELS, 0)
        for row in self.grid:
            for level in row:
                counts[level] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "importance": [{"score": a.score, "label": a.label} for a in self.importance],
            "urgency": [{"score": a.score, "label": a.label} for a in self.urgency],
            "levels": {k: {"name": v.name, "action": v.action} for k, v in self.levels.items()},
            "grid": [list(row) for row in self.grid],
        }


def _require_score(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value not in SCORES:
        raise ValueError(f"{name} must be an integer from 1 to 5, got {value!r}")


def matrix_from_dict(data: dict[str, Any]) -> Matrix:
    """Build a matrix from parsed JSON, raising MatrixError on a malformed shape."""
    try:
        importance = tuple(Anchor(int(a["score"]), str(a["label"])) for a in data["importance"])
        urgency = tuple(Anchor(int(a["score"]), str(a["label"])) for a in data["urgency"])
        raw_levels = data["levels"]
        raw_grid = data["grid"]
    except (KeyError, TypeError, ValueError) as exc:
        raise MatrixError(f"matrix is missing or has a malformed field: {exc}") from exc

    for scale_name, scale in (("importance", importance), ("urgency", urgency)):
        if tuple(a.score for a in scale) != SCORES:
            raise MatrixError(f"{scale_name} anchors must cover scores 1 to 5 in order")
        if not all(a.label.strip() for a in scale):
            raise MatrixError(f"every {scale_name} anchor needs a label")

    if set(raw_levels) != set(LEVELS):
        raise MatrixError(f"levels must be exactly {', '.join(LEVELS)}")
    levels = {
        cast(Level, k): LevelInfo(str(v["name"]), str(v["action"])) for k, v in raw_levels.items()
    }

    if len(raw_grid) != 5 or any(len(row) != 5 for row in raw_grid):
        raise MatrixError("grid must be 5 rows of 5 cells")
    bad = {cell for row in raw_grid for cell in row if cell not in LEVELS}
    if bad:
        raise MatrixError(f"grid has unknown levels: {sorted(bad)}")
    grid = tuple(tuple(cast(Level, cell) for cell in row) for row in raw_grid)
    return Matrix(importance, urgency, levels, grid)


def load_matrix(path: str | Path) -> Matrix:
    return matrix_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def default_matrix() -> Matrix:
    text = resources.files("prioritykit").joinpath("data/default_matrix.json").read_text("utf-8")
    return matrix_from_dict(json.loads(text))


def check_matrix(m: Matrix) -> MatrixReport:
    """Check the properties the default matrix was designed to have.

    Errors: raising either score must never lower the level (monotonicity).
    Warnings: urgency alone lifting importance 1-2 work above P2, P0 cells outside the
    importance >= 4 and urgency >= 4 corner, and a P0 region larger than 4 of 25 cells.
    """
    errors: list[str] = []
    warnings: list[str] = []
    for i in SCORES:
        for u in SCORES:
            here = RANK[m.level(i, u)]
            if i < 5 and RANK[m.level(i + 1, u)] < here:
                errors.append(
                    f"raising importance from {i} to {i + 1} at urgency {u} lowers the level"
                )
            if u < 5 and RANK[m.level(i, u + 1)] < here:
                errors.append(
                    f"raising urgency from {u} to {u + 1} at importance {i} lowers the level"
                )
            level = m.level(i, u)
            if i <= 2 and RANK[level] > RANK["P2"]:
                warnings.append(
                    f"importance {i}, urgency {u} is {level}: urgency alone lifts it above P2"
                )
            if level == "P0" and not (i >= 4 and u >= 4):
                warnings.append(f"importance {i}, urgency {u} is P0 outside the top-right corner")
    if m.counts()["P0"] > 4:
        warnings.append(f"{m.counts()['P0']} of 25 cells are P0; interruptions will be frequent")
    return MatrixReport(tuple(errors), tuple(warnings))


def classify(importance: int, urgency: int, matrix: Matrix | None = None) -> Classification:
    """Map 1-5 importance and urgency scores to a level and the action for that level."""
    m = matrix or default_matrix()
    level = m.level(importance, urgency)
    info = m.levels[level]
    return Classification(
        importance=importance,
        urgency=urgency,
        level=level,
        name=info.name,
        action=info.action,
        importance_anchor=m.importance[importance - 1].label,
        urgency_anchor=m.urgency[urgency - 1].label,
    )
