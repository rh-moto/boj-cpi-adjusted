"""ガソリン調整（Phase 1）

調整方式:
  PDFグラフ（nenryo-teigakuhikisage.go.jp/current_graph.pdf）から読み取った
  月次の「補助なし価格」と小売価格の差額（=総補助額）を使用。

  補助金は定額部分（基準価格引下げ）と変動部分（超過分補助）の合計であり、
  定額部分のみのテーブルでは精度が出ない。

  I_adj(t) = I_CPI(t) + subsidy_total(t) / P₀ × 100

  P₀ = 2020年平均ガソリン小売価格 ≈ 134.1円/L (METI週次調査)

暫定税率廃止の処理:
  2025年12月31日にガソリン暫定税率25.1円/Lが廃止された。
  廃止は特殊要因として除去対象なので、廃止前の水準に復元する。

  復元額 = 25.1円（税本体）+ 25.1 × 0.1（消費税分）= 27.61円/L
  2026年1月以降の調整済指数に加算。

データソース:
  data/policy_params/gasoline_subsidy_monthly.csv
    PDFグラフから目視で読み取った月次データ（±2円/Lの誤差あり）
    scripts/build_gasoline_subsidy.py で生成
"""

import pandas as pd

from src.config import POLICY_DIR

GASOLINE_ITEM_CODE = "7301"
P0_GASOLINE = 134.1  # 2020年平均小売価格（円/L）
PROVISIONAL_TAX_RESTORE = 25.1 * 1.1  # 暫定税率復元額（27.61円/L）


def load_monthly_subsidy() -> pd.Series:
    """月次補助額（PDFグラフ読み取りベース）を読み込み

    Returns:
        月次の総補助額（index=YYYY-MM, 円/L）
    """
    path = POLICY_DIR / "gasoline_subsidy_monthly.csv"
    df = pd.read_csv(path)
    return pd.Series(
        df["subsidy_total"].values,
        index=df["year_month"].values,
        name="gasoline_subsidy",
    )


def compute_adjusted_index(cpi_gas_index: pd.Series) -> pd.Series:
    """ガソリン調整済CPI指数を算出

    Args:
        cpi_gas_index: CPIガソリン指数（月次）

    Returns:
        調整済CPI指数（補助金+暫定税率を除去した場合の指数）
    """
    monthly_sub = load_monthly_subsidy()

    adjusted = cpi_gas_index.copy()
    for ym in cpi_gas_index.index:
        # 補助金分を加算
        sub = monthly_sub.get(ym, 0.0)
        adjusted[ym] = cpi_gas_index[ym] + sub / P0_GASOLINE * 100

        # 暫定税率復元（2026年1月以降）
        if ym >= "2026-01":
            adjusted[ym] += PROVISIONAL_TAX_RESTORE / P0_GASOLINE * 100

    return adjusted
