"""Tests for days → Jira time-tracking string conversion."""

import pytest

from delivery_runtime.jira.estimation_format import days_to_jira_estimate


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (1.0, "1d"),
        (0.5, "4h"),
        (1.5, "1d 4h"),
        (0.25, "2h"),
        (2.0, "2d"),
        (3.75, "3d 6h"),
        (0.125, "1h"),
    ],
)
def test_days_to_jira_estimate(days, expected):
    assert days_to_jira_estimate(days) == expected


def test_rounds_up_to_minimum_one_hour():
    assert days_to_jira_estimate(0.01) == "1h"


def test_rejects_non_positive():
    with pytest.raises(ValueError):
        days_to_jira_estimate(0)
    with pytest.raises(ValueError):
        days_to_jira_estimate(-1.0)
