"""Smoke tests for the monthly update pipeline."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_parse_cpi_csv_2020():
    from src.fetch_cpi import parse_cpi_csv, get_fixed_weights

    indices, meta = parse_cpi_csv(base_year=2020)
    weights = get_fixed_weights(meta)

    assert indices.shape[0] >= 60, "Should have at least 60 months"
    assert indices.shape[1] >= 700, "Should have at least 700 columns"
    assert indices.index[0] == "2020-01"
    assert "7301" in indices.columns, "Gasoline should exist"
    assert "3500" in indices.columns, "Electricity should exist"
    assert weights["0001"] == 10000, "Total weight should be 10000"


def test_parse_cpi_csv_2015():
    from src.fetch_cpi import parse_cpi_csv

    indices, meta = parse_cpi_csv(base_year=2015)

    assert indices.index[0] == "2015-01"
    assert indices.index[-1] >= "2021-01"
    assert "7301" in indices.columns


def test_load_item_master_2020():
    from src.item_master import load_item_master

    master = load_item_master(base_year=2020)

    assert len(master) == 582
    assert master["weight_per_10000"].sum() in range(9990, 10010)
    assert master["is_energy"].sum() == 5
    assert "7301" in master["item_code"].values


def test_load_item_master_2015():
    from src.item_master import load_item_master

    master = load_item_master(base_year=2015)

    assert len(master) == 585
    assert master["weight_per_10000"].sum() in range(10000, 10020)
    assert "8080" in master["item_code"].values, "2015 should have kindergarten"
    assert "8090" in master["item_code"].values


def test_parse_boj_2020():
    from src.fetch_boj import parse_boj

    boj = parse_boj(base_year=2020)

    assert "core_ex_special" in boj
    assert "core_core_ex_special" in boj
    assert "boj_core_ex_special" in boj
    assert len(boj["core_ex_special"]) >= 50


def test_parse_boj_2015():
    from src.fetch_boj import parse_boj

    boj = parse_boj(base_year=2015)

    assert "core_ex_special" in boj
    assert len(boj["core_ex_special"]) >= 30


def test_build_adjusted_indices():
    """Smoke test: build_adjusted_indices runs without error."""
    from src.fetch_cpi import parse_cpi_csv
    from scripts.monthly_update import build_adjusted_indices

    indices, _ = parse_cpi_csv(base_year=2020)
    adj = build_adjusted_indices(indices)

    assert adj.shape == indices.shape
    # Gasoline should be adjusted (higher than original in subsidy period)
    assert adj.loc["2022-06", "7301"] > indices.loc["2022-06", "7301"]
    # Electricity should be adjusted in subsidy period
    assert adj.loc["2023-03", "3500"] > indices.loc["2023-03", "3500"]


def test_pipeline_output_precision():
    """Check that MAE against BOJ is within expected range."""
    from src.fetch_cpi import parse_cpi_csv, get_fixed_weights
    from src.fetch_boj import parse_boj
    from src.item_master import load_item_master
    from src.aggregate import compute_weighted_index, compute_yoy
    from scripts.monthly_update import build_adjusted_indices

    indices, meta = parse_cpi_csv(base_year=2020)
    weights = get_fixed_weights(meta)
    master = load_item_master(base_year=2020)
    boj = parse_boj(base_year=2020)

    adj = build_adjusted_indices(indices)

    for series_name, boj_name, max_mae in [
        ("core", "core_ex_special", 0.25),
        ("core_core", "core_core_ex_special", 0.15),
        ("boj_core", "boj_core_ex_special", 0.15),
    ]:
        computed = compute_weighted_index(adj, weights, series_name, master)
        yoy = compute_yoy(computed)
        boj_s = boj[boj_name]
        common = sorted(set(yoy.index) & set(boj_s.index))[-6:]
        mae = sum(abs(yoy[ym] - boj_s[ym]) for ym in common) / len(common)
        assert mae < max_mae, f"{series_name} MAE={mae:.2f} exceeds {max_mae}"
