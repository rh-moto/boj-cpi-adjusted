"""総務省CPI品目別指数の取得・パース

データソース:
- 月次品目別CSV: https://www.stat.go.jp/data/cpi/2020/csv/zmi2020aa.csv
  2020年1月〜最新月、全品目（類・品目レベル含む）の月次指数
  CSV構造:
    行0: 品目名（日本語）
    行1: 品目名（英語）
    行2: 品目符号（類符号 or 品目符号）
    行3: 含類総連番
    行4: ウエイト（実数）
    行5: ウエイト（1万分比）
    行6〜: データ行（年月=YYYYMM, 指数値）
"""

from pathlib import Path

import pandas as pd
import requests

from src.config import SOUMU_DIR

CPI_CSV_URL = "https://www.stat.go.jp/data/cpi/2020/csv/zmi2020aa.csv"
CPI_CSV_PATH = SOUMU_DIR / "cpi_monthly_all.csv"


def download_cpi_csv(force: bool = False) -> Path:
    """総務省月次CPI CSVをダウンロード"""
    if CPI_CSV_PATH.exists() and not force:
        print(f"既存ファイルを使用: {CPI_CSV_PATH}")
        return CPI_CSV_PATH

    print(f"ダウンロード中: {CPI_CSV_URL}")
    resp = requests.get(CPI_CSV_URL, timeout=60)
    resp.raise_for_status()
    CPI_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    CPI_CSV_PATH.write_bytes(resp.content)
    print(f"保存: {CPI_CSV_PATH} ({len(resp.content)} bytes)")
    return CPI_CSV_PATH


def parse_cpi_csv(filepath: Path | None = None) -> tuple[pd.DataFrame, dict]:
    """月次CPI CSVをパースして品目別月次指数のDataFrameを返す

    Returns:
        (item_indices, metadata)
        item_indices: index=YYYY-MM形式の年月, columns=品目コード(str), values=指数値(float)
        metadata: 品目コードをキーとする辞書 {code: {name_jp, name_en, serial, weight, weight_10000}}
    """
    if filepath is None:
        filepath = CPI_CSV_PATH

    # ヘッダ部分（6行）の読み込み
    header = pd.read_csv(filepath, encoding="shift_jis", header=None, nrows=6)

    # 品目コード（行2）、品目名（行0）、ウエイト（行5）
    codes = header.iloc[2, 1:].astype(str).values
    names_jp = header.iloc[0, 1:].astype(str).values
    weights = header.iloc[5, 1:].values

    # メタデータ構築
    metadata = {}
    for i, code in enumerate(codes):
        metadata[code] = {
            "name_jp": names_jp[i],
            "weight_10000": int(weights[i]) if pd.notna(weights[i]) else 0,
        }

    # データ部分（行6〜）の読み込��
    data = pd.read_csv(filepath, encoding="shift_jis", header=None, skiprows=6)

    # 年月を YYYY-MM 形式に変換
    ym_raw = data.iloc[:, 0].astype(str)
    ym_index = ym_raw.apply(lambda x: f"{x[:4]}-{x[4:6]}")

    # 品目別指数DataFrame
    item_indices = pd.DataFrame(
        data.iloc[:, 1:].values,
        index=ym_index,
        columns=codes,
    )
    item_indices.index.name = "year_month"

    # 数値変換（"-"や空欄はNaN）
    item_indices = item_indices.apply(pd.to_numeric, errors="coerce")

    return item_indices, metadata


def get_fixed_weights(metadata: dict) -> pd.Series:
    """CSVヘッダに含まれる固定基準ウエイト（2020年基準、1万分比）を返す

    Returns:
        品目��ードをインデックスとするウエイトSeries
    """
    w = {code: m["weight_10000"] for code, m in metadata.items()}
    return pd.Series(w, name="weight_10000")


def get_item_level_indices(item_indices: pd.DataFrame, master_codes: list[str]) -> pd.DataFrame:
    """品目マスタに存在する品目コードだけを抽出

    CSVには類（大分類・中分類・小分類）レベルの集計値も含まれるため、
    品目マスタに存在する末端品目のみを抽出する。
    """
    available = [c for c in master_codes if c in item_indices.columns]
    return item_indices[available]
