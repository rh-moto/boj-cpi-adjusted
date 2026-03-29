# Refactoring Plan

## Commit order (smallest risk first)

### Commit 1: Add tests
- Smoke test for `monthly_update.py` (runs without error, outputs expected columns)
- Regression tests for both base years (`parse_cpi_csv`, `load_item_master`, `apply_all_events`)
- Unit tests for `policy_engine.py` (step, hold_and_step, trend_extend)
- Unit tests for energy subsidy CPI lag helper
- Builder tests (row counts, key item codes, weight sum)

### Commit 2: Extract shared pipeline function
- Move `build_adjusted_indices()` from `monthly_update.py` into `src/pipeline.py`
- Have both `monthly_update.py` and `plot_results.py` call it
- Eliminates duplicated adjustment assembly logic

### Commit 3: Extract energy subsidy helper
- Move `get_monthly_subsidy_by_cpi_month()` from `adjust_energy.py` to `src/energy_subsidy.py`
- Update imports in `model_electricity.py` and `model_gas.py`
- Delete `adjust_energy.py`

### Commit 4: Delete superseded modules
- Delete `src/adjust_education.py` (replaced by policy_engine)
- Delete `src/adjust_interpolation.py` (replaced by policy_engine)
- Remove stale references in `monthly_update.py` comments and docs

### Commit 5: Merge item master builders
- Extract shared logic into `scripts/build_item_master_common.py`
- Thin wrappers for 2020 and 2015 (or single script with `--base-year` arg)

### Commit 6: Delete unused files
- `src/fetch_weights.py` (unused, fixed weights from CSV headers)
- `data/policy_params/gasoline_subsidy.csv` (old daily format, replaced by monthly)
- Move `scripts/run_phase0.py` and `scripts/explore_estat.py` to `scripts/dev/`

### Commit 7: Clean up docs
- Update CLAUDE.md to match current architecture
- Remove references to deleted modules
- Verify operations_guide.md is up to date

## Files to delete
- `src/adjust_education.py`
- `src/adjust_interpolation.py`
- `src/adjust_energy.py`
- `src/fetch_weights.py`
- `data/policy_params/gasoline_subsidy.csv`

## Files to merge
- `scripts/build_item_master.py` + `build_item_master_2015.py` → shared core
- `monthly_update.py` + `plot_results.py` → shared `src/pipeline.py`
- `adjust_energy.py` (surviving helper) → `src/energy_subsidy.py`

## Files to create
- `src/pipeline.py` (shared adjusted index assembly)
- `src/energy_subsidy.py` (CPI lag helper)
- `tests/test_pipeline.py`
- `tests/test_policy_engine.py`
- `tests/test_energy_subsidy.py`
- `tests/test_item_master.py`
