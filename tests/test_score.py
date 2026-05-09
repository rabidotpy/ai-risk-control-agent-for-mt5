"""Score formula: round(100 / N * count_true)."""

from __future__ import annotations

import pytest

from app.engine import compute_score


@pytest.mark.parametrize(
    "n, true_count, expected",
    [
        (4, 0, 0),
        (4, 1, 25),
        (4, 2, 50),
        (4, 3, 75),
        (4, 4, 100),
        (5, 0, 0),
        (5, 1, 20),
        (5, 2, 40),
        (5, 3, 60),
        (5, 4, 80),
        (5, 5, 100),
        (3, 1, 33),  # round(33.33...) → 33
        (3, 2, 67),  # round(66.66...) → 67
        (0, 0, 0),
        (0, 5, 0),
    ],
)
def test_compute_score(n, true_count, expected):
    assert compute_score(n, true_count) == expected
