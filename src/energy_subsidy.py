"""Energy subsidy CSV loading with CPI lag handling.

Reads electricity_subsidy.csv and gas_subsidy.csv (usage-month basis)
and converts to CPI-month basis by applying +1 month lag.
"""

import pandas as pd

from src.config import POLICY_DIR

CPI_LAG_MONTHS = 1


def _shift_month(ym: str, delta: int) -> str:
    """Shift YYYY-MM by delta months."""
    y, m = int(ym[:4]), int(ym[5:7])
    m += delta
    while m > 12:
        y += 1
        m -= 12
    while m <= 0:
        y -= 1
        m += 12
    return f"{y:04d}-{m:02d}"


def load_subsidy_table(kind: str) -> pd.DataFrame:
    """Load subsidy table CSV.

    Args:
        kind: "electricity" or "gas"
    """
    if kind == "electricity":
        path = POLICY_DIR / "electricity_subsidy.csv"
    elif kind == "gas":
        path = POLICY_DIR / "gas_subsidy.csv"
    else:
        raise ValueError(f"Unknown kind: {kind}")
    return pd.read_csv(path)


def get_monthly_subsidy_by_cpi_month(kind: str) -> pd.Series:
    """Convert usage-month subsidy to CPI-month basis (+1 month lag).

    Args:
        kind: "electricity" or "gas"

    Returns:
        Monthly subsidy Series (index=YYYY-MM, CPI month basis)
    """
    df = load_subsidy_table(kind)
    col = "subsidy_yen_per_kwh" if kind == "electricity" else "subsidy_yen_per_m3"

    records = {}
    for _, row in df.iterrows():
        start = pd.Period(row["usage_month_start"], freq="M")
        end = pd.Period(row["usage_month_end"], freq="M")
        for period in pd.period_range(start, end, freq="M"):
            usage_ym = str(period)
            cpi_ym = _shift_month(usage_ym, CPI_LAG_MONTHS)
            records[cpi_ym] = row[col]

    return pd.Series(records, name=f"subsidy_{kind}")
