"""CPI品目別ウエイト（連鎖ウエイト）の取得・パース

データソース:
- 連鎖ウエイトExcel: https://www.stat.go.jp/data/cpi/2020/zuhyou/rensa-wt_2020.xlsx
  2020年〜最新年の品目別ウエイト（1万分比）

Excel構造:
  行0-2: ヘッダ（品目名・年次・実数/1万分比）
  行3〜: データ（品目ごと）
  col 8: 品目符号
  col 11,13,15,17,19,21: 各年の1万分比ウエイト
"""

from pathlib import Path

import pandas as pd
import requests

from src.config import SOUMU_DIR

WEIGHT_URL = "https://www.stat.go.jp/data/cpi/2020/zuhyou/rensa-wt_2020.xlsx"
WEIGHT_PATH = SOUMU_DIR / "weight_chain.xlsx"

# 年次→1万分比の列インデックスの対応
YEAR_COL_MAP = {
    2020: 11,
    2021: 13,
    2022: 15,
    2023: 17,
    2024: 19,
    2025: 21,
}


def download_weights(force: bool = False) -> Path:
    """連鎖ウエイトExcelをダウンロード"""
    if WEIGHT_PATH.exists() and not force:
        print(f"既存ファイルを使用: {WEIGHT_PATH}")
        return WEIGHT_PATH

    print(f"ダウンロード中: {WEIGHT_URL}")
    resp = requests.get(WEIGHT_URL, timeout=60)
    resp.raise_for_status()
    WEIGHT_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEIGHT_PATH.write_bytes(resp.content)
    print(f"保存: {WEIGHT_PATH} ({len(resp.content)} bytes)")
    return WEIGHT_PATH


def parse_weights(filepath: Path | None = None) -> pd.DataFrame:
    """連鎖ウエイトExcelをパースして年次×品目のウエイトDataFrameを返す

    Returns:
        DataFrame: index=年(int), columns=品目コード(str), values=ウエイト(1万分比)
    """
    if filepath is None:
        filepath = WEIGHT_PATH

    df = pd.read_excel(filepath, sheet_name="ウエイト", header=None, skiprows=3)

    # 品目行のみ抽出（品目符号col[8]が存在する行）
    items = df[df[8].notna()].copy()

    # 品目コード
    codes = items[8].apply(lambda x: str(int(x))).values

    # 年次別1万分比ウエイトを取得
    years = sorted(YEAR_COL_MAP.keys())
    weight_data = {}
    for year in years:
        col = YEAR_COL_MAP[year]
        if col < df.shape[1]:
            w = pd.to_numeric(items[col], errors="coerce").values
            weight_data[year] = w

    weights = pd.DataFrame(weight_data, index=codes).T
    weights.index.name = "year"
    weights.columns.name = "item_code"

    return weights


def get_weight_for_month(weights: pd.DataFrame, year_month: str) -> pd.Series:
    """指定年月に適用されるウエイトを返す

    CPIのウエイトは毎年1月に更新される。
    指定年月の年に対応するウエイトを返す。
    該当年のウエイトがなければ最も近い過去年を使う。

    Args:
        weights: parse_weights()の戻り値
        year_month: "YYYY-MM"形式

    Returns:
        品目コードをインデックスとするウエイトSeries
    """
    year = int(year_month[:4])
    available = weights.index[weights.index <= year]
    if len(available) == 0:
        raise ValueError(f"利用可能なウエイトがありません: {year_month}")
    return weights.loc[available[-1]]
