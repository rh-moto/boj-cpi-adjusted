"""ガソリン調整（Phase 1）

調整方式:
  資源エネルギー庁の「補助金なかりせば価格」を用いて、補助金がなかった場合の
  ガソリンCPI指数を算出する。

  I_調整済(t) = 補助金なかりせば価格(t) / P₀ × 100

  P₀ = 2020年平均のガソリン小売価格（円/L）

2層構造:
  Layer 1: 補助金除去 → 「補助金なかりせば価格」を直接使用
  Layer 2: 暫定税率廃止調整 → 2025年12月31日以降、廃止された暫定税率分を復元

暫定税率廃止の処理:
  2025年12月31日にガソリン暫定税率25.1円/Lが廃止された。
  「補助金なかりせば価格」は廃止後の税率で計算されているため、
  廃止前の状態に戻すには暫定税率相当額を加算する必要がある。

  暫定税率復元額 = 25.1円（税本体）+ 25.1 × 0.1（消費税分）= 27.61円/L
  ※ 2025年11月〜12月は補助金増額で段階的に移行しているため線形補間で処理

週次→月次変換:
  CPIガソリンは毎月中旬の調査価格を基に算出される。
  METIの週次価格は月曜日時点の価格。
  月次化は当月の全週の単純平均を使用（CPIの採価タイミングとの厳密な整合は
  日銀公表値との突合で検証する）。
"""

import pandas as pd
import numpy as np

from src.config import METI_DIR

# ガソリン関連定数
GASOLINE_ITEM_CODE = "7301"

# 暫定税率関連
PROVISIONAL_TAX_RATE = 25.1         # 円/L（暫定税率額）
CONSUMPTION_TAX_RATE = 0.10         # 消費税率
PROVISIONAL_TAX_TOTAL = PROVISIONAL_TAX_RATE * (1 + CONSUMPTION_TAX_RATE)  # ≈ 27.61円/L

# 暫定税率廃止のスケジュール
# 2025年11月13日: 補助金10円→15円（暫定税率廃止への移行開始）
# 2025年11月27日: 補助金15円→20円
# 2025年12月11日: 補助金20円→25.1円
# 2025年12月31日: 暫定税率正式廃止
TAX_ABOLITION_DATE = "2025-12-31"
TAX_TRANSITION_START = "2025-11"  # 移行期間開始月
TAX_TRANSITION_END = "2026-01"    # 完全廃止後の最初の月


def load_counterfactual_prices(filepath=None) -> pd.DataFrame:
    """METI「補助金なかりせば価格」の週次データを読み込む

    Returns:
        DataFrame with columns: date, price_counterfactual
        date: 調査日（週次、月曜日）
        price_counterfactual: 補助金なかりせば価格（円/L）
    """
    if filepath is None:
        filepath = METI_DIR / "gasoline_counterfactual.csv"

    df = pd.read_csv(filepath, parse_dates=["date"])
    return df


def load_retail_prices(filepath=None) -> pd.DataFrame:
    """METI石油製品価格調査のガソリン小売価格を読み込む

    Returns:
        DataFrame with columns: date, price_retail
    """
    if filepath is None:
        filepath = METI_DIR / "gasoline_retail.csv"

    df = pd.read_csv(filepath, parse_dates=["date"])
    return df


def compute_p0(retail_prices: pd.DataFrame, year: int = 2020) -> float:
    """基準年の平均ガソリン小売価格(P₀)を算出

    Args:
        retail_prices: METI小売価格DataFrame
        year: 基準年（デフォルト2020）

    Returns:
        P₀（円/L）
    """
    mask = retail_prices["date"].dt.year == year
    prices = retail_prices.loc[mask, "price_retail"]
    if len(prices) == 0:
        raise ValueError(f"{year}年のデータがありません")

    p0 = prices.mean()
    return p0


def weekly_to_monthly(weekly_df: pd.DataFrame, price_col: str) -> pd.Series:
    """週次価格を月次平均に変換

    Args:
        weekly_df: date列と価格列を持つDataFrame
        price_col: 価格列名

    Returns:
        月次平均価格（index=YYYY-MM）
    """
    df = weekly_df.copy()
    df["year_month"] = df["date"].dt.strftime("%Y-%m")
    monthly = df.groupby("year_month")[price_col].mean()
    return monthly


def adjust_for_provisional_tax(
    monthly_counterfactual: pd.Series,
) -> pd.Series:
    """暫定税率廃止の影響を復元（Layer 2）

    2025年12月31日以降の「補助金なかりせば価格」には暫定税率廃止が反映されている。
    特殊要因として除去するため、廃止前の税額分を加算して復元する。

    2025年11月〜12月は移行期間として線形補間で処理。

    Returns:
        暫定税率復元後の月次価格
    """
    adjusted = monthly_counterfactual.copy()

    for ym in adjusted.index:
        if ym < TAX_TRANSITION_START:
            # 移行前: 調整不要
            pass
        elif ym == "2025-11":
            # 移行期間1: 補助金増額が始まったが暫定税率はまだ存在
            # 段階的な補助金増額は反実仮想価格には影響しない
            # （反実仮想価格は補助金を除いた価格なので）
            pass
        elif ym == "2025-12":
            # 移行期間2: 月の途中（12/31）で暫定税率廃止
            # 12月分は暫定税率ありの期間が大半なので調整は小さい
            # 約1/31日分だけ暫定税率がない → ほぼ調整不要
            pass
        elif ym >= TAX_TRANSITION_END:
            # 完全廃止後: 暫定税率分を加算して復元
            adjusted[ym] = adjusted[ym] + PROVISIONAL_TAX_TOTAL

    return adjusted


def compute_adjusted_index(
    monthly_counterfactual: pd.Series,
    p0: float,
    apply_tax_adjustment: bool = True,
) -> pd.Series:
    """ガソリン調整済CPI指数を算出

    Args:
        monthly_counterfactual: 月次の「補助金なかりせば価格」（円/L）
        p0: 基準年平均価格（円/L）
        apply_tax_adjustment: 暫定税率復元を適用するか

    Returns:
        調整済ガソリンCPI指数（index=YYYY-MM）
    """
    if apply_tax_adjustment:
        prices = adjust_for_provisional_tax(monthly_counterfactual)
    else:
        prices = monthly_counterfactual

    # I_調整済(t) = 価格(t) / P₀ × 100
    adjusted_index = prices / p0 * 100
    adjusted_index.name = GASOLINE_ITEM_CODE

    return adjusted_index


def compute_adjusted_index_from_cpi(
    cpi_gas_index: pd.Series,
    subsidy_per_liter: pd.Series,
    p0: float,
    apply_tax_adjustment: bool = True,
) -> pd.Series:
    """CPIガソリン指数と補助金単価から調整済指数を算出する代替方式

    METIの反実仮想価格が利用できない場合のフォールバック。
    CPI指数から実勢価格を復元し、補助金分を加算して反実仮想価格を得る。

    I_調整済(t) = (I_CPI(t)/100 × P₀ + subsidy(t)) / P₀ × 100
                = I_CPI(t) + subsidy(t)/P₀ × 100

    Args:
        cpi_gas_index: CPIガソリン指数（月次）
        subsidy_per_liter: 補助金単価（円/L、月次）
        p0: 基準年平均価格（円/L）
        apply_tax_adjustment: 暫定税率復元を適用するか

    Returns:
        調整済ガソリンCPI指数
    """
    # 補助金分のCPI指数への影響
    subsidy_index_impact = subsidy_per_liter / p0 * 100
    adjusted = cpi_gas_index + subsidy_index_impact

    if apply_tax_adjustment:
        # 2026年1月以降に暫定税率復元分を加算
        tax_index_impact = PROVISIONAL_TAX_TOTAL / p0 * 100
        for ym in adjusted.index:
            if ym >= TAX_TRANSITION_END:
                adjusted[ym] = adjusted[ym] + tax_index_impact

    adjusted.name = GASOLINE_ITEM_CODE
    return adjusted
