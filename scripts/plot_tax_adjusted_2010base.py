"""2010基準の品目別税調整の検証グラフ

3つの系列を比較:
  1. 無調整 (2010基準 0001 総合)
  2. 自前PDF仕様品目別調整 (本プロジェクトで集計)
  3. 公表 tax_adjusted.xlsx
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np


def aggregate_weighted(df: pd.DataFrame, codes: list, weights: dict) -> pd.Series:
    rows = []
    for ym in df.index:
        sw, sv = 0.0, 0.0
        for c in codes:
            v = df.at[ym, c]
            w = weights.get(c, 0)
            if pd.notna(v) and w > 0:
                sw += w
                sv += v * w
        rows.append((ym, sv/sw if sw else None))
    return pd.Series(dict(rows))


def aggregate_factor_then_apply(adj_df: pd.DataFrame, orig_df: pd.DataFrame,
                                 codes: list, weights: dict,
                                 official_index: pd.Series) -> pd.Series:
    """品目別の調整factor (adj/orig) のウエイト平均を取って、公式0001に適用

    バスケット変動の影響を排除した検証用集計。
    factor は基本的に1.0付近、新規品目登場による level jump は factor 比で打ち消される。
    """
    rows = []
    for ym in adj_df.index:
        sw, sv = 0.0, 0.0
        for c in codes:
            v_adj = adj_df.at[ym, c]
            v_orig = orig_df.at[ym, c]
            w = weights.get(c, 0)
            if pd.notna(v_adj) and pd.notna(v_orig) and v_orig > 0 and w > 0:
                sw += w
                sv += (v_adj / v_orig) * w
        if sw > 0:
            avg_factor = sv / sw
            off = official_index.get(ym)
            rows.append((ym, off * avg_factor if pd.notna(off) else None))
        else:
            rows.append((ym, None))
    return pd.Series(dict(rows))


def main():
    # === Load adjusted item-level (output of build_tax_adjusted_2010base.py) ===
    adj = pd.read_csv('output/cpi_2010base_tax_adjusted.csv', encoding='utf-8-sig')
    adj = adj.set_index('ym').apply(pd.to_numeric, errors='coerce')

    # === Load original 2010-base data (for unadjusted aggregate + weights) ===
    files = ['000011288577.csv', '000011288578.csv', '000011288579.csv',
             '000011288580.csv', '000011288581.csv']
    weights = {}
    for f in files:
        full = pd.read_csv(f'data/soumu/2010base/{f}', encoding='shift_jis', header=None)
        codes = [str(c) for c in full.iloc[2, 1:].tolist()]
        ws = full.iloc[5, 1:].tolist()
        for c, w in zip(codes, ws):
            if c not in weights:
                try: weights[c] = float(w)
                except: weights[c] = 0

    orig = pd.read_csv('data/soumu/cpi_2010base_items.csv')
    orig['ym'] = orig['year_month'].astype(str).str[:4] + '-' + orig['year_month'].astype(str).str[4:]
    orig = orig.set_index('ym')

    # Item codes (4-digit, not aggregate)
    item_codes = [c for c in adj.columns if not str(c).startswith('0') and weights.get(c, 0) > 0]
    print(f"集計対象品目: {len(item_codes)}")

    orig_items = orig[item_codes].apply(pd.to_numeric, errors='coerce')

    # Official 2010-base aggregate (0001) — direct from CSV
    off_unadj = pd.to_numeric(orig['0001'], errors='coerce')

    # Self-aggregated: factor-method (stable across basket changes)
    # 品目別 adj/orig のウエイト平均 → 公式 0001 に乗じる
    print("Aggregating (factor method)...")
    self_adj = aggregate_factor_then_apply(adj, orig_items, item_codes, weights, off_unadj)
    self_unadj = off_unadj  # 無調整は公式0001そのまま

    # Official tax_adjusted (rebased to 2010=100)
    tax = pd.read_excel('data/soumu/tax_adjusted.xlsx', sheet_name='zmi', header=None)
    td = tax.iloc[6:].copy()
    td.columns = ['ym_raw', 'all', 'core', 'less_imp', 'less_imp_fresh', 'core_core', 'boj_core']
    td['ym'] = td['ym_raw'].astype(str).str[:4] + '-' + td['ym_raw'].astype(str).str[4:]
    td = td.set_index('ym')
    off_adj_raw = pd.to_numeric(td['all'], errors='coerce')
    off_2010 = off_adj_raw.loc['2010-01':'2010-12'].mean()
    off_adj = off_adj_raw / off_2010 * 100

    # YoY
    def yoy(s): return ((s / s.shift(12)) - 1) * 100

    # Convert ym strings to datetime for plotting
    def to_dt(idx):
        return pd.to_datetime([f"{y}-01" for y in idx])

    # === Build comparison frame ===
    df_plot = pd.DataFrame({
        'self_unadj': self_unadj,
        'self_adj': self_adj,
        'off_unadj_0001': off_unadj,
        'off_adj_taxadj': off_adj,
    })
    df_plot.index = pd.to_datetime([f"{y}-01" for y in df_plot.index])
    df_plot = df_plot.sort_index()

    df_yoy = df_plot.apply(yoy)

    # === Plot ===
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))

    # (A) 1995-2017 YoY: 全期間で 1997-04 と 2014-04 を含む
    ax = axes[0, 0]
    sub = df_yoy.loc['1995-01':'2017-12']
    ax.plot(sub.index, sub['off_unadj_0001'], label='Unadjusted (0001)', color='gray', linewidth=1.0)
    ax.plot(sub.index, sub['self_adj'], label='Self adj (PDF spec)', color='C0', linewidth=1.5)
    ax.plot(sub.index, sub['off_adj_taxadj'], label='Official tax_adjusted', color='C3', linewidth=1.0, linestyle='--')
    ax.axvline(pd.Timestamp('1997-04'), color='red', linewidth=0.5, alpha=0.5)
    ax.axvline(pd.Timestamp('2014-04'), color='red', linewidth=0.5, alpha=0.5)
    ax.set_title('YoY comparison (1995-2017): unadj vs adj vs official', fontsize=11)
    ax.set_ylabel('YoY (%)')
    ax.legend(loc='upper right', fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.axhline(0, color='black', linewidth=0.5)

    # (B) 2014-04 zoom
    ax = axes[0, 1]
    sub = df_yoy.loc['2013-01':'2016-06']
    ax.plot(sub.index, sub['off_unadj_0001'], label='Unadjusted (0001)', color='gray', linewidth=1.5)
    ax.plot(sub.index, sub['self_adj'], label='Self adj (PDF spec)', color='C0', linewidth=2.0, marker='o', markersize=3)
    ax.plot(sub.index, sub['off_adj_taxadj'], label='Official tax_adjusted', color='C3', linewidth=1.5, linestyle='--', marker='x', markersize=4)
    ax.axvline(pd.Timestamp('2014-04'), color='red', linewidth=1.0, alpha=0.5, label='2014-04 tax change')
    ax.set_title('2014-04 zoom: tax effect detail', fontsize=11)
    ax.set_ylabel('YoY (%)')
    ax.legend(loc='upper right', fontsize=9)
    ax.grid(True, alpha=0.3)

    # (C) 1997-04 zoom
    ax = axes[1, 0]
    sub = df_yoy.loc['1996-01':'1999-06']
    ax.plot(sub.index, sub['off_unadj_0001'], label='Unadjusted (0001)', color='gray', linewidth=1.5)
    ax.plot(sub.index, sub['self_adj'], label='Self adj (PDF spec)', color='C0', linewidth=2.0, marker='o', markersize=3)
    ax.plot(sub.index, sub['off_adj_taxadj'], label='Official tax_adjusted', color='C3', linewidth=1.5, linestyle='--', marker='x', markersize=4)
    ax.axvline(pd.Timestamp('1997-04'), color='red', linewidth=1.0, alpha=0.5, label='1997-04 tax change')
    ax.set_title('1997-04 zoom: tax effect detail', fontsize=11)
    ax.set_ylabel('YoY (%)')
    ax.legend(loc='upper right', fontsize=9)
    ax.grid(True, alpha=0.3)

    # (D) 自前 - 公表 の差
    ax = axes[1, 1]
    diff = df_yoy['self_adj'] - df_yoy['off_adj_taxadj']
    sub = diff.loc['1995-01':'2017-12']
    ax.plot(sub.index, sub, color='C2', linewidth=1.0)
    ax.axhline(0, color='black', linewidth=0.5)
    ax.axvline(pd.Timestamp('1997-04'), color='red', linewidth=0.5, alpha=0.5)
    ax.axvline(pd.Timestamp('2014-04'), color='red', linewidth=0.5, alpha=0.5)
    ax.fill_between(sub.index, sub, 0, alpha=0.3, color='C2')
    ax.set_title('Difference: Self adj − Official (pp)', fontsize=11)
    ax.set_ylabel('YoY diff (pp)')
    ax.grid(True, alpha=0.3)

    plt.suptitle('2010-base CPI tax adjustment: PDF-spec item-level vs official', fontsize=13, y=1.00)
    plt.tight_layout()
    out_path = Path('output/fig_tax_adjusted_2010base.png')
    plt.savefig(out_path, dpi=130, bbox_inches='tight')
    plt.close()
    print(f"\n保存: {out_path}")

    # Also save level comparison plot
    fig, ax = plt.subplots(figsize=(13, 6))
    sub = df_plot.loc['1990-01':'2016-12']
    ax.plot(sub.index, sub['off_unadj_0001'], label='Unadjusted (0001 total)', color='gray', linewidth=1.0)
    ax.plot(sub.index, sub['self_adj'], label='Self adj (PDF spec)', color='C0', linewidth=1.5)
    ax.plot(sub.index, sub['off_adj_taxadj'], label='Official tax_adjusted (rebased to 2010=100)', color='C3', linewidth=1.0, linestyle='--')
    ax.axvline(pd.Timestamp('1997-04'), color='red', linewidth=0.5, alpha=0.5, label='1997-04')
    ax.axvline(pd.Timestamp('2014-04'), color='orange', linewidth=0.5, alpha=0.5, label='2014-04')
    ax.set_title('Level comparison: 2010-base CPI (Index, 2010=100)', fontsize=12)
    ax.set_ylabel('Index (2010=100)')
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    out_path2 = Path('output/fig_tax_adjusted_2010base_level.png')
    plt.savefig(out_path2, dpi=130, bbox_inches='tight')
    plt.close()
    print(f"保存: {out_path2}")


if __name__ == '__main__':
    main()
