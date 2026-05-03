"""集計系列(core/core_core/boj_core)の前年比を3基準で接続して長期時系列CSVを出力

接続方針:
- 1991-01 〜 2015-12: 総務省公表 tax_adjusted.xlsx (1990-2019, 既にtax-adjusted済aggregate)
- 2016-01 〜 2020-12: 2015基準パイプライン our-estimates
- 2021-01 〜 最新月: 2020基準パイプライン our-estimates

出力: output/cpi_aggregate_yoy_long.csv
  columns: ym, core_yoy, core_core_yoy, boj_core_yoy, source
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.adjust_tax import apply_tax_adjustment
from src.aggregate import compute_weighted_index, compute_yoy
from src.config import OUTPUT_DIR
from src.fetch_cpi import parse_cpi_csv, get_fixed_weights
from src.item_master import load_item_master
from src.pipeline import build_adjusted_indices


SERIES = ['core', 'core_core', 'boj_core']


def yoy_from_taxadj_xlsx() -> dict[str, pd.Series]:
    """tax_adjusted.xlsx から集計系列の前年比を計算"""
    tax = pd.read_excel('data/soumu/tax_adjusted.xlsx', sheet_name='zmi', header=None)
    data = tax.iloc[6:].copy()
    # cols: 0=ym, 1=all, 2=core(161), 3=less_imp(163), 4=less_imp_fresh(166), 5=core_core(178), 6=boj_core(168)
    data.columns = ['ym_raw', 'all', 'core', 'less_imp', 'less_imp_fresh', 'core_core', 'boj_core']
    data['ym'] = data['ym_raw'].astype(str).str[:4] + '-' + data['ym_raw'].astype(str).str[4:]
    data = data.set_index('ym')
    out = {}
    for s in SERIES:
        s_idx = pd.to_numeric(data[s], errors='coerce')
        out[s] = compute_yoy(s_idx)
    return out


def yoy_from_pipeline(base_year: int) -> dict[str, pd.Series]:
    indices, meta = parse_cpi_csv(base_year=base_year)
    weights = get_fixed_weights(meta)
    master = load_item_master(base_year=base_year)

    adj = indices.copy()
    if base_year == 2015:
        adj = apply_tax_adjustment(adj, master['item_code'].tolist(), master)
    adj = build_adjusted_indices(adj, base_year=base_year)

    return {s: compute_yoy(compute_weighted_index(adj, weights, s, master)) for s in SERIES}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading tax_adjusted.xlsx (1990-2019)...")
    yoy_taxadj = yoy_from_taxadj_xlsx()

    print("Building 2015-base pipeline YoY...")
    yoy_15 = yoy_from_pipeline(2015)

    print("Building 2020-base pipeline YoY...")
    yoy_20 = yoy_from_pipeline(2020)

    # Splice
    rows = []
    all_ym = sorted(set(yoy_taxadj['core'].index) | set(yoy_15['core'].index) | set(yoy_20['core'].index))
    for ym in all_ym:
        if ym < '1991-01':
            continue
        if ym <= '2015-12':
            src = '2010base_taxadj_xlsx'
            vals = {s: yoy_taxadj[s].get(ym) for s in SERIES}
        elif ym <= '2020-12':
            src = '2015base_pipeline'
            vals = {s: yoy_15[s].get(ym) for s in SERIES}
        else:
            src = '2020base_pipeline'
            vals = {s: yoy_20[s].get(ym) for s in SERIES}
        if all(pd.notna(vals[s]) for s in SERIES) is False:
            # 部分的に欠損する場合もそのまま出す (NaNで)
            pass
        rows.append({'ym': ym, **{f'{s}_yoy': vals[s] for s in SERIES}, 'source': src})

    df = pd.DataFrame(rows)
    out_path = OUTPUT_DIR / 'cpi_aggregate_yoy_long.csv'
    df.to_csv(out_path, index=False, float_format='%.4f')
    print(f"\n保存: {out_path}")
    print(f"  期間: {df['ym'].iloc[0]}〜{df['ym'].iloc[-1]}, {len(df)} ヶ月")
    print(f"  source構成:")
    print(df['source'].value_counts().to_string())

    print("\n=== 接続境界サンプル ===")
    for boundary in ['2015-12', '2016-01', '2020-12', '2021-01']:
        row = df[df['ym'] == boundary]
        if not row.empty:
            r = row.iloc[0]
            print(f"  {boundary} [{r['source']}]: core={r['core_yoy']:.2f}  core_core={r['core_core_yoy']:.2f}  boj_core={r['boj_core_yoy']:.2f}")


if __name__ == '__main__':
    main()
