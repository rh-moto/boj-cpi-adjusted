"""電気代モデル価格による調整（東京電力 従量電灯Bベース）

CPIの電気代指数は10電力会社×5使用量パターン×2区分の加重平均だが、
ここでは東京電力の従量電灯B（30A）をモデルとして使用。

モデル式:
  月額 = 基本料金 + Σ(段階別単価 + 燃調単価) × 段階内kWh
         + 再エネ賦課金 × 総kWh - 口座振替割引

調整方式:
  補助金ありの燃調単価で計算した月額 → 公表CPIに対応
  補助金なしの燃調単価で計算した月額 → 調整済CPIに対応

  調整比 = P_no_subsidy(t) / P_with_subsidy(t)
  I_adj(t) = I_CPI(t) × 調整比

  これにより感応度の固定値推定を不要にし、
  燃調・再エネ・基本料金の変化を正確に反映する。
"""

import pandas as pd

from src.config import POLICY_DIR

ELECTRICITY_ITEM_CODE = "3500"
DEFAULT_USAGE_KWH = 330  # 5パターンの中央値


def _load_rates() -> pd.DataFrame:
    """TEPCO料金テーブルを読み込み"""
    return pd.read_csv(POLICY_DIR / "tepco_rates.csv")


def _load_fuel_adj() -> pd.DataFrame:
    """燃調単価の月次データを読み込み"""
    return pd.read_csv(POLICY_DIR / "tepco_fuel_adjustment.csv")


def _load_renew_surcharge() -> pd.DataFrame:
    """再エネ賦課金テーブルを読み込み"""
    return pd.read_csv(POLICY_DIR / "renew_energy_surcharge.csv")


def _get_rate_for_month(rates_df: pd.DataFrame, ym: str) -> dict:
    """指定月に適用される料金を返す"""
    applicable = rates_df[rates_df["effective_from"] <= ym]
    if len(applicable) == 0:
        raise ValueError(f"料金データがありません: {ym}")
    row = applicable.iloc[-1]
    return {
        "basic": row["basic_30a"],
        "tier1_limit": int(row["tier1_limit"]),
        "tier1_rate": row["tier1_rate"],
        "tier2_limit": int(row["tier2_limit"]),
        "tier2_rate": row["tier2_rate"],
        "tier3_rate": row["tier3_rate"],
        "discount": row["discount"],
    }


def _get_renew_surcharge(surcharge_df: pd.DataFrame, ym: str) -> float:
    """指定月の再エネ賦課金単価を返す"""
    for _, row in surcharge_df.iterrows():
        if row["effective_from"] <= ym <= row["effective_to"]:
            return row["surcharge_per_kwh"]
    # 範囲外の場合は最後の値を使う
    return surcharge_df.iloc[-1]["surcharge_per_kwh"]


def compute_model_price(
    rate: dict,
    fuel_adj: float,
    renew_surcharge: float,
    usage_kwh: int = DEFAULT_USAGE_KWH,
) -> float:
    """モデル月額料金を計算

    Args:
        rate: 料金テーブル（_get_rate_for_monthの戻り値）
        fuel_adj: 燃料費調整単価（円/kWh）
        renew_surcharge: 再エネ賦課金（円/kWh）
        usage_kwh: 使用量（kWh）

    Returns:
        月額料金（円）
    """
    basic = rate["basic"]
    discount = rate["discount"]

    # 段階別の従量料金計算
    tier1 = min(usage_kwh, rate["tier1_limit"])
    tier2 = min(max(usage_kwh - rate["tier1_limit"], 0),
                rate["tier2_limit"] - rate["tier1_limit"])
    tier3 = max(usage_kwh - rate["tier2_limit"], 0)

    energy_charge = (
        tier1 * (rate["tier1_rate"] + fuel_adj)
        + tier2 * (rate["tier2_rate"] + fuel_adj)
        + tier3 * (rate["tier3_rate"] + fuel_adj)
    )

    renew_charge = renew_surcharge * usage_kwh

    return basic + energy_charge + renew_charge - discount


def compute_adjusted_index(
    cpi_index: pd.Series,
    usage_kwh: int = DEFAULT_USAGE_KWH,
) -> pd.Series:
    """電気代の調整済CPI指数を算出（モデル価格方式）

    補助金ありと補助金なしのモデル価格を計算し、その比で調整。

    Args:
        cpi_index: CPIの電気代指数（月次）
        usage_kwh: モデル使用量

    Returns:
        調整済CPI指数
    """
    rates_df = _load_rates()
    fuel_df = _load_fuel_adj()
    surcharge_df = _load_renew_surcharge()

    fuel_dict_with = dict(zip(fuel_df["year_month"], fuel_df["fuel_adj_with_subsidy"]))
    fuel_dict_without = dict(zip(fuel_df["year_month"], fuel_df["fuel_adj_without_subsidy"]))

    adjusted = cpi_index.copy()

    for ym in cpi_index.index:
        if ym not in fuel_dict_with or ym not in fuel_dict_without:
            continue

        fuel_with = fuel_dict_with[ym]
        fuel_without = fuel_dict_without[ym]

        # 補助金なしの場合と同じなら調整不要
        if abs(fuel_with - fuel_without) < 0.001:
            continue

        rate = _get_rate_for_month(rates_df, ym)
        renew = _get_renew_surcharge(surcharge_df, ym)

        price_with = compute_model_price(rate, fuel_with, renew, usage_kwh)
        price_without = compute_model_price(rate, fuel_without, renew, usage_kwh)

        # 調整比でCPI指数を補正
        ratio = price_without / price_with
        adjusted[ym] = cpi_index[ym] * ratio

    return adjusted
