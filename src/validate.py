"""日銀公表値との突合・検証レポート

検証の独立性:
  日銀公表値は最終検証専用。推定パラメータをこれに合わせ込まない。
"""

import pandas as pd


def compare_series(
    computed: pd.Series,
    published: pd.Series,
    series_name: str,
) -> pd.DataFrame:
    """計算値と公表値の差分を算出

    Args:
        computed: 自前で計算した系列（前年比%）
        published: 日銀公表値（前年比%）
        series_name: 系列名（表示用）

    Returns:
        DataFrame with columns:
            year_month, computed, published, diff_pp, diff_bp
            (diff_ppは%pt差、diff_bpはbp差)
    """
    # 共通の期間で比較
    common_idx = computed.index.intersection(published.index)
    if len(common_idx) == 0:
        print(f"[{series_name}] 共通期間なし")
        return pd.DataFrame()

    df = pd.DataFrame({
        "year_month": common_idx,
        "computed": computed[common_idx].values,
        "published": published[common_idx].values,
    })
    df["diff_pp"] = df["computed"] - df["published"]  # %pt差
    df["diff_bp"] = df["diff_pp"] * 100               # bp差

    return df


def print_validation_report(comparisons: dict[str, pd.DataFrame]) -> None:
    """検証レポートをコンソール出力

    Args:
        comparisons: {系列名: compare_series()の結果}
    """
    for name, df in comparisons.items():
        if df.empty:
            print(f"\n=== {name}: データなし ===")
            continue

        print(f"\n=== {name} ===")
        print(f"比較期間: {df['year_month'].iloc[0]} 〜 {df['year_month'].iloc[-1]}")
        print(f"データ点数: {len(df)}")

        valid = df.dropna(subset=["diff_bp"])
        if len(valid) == 0:
            print("有効な比較データなし")
            continue

        abs_diff = valid["diff_bp"].abs()
        print(f"平均絶対誤差: {abs_diff.mean():.1f} bp")
        print(f"最大絶対誤差: {abs_diff.max():.1f} bp")
        print(f"RMSE: {(valid['diff_bp'] ** 2).mean() ** 0.5:.1f} bp")

        # 誤差が大きい月を表示
        large = valid[abs_diff > 10].sort_values("diff_bp", key=abs, ascending=False)
        if len(large) > 0:
            print(f"\n誤差 > 10bp の月:")
            for _, row in large.head(10).iterrows():
                print(f"  {row['year_month']}: 計算={row['computed']:.2f}% "
                      f"公表={row['published']:.2f}% 差={row['diff_bp']:.0f}bp")


def save_validation_csv(comparisons: dict[str, pd.DataFrame], output_dir) -> None:
    """検証結果をCSV出力"""
    from pathlib import Path
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, df in comparisons.items():
        if df.empty:
            continue
        path = output_dir / f"validation_{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"保存: {path}")
