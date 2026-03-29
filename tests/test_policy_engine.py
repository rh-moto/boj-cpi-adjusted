"""Unit tests for policy_engine.py adjustment types."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.policy_engine import apply_step, apply_hold_and_step, apply_trend_extend


def _make_series(values, start="2020-01"):
    """Helper: create a monthly CPI-like Series."""
    months = [f"{int(start[:4]) + (int(start[5:7]) - 1 + i) // 12}-{((int(start[5:7]) - 1 + i) % 12) + 1:02d}"
              for i in range(len(values))]
    return pd.Series(values, index=months, name="TEST")


class TestStep:
    def test_basic_step(self):
        s = _make_series([100.0] * 12, "2024-01")
        events = pd.DataFrame([{
            "effective_from": "2024-04",
            "effective_to": "",
            "parameter": "5.0",
        }])
        result = apply_step(s, events)
        assert result["2024-03"] == 100.0  # Before: unchanged
        assert result["2024-04"] == 105.0  # After: +5
        assert result["2024-12"] == 105.0  # Persists

    def test_cumulative_steps(self):
        s = _make_series([100.0] * 12, "2024-01")
        events = pd.DataFrame([
            {"effective_from": "2024-04", "effective_to": "", "parameter": "5.0"},
            {"effective_from": "2024-07", "effective_to": "", "parameter": "3.0"},
        ])
        result = apply_step(s, events)
        assert result["2024-06"] == 105.0  # First step only
        assert result["2024-07"] == 108.0  # Both steps


class TestHoldAndStep:
    def test_basic_hold(self):
        values = [100.0, 100.0, 100.0, 60.0, 55.0, 50.0, 50.0, 50.0, 50.0, 51.0, 51.0, 51.0]
        s = _make_series(values, "2021-01")
        events = pd.DataFrame([{
            "effective_from": "2021-04",
            "effective_to": "2021-09",
            "parameter": "",
        }])
        result = apply_hold_and_step(s, events)
        # Hold period: should be at pre-drop level (2021-03 = 100.0)
        assert result["2021-04"] == 100.0
        assert result["2021-09"] == 100.0
        # After hold: step = 100 - 50 = 50
        assert result["2021-10"] == 51.0 + 50.0  # 101.0

    def test_effective_to_beyond_data(self):
        values = [100.0, 100.0, 100.0, 60.0, 55.0, 50.0]
        s = _make_series(values, "2021-01")
        events = pd.DataFrame([{
            "effective_from": "2021-04",
            "effective_to": "2022-03",  # Beyond data range
            "parameter": "",
        }])
        result = apply_hold_and_step(s, events)
        # Should fall back to last available month
        assert result["2021-04"] == 100.0
        assert result["2021-06"] == 100.0


class TestTrendExtend:
    def test_with_prior_year(self):
        # 2 years of data, support in year 2
        values_y1 = [100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 112.0, 120.0, 115.0, 110.0, 108.0, 106.0]
        values_y2 = [105.0, 107.0, 109.0, 111.0, 113.0, 115.0, 117.0, 80.0, 75.0, 70.0, 72.0, 105.0]
        s = _make_series(values_y1 + values_y2, "2021-01")
        events = pd.DataFrame([{
            "effective_from": "2022-08",
            "effective_to": "2022-12",
            "parameter": "",
        }])
        result = apply_trend_extend(s, events)
        # Support months should be replaced with estimated values
        assert result["2022-07"] == 117  # Before support: unchanged
        assert result["2022-08"] != 80   # Should be adjusted
        assert result["2022-08"] > 100   # Should be higher than actual
