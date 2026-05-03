"""2010基準データに品目別消費税調整を適用してCSV出力

仕様: data/soumu/2015taxadj.pdf 準拠
入力: data/soumu/cpi_2010base_items.csv (1970-2016, 593品目)
出力: output/cpi_2010base_tax_adjusted.csv (品目別調整済指数)

適用イベント: 1997-04 (3%→5%), 2014-04 (5%→8%)
基準時(2010年)の税率は5%。本スクリプトの調整済指数は
「全期間を3%税率基準で表現」した系列となる。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.tax_adjust_pdf_spec import apply_all_tax_adjustments, compute_factor, load_tax_categories


def load_2010_items_long() -> tuple[pd.DataFrame, dict]:
    """2010基準の品目別データと品目名辞書を返す"""
    files = ['000011288577.csv', '000011288578.csv', '000011288579.csv',
             '000011288580.csv', '000011288581.csv']
    item_names = {}
    for f in files:
        full = pd.read_csv(f'data/soumu/2010base/{f}', encoding='shift_jis', header=None)
        codes = [str(c) for c in full.iloc[2, 1:].tolist()]
        names = [str(n) for n in full.iloc[0, 1:].tolist()]
        for c, n in zip(codes, names):
            if c not in item_names:
                item_names[c] = n

    df = pd.read_csv('data/soumu/cpi_2010base_items.csv')
    df['ym'] = df['year_month'].astype(str).str[:4] + '-' + df['year_month'].astype(str).str[4:]
    df = df.set_index('ym').drop(columns=['year_month'])
    # Keep only item columns (drop nan-only & empty)
    return df, item_names


def main():
    print("Loading 2010-base data...")
    df, names = load_2010_items_long()
    print(f"  {df.shape[0]} 月, {df.shape[1]} 列")

    # 品目コード（4桁、'0'始まりは集計符号なので除外）
    item_codes = [c for c in df.columns if not str(c).startswith('0')]
    agg_codes = [c for c in df.columns if str(c).startswith('0')]
    print(f"  品目: {len(item_codes)}, 集計符号: {len(agg_codes)}")

    # 品目別データのみに調整適用（集計符号は後で再計算）
    items_df = df[item_codes].apply(pd.to_numeric, errors='coerce')

    print("\nApplying tax adjustments (1997-04, 2014-04)...")
    adjusted_items = apply_all_tax_adjustments(items_df, names, events=(1997, 2014))

    # 出力: 品目別調整済指数
    out = adjusted_items.reset_index()
    out_path = Path('output/cpi_2010base_tax_adjusted.csv')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f"\n保存: {out_path}")
    print(f"  shape: {out.shape}")

    # サンプル: 主要品目の調整前後（2014-04前後）
    print("\n=== 調整前後サンプル ===")
    sample_codes = [
        ('1001', 'うるち米Ａ', 'standard'),
        ('3000', '民営家賃', 'exempt'),
        ('3500', '電気代', 'trans1'),
        ('7410', '固定電話通信料', 'trans2'),
        ('5104', '背広服（冬物，普通品）', 'seasonal1'),
        ('5101', '背広服（夏物，中級品）', 'seasonal2'),
    ]
    sample_periods = ['2014-03', '2014-04', '2014-05', '2014-08', '2014-09', '2014-12']
    for code, name, cat in sample_codes:
        if code not in items_df.columns:
            print(f"  {code} {name}: 該当列なし")
            continue
        print(f"\n  {code} {name} (PDF区分={cat})")
        for ym in sample_periods:
            if ym in items_df.index:
                orig = items_df.at[ym, code]
                adj = adjusted_items.at[ym, code]
                ratio = adj/orig if pd.notna(orig) and orig != 0 else None
                print(f"    {ym}: 調整前={orig:.2f}  調整後={adj:.2f}  ratio={ratio:.4f}" if ratio is not None else f"    {ym}: --")


if __name__ == '__main__':
    main()
