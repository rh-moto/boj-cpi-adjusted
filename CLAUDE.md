# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pipeline to reproduce the Bank of Japan's "CPI excluding special factors" (特殊要因を除いたCPI). Supports both 2015-base and 2020-base CPI.

Target series: Core CPI, Core-core CPI, BOJ Core (excl. food & energy)

Special factors: Energy subsidies, education policy, mobile fee reduction, travel support, consumption tax (2015-base)

## Development

```bash
source .venv/bin/activate
python scripts/monthly_update.py       # Monthly pipeline
python scripts/monthly_update.py --refresh  # Re-download CPI data
pytest                                  # Run tests (17 tests)
ruff check src/                         # Lint
```

## Architecture

```
src/
  config.py            # Paths, base_year, URLs
  pipeline.py          # Shared: build_adjusted_indices()
  fetch_cpi.py         # Statistics Bureau CPI CSV parser (2015/2020)
  fetch_boj.py         # BOJ published values parser (2015/2020)
  item_master.py       # Item master with classification flags (2015/2020)
  aggregate.py         # Weighted average, official series lookup
  policy_engine.py     # CSV-driven policy event engine
  energy_subsidy.py    # CPI lag handling for electricity/gas
  adjust_gasoline.py   # Gasoline: PDF subsidy + provisional tax
  adjust_kerosene.py   # Kerosene: PDF subsidy
  model_electricity.py # Electricity: TEPCO model + additive subsidy
  model_gas.py         # City gas: Tokyo Gas model + additive subsidy
  adjust_tax.py        # Consumption tax (2015-base only)
  validate.py          # Validation helpers

scripts/
  monthly_update.py       # Monthly pipeline entry point
  plot_results.py         # Generate comparison charts
  build_item_master.py    # Generate 2020-base item master CSV
  build_item_master_2015.py  # Generate 2015-base item master CSV
  build_gasoline_subsidy.py  # Generate gasoline subsidy CSV

data/policy_params/       # Policy parameter CSVs (git-tracked)
  policy_events.csv       # Education, mobile, travel events
  electricity_subsidy.csv # Electricity subsidy by usage month
  gas_subsidy.csv         # Gas subsidy by usage month
  gasoline_subsidy_monthly.csv  # Gasoline subsidy (PDF graph)
  kerosene_subsidy_monthly.csv  # Kerosene subsidy (PDF graph)
  tepco_fuel_adjustment.csv     # TEPCO monthly fuel adjustment
  tokyo_gas_adjustment.csv      # Tokyo Gas monthly adjustment
  tepco_rates.csv               # TEPCO tariff table
  renew_energy_surcharge.csv    # Renewable energy surcharge
  tax_category_2019.csv         # Consumption tax classification
  item_master.csv               # 2020-base item master (582 items)
  item_master_2015.csv          # 2015-base item master (585 items)
  crosswalk_2015_2020.csv       # Item code crosswalk
```

## Key Design Decisions

- **Item codes differ from work plan**: Gasoline=7301, City gas=3600, Mobile=7430, Hotel=9300. See `item_master.py` SPECIAL_FACTOR_ITEMS.
- **Kindergarten tuition gone in 2020-base**: ECE free already in base period. Exists in 2015-base (8080/8090).
- **Official aggregate series for unadjusted**: Fixed-weight aggregation diverges ~0.3pp from official. Use CSV official values (0161, 0178, 0168).
- **No calibration against BOJ**: BOJ values are for validation only. Parameters are set independently.
- **Energy: additive method**: `adjusted = CPI + subsidy × usage / P₀ × 100`. Ratio method causes distortion at tariff transitions.
- **Policy events are CSV-driven**: Add a row to `policy_events.csv` for new policies. No code changes needed.

## Monthly Update

See `docs/operations_guide.md` for detailed procedure. In brief:
1. Update 4 CSVs (gasoline, kerosene, TEPCO fuel adj, Tokyo Gas adj)
2. Check electricity/gas subsidy tables if subsidy is active
3. Run `python scripts/monthly_update.py --refresh`

## Docs

- `docs/operations_guide.md` — Full operations guide
- `docs/refactoring_plan.md` — Refactoring roadmap
- `boj_cpi_workplan_v2.md` — Original work plan
- `workplan_2015base.md` — 2015-base expansion plan
