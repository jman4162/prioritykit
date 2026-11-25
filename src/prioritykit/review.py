"""The periodic P2 review: rescore, promote a few, delete the rest.

Under strict priority the lowest level only gets the capacity the higher levels leave, so a P2
list grows unless something takes items off it. The review is that something. Items whose
current scores now map to P1 or P0 are promotion candidates; items older than ``max_age_days``
that still score P2 or lower, or were never scored, are deletion candidates; the rest stay.
Each entry carries ``confirmed``, so an agent's proposed scores reach the review marked as such.
An old item with ``confirmed=False`` (an agent added or scored it, and no person has confirmed)
goes to ``confirm`` instead of ``delete``: a person scores it or deletes it, so a batch approval
of the delete list never removes an item nobody looked at.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from .matrix import RANK, Classification, Matrix, classify

DEFAULT_MAX_AGE_DAYS = 90  # one quarter; change it to match your review cadence


@dataclass(frozen=True)
class P2Item:
    title: str
    added: date
    importance: int | None = None
    urgency: int | None = None
    confirmed: bool = True  # False: an agent proposed the scores and the person has not confirmed


@dataclass(frozen=True)
class ReviewReport:
    promote: tuple[tuple[P2Item, Classification], ...]
    delete: tuple[P2Item, ...]
    keep: tuple[P2Item, ...]
    expected_wait_months: float | None
    confirm: tuple[P2Item, ...] = ()  # old and unconfirmed: a person scores it or deletes it

    def to_dict(self) -> dict[str, Any]:
        return {
            "promote": [
                {
                    "title": item.title,
                    "added": item.added.isoformat(),
                    "confirmed": item.confirmed,
                    **c.to_dict(),
                }
                for item, c in self.promote
            ],
            "delete": [_entry(i) for i in self.delete],
            "confirm": [_entry(i) for i in self.confirm],
            "keep": [_entry(i) for i in self.keep],
            "expected_wait_months": self.expected_wait_months,
        }


def _entry(item: P2Item) -> dict[str, Any]:
    return {"title": item.title, "added": item.added.isoformat(), "confirmed": item.confirmed}


def littles_law_wait(backlog: int, departures_per_period: float) -> float:
    """Mean time an item waits on a list in steady state, W = L / throughput (Little, 1961).

    ``departures_per_period`` counts items leaving the list, done or deleted, per period; the
    result is in the same period. A list nothing leaves has no finite wait.
    """
    if backlog < 0:
        raise ValueError("backlog cannot be negative")
    if departures_per_period <= 0:
        raise ValueError("departures must be positive; a list nothing leaves never clears")
    return backlog / departures_per_period


def review_p2(
    items: Iterable[P2Item],
    today: date,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    departures_per_month: float | None = None,
    matrix: Matrix | None = None,
) -> ReviewReport:
    items = list(items)
    promote: list[tuple[P2Item, Classification]] = []
    delete: list[P2Item] = []
    confirm: list[P2Item] = []
    keep: list[P2Item] = []
    for item in items:
        age = (today - item.added).days
        if item.importance is not None and item.urgency is not None:
            c = classify(item.importance, item.urgency, matrix)
            if RANK[c.level] > RANK["P2"]:
                promote.append((item, c))
                continue
        if age <= max_age_days:
            keep.append(item)
        elif not item.confirmed:
            confirm.append(item)
        else:
            delete.append(item)
    wait = (
        littles_law_wait(len(items), departures_per_month)
        if departures_per_month is not None
        else None
    )
    return ReviewReport(tuple(promote), tuple(delete), tuple(keep), wait, tuple(confirm))
