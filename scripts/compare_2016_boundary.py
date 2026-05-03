"""2016-01 接続境界での 総務省・BOJ・我々の推計の前年比比較

出力: output/compare_2016_boundary.csv
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.adjust_tax import apply_tax_adjustment
from src.aggregate import compute_weighted_index, compute_yoy
from src.config import OUTPUT_DIR
from src.fetch_boj import parse_boj
from src.fetch_cpi import parse_cpi_csv, get_fixed_weights
from src.item_master import load_item_master
from src.pipeline import build_adjusted_indices

SERIES = ['core', 'core_core', 'boj_core']
BOJ_KEY = {'core': 'core_ex_special', 'core_core': 'core_core_ex_special', 'boj_core': 'boj_core_ex_special'}


def yoy_taxadj():
    tax = pd.read_excel('data/soumu/tax_adjusted.xlsx', sheet_name='zmi', header=None)
    data = tax.iloc[6:].copy()
    data.columns = ['ym_raw', 'all', 'core', 'less_imp', 'less_imp_fresh', 'core_core', 'boj_core']
    data['ym'] = data['ym_raw'].astype(str).str[:4] + '-' + data['ym_raw'].astype(str).str[4:]
    data = data.set_index('ym')
    return {s: compute_yoy(pd.to_numeric(data[s], errors='coerce')) for s in SERIES}


def yoy_pipeline_2015():
    indices, meta = parse_cpi_csv(base_year=2015)
    weights = get_fixed_weights(meta)
    master = load_item_master(base_year=2015)
    adj = apply_tax_adjustment(indices, master['item_code'].tolist(), master)
    adj = build_adjusted_indices(adj, base_year=2015)
    return {s: compute_yoy(compute_weighted_index(adj, weights, s, master)) for s in SERIES}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    soumu = yoy_taxadj()
    ours = yoy_pipeline_2015()
    boj = parse_boj(base_year=2015)

    rows = []
    period = pd.date_range('2015-01', '2017-12', freq='MS').strftime('%Y-%m').tolist()
    for ym in period:
        row = {'ym': ym}
        for s in SERIES:
            sm = soumu[s].get(ym)
            ou = ours[s].get(ym)
            bo = boj.get(BOJ_KEY[s], pd.Series()).get(ym)
            row[f'{s}_soumu'] = sm
            row[f'{s}_ours'] = ou
            row[f'{s}_boj'] = bo
            row[f'{s}_ours-soumu'] = (ou - sm) if pd.notna(ou) and pd.notna(sm) else None
            row[f'{s}_ours-boj'] = (ou - bo) if pd.notna(ou) and pd.notna(bo) else None
        rows.append(row)
    df = pd.DataFrame(rows)
    out_path = OUTPUT_DIR / 'compare_2016_boundary.csv'
    df.to_csv(out_path, index=False, float_format='%.3f')
    print(f"保存: {out_path}\n")

    # 表示用に整形
    for s in SERIES:
        print(f"\n=== {s} (前年比 %) ===")
        cols = ['ym', f'{s}_soumu', f'{s}_ours', f'{s}_boj', f'{s}_ours-soumu', f'{s}_ours-boj']
        sub = df[cols].copy()
        sub.columns = ['ym', '総務省公表', '我々の推計', '日銀公表', '我々-総務省', '我々-日銀']
        print(sub.to_string(index=False, float_format='%.2f'))


if __name__ == '__main__':
    main()
