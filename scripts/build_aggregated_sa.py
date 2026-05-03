"""品目別季節調整済指数から階層型集計指数を構築

入力:
- output/cpi_item_adjusted_long_sa.csv (品目別SA、2020基準スケール)
- data/policy_params/item_master.csv (2020基準分類・ウエイト)

階層: 小分類(81) → 中分類(49) → 10大費目(10) → 総合

出力: output/cpi_aggregated_sa_long.csv
columns: ym, total, [10大費目10列], [中分類49列], [小分類81列]
prefixed: total / 10:<name> / mid:<name> / small:<name>

集計式: 加重平均 (item-level SA × weight) / sum(weight)
NaN処理: 利用可能な品目のみ使用（重み比例配分）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src.config import OUTPUT_DIR


def weighted_aggregate(sub: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """加重平均 (NaN対応): 各月で利用可能な品目だけで再正規化"""
    w = weights.reindex(sub.columns).values.astype(float)
    mask = sub.notna()
    w_mat = np.broadcast_to(w[None, :], sub.shape)
    num = (sub.fillna(0).values * w_mat).sum(axis=1)
    denom = (mask.values * w_mat).sum(axis=1)
    res = np.where(denom > 0, num / denom, np.nan)
    return pd.Series(res, index=sub.index)


def main():
    sa = pd.read_csv('output/cpi_item_adjusted_long_sa.csv').set_index('ym').apply(pd.to_numeric, errors='coerce')
    master = pd.read_csv('data/policy_params/item_master.csv', dtype={'item_code': str})
    print(f"SA shape: {sa.shape}, item_master {len(master)} 品目")

    # 集計対象は item_code が SA 列に存在するもの
    master = master[master['item_code'].isin(sa.columns)].copy()
    print(f"  SAに存在する品目: {len(master)}")

    weights = master.set_index('item_code')['weight_per_10000'].astype(float)

    out = pd.DataFrame(index=sa.index)

    # 総合 (全品目)
    codes = master['item_code'].tolist()
    out['total'] = weighted_aggregate(sa[codes], weights)

    # 10大費目
    for cat, grp in master.groupby('category_10'):
        codes = grp['item_code'].tolist()
        out[f'10:{cat}'] = weighted_aggregate(sa[codes], weights)

    # 中分類
    for cat, grp in master.groupby('category_mid'):
        codes = grp['item_code'].tolist()
        out[f'mid:{cat}'] = weighted_aggregate(sa[codes], weights)

    # 小分類
    for cat, grp in master.groupby('category_small'):
        codes = grp['item_code'].tolist()
        out[f'small:{cat}'] = weighted_aggregate(sa[codes], weights)

    out_path = OUTPUT_DIR / 'cpi_aggregated_sa_long.csv'
    out.reset_index().to_csv(out_path, index=False, float_format='%.4f')
    print(f"\n保存: {out_path}  shape={out.shape}")
    print(f"  総合 1列 + 10大費目 {sum(c.startswith('10:') for c in out.columns)} + "
          f"中分類 {sum(c.startswith('mid:') for c in out.columns)} + "
          f"小分類 {sum(c.startswith('small:') for c in out.columns)} 列")

    # サンプル: 直近の総合と10大費目
    print("\n=== 直近6ヶ月 総合・10大費目 ===")
    cols = ['total'] + sorted([c for c in out.columns if c.startswith('10:')])
    print(out[cols].tail(6).to_string(float_format='%.2f'))


if __name__ == '__main__':
    main()
