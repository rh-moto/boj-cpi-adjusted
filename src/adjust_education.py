"""教育無償化調整（Phase 4）

調整方式:
  政策による指数の段差を加算して、政策がなかった場合の水準に復元する。
    I_adj(i,t) = I_公表(i,t) + step_size  （政策開始月以降）

  step_size = I(政策開始前月) − I(政策開始月)
  （政策で指数が下がった分を足し戻す）

対象品目と政策イベント:
  8020 高等学校授業料（公立）:
    2024-04: Δ=-6.7  (何らかの制度変更)
    2025-04: Δ=-87.3 (高校就学支援金の所得制限撤廃→実質完全無償化)
  8030 高等学校授業料（私立）:
    2020-04: Δ=-8.6  (2020年4月の私立高校支援拡充)
    2024-04: Δ=-11.9 (支援拡充)
    2025-04: Δ=-9.7  (所得制限撤廃に伴う追加支援)

注意:
  - 段差が純粋に政策由来かの検証が必要（季節要因・定義変更の除外）
  - 授業料は年度単位で変わるため、4月の段差は政策由来と判断して問題ない
  - 2020-04の私立高校の段差は基準年内のため、前年比には2021-04以降に影響
"""

import pandas as pd

from src.config import POLICY_DIR

# 教育無償化による指数段差テーブル
# (品目コード, 政策開始月, 段差=開始前月-開始月)
EDUCATION_STEPS = [
    # 高等学校授業料（公立）
    ("8020", "2024-04", 6.7),    # 99.5→92.8
    ("8020", "2025-04", 87.3),   # 92.8→5.5（所得制限撤廃→実質完全無償化）
    # 高等学校授業料（私立）
    ("8030", "2020-04", 8.6),    # 106.4→97.9 (基準年内、前年比は2021-04〜)
    ("8030", "2024-04", 11.9),   # 102.6→90.7
    ("8030", "2025-04", 9.7),    # 90.7→81.1（所得制限撤廃に伴う追加支援）
    # 保育所保育料
    ("9921", "2025-09", 7.2),    # 95.6→88.3（多子世帯無償化拡充）
]


def compute_adjusted_index(cpi_index: pd.Series, item_code: str) -> pd.Series:
    """教育品目の調整済CPI指数を算出

    対象品目の政策段差を累積的に加算し、政策がなかった場合の指数水準を復元する。

    Args:
        cpi_index: CPI指数（月次）
        item_code: 品目コード

    Returns:
        調整済CPI指数
    """
    # この品目に該当する段差を収集
    steps = [(ym, step) for code, ym, step in EDUCATION_STEPS if code == item_code]
    if not steps:
        return cpi_index.copy()

    adjusted = cpi_index.copy()
    for ym in adjusted.index:
        # この月以前に発生した段差を累積加算
        total_step = sum(step for step_ym, step in steps if ym >= step_ym)
        if total_step > 0:
            adjusted[ym] = cpi_index[ym] + total_step

    return adjusted


def get_all_education_adjusted(indices: pd.DataFrame) -> dict[str, pd.Series]:
    """全教育品目の調整済指数を返す

    Returns:
        {品目コード: 調整済指数Series}
    """
    affected_codes = set(code for code, _, _ in EDUCATION_STEPS)
    result = {}
    for code in affected_codes:
        if code in indices.columns:
            result[code] = compute_adjusted_index(indices[code], code)
    return result
