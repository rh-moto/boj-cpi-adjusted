"""cpi_item_adjusted_long.csv の各品目に X-13 ARIMA-SEATS 季節調整を適用

入力: output/cpi_item_adjusted_long.csv (1970-01〜2026-03)
出力: output/cpi_item_adjusted_long_sa.csv (季節調整済)

X-13設定:
- outlier=False (長期系列で外れ値多数→回帰効果制限を回避)
- prefer_x13=True (x13as binary使用)
- 36ヶ月以上のデータがある品目のみ処理
"""

import os
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

X13_PATH = '/Users/rhashimoto/.local/bin/x13as'
MIN_MONTHS = 36  # 3年以上


def sa_one(args):
    code, ym_index, values = args
    from statsmodels.tsa.x13 import x13_arima_analysis
    s = pd.Series(values, index=pd.to_datetime(ym_index))
    s = s.dropna()
    if len(s) < MIN_MONTHS:
        return code, None, f'too short ({len(s)} months)'
    s.index = pd.PeriodIndex(s.index, freq='M').to_timestamp()
    if (s <= 0).any():
        return code, None, 'has non-positive values'
    try:
        res = x13_arima_analysis(s, x12path=X13_PATH, prefer_x13=True, outlier=False)
        seasadj = res.seasadj
        return code, seasadj, None
    except Exception as e:
        return code, None, f'{type(e).__name__}: {str(e)[:100]}'


def main():
    in_path = Path('output/cpi_item_adjusted_long.csv')
    df = pd.read_csv(in_path).set_index('ym').apply(pd.to_numeric, errors='coerce')
    print(f"入力: {df.shape}, {df.index.min()}〜{df.index.max()}")

    codes = list(df.columns)
    print(f"対象品目: {len(codes)}")

    out_df = pd.DataFrame(index=df.index)
    out_df.index.name = 'ym'

    # 並列実行
    tasks = [(c, df.index.tolist(), df[c].values) for c in codes]
    fail_log = []
    sa_dict = {}

    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        futures = {ex.submit(sa_one, t): t[0] for t in tasks}
        done = 0
        for fut in as_completed(futures):
            code, seasadj, err = fut.result()
            done += 1
            if seasadj is not None:
                # PeriodIndex日付を ym 文字列に
                seasadj.index = seasadj.index.strftime('%Y-%m')
                sa_dict[code] = seasadj
            else:
                fail_log.append((code, err))
            if done % 50 == 0 or done == len(codes):
                print(f"  進捗 {done}/{len(codes)} (失敗 {len(fail_log)})")

    # まとめてDataFrame構築
    sa_df = pd.DataFrame(sa_dict).reindex(df.index)
    sa_df = sa_df[sorted(sa_df.columns)]

    out_path = Path('output/cpi_item_adjusted_long_sa.csv')
    sa_df.reset_index().to_csv(out_path, index=False, float_format='%.4f')
    print(f"\n保存: {out_path}")
    print(f"  shape: {sa_df.shape}")
    print(f"  季節調整済品目: {sa_df.shape[1]}")
    print(f"  失敗品目: {len(fail_log)}")

    if fail_log:
        log_path = Path('output/sa_fail_log.csv')
        pd.DataFrame(fail_log, columns=['code', 'reason']).to_csv(log_path, index=False)
        print(f"  失敗ログ: {log_path}")
        # 失敗理由内訳
        reasons = pd.Series([r for _, r in fail_log])
        print("  失敗理由:")
        for r, c in reasons.value_counts().head(10).items():
            print(f"    {c:3d}件: {r}")


if __name__ == '__main__':
    main()
