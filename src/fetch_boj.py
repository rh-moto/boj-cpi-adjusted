"""日銀「消費者物価のコア指標」データの取得・パース

データソース:
- https://www.boj.or.jp/research/research_data/cpi/cpirev.xlsx
  毎月CPI公表日の2営業日後に更新

Excel構造 (chartシート):
  行0: 空
  行1: 系列名（日本語）
  行2: 基準年（20年基準 / 15年基準）
  行3: 系列名（英語）
  行4: 基準年（英語）
  行5〜: データ（col 0=日付, col 1〜=前年比%）
"""

from pathlib import Path

import pandas as pd
import requests

from src.config import BOJ_DIR, BOJ_SERIES_COLS, BASE_YEAR

BOJ_URL = "https://www.boj.or.jp/research/research_data/cpi/cpirev.xlsx"
BOJ_PATH = BOJ_DIR / "cpi_core_indicators.xlsx"


def download_boj(force: bool = False) -> Path:
    """日銀コア指標Excelをダウンロード"""
    if BOJ_PATH.exists() and not force:
        print(f"既存ファイルを使用: {BOJ_PATH}")
        return BOJ_PATH

    print(f"ダウンロード中: {BOJ_URL}")
    resp = requests.get(BOJ_URL, timeout=60)
    resp.raise_for_status()
    BOJ_PATH.parent.mkdir(parents=True, exist_ok=True)
    BOJ_PATH.write_bytes(resp.content)
    print(f"保存: {BOJ_PATH} ({len(resp.content)} bytes)")
    return BOJ_PATH


def parse_boj(
    filepath: Path | None = None,
    base_year: int | None = None,
) -> dict[str, pd.Series]:
    """日銀コア指標Excelをパース

    Args:
        filepath: Excelファイルパス
        base_year: 基準年（2015 or 2020）

    Returns:
        {系列名: 前年比%のSeries(index=YYYY-MM)}
    """
    if filepath is None:
        filepath = BOJ_PATH
    by = base_year or BASE_YEAR
    cols = BOJ_SERIES_COLS[by]

    df = pd.read_excel(filepath, sheet_name="chart", header=None, skiprows=5)

    # 日付列をYYYY-MM形式に変換
    dates = pd.to_datetime(df.iloc[:, 0])
    ym_index = dates.dt.strftime("%Y-%m")

    result = {}
    for name, col in cols.items():
        if col < df.shape[1]:
            values = pd.to_numeric(df.iloc[:, col], errors="coerce")
            s = pd.Series(values.values, index=ym_index, name=name)
            s = s.dropna()
            result[name] = s

    return result
