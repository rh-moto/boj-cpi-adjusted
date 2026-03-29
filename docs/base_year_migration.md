# Base Year Migration Guide (2025 Base)

The Statistics Bureau is expected to release the 2025-base CPI in August 2026.

## Steps

### 1. config.py — Add 2025 entries

```python
CPI_CSV_URLS[2025] = "https://www.stat.go.jp/data/cpi/2025/csv/zmi2025aa.csv"
CPI_CSV_FILENAMES[2025] = "cpi_monthly_2025.csv"
BOJ_SERIES_COLS[2025] = {
    "core_ex_special": TBD,  # Check BOJ Excel column positions
    "core_core_ex_special": TBD,
    "boj_core_ex_special": TBD,
}
```

### 2. Item master

Add a 2025 schema to `SCHEMAS` in `scripts/build_item_master.py`. Download the 2025-base item classification Excel and check column structure (item code column, weight column, flag columns may shift).

```bash
python scripts/build_item_master.py --2025
```

### 3. item_master.py — Add path

```python
ITEM_MASTER_PATHS[2025] = POLICY_DIR / "item_master_2025.csv"
```

### 4. Crosswalk

Create `data/policy_params/crosswalk_2020_2025.csv` (same format as existing crosswalk). Check:
- Which item codes changed, merged, or were added
- Special factor items in particular: 7301 (gasoline), 3500 (electricity), 3600 (city gas), 3701 (kerosene), 7430 (mobile), 9300 (hotel), education items

### 5. Policy events

Review `data/policy_params/policy_events.csv`:
- Rows with empty `base_year` → automatically apply to 2025 base too
- Add `base_year=2025` rows if there are 2025-base-specific events
- Verify item codes haven't changed

### 6. Energy model P₀ recalculation

If TEPCO or Tokyo Gas tariff structures change:
- Update `tepco_rates.csv`
- Recalculate P₀ (model_electricity.py `compute_p0()`, model_gas.py `compute_p0()`)
- CPI model formula (usage patterns, number of companies) may also change

### 7. Test

```bash
python scripts/build_item_master.py --2025
python -m pytest tests/
# Add test_load_item_master_2025 and test_parse_cpi_csv_2025 to test_pipeline.py
```

## Already handled automatically

| Component | Status |
|---|---|
| `parse_cpi_csv(base_year=2025)` | Works if URL is set and CSV format is unchanged |
| `parse_boj(base_year=2025)` | Works if column mapping is set |
| `build_adjusted_indices(indices, base_year=2025)` | Works if item codes match |
| `apply_all_events(indices, base_year=2025)` | Filters by base_year column |
| `apply_tax_adjustment()` | Works if item codes match |

## Risks

- CPI calculation methodology may change (full chain-linking, new model formulas)
- Item codes may change significantly (more merging/splitting than 2015→2020)
- Energy model pricing may require new rate tables
- Statistics Bureau methodology document expected ~June 2026
