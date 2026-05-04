"""YoY整合の品目別レベル系列を再構築

入力:
- data/soumu/longterm/zmy2020_yoy_all.csv (公表前年同月比、1970-2026)
- data/soumu/cpi_2010base_items.csv (公表レベル、2010基準、アンカーとして2010年12ヶ月分のみ使用)

出力: output/cpi_item_long_yoy_based.csv
  品目コード列、ym行、1970-01〜2026-03

アルゴリズム:
1. 2010年12ヶ月のレベル値をアンカーとして固定
2. 過去方向: t < 2010-01 で level(t) = level(t+12) / (1 + YoY(t+12)/100)
3. 未来方向: t > 2010-12 で level(t) = level(t-12) × (1 + YoY(t)/100)

2015年以降の値は別途既存パイプラインの値と接続するため、まずはYoY整合系列を全期間で
作って既存レベル系列との比較診断ができるようにする。

NB: 品目コード照合は単純1:1のみ。crosswalk適用は後段で。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src.config import OUTPUT_DIR


def load_yoy() -> pd.DataFrame:
    """公表前年同月比 long format → DataFrame (rows=ym, cols=item_code)"""
    df = pd.read_csv('data/soumu/longterm/zmy2020_yoy_all.csv', header=None,
                     low_memory=False, encoding='cp932')
    codes = [str(c).strip() for c in df.iloc[2, 1:].tolist()]
    ym_col = df.iloc[6:, 0].astype(str).reset_index(drop=True)
    data = {}
    for i, c in enumerate(codes):
        if c == 'nan' or not c:
            continue
        if c in data:
            continue  # skip duplicates (use first)
        data[c] = pd.to_numeric(df.iloc[6:, i+1].reset_index(drop=True), errors='coerce')
    out = pd.DataFrame(data)
    out.index = (ym_col.str[:4] + '-' + ym_col.str[4:]).values
    return out


def load_2010_anchor() -> pd.DataFrame:
    """2010基準raw データ → 2010年12ヶ月のみアンカー用"""
    df = pd.read_csv('data/soumu/cpi_2010base_items.csv')
    df['ym'] = df['year_month'].astype(str).str[:4] + '-' + df['year_month'].astype(str).str[4:]
    df = df.set_index('ym').apply(pd.to_numeric, errors='coerce')
    return df.loc['2010-01':'2010-12']


def reconstruct_one(code: str, anchor: pd.Series, yoy: pd.Series, ym_index: list[str]) -> pd.Series:
    """単一品目のYoY整合レベルを再構築

    anchor: 2010-01〜2010-12 のレベル (12点)
    yoy: 1970-01〜2026-03 の前年同月比 (%)
    """
    out = pd.Series(np.nan, index=ym_index, dtype=float)
    # アンカー
    for ym, v in anchor.items():
        out[ym] = v

    # 順次計算 (2011-01 以降)
    for ym in ym_index:
        if ym <= '2010-12':
            continue
        prev = f'{int(ym[:4])-1}-{ym[5:]}'
        if prev not in out.index or pd.isna(out[prev]):
            continue
        y = yoy.get(ym)
        if pd.isna(y):
            continue
        out[ym] = out[prev] * (1 + y/100)

    # 遡及計算 (1970-12 以前から、2009-12 まで)
    for ym in reversed(ym_index):
        if ym >= '2010-01':
            continue
        nxt = f'{int(ym[:4])+1}-{ym[5:]}'
        if nxt not in out.index or pd.isna(out[nxt]):
            continue
        y = yoy.get(nxt)
        if pd.isna(y):
            continue
        denom = 1 + y/100
        if denom == 0:
            continue
        out[ym] = out[nxt] / denom

    return out


def main():
    print("Loading YoY published data...")
    yoy_df = load_yoy()
    print(f"  YoY: {yoy_df.shape}, range {yoy_df.index.min()}〜{yoy_df.index.max()}")

    print("Loading 2010 anchor (2010-01〜2010-12)...")
    anchor_df = load_2010_anchor()
    print(f"  Anchor: {anchor_df.shape}")

    # 品目コードのみ (4桁、'0'始まり集計符号除外)
    def is_item(c):
        return len(str(c)) == 4 and not str(c).startswith('0')

    yoy_items = {c for c in yoy_df.columns if is_item(c)}
    anchor_items = {c for c in anchor_df.columns if is_item(c)}
    common = sorted(yoy_items & anchor_items)
    only_yoy = yoy_items - anchor_items
    only_anchor = anchor_items - yoy_items
    print(f"  共通品目 (再構築対象): {len(common)}")
    print(f"  YoYのみ: {len(only_yoy)} (新設・変更品目)")
    print(f"  アンカーのみ: {len(only_anchor)} (廃止品目)")

    # 全期間 1970-01 〜 2026-03
    ym_index = pd.date_range('1970-01', '2026-03', freq='MS').strftime('%Y-%m').tolist()

    out_data = {}
    skipped = []
    for code in common:
        anchor = anchor_df[code]
        yoy = yoy_df[code]
        # アンカー値がすべて NaN ならスキップ
        if anchor.dropna().empty:
            skipped.append((code, 'anchor全NaN'))
            continue
        if anchor.dropna().min() <= 0:
            skipped.append((code, 'anchor非正値あり'))
            continue
        s = reconstruct_one(code, anchor, yoy, ym_index)
        if s.notna().sum() < 12:
            skipped.append((code, f'有効値少ない({s.notna().sum()})'))
            continue
        out_data[code] = s

    out_df = pd.DataFrame(out_data, index=ym_index)
    out_df.index.name = 'ym'
    out_df = out_df[sorted(out_df.columns)]

    out_path = OUTPUT_DIR / 'cpi_item_long_yoy_based.csv'
    out_df.reset_index().to_csv(out_path, index=False, float_format='%.4f')
    print(f"\n保存: {out_path}  shape={out_df.shape}")
    print(f"  再構築品目: {len(out_data)}")
    print(f"  スキップ: {len(skipped)}")

    # 1995-2026年の年別 NaN率
    print("\n=== 年別 NaN率 (再構築品目内) ===")
    for year in [1970, 1980, 1990, 1995, 2000, 2005, 2010, 2015, 2020, 2025]:
        ymonth_year = [ym for ym in ym_index if ym.startswith(str(year))]
        sub = out_df.loc[ymonth_year]
        nan_pct = sub.isna().sum().sum() / sub.size * 100
        print(f'  {year}: {nan_pct:.1f}%')

    # サンプル: 問題品目で再構築結果を確認
    print('\n=== 問題品目の再構築結果 (1999-12, 2000-01, 2000-12, 2001-01) ===')
    for code in ['1401','1406','1414','1434','5111','5162','5181','5183']:
        if code in out_df.columns:
            v99 = out_df.at['1999-12', code]
            v00 = out_df.at['2000-01', code]
            v0012 = out_df.at['2000-12', code]
            v01 = out_df.at['2001-01', code]
            mom = (v00/v99-1)*100 if pd.notna(v99) and pd.notna(v00) else float('nan')
            print(f'  {code}: 99-12={v99:.2f}, 00-01={v00:.2f} (MoM {mom:+.2f}%), 00-12={v0012:.2f}, 01-01={v01:.2f}')


if __name__ == '__main__':
    main()
