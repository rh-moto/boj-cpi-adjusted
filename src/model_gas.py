"""都市ガス代モデル価格による調整（東京ガス一般料金ベース）

電気代(model_electricity.py)と同じアプローチ:
  - 東京ガスの料金表＋原料費調整単価でモデル月額を計算
  - P₀(2020年平均)で感応度を導出
  - 加法方式で補助金の影響をCPI指数に加算

モデル式（東京ガス一般料金 B表）:
  月額 = 基本料金(1,056円) + (基準単位料金(130.46円) + 原料費調整額) × 使用量

使用量:
  CPIのモデルは5パターン(400/900/1400/2100/3900 MJ)
  都市ガス13A: 1m³≈45MJ → 8.9/20/31.1/46.7/86.7 m³
  中央値: 31.1m³ ≈ 31m³

補助金のCPI反映:
  使用月＋1ヶ月ラグ（電気代と同じ）
"""

import pandas as pd

from src.config import POLICY_DIR

CITY_GAS_ITEM_CODE = "3600"
DEFAULT_USAGE_M3 = 31  # 中央値パターン

# 東京ガス一般料金 B表
BASIC_CHARGE = 1056.0  # 円/月
BASE_UNIT_RATE = 130.46  # 円/m³（基準単位料金）


def _load_gas_adjustment() -> pd.DataFrame:
    """東京ガスの原料費調整単価の月次データを読み込み"""
    path = POLICY_DIR / "tokyo_gas_adjustment.csv"
    return pd.read_csv(path)


def compute_p0(usage_m3: int = DEFAULT_USAGE_M3) -> float:
    """2020年平均のモデル月額料金(P₀)を算出"""
    df = _load_gas_adjustment()
    adj_dict = dict(zip(df["year_month"], df["adj_with_subsidy"]))

    total = 0
    count = 0
    for m in range(1, 13):
        ym = f"2020-{m:02d}"
        adj = adj_dict.get(ym, 0)
        price = BASIC_CHARGE + (BASE_UNIT_RATE + adj) * usage_m3
        total += price
        count += 1
    return total / count


def compute_adjusted_index(
    cpi_index: pd.Series,
    usage_m3: int = DEFAULT_USAGE_M3,
) -> pd.Series:
    """都市ガス代の調整済CPI指数を算出（加法方式）

    電気代と同じく、モデル由来のP₀で感応度を計算し、
    補助金の絶対額をCPI指数に加算。

      adjusted = CPI + subsidy_per_m3 × usage / P₀ × 100

    補助金はCPIラグ（使用月+1ヶ月）を反映した値を使用。
    """
    from src.adjust_energy import get_monthly_subsidy_by_cpi_month
    subsidy_by_cpi = get_monthly_subsidy_by_cpi_month("gas")

    p0 = compute_p0(usage_m3)
    sensitivity = usage_m3 / p0 * 100

    adjusted = cpi_index.copy()
    for ym in cpi_index.index:
        sub = subsidy_by_cpi.get(ym, 0.0)
        if sub > 0:
            adjusted[ym] = cpi_index[ym] + sub * sensitivity

    return adjusted
