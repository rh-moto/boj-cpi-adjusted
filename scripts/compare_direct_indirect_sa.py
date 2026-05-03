"""直接SA vs 間接SA の比較

- 間接SA (現状): 品目別X-13 → 加重平均 (cpi_aggregated_sa_long.csv に保存済)
- 直接SA: 品目別を加重平均 → X-13 をその集計系列に適用

代表カテゴリで両方を計算し、差を集計。
出力: output/compare_direct_indirect_sa.csv
"""

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src.config import OUTPUT_DIR

warnings.filterwarnings('ignore')

X13_PATH = '/Users/rhashimoto/.local/bin/x13as'

TARGETS = [
    ('total', None, None),  # 総合
    ('10:食料', 'category_10', '食料'),
    ('10:被服及び履物', 'category_10', '被服及び履物'),
    ('10:交通・通信', 'category_10', '交通・通信'),
    ('10:教養娯楽', 'category_10', '教養娯楽'),
]


def weighted_aggregate(sub: pd.DataFrame, weights: pd.Series) -> pd.Series:
    w = weights.reindex(sub.columns).values.astype(float)
    mask = sub.notna()
    w_mat = np.broadcast_to(w[None, :], sub.shape)
    num = (sub.fillna(0).values * w_mat).sum(axis=1)
    denom = (mask.values * w_mat).sum(axis=1)
    return pd.Series(np.where(denom > 0, num / denom, np.nan), index=sub.index)


def direct_x13(s: pd.Series) -> pd.Series | None:
    from statsmodels.tsa.x13 import x13_arima_analysis
    s = s.dropna()
    if len(s) < 36 or (s <= 0).any():
        return None
    s.index = pd.PeriodIndex(s.index, freq='M').to_timestamp()
    for start in [None, '1985-01', '1995-01', '2000-01']:
        s2 = s if start is None else s[s.index >= start]
        if len(s2) < 36:
            continue
        try:
            res = x13_arima_analysis(s2, x12path=X13_PATH, prefer_x13=True, outlier=False)
            return res.seasadj
        except Exception:
            continue
    return None


def yoy(s: pd.Series) -> pd.Series:
    return ((s / s.shift(12)) - 1) * 100


def main():
    raw = pd.read_csv('output/cpi_item_adjusted_long.csv').set_index('ym').apply(pd.to_numeric, errors='coerce')
    indirect = pd.read_csv('output/cpi_aggregated_sa_long.csv').set_index('ym').apply(pd.to_numeric, errors='coerce')
    master = pd.read_csv('data/policy_params/item_master.csv', dtype={'item_code': str})
    master = master[master['item_code'].isin(raw.columns)].copy()
    weights = master.set_index('item_code')['weight_per_10000'].astype(float)
    print(f"raw shape: {raw.shape}, master {len(master)} 品目")

    rows = []
    for label, group_col, group_val in TARGETS:
        # 集計対象品目
        if group_col is None:
            codes = master['item_code'].tolist()
        else:
            codes = master[master[group_col] == group_val]['item_code'].tolist()
        codes = [c for c in codes if c in raw.columns]
        print(f"\n=== {label} ({len(codes)} 品目) ===")

        # 直接SA: 集計後X-13
        agg_raw = weighted_aggregate(raw[codes], weights)
        direct = direct_x13(agg_raw)
        if direct is not None:
            direct.index = direct.index.strftime('%Y-%m')
            direct = direct.reindex(raw.index)

        # 間接SA: 既存
        ind = indirect[label] if label in indirect.columns else None

        if direct is None or ind is None:
            print('  欠損あり、スキップ')
            continue

        # YoY比較
        yoy_d = yoy(direct)
        yoy_i = yoy(ind)
        diff_yoy = (yoy_d - yoy_i).dropna()
        diff_lvl = (direct - ind).dropna()

        # 統計
        print(f"  Level 差: 平均 {diff_lvl.mean():+.3f}, std {diff_lvl.std():.3f}, |max| {diff_lvl.abs().max():.3f}")
        print(f"  YoY 差 (pp): 平均 {diff_yoy.mean():+.3f}, std {diff_yoy.std():.3f}, |max| {diff_yoy.abs().max():.3f}")

        # 直近6ヶ月サンプル
        recent_ym = ['2025-10','2025-11','2025-12','2026-01','2026-02','2026-03']
        for ym in recent_ym:
            if ym in raw.index:
                rows.append({
                    'category': label, 'ym': ym,
                    'raw_agg': agg_raw.get(ym),
                    'indirect_sa': ind.get(ym),
                    'direct_sa': direct.get(ym),
                    'diff_lvl': (direct.get(ym) - ind.get(ym)) if pd.notna(direct.get(ym)) and pd.notna(ind.get(ym)) else None,
                    'yoy_indirect': yoy_i.get(ym),
                    'yoy_direct': yoy_d.get(ym),
                    'yoy_diff_pp': diff_yoy.get(ym),
                })

    df = pd.DataFrame(rows)
    out_path = OUTPUT_DIR / 'compare_direct_indirect_sa.csv'
    df.to_csv(out_path, index=False, float_format='%.3f')
    print(f"\n保存: {out_path}")

    print("\n=== 直近6ヶ月サンプル ===")
    for cat in df['category'].unique():
        print(f"\n--- {cat} ---")
        sub = df[df['category'] == cat][['ym', 'raw_agg', 'indirect_sa', 'direct_sa', 'diff_lvl', 'yoy_indirect', 'yoy_direct', 'yoy_diff_pp']]
        print(sub.to_string(index=False, float_format='%.2f'))


if __name__ == '__main__':
    main()
