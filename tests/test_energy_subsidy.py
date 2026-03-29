"""Unit tests for energy subsidy CPI lag handling."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adjust_energy import get_monthly_subsidy_by_cpi_month


class TestCPILag:
    def test_electricity_lag(self):
        """Electricity subsidy should be shifted +1 month (usage → CPI)."""
        sub = get_monthly_subsidy_by_cpi_month("electricity")
        # Usage month 2023-01 (7 yen) → CPI month 2023-02
        assert sub.get("2023-01", 0) == 0, "2023-01 CPI should have no subsidy (usage 2022-12)"
        assert sub.get("2023-02", 0) == 7.0, "2023-02 CPI should reflect usage 2023-01 subsidy"

    def test_gas_lag(self):
        """Gas subsidy should be shifted +1 month."""
        sub = get_monthly_subsidy_by_cpi_month("gas")
        assert sub.get("2023-02", 0) == 30.0, "2023-02 CPI should reflect usage 2023-01 gas subsidy"

    def test_zero_subsidy_period(self):
        """No subsidy → no entry or zero."""
        sub = get_monthly_subsidy_by_cpi_month("electricity")
        # Usage 2024-05 to 2024-07 = 0 → CPI 2024-06 to 2024-08 = 0
        assert sub.get("2024-07", 0) == 0

    def test_subsidy_end_boundary(self):
        """Subsidy should stop at the correct CPI month."""
        sub = get_monthly_subsidy_by_cpi_month("electricity")
        # Usage 2023-08 = 7.0 (last month of first subsidy) → CPI 2023-09
        assert sub.get("2023-09", 0) == 7.0
        # Usage 2023-09 = 3.5 (phase-down) → CPI 2023-10
        assert sub.get("2023-10", 0) == 3.5
