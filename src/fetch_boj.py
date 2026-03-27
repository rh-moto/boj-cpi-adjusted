"""日銀「消費者物価のコア指標」データの取得・パース

データソース:
- https://www.boj.or.jp/research/research_data/cpi/cpirev.xlsx
  毎月CPI公表日の2営業日後に更新

Excel構造 (chartシート):
  行0: 空
  行1: 系列名（日本語）
  行2: 基準年
  行3: 系列名（英語）
  行4: 基準年（英語）
  行5〜: データ（col 0=日付, col 1〜=前年比%）

  2020年基準の列:
    col 1: 除く生鮮食品、特殊要因（前年比%）= コアCPI
    col 4: 除く生鮮食品・エネルギー、特殊要因（前年比%）= コアコアCPI
    col 7: 除く食料・エネルギー、特殊要因（前年比%）= 日銀コア
    col 10: 刈込平均値（前年比%）
    col 16: 加重中央値（前年比%）
"""

from pathlib import Path

import pandas as pd
import requests

from src.config import BOJ_DIR

BOJ_URL = "https://www.boj.or.jp/research/research_data/cpi/cpirev.xlsx"
BOJ_PATH = BOJ_DIR / "cpi_core_indicators.xlsx"

# 2020年基準の特殊要因除外系列の列インデックス
BOJ_SERIES_COLS = {
    "core_ex_special": 1,       # 除く生鮮食品、特殊要因
    "core_core_ex_special": 4,  # 除く生鮮食品・エネルギー、特殊要因
    "boj_core_ex_special": 7,   # 除く食料・エネルギー、特殊要因
}


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


def parse_boj(filepath: Path | None = None) -> dict[str, pd.Series]:
    """日銀コア指標Excelをパース

    Returns:
        {系列名: 前年比%のSeries(index=YYYY-MM)}
        系列名: "core_ex_special", "core_core_ex_special", "boj_core_ex_special"
    """
    if filepath is None:
        filepath = BOJ_PATH

    df = pd.read_excel(filepath, sheet_name="chart", header=None, skiprows=5)

    # 日付列をYYYY-MM形式に変換
    dates = pd.to_datetime(df.iloc[:, 0])
    ym_index = dates.dt.strftime("%Y-%m")

    result = {}
    for name, col in BOJ_SERIES_COLS.items():
        if col < df.shape[1]:
            values = pd.to_numeric(df.iloc[:, col], errors="coerce")
            s = pd.Series(values.values, index=ym_index, name=name)
            # NaN行を除去
            s = s.dropna()
            result[name] = s

    return result
