"""Shared pipeline: build adjusted indices from raw CPI data.

Used by both monthly_update.py and plot_results.py.
"""

import pandas as pd

from src.adjust_gasoline import compute_adjusted_index as adjust_gasoline
from src.adjust_kerosene import compute_adjusted_index as adjust_kerosene
from src.model_electricity import compute_adjusted_index as adjust_electricity
from src.model_gas import compute_adjusted_index as adjust_gas
from src.policy_engine import apply_all_events


def build_adjusted_indices(
    indices: pd.DataFrame,
    base_year: int | None = None,
) -> pd.DataFrame:
    """Apply all special-factor adjustments to item-level CPI indices.

    Args:
        indices: Raw item-level CPI index DataFrame
        base_year: 2015 or 2020 (None = config default)

    Returns:
        Adjusted indices DataFrame (same shape as input)
    """
    adj = indices.copy()

    # Energy (CSV-driven, dedicated modules)
    if "7301" in adj.columns:
        adj["7301"] = adjust_gasoline(indices["7301"])
    if "3701" in adj.columns:
        adj["3701"] = adjust_kerosene(indices["3701"])
    if "3500" in adj.columns:
        adj["3500"] = adjust_electricity(indices["3500"])
    if "3600" in adj.columns:
        adj["3600"] = adjust_gas(indices["3600"])

    # Education, mobile, travel, tax_restore (policy_events.csv driven)
    adj = apply_all_events(adj, base_year=base_year)

    return adj
