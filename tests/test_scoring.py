"""Score → level → action mapping."""

from __future__ import annotations

import pytest

from app.services import compute_score, level_to_action, score_to_level


@pytest.mark.parametrize(
    "n,t,expected",
    [
        (4, 0, 0),
        (4, 1, 25),
        (4, 2, 50),
        (4, 3, 75),
        (4, 4, 100),
        (5, 0, 0),
        (5, 3, 60),
        (5, 5, 100),
        (0, 0, 0),
    ],
)
def test_compute_score(n, t, expected):
    assert compute_score(n, t) == expected


@pytest.mark.parametrize(
    "score,level",
    [
        (0, "low"),
        (25, "low"),
        (40, "watch"),
        (60, "medium"),
        (75, "high"),
        (90, "critical"),
        (100, "critical"),
    ],
)
def test_score_to_level(score, level):
    assert score_to_level(score) == level


def test_level_to_action_covers_every_level():
    for lvl in ("low", "watch", "medium", "high", "critical"):
        assert level_to_action(lvl)
