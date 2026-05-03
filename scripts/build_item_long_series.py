"""3基準の品目別調整済指数を chain splicing で接続して長期時系列を構築

入力:
- output/cpi_2010base_tax_adjusted.csv (1970-01〜2016-12)
- output/cpi_2015base_adjusted_items.csv (2015-01〜2021-06)
- output/cpi_2020base_adjusted_items.csv (2020-01〜2026-03)
- data/policy_params/crosswalk_2010_2015.csv
- data/policy_params/crosswalk_2015_2020.csv

出力: output/cpi_item_adjusted_long.csv (1970-01〜2026-03、2020年=100基準)

方針:
- 接続は 2020基準 = 100 となるよう forward chain splicing
- 2015→2020 接続: ratio = mean(2020base[2020]) / mean(2015base[2020])
- 2010→2015 接続: ratio = mean(2015base[2015]) / mean(2010base[2015])
- 2010基準で「同コードでrenamed」も実質同一品目として接続
- 各品目で利用可能な基準のみで接続 (2010無い品目は2015から開始など)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src.config import OUTPUT_DIR, POLICY_DIR


def load_indexed(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding='utf-8-sig' if '2010base' in path.name else 'utf-8')
    df = df.set_index('ym')
    df = df.apply(pd.to_numeric, errors='coerce')
    return df


def splice_ratio(early: pd.Series, late: pd.Series, overlap_year: str) -> float | None:
    """重複年の年平均比 late/early を返す。重複が不十分ならNone。"""
    e = early[(early.index >= f'{overlap_year}-01') & (early.index <= f'{overlap_year}-12')]
    l = late[(late.index >= f'{overlap_year}-01') & (late.index <= f'{overlap_year}-12')]
    e_mean = e.dropna().mean() if not e.empty else np.nan
    l_mean = l.dropna().mean() if not l.empty else np.nan
    if pd.isna(e_mean) or pd.isna(l_mean) or e_mean == 0:
        return None
    return l_mean / e_mean


def main():
    print("Loading data...")
    df10 = load_indexed(OUTPUT_DIR / 'cpi_2010base_tax_adjusted.csv')
    df15 = load_indexed(OUTPUT_DIR / 'cpi_2015base_adjusted_items.csv')
    df20 = load_indexed(OUTPUT_DIR / 'cpi_2020base_adjusted_items.csv')
    print(f"  2010基準: {df10.shape}, {df10.index.min()}〜{df10.index.max()}")
    print(f"  2015基準: {df15.shape}, {df15.index.min()}〜{df15.index.max()}")
    print(f"  2020基準: {df20.shape}, {df20.index.min()}〜{df20.index.max()}")

    cw1015 = pd.read_csv(POLICY_DIR / 'crosswalk_2010_2015.csv', dtype=str).fillna('')
    cw1520 = pd.read_csv(POLICY_DIR / 'crosswalk_2015_2020.csv', dtype=str).fillna('')

    # 2010↔2015 マップ (renamedも含む)
    map_10_to_15 = {r['code_2010']: r['code_2015'] for _, r in cw1015.iterrows()
                    if r['code_2010'] and r['code_2015']}
    # 2015↔2020 マップ (1:1のみ)
    map_15_to_20 = {r['code_2015']: r['code_2020'] for _, r in cw1520.iterrows()
                    if r['code_2015'] and r['code_2020']}

    # 接続キーは 2020基準コード (canonical)。2020に存在しない場合は2015コードをそのまま。
    # ここでは2020基準がある品目のみを「直近まで持つ」連続系列として扱う。
    # 2015のみ・2010のみの品目も基底コードで保持。

    out_index = pd.date_range('1970-01', '2026-03', freq='MS').strftime('%Y-%m').tolist()
    out_df = pd.DataFrame(index=out_index)
    out_df.index.name = 'ym'

    stats = {'all_three': 0, 'fifteen_twenty': 0, 'ten_fifteen': 0,
             'ten_only': 0, 'fifteen_only': 0, 'twenty_only': 0,
             'splice_failed': 0}

    # 接続候補: 全コード集合 (2010 + 2015 + 2020)
    all_2020 = set(df20.columns)
    all_2015 = set(df15.columns)
    all_2010 = set(df10.columns)

    # canonical_codeとして 2020基準コードを優先、無ければ2015、無ければ2010
    # 接続対象は実際に品目コードのみ（4桁、'0'始まり集計符号除外）
    def is_item(c): return len(str(c)) == 4 and not str(c).startswith('0')

    canonical_codes = sorted({c for c in (all_2020 | all_2015 | all_2010) if is_item(c)})

    for code in canonical_codes:
        s20 = df20[code] if code in all_2020 else None
        # 2015→2020 mapping (通常同一コード)
        c15 = code  # 大半は同一コード。crosswalkは1:1のものはそのまま。
        s15 = df15[c15] if c15 in all_2015 else None
        # 2010→2015 mapping
        c10 = code
        s10 = df10[c10] if c10 in all_2010 else None

        # コードが2010-2015でリネームされていた場合、map_10_to_15で逆引き
        # しかしrenamedは同一コードのケースのみ（cwで確認済み）なのでスキップ

        # Splice ratios
        r_15to20 = splice_ratio(s15, s20, '2020') if (s15 is not None and s20 is not None) else None
        r_10to15 = splice_ratio(s10, s15, '2015') if (s10 is not None and s15 is not None) else None

        # 構築
        long_series = pd.Series(np.nan, index=out_index, dtype=float)

        # 2020基準 (2021-01以降)
        if s20 is not None:
            mask = (s20.index >= '2021-01')
            for ym, v in s20[mask].items():
                long_series[ym] = v

        # 2015基準 (重複期間の処理)
        if s15 is not None:
            scale = r_15to20 if r_15to20 is not None else (1.0 if s20 is None else None)
            if scale is not None:
                # 2015-01 〜 2020-12 (s20があれば2020-12まで、無ければ全期間)
                end_15 = '2020-12' if s20 is not None else s15.index.max()
                mask = (s15.index >= '2015-01') & (s15.index <= end_15)
                for ym, v in s15[mask].items():
                    if pd.notna(v):
                        long_series[ym] = v * scale

        # 2010基準 (1970-01 〜 2014-12)
        if s10 is not None:
            scale10 = None
            if r_10to15 is not None and (r_15to20 is not None or s20 is None):
                scale10 = r_10to15 * (r_15to20 if r_15to20 is not None else 1.0)
            elif r_10to15 is None and s15 is None and s20 is None:
                scale10 = 1.0
            if scale10 is not None:
                mask = (s10.index >= '1970-01') & (s10.index <= '2014-12')
                for ym, v in s10[mask].items():
                    if pd.notna(v):
                        long_series[ym] = v * scale10

        # 統計
        if s10 is not None and s15 is not None and s20 is not None:
            stats['all_three'] += 1
        elif s15 is not None and s20 is not None:
            stats['fifteen_twenty'] += 1
        elif s10 is not None and s15 is not None:
            stats['ten_fifteen'] += 1
        elif s10 is not None:
            stats['ten_only'] += 1
        elif s15 is not None:
            stats['fifteen_only'] += 1
        elif s20 is not None:
            stats['twenty_only'] += 1

        if long_series.notna().any():
            out_df[code] = long_series

    # 並び替え (品目コード順)
    out_df = out_df[sorted(out_df.columns)]

    out_path = OUTPUT_DIR / 'cpi_item_adjusted_long.csv'
    out_df.reset_index().to_csv(out_path, index=False)
    print(f"\n保存: {out_path}")
    print(f"  shape: {out_df.shape}")
    print(f"  期間: {out_df.index.min()}〜{out_df.index.max()}")
    print(f"\n品目接続統計:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == '__main__':
    main()
