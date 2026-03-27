"""上位指数の加重平均集計

未調整の上位指数はCSVに含まれる公式集計値をそのまま使用する。
調整済の上位指数は、品目別調整済指数を固定ウエイト（2020年基準）で加重平均して算出する。
  上位指数(t) = Σ w(i) × I_adj(i,t) / Σ w(i)
"""

import pandas as pd

from src.item_master import get_series_filter, load_item_master

# CSVに含まれる公式集計系列の品目コード
OFFICIAL_SERIES_CODES = {
    "total": "0001",        # 総合
    "core": "0161",         # 生鮮食品を除く総合
    "core_core": "0178",    # 生鮮食品及びエネルギーを除く総合
    "boj_core": "0168",     # 食料（酒類を除く）及びエネルギーを除く総合
    "energy": "0167",       # エネルギー
    "fresh": "0157",        # 生鮮食品
}


def get_official_series(item_indices: pd.DataFrame, series_name: str) -> pd.Series:
    """CSVに含まれる公式集計値を取得

    Args:
        item_indices: parse_cpi_csv()で取得したDataFrame（集計系列コードを含む）
        series_name: "total", "core", "core_core", "boj_core", "energy", "fresh"

    Returns:
        公式集計指数のSeries
    """
    code = OFFICIAL_SERIES_CODES.get(series_name)
    if code is None:
        raise ValueError(f"未知の系列名: {series_name}")
    if code not in item_indices.columns:
        raise ValueError(f"CSVに系列が含まれていません: {series_name} (code={code})")
    return item_indices[code].rename(series_name)


def compute_weighted_index(
    item_indices: pd.DataFrame,
    weights: pd.Series,
    series_name: str,
    master: pd.DataFrame | None = None,
) -> pd.Series:
    """品目別指数と固定ウエイトから上位指数を算出

    Args:
        item_indices: 品目別指数。columns=品目コード, index=年月(YYYY-MM形式)
        weights: 品目別固定ウエイト（1万分比）。index=品目コード
        series_name: "core", "core_core", "boj_core"
        master: 品目マスタ（Noneなら自動読込）

    Returns:
        Series: 上位指数（index=年月）
    """
    if master is None:
        master = load_item_master()

    # 系列に含まれる品目をフィルタ
    mask = get_series_filter(series_name, master)
    included_codes = master.loc[mask, "item_code"].values

    # 指数とウエイトの両方に存在する品目
    available_codes = [
        c for c in included_codes
        if c in item_indices.columns and c in weights.index
    ]
    if not available_codes:
        raise ValueError(f"計算可能な品目がありません: {series_name}")

    w = weights[available_codes].astype(float)
    w = w[w.notna() & (w > 0)]
    valid_codes = list(w.index)

    idx_sub = item_indices[valid_codes].astype(float)

    # ベクトル演算で全月一括計算
    weighted = idx_sub.multiply(w, axis=1)
    result = weighted.sum(axis=1) / w.sum()
    result.name = series_name

    return result


def compute_yoy(series: pd.Series) -> pd.Series:
    """前年同月比（%）を算出

    Args:
        series: 月次指数（index=YYYY-MM形式の文字列）

    Returns:
        前年同月比（%、例: 2.5 は +2.5%）
    """
    result = pd.Series(index=series.index, dtype=float)

    for ym in series.index:
        year = int(ym[:4])
        month = ym[5:]
        prev_ym = f"{year - 1}-{month}"
        if prev_ym in series.index and pd.notna(series[prev_ym]) and series[prev_ym] != 0:
            result[ym] = (series[ym] / series[prev_ym] - 1) * 100

    return result
