"""X-13で失敗した品目を、開始年を短縮して再試行する救済スクリプト

入力:
- output/cpi_item_adjusted_long.csv (元データ)
- output/cpi_item_adjusted_long_sa.csv (X-13済データ、失敗列はNaN)
- output/sa_fail_log.csv (失敗ログ)

出力:
- output/cpi_item_adjusted_long_sa.csv に成功列を追加
- output/sa_fail_log.csv 更新（救済できなかった品目のみ）

戦略:
- 失敗品目について、開始年を ['1985-01', '1995-01', '2000-01', '2010-01'] と段階的に短縮して再試行
- 開始年より前の月は NaN で残す（救済前と同じ）
"""

import os
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

warnings.filterwarnings('ignore')

X13_PATH = '/Users/rhashimoto/.local/bin/x13as'
START_CANDIDATES = ['1985-01', '1995-01', '2000-01', '2010-01']
MIN_MONTHS = 36


def sa_one_with_retry(args):
    code, ym_index, values = args
    from statsmodels.tsa.x13 import x13_arima_analysis
    s_full = pd.Series(values, index=pd.to_datetime(ym_index))
    s_full = s_full.dropna()
    if len(s_full) < MIN_MONTHS:
        return code, None, f'too short ({len(s_full)} months)', None
    s_full.index = pd.PeriodIndex(s_full.index, freq='M').to_timestamp()
    if (s_full <= 0).any():
        return code, None, 'has non-positive values', None

    last_err = None
    for start in START_CANDIDATES:
        s = s_full[s_full.index >= start]
        if len(s) < MIN_MONTHS:
            continue
        try:
            res = x13_arima_analysis(s, x12path=X13_PATH, prefer_x13=True, outlier=False)
            return code, res.seasadj, None, start
        except Exception as e:
            last_err = f'{type(e).__name__}: {str(e)[:100]}'
            continue
    return code, None, last_err or 'all retries failed', None


def main():
    df = pd.read_csv('output/cpi_item_adjusted_long.csv').set_index('ym').apply(pd.to_numeric, errors='coerce')
    sa = pd.read_csv('output/cpi_item_adjusted_long_sa.csv').set_index('ym').apply(pd.to_numeric, errors='coerce')
    fail = pd.read_csv('output/sa_fail_log.csv')

    failed_codes = [c for c in fail['code'].astype(str).tolist() if c in df.columns]
    print(f"再試行対象: {len(failed_codes)} 品目")

    tasks = [(c, df.index.tolist(), df[c].values) for c in failed_codes]
    rescued = {}
    rescue_starts = []
    new_fail = []

    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        futures = {ex.submit(sa_one_with_retry, t): t[0] for t in tasks}
        done = 0
        for fut in as_completed(futures):
            code, seasadj, err, start = fut.result()
            done += 1
            if seasadj is not None:
                seasadj.index = seasadj.index.strftime('%Y-%m')
                rescued[code] = seasadj
                rescue_starts.append((code, start))
            else:
                new_fail.append((code, err))
            if done % 20 == 0 or done == len(failed_codes):
                print(f"  進捗 {done}/{len(failed_codes)} (救済成功 {len(rescued)})")

    # SA CSV に救済列を追加
    if rescued:
        rescued_df = pd.DataFrame(rescued).reindex(sa.index)
        for c in rescued_df.columns:
            sa[c] = rescued_df[c]
        # ソート
        sa = sa[sorted(sa.columns)]
        sa.reset_index().to_csv('output/cpi_item_adjusted_long_sa.csv', index=False, float_format='%.4f')
        print(f"\nSA CSV更新: 救済 {len(rescued)} 品目追加")
        print(f"  全季節調整済品目: {sa.shape[1]}")

    # 失敗ログ更新
    pd.DataFrame(new_fail, columns=['code', 'reason']).to_csv('output/sa_fail_log.csv', index=False)
    print(f"  最終失敗: {len(new_fail)} 品目 (sa_fail_log.csv 更新)")

    # 救済使用パラメータ集計
    if rescue_starts:
        starts = pd.Series([s for _, s in rescue_starts])
        print(f"\n=== 救済使用開始年 ===")
        for s, c in starts.value_counts().items():
            print(f"  {s}: {c} 品目")

    if new_fail:
        nf = pd.DataFrame(new_fail, columns=['code','reason'])
        print(f"\n=== 最終失敗理由 ===")
        nf['reason_short'] = nf['reason'].str.split(':').str[0]
        for r, c in nf['reason_short'].value_counts().items():
            print(f"  {c:3d}件: {r}")


if __name__ == '__main__':
    main()
