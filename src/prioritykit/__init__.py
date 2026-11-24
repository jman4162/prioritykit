"""prioritykit: importance-urgency scoring, P0/P1/P2 levels, and three daily goals.

Pure, deterministic functions with no storage. People call them from the CLI, and AI agents
call them through the MCP server, so the rules are applied the same way in both places.
"""

from importlib.metadata import PackageNotFoundError, version

from .matrix import (
    LEVELS,
    Anchor,
    Classification,
    Level,
    LevelInfo,
    Matrix,
    MatrixError,
    MatrixReport,
    check_matrix,
    classify,
    default_matrix,
    load_matrix,
    matrix_from_dict,
)
from .plan import DailyGoal, Goal, PlanReport, check_day_plan, check_goal_tree, replan_for_p0
from .review import P2Item, ReviewReport, littles_law_wait, review_p2
from .workspace import Workspace, WorkspaceError, load_workspace, workspace_from_dict

try:
    __version__ = version("prioritykit")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0"

__all__ = [
    "LEVELS",
    "Anchor",
    "Classification",
    "DailyGoal",
    "Goal",
    "Level",
    "LevelInfo",
    "Matrix",
    "MatrixError",
    "MatrixReport",
    "P2Item",
    "PlanReport",
    "ReviewReport",
    "Workspace",
    "WorkspaceError",
    "__version__",
    "check_day_plan",
    "check_goal_tree",
    "check_matrix",
    "classify",
    "default_matrix",
    "littles_law_wait",
    "load_matrix",
    "load_workspace",
    "matrix_from_dict",
    "replan_for_p0",
    "review_p2",
    "workspace_from_dict",
]
