"""総務省CPI品目別指数の取得・パース

データソース:
- 月次品目別CSV（2015年基準・2020年基準共通フォーマット）
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

from src.config import SOUMU_DIR, CPI_CSV_URLS, CPI_CSV_FILENAMES, BASE_YEAR


def _csv_path(base_year: int | None = None) -> Path:
    by = base_year or BASE_YEAR
    return SOUMU_DIR / CPI_CSV_FILENAMES[by]


def _csv_url(base_year: int | None = None) -> str:
    by = base_year or BASE_YEAR
    return CPI_CSV_URLS[by]


def download_cpi_csv(force: bool = False, base_year: int | None = None) -> Path:
    """総務省月次CPI CSVをダウンロード"""
    path = _csv_path(base_year)
    url = _csv_url(base_year)

    if path.exists() and not force:
        print(f"既存ファイルを使用: {path}")
        return path

    print(f"ダウンロード中: {url}")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resp.content)
    print(f"保存: {path} ({len(resp.content)} bytes)")
    return path


def parse_cpi_csv(
    filepath: Path | None = None,
    base_year: int | None = None,
) -> tuple[pd.DataFrame, dict]:
    """月次CPI CSVをパースして品目別月次指数のDataFrameを返す

    Args:
        filepath: CSVファイルパス（Noneならbase_yearから自動決定）
        base_year: 基準年（2015 or 2020）

    Returns:
        (item_indices, metadata)
        item_indices: index=YYYY-MM形式の年月, columns=品目コード(str), values=指数値(float)
        metadata: 品目コードをキーとする辞書 {code: {name_jp, weight_10000}}
    """
    if filepath is None:
        filepath = _csv_path(base_year)

    if not filepath.exists():
        download_cpi_csv(base_year=base_year)

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

    # データ部分（行6〜）の読み込み
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
    """CSVヘッダに含まれる固定基準ウエイト（1万分比）を返す"""
    w = {code: m["weight_10000"] for code, m in metadata.items()}
    return pd.Series(w, name="weight_10000")


def get_item_level_indices(item_indices: pd.DataFrame, master_codes: list[str]) -> pd.DataFrame:
    """品目マスタに存在する品目コードだけを抽出"""
    available = [c for c in master_codes if c in item_indices.columns]
    return item_indices[available]
