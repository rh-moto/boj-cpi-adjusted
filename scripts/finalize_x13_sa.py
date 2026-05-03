"""X-13季節調整の最終処理

Option 2: 固定価格品目 (X13Error 20件) → 元データを SA 列に流用
Option 1: 生鮮食品 (AttributeError 18件) → 上位分類 0157/0158/0159/0160 を chain-splice + X-13

処理:
1. 失敗ログから固定価格品目を特定 → cpi_item_adjusted_long_sa.csv に元値を埋める
2. 2010/2015/2020基準の集計符号 0157/0158/0159/0160 を chain-splice
3. 集計符号を X-13 → SA CSV に追加列として出力
"""

import os
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

X13_PATH = '/Users/rhashimoto/.local/bin/x13as'
FRESH_AGG_CODES = ['0157', '0158', '0159', '0160']  # 生鮮食品/魚介/野菜/果物
FRESH_ITEM_PREFIX = ('11', '14', '15')  # 1100s魚介, 1400s野菜, 1500s果物（の一部）


def x13_run(s: pd.Series, label: str = ''):
    from statsmodels.tsa.x13 import x13_arima_analysis
    s = s.dropna()
    if len(s) < 36 or (s <= 0).any():
        return None
    s.index = pd.PeriodIndex(s.index, freq='M').to_timestamp()
    for start in [None, '1985-01', '1995-01', '2000-01', '2010-01']:
        s2 = s if start is None else s[s.index >= start]
        if len(s2) < 36:
            continue
        try:
            res = x13_arima_analysis(s2, x12path=X13_PATH, prefer_x13=True, outlier=False)
            print(f'  {label}: OK ({len(s2)} months, start={start or "full"})')
            return res.seasadj
        except Exception as e:
            continue
    print(f'  {label}: 全フォールバック失敗')
    return None


def chain_splice_aggregate(code: str) -> pd.Series:
    """2010/2015/2020基準の集計符号を chain-splice (2020基準スケール=100)"""
    from src.fetch_cpi import parse_cpi_csv
    ind10 = pd.read_csv('data/soumu/cpi_2010base_items.csv')
    ind10['ym'] = ind10['year_month'].astype(str).str[:4] + '-' + ind10['year_month'].astype(str).str[4:]
    ind10 = ind10.set_index('ym')
    s10 = pd.to_numeric(ind10[code], errors='coerce') if code in ind10.columns else None

    ind15, _ = parse_cpi_csv(base_year=2015)
    s15 = pd.to_numeric(ind15[code], errors='coerce') if code in ind15.columns else None

    ind20, _ = parse_cpi_csv(base_year=2020)
    s20 = pd.to_numeric(ind20[code], errors='coerce') if code in ind20.columns else None

    if s20 is None:
        return None

    # 2015→2020 ratio (2020年平均で正規化)
    r1520 = (s20.loc['2020-01':'2020-12'].mean() / s15.loc['2020-01':'2020-12'].mean()
             if s15 is not None else 1.0)
    # 2010→2015 ratio (2015年平均)
    r1015 = (s15.loc['2015-01':'2015-12'].mean() / s10.loc['2015-01':'2015-12'].mean()
             if s10 is not None and s15 is not None else 1.0)

    out_index = pd.date_range('1970-01', '2026-03', freq='MS').strftime('%Y-%m').tolist()
    out = pd.Series(np.nan, index=out_index, dtype=float)

    # 2020基準
    mask = s20.index >= '2021-01'
    for ym, v in s20[mask].items():
        if pd.notna(v):
            out[ym] = v
    # 2015基準
    if s15 is not None:
        mask = (s15.index >= '2015-01') & (s15.index <= '2020-12')
        for ym, v in s15[mask].items():
            if pd.notna(v):
                out[ym] = v * r1520
    # 2010基準
    if s10 is not None:
        scale = r1015 * r1520
        mask = (s10.index >= '1970-01') & (s10.index <= '2014-12')
        for ym, v in s10[mask].items():
            if pd.notna(v):
                out[ym] = v * scale

    return out


def main():
    # 入力
    sa = pd.read_csv('output/cpi_item_adjusted_long_sa.csv').set_index('ym').apply(pd.to_numeric, errors='coerce')
    long_df = pd.read_csv('output/cpi_item_adjusted_long.csv').set_index('ym').apply(pd.to_numeric, errors='coerce')
    fail = pd.read_csv('output/sa_fail_log.csv')
    print(f"SA shape前: {sa.shape}, 失敗 {len(fail)} 品目")

    # Option 2: 固定価格品目（X13Error）→ 元データ流用
    fixed_codes = fail[fail['reason'].str.startswith('X13Error', na=False)]['code'].astype(str).tolist()
    fresh_codes = fail[fail['reason'].str.startswith('AttributeError', na=False)]['code'].astype(str).tolist()
    print(f"\n[Option 2] 固定価格品目 {len(fixed_codes)} 件: 元データを流用")
    for code in fixed_codes:
        if code in long_df.columns:
            sa[code] = long_df[code]

    # Option 1: 生鮮食品上位分類のX-13
    print(f"\n[Option 1] 生鮮個別18件はNaNのまま、集計符号 {FRESH_AGG_CODES} に X-13 適用:")
    agg_sa = {}
    for code in FRESH_AGG_CODES:
        s_long = chain_splice_aggregate(code)
        if s_long is None:
            print(f'  {code}: chain-splice失敗')
            continue
        seasadj = x13_run(s_long.dropna(), label=f'agg {code}')
        if seasadj is not None:
            seasadj.index = seasadj.index.strftime('%Y-%m')
            agg_sa[code] = seasadj.reindex(sa.index)

    # 集計符号を SA に追加
    for code, ser in agg_sa.items():
        sa[code] = ser

    # ソート (集計符号と品目コード混在、文字列順)
    sa = sa[sorted(sa.columns)]
    sa.reset_index().to_csv('output/cpi_item_adjusted_long_sa.csv', index=False, float_format='%.4f')
    print(f"\n保存: output/cpi_item_adjusted_long_sa.csv  shape={sa.shape}")
    print(f"  Option 2追加: {len([c for c in fixed_codes if c in sa.columns])} 品目")
    print(f"  Option 1追加: {len(agg_sa)} 集計符号 ({list(agg_sa.keys())})")
    print(f"  生鮮個別NaNのまま: {len(fresh_codes)} 品目")

    # 失敗ログ更新（生鮮個別18件のみ残す。理由を明記）
    new_fail = pd.DataFrame({
        'code': fresh_codes,
        'reason': '生鮮個別品目: NaN多数のためX-13困難 (上位分類0157-0160で代替)',
    })
    new_fail.to_csv('output/sa_fail_log.csv', index=False)
    print(f"  失敗ログ更新: {len(new_fail)} 品目 (生鮮個別、上位分類で代替済)")


if __name__ == '__main__':
    main()
