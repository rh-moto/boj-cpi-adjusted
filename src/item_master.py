"""CPI品目マスタの管理

品目分類の階層:
  10大費目 → 中分類 → 小分類 → 品目

3系列の除外ルール:
  コアCPI = 総合 - 生鮮食品
  コアコアCPI = 総合 - 生鮮食品 - エネルギー
  日銀コア = 総合 - 食料（酒類を除く） - エネルギー

分類フラグ:
  is_fresh: 生鮮食品（生鮮魚介、生鮮野菜、生鮮果物）
  is_energy: エネルギー（電気代、都市ガス代、プロパンガス、灯油、ガソリン）
  is_food_ex_alcohol: 食料から酒類を除いたもの
"""

from pathlib import Path

import pandas as pd

from src.config import POLICY_DIR, BASE_YEAR

# 品目マスタCSVのパス（基準年別）
ITEM_MASTER_PATHS = {
    2015: POLICY_DIR / "item_master_2015.csv",
    2020: POLICY_DIR / "item_master.csv",
}

# エネルギー品目コード（2020年基準、品目情報一覧Excelから確認済み）
ENERGY_ITEM_CODES = {
    "3500",   # 電気代
    "3600",   # 都市ガス代
    "3612",   # プロパンガス
    "3701",   # 灯油
    "7301",   # ガソリン
}

# 特殊要因対象品目コード（品目情報一覧Excelから確認済み）
# ※計画書(boj_cpi_workplan_v2.md)の品目コードと実際のコードが異なる
SPECIAL_FACTOR_ITEMS = {
    "gasoline": {"7301"},                     # ガソリン (計画書では7311)
    "electricity": {"3500"},                  # 電気代
    "city_gas": {"3600"},                     # 都市ガス代 (計画書では3510)
    "mobile": {"7430"},                       # 通信料（携帯電話）(計画書では7340)
    "hotel": {"9300"},                        # 宿泊料 (計画書では9341)
    # 幼稚園保育料: 2020年基準では幼保無償化後のため品目なし（調整不要）
    "nursery": {"9921"},                      # 保育所保育料 (計画書では9511)
    "highschool_public": {"8020"},            # 高等学校授業料（公立）(計画書では8720)
    "highschool_private": {"8030"},           # 高等学校授業料（私立）(計画書では8730)
}


def load_item_master(base_year: int | None = None) -> pd.DataFrame:
    """品目マスタCSVを読み込む

    Args:
        base_year: 基準年（2015 or 2020）。Noneならconfig.BASE_YEARを使用。
    """
    by = base_year or BASE_YEAR
    path = ITEM_MASTER_PATHS[by]
    if not path.exists():
        raise FileNotFoundError(
            f"品目マスタが見つかりません: {path}\n"
            f"scripts/build_item_master{'_2015' if by == 2015 else ''}.py を実行してください"
        )
    df = pd.read_csv(path, dtype={"item_code": str})
    return df


def get_series_filter(series_name: str, master: pd.DataFrame) -> pd.Series:
    """指定系列に含まれる品目のbooleanマスクを返す

    Args:
        series_name: "core", "core_core", "boj_core"
        master: 品目マスタDataFrame

    Returns:
        boolean Series (True = 系列に含まれる)
    """
    if series_name == "core":
        # 総合 - 生鮮食品
        return ~master["is_fresh"]
    elif series_name == "core_core":
        # 総合 - 生鮮食品 - エネルギー
        return ~master["is_fresh"] & ~master["is_energy"]
    elif series_name == "boj_core":
        # 総合 - 食料（酒類を除く） - エネルギー
        # 食料から酒類を除いたものを除外 → 酒類は残る
        is_food_ex_alcohol = master["is_food"] & ~master["is_alcohol"]
        return ~is_food_ex_alcohol & ~master["is_energy"]
    else:
        raise ValueError(f"未知の系列名: {series_name}")
