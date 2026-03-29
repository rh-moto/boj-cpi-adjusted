# Operations Guide: BOJ CPI Adjusted Pipeline

## Overview

This pipeline reproduces the Bank of Japan's "CPI excluding special factors" by adjusting item-level CPI indices for policy interventions.

**2020-base adjustments (monthly pipeline):**
1. Energy subsidies (gasoline, kerosene, electricity, city gas)
2. Education policy (high school/university tuition waivers, childcare)
3. Mobile phone fee reduction (2021 government-pressured price drop)
4. Travel support (GoTo Travel 2020, National Travel Support 2022-23)

**2015-base adjustments (backtest only):**
5. Consumption tax (8%→10% in Oct 2019) + ECE free (幼保無償化)

### Precision

| Series | Recent 6-month MAE | Full-period MAE |
|---|---|---|
| Core CPI | 0.11pp | 0.18pp |
| Core-core CPI | 0.03pp | 0.10pp |
| BOJ Core | 0.03pp | 0.07pp |

---

## 1. Monthly Update Procedure

### Pre-run checklist

Update these files **before** running the pipeline. The freshness check will warn if any are stale.

#### Always (4 files, every month)

| # | File | Source | What to add |
|---|---|---|---|
| 1 | `gasoline_subsidy_monthly.csv` | [METI PDF p.1](https://nenryo-teigakuhikisage.go.jp/current_graph.pdf) | 1 row: no-subsidy price, retail price, subsidy |
| 2 | `kerosene_subsidy_monthly.csv` | Same PDF p.3 | 1 row: same format |
| 3 | `tepco_fuel_adjustment.csv` | [TEPCO](https://www.tepco.co.jp/ep/private/fuelcost2/newlist/index-j.html) | 1 row: fuel adj with/without subsidy |
| 4 | `tokyo_gas_adjustment.csv` | [selectra](https://selectra.jp/energy/citygas/fuel-cost-adjustment-fee) | 1 row: adj with/without subsidy |

#### When subsidy is active (check monthly)

If electricity or gas subsidies are currently active, confirm the subsidy tables cover the new month:

| # | File | Check |
|---|---|---|
| 5 | `electricity_subsidy.csv` | Does `usage_month_end` cover the current usage month? |
| 6 | `gas_subsidy.csv` | Same check. Extend `usage_month_end` if subsidy continues. |

**Important:** These use **usage month** (not CPI month). The code applies +1 month lag automatically.

#### Optional (for validation)

| # | File | Source |
|---|---|---|
| 7 | `data/boj/cpi_core_indicators.xlsx` | [BOJ Excel](https://www.boj.or.jp/research/research_data/cpi/cpirev.xlsx) (overwrite) |

### CSV formats

**Gasoline/kerosene** (`gasoline_subsidy_monthly.csv`):
```csv
year_month,counterfactual_price,retail_price,subsidy_total
2026-03,208,178,30
```
Read from METI PDF graph. Precision ±2 yen/L.

**TEPCO fuel adjustment** (`tepco_fuel_adjustment.csv`):
```csv
year_month,fuel_adj_with_subsidy,fuel_adj_without_subsidy,subsidy_per_kwh,note
2026-04,-8.93,-8.93,0.0,
```
- `without = with + subsidy_per_kwh`
- Set `subsidy_per_kwh=0` when no subsidy is active

**Tokyo Gas adjustment** (`tokyo_gas_adjustment.csv`):
```csv
year_month,adj_without_subsidy,subsidy_per_m3,adj_with_subsidy,note
2026-04,5.00,0,5.00,selectra
```
- `with = without - subsidy_per_m3`

**Electricity/gas subsidy** (`electricity_subsidy.csv`):
```csv
usage_month_start,usage_month_end,subsidy_yen_per_kwh,note
2026-04,2026-09,3.0,Summer support
```

### Run the pipeline

```bash
source .venv/bin/activate

# Normal run (uses cached CPI data)
python scripts/monthly_update.py

# Re-download CPI data from Statistics Bureau
python scripts/monthly_update.py --refresh
```

### Check output

The script prints MAE against BOJ published values. Expected ranges:
- Core CPI: < 0.2pp
- Core-core / BOJ Core: < 0.1pp

If MAE suddenly increases, check:
1. Data entry errors in CSVs
2. New policy changes not yet captured (see Section 2)
3. Subsidy table not covering the latest month

### Output files

```
output/
  adjusted_cpi_yoy.csv          # Adjusted YoY for 3 series
  fig1_yoy_comparison.png       # YoY: unadjusted vs adjusted vs BOJ
  fig2_residuals.png            # Residuals (adjusted - BOJ)
  fig3_item_adjustments.png     # Item-level adjustment effects
```

---

## 2. Adding New Policy Factors

### 2.1 Education/childcare policy (step adjustment)

**File:** `data/policy_params/policy_events.csv`

Add a row:
```csv
Private HS support increase,8030,,step,2026-04,,X.X,CPI step(81.1->??)
```

**How to determine the step size:**
```python
from src.fetch_cpi import parse_cpi_csv
indices, _ = parse_cpi_csv()
print(indices['8030']['2026-03'])  # Before: e.g., 81.1
print(indices['8030']['2026-04'])  # After:  e.g., 72.0
# step = 81.1 - 72.0 = 9.1
```

No code changes needed. The policy engine reads the CSV automatically.

### 2.2 New travel support program (trend_extend)

```csv
New travel support,9300,,trend_extend,2026-07,2026-12,,Travel support period
```

The engine replaces the support period with trend-extended values from the pre-support year-over-year pattern. If prior-year data is missing from the CPI CSV, it falls back to the long-term time series (`cpi_longterm_2020base.csv`), then to a flat hold at the pre-support month's value.

### 2.3 New mobile/telecom shock (hold_and_step)

```csv
New mobile reform,7430,,hold_and_step,2027-04,2028-03,,Hold period
```

- `effective_from` to `effective_to`: Hold flat at pre-drop level
- After `effective_to`: Fixed step (auto-calculated as pre-drop minus end-of-hold level)
- **Edge case:** If `effective_to` is beyond available data, the engine uses the last available month as a temporary endpoint. The step may change when more data becomes available.

### 2.4 Energy subsidy changes

Edit the subsidy tables directly (not `policy_events.csv`):

| Target | File |
|---|---|
| Electricity subsidy | `electricity_subsidy.csv` |
| City gas subsidy | `gas_subsidy.csv` |
| Gasoline subsidy | `gasoline_subsidy_monthly.csv` (add rows) |
| Kerosene subsidy | `kerosene_subsidy_monthly.csv` (add rows) |

### 2.5 TEPCO rate changes (rare)

**File:** `data/policy_params/tepco_rates.csv`

```csv
effective_from,basic_30a,tier1_limit,tier1_rate,tier2_limit,tier2_rate,tier3_rate,discount,note
2027-04,950.00,120,31.00,300,38.00,42.00,0,Rate revision
```

### 2.6 Renewable energy surcharge (annual, every May)

**File:** `data/policy_params/renew_energy_surcharge.csv`

```csv
effective_from,effective_to,surcharge_per_kwh
2027-05,2028-04,4.50
```

---

## 3. adjustment_type Reference

| Type | Use case | `parameter` | `effective_to` |
|---|---|---|---|
| `step` | One-time level shift (education, childcare) | Step size (positive = add back) | Not used |
| `hold_and_step` | Flat hold then permanent step (mobile) | Auto-calculated | End of hold period |
| `trend_extend` | Replace with trend values (travel support) | Not used | End of support |
| `tax_restore` | Informational only; actual processing in `adjust_gasoline.py` | Restoration amount | Not used |

### base_year column

| Value | Meaning |
|---|---|
| (empty) | Both 2015 and 2020 base |
| `2015` | 2015 base only (e.g., ECE free Oct 2019) |
| `2020` | 2020 base only |

---

## 4. Architecture

### Data flow

```
[Statistics Bureau CSV] → fetch_cpi.py → item-level indices
                                              │
                          ┌───────────────────┤
                          ↓                   ↓
            Energy CSVs → adjust_gasoline.py  policy_events.csv
                          adjust_kerosene.py       ↓
              TEPCO CSV → model_electricity.py  policy_engine.py
          Tokyo Gas CSV → model_gas.py             │
                          │                        │
                          └───────┬────────────────┘
                                  ↓
                           adjusted indices
                                  ↓
                       aggregate.py → weighted avg → YoY
                                  ↓
                     monthly_update.py → BOJ comparison + output
```

### Key modules

| Module | Responsibility |
|---|---|
| `config.py` | Paths, base_year, URL/column mappings |
| `fetch_cpi.py` | Download/parse Statistics Bureau CPI CSV (2015/2020 base) |
| `fetch_boj.py` | Parse BOJ published values Excel (2015/2020 base) |
| `item_master.py` | Item master with classification flags (2015/2020 base) |
| `aggregate.py` | Weighted average, official series lookup |
| `policy_engine.py` | CSV-driven policy event engine (step, hold_and_step, trend_extend) |
| `adjust_gasoline.py` | Gasoline: PDF-based subsidy + provisional tax restoration |
| `adjust_kerosene.py` | Kerosene: PDF-based subsidy |
| `model_electricity.py` | Electricity: TEPCO model P₀ + additive subsidy |
| `model_gas.py` | City gas: Tokyo Gas model P₀ + additive subsidy |
| `adjust_tax.py` | Consumption tax (2015-base backtest only, not in monthly pipeline) |
| `adjust_energy.py` | CPI lag handling for electricity/gas subsidy tables |
| `adjust_education.py` | Legacy; superseded by `policy_engine.py` + `policy_events.csv` |

---

## 5. Data Sources

| Data | URL | Frequency |
|---|---|---|
| CPI item indices | stat.go.jp `.../zmi2020aa.csv` | Monthly |
| CPI long-term series | e-Stat table 4-1 | Monthly |
| BOJ core indicators | boj.or.jp `.../cpirev.xlsx` | Monthly |
| Gasoline/kerosene PDF | nenryo-teigakuhikisage.go.jp | Weekly |
| TEPCO fuel adjustment | tepco.co.jp | Monthly |
| Tokyo Gas adjustment | selectra.jp | Monthly |
| Renewable surcharge | tepco.co.jp (corporate) | Annual (May) |

---

## 6. Known Limitations

1. **Core CPI 2023 bias (-0.28pp):** TEPCO tariff reform (June 2023) created a structural break. The old tariff's fuel adjustment cap artificially suppressed prices.

2. **Mobile phone 2021-22:** BOJ likely uses YoY-based contribution subtraction rather than our index-level approach, causing structural mismatch.

3. **Fixed vs chain weights:** Our aggregation uses fixed base-year weights. The official CPI uses chain weights, causing ~0.3pp divergence by 2026.

4. **Energy sensitivity gap:** TEPCO/Tokyo Gas model P₀ is lower than national average, making model sensitivity ~30% higher than empirical. The additive approach mitigates this (subsidy impact in yen is uniform nationally).

5. **Seasonal survey items in tax adjustment:** The 2015-base consumption tax adjustment doesn't fully handle items whose survey timing shifts the tax change reflection month.

---

## 7. Future: 2025 Base Revision (Expected August 2026)

Required actions when the 2025-base CPI is released:
1. Download new item classification Excel → rebuild item master
2. Create crosswalk CSV (2020→2025)
3. Add `2025` to `config.py` URL/column mappings
4. Update TEPCO/Tokyo Gas rate tables if model formulas change
5. Run full regression test
