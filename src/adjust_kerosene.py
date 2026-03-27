"""灯油調整

調整方式:
  ガソリンと同じ燃料油補助制度の対象。
  PDFグラフ（nenryo-teigakuhikisage.go.jp/current_graph.pdf 3ページ目）から
  月次の補助なし価格と小売価格を読み取り、差額を補助額として使用。

  I_adj(t) = I_CPI(t) + subsidy(t) / P₀ × 100

  P₀ = 2020年平均灯油小売価格

注意:
  灯油にはガソリンの暫定税率に相当するものはないため、税制調整は不要。
"""

import pandas as pd

from src.config import POLICY_DIR

KEROSENE_ITEM_CODE = "3701"


def compute_adjusted_index(cpi_index: pd.Series) -> pd.Series:
    """灯油調整済CPI指数を算出"""
    path = POLICY_DIR / "kerosene_subsidy_monthly.csv"
    df = pd.read_csv(path)
    sub_dict = dict(zip(df["year_month"], df["subsidy_total"]))

    # P₀: CPI 2020年平均=100 → P₀ = 2020年平均灯油小売価格
    # METI 2020年平均灯油(店頭)は約81円/L
    P0 = 81.0

    adjusted = cpi_index.copy()
    for ym in cpi_index.index:
        sub = sub_dict.get(ym, 0.0)
        if sub > 0:
            adjusted[ym] = cpi_index[ym] + sub / P0 * 100

    return adjusted
