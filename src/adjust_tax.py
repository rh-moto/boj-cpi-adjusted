"""消費税調整モジュール（2019年10月 8%→10%）

調整方式（総務省方式に準拠）:
  I_調整済(i,t) = I_公表(i,t) × v(i,t)

  v(i,t)の設定:
    通常課税品目: v = 1.08/1.10 (2019年10月以降)
    非課税品目:   v = 1 (調整なし)
    軽減税率品目: v = 1 (8%据置のため)
    経過措置品目: 月によって異なる（type1: 翌月から、type2: 部分適用）
    季節調査品目: 調査月に応じて適用開始月がずれる（未実装、必要に応じて追加）

データソース:
  data/policy_params/tax_category_2019.csv（品目別課税区分）
  総務省「消費税調整済指数の作成について」(2015taxadj.pdf)
"""

import pandas as pd

from src.config import POLICY_DIR

TAX_CATEGORY_PATH = POLICY_DIR / "tax_category_2019.csv"

# 税率
OLD_RATE = 1.08  # 旧税率（8%）
NEW_RATE = 1.10  # 新税率（10%）
BASE_FACTOR = OLD_RATE / NEW_RATE  # ≈ 0.98182


def load_tax_categories() -> pd.DataFrame:
    """品目別消費税区分を読み込み"""
    return pd.read_csv(TAX_CATEGORY_PATH, dtype={"item_code": str})


def get_adjustment_factor(
    item_code: str,
    year_month: str,
    tax_cats: pd.DataFrame,
    master: pd.DataFrame | None = None,
) -> float:
    """品目×月の消費税調整係数v(i,t)を返す

    Returns:
        1.0 = 調整なし、BASE_FACTOR ≈ 0.982 = 通常課税品目の10月以降
    """
    # まずCSVに明示登録されている品目を確認
    row = tax_cats[tax_cats["item_code"] == item_code]
    if not row.empty:
        cat = row.iloc[0]["tax_category"]
        detail = row.iloc[0]["tax_detail"] if pd.notna(row.iloc[0]["tax_detail"]) else ""
    else:
        # CSVに未登録の品目: 食料（酒類・外食除く）は軽減税率
        if master is not None:
            m_row = master[master["item_code"] == item_code]
            if not m_row.empty:
                row_data = m_row.iloc[0]
                is_food = row_data["is_food"]
                is_alcohol = row_data["is_alcohol"]
                is_eating_out = "外食" in str(row_data.get("category_mid", ""))
                if is_food and not is_alcohol and not is_eating_out:
                    cat = "reduced"
                    detail = ""
                else:
                    cat = "standard"
                    detail = ""
            else:
                cat = "standard"
                detail = ""
        else:
            cat = "standard"
            detail = ""

    if cat == "exempt":
        return 1.0

    if cat == "reduced":
        return 1.0

    if cat == "transitional":
        if detail == "type1":
            # 電気代・ガス代・水道等: 改定当月は旧税率、翌月から新税率
            if year_month <= "2019-10":
                return 1.0
            else:
                return BASE_FACTOR

        if detail == "type2":
            # 固定電話: 2019年10月にウエイトで2/3が新税率
            if year_month <= "2019-09":
                return 1.0
            elif year_month == "2019-10":
                return OLD_RATE / NEW_RATE * (2 / 3) + 1.0 * (1 / 3)
            else:
                return BASE_FACTOR

        if detail == "type2_mobile":
            # 携帯電話: 2019年10月にウエイトで4/5が新税率
            if year_month <= "2019-09":
                return 1.0
            elif year_month == "2019-10":
                return OLD_RATE / NEW_RATE * (4 / 5) + 1.0 * (1 / 5)
            else:
                return BASE_FACTOR

    # デフォルト: 通常課税品目
    if year_month >= "2019-10":
        return BASE_FACTOR
    return 1.0


def apply_tax_adjustment(
    indices: pd.DataFrame,
    item_codes: list[str] | None = None,
    master: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """消費税調整を品目別指数に適用

    Args:
        indices: 品目別CPI指数DataFrame
        item_codes: 対象品目コードのリスト（Noneなら全品目）
        master: 品目マスタ（軽減税率判定用）

    Returns:
        消費税調整済の指数DataFrame
    """
    tax_cats = load_tax_categories()
    adjusted = indices.copy()

    codes = item_codes or [c for c in indices.columns if not c.startswith("0")]

    for code in codes:
        if code not in adjusted.columns:
            continue
        for ym in adjusted.index:
            factor = get_adjustment_factor(code, ym, tax_cats, master)
            if factor != 1.0:
                adjusted.loc[ym, code] = indices.loc[ym, code] * factor

    return adjusted
