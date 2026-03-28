"""携帯通信料・旅行支援の調整（Phase 5）

携帯通信料（7430）:
  2021年3月〜4月にahamo等の低価格プラン登場で指数が急落。
  政府の値下げ要請による事実上の政策誘導で、恒久的なレベルシフト。

  調整方式:
    1. 過渡期（2021-04〜2021-12）: 急落前水準から安定後水準への線形補間
    2. 安定後（2022-01〜）: 段差（急落前 - 安定後）を恒久的に加算

  これにより「値下げ要請がなかった場合」の仮想的な指数を復元する。
  恒久的加算により、以降の前年比は実際の月次変動を反映する。

宿泊料（9300）:
  2022年10月〜2023年12月に旅行支援策で指数が低下。
  旅行支援は一時的な政策のため、支援期間のみ加算し期間後は実績値に戻す。
  支援期間中の指数に段差を加算して「支援がなかった場合」を復元。
"""

import numpy as np
import pandas as pd


def adjust_mobile(cpi_index: pd.Series) -> pd.Series:
    """携帯通信料の調整（保合＋60%反映＋固定段差方式）

    1. 急落前（〜2021-03）: 実績値そのまま
    2. 2021-04: 急落前水準で保合
    3. 2021-05〜2022-03: 実績の月次変動の60%を反映
       （残り40%は自然な市場競争として許容）
    4. 2022-04以降: 実績の月次変動を100%反映（固定段差）
    """
    adjusted = cpi_index.copy()
    all_months = list(cpi_index.index)

    start_ym = "2021-03"
    fy21_end = "2022-03"
    if start_ym not in all_months:
        return adjusted

    i_start = all_months.index(start_ym)
    val_pre = cpi_index[start_ym]

    # 2021-04: 保合
    adjusted.iloc[i_start + 1] = val_pre

    # 2021-05以降
    for i in range(i_start + 2, len(all_months)):
        change = cpi_index.iloc[i] - cpi_index.iloc[i - 1]
        if all_months[i] <= fy21_end:
            adjusted.iloc[i] = adjusted.iloc[i - 1] + change * 0.6
        else:
            adjusted.iloc[i] = adjusted.iloc[i - 1] + change * 1.0

    return adjusted


def adjust_hotel(cpi_index: pd.Series) -> pd.Series:
    """宿泊料の調整（前年同月トレンド延長方式）

    旅行支援期間中の指数を、支援前のトレンドで延長した
    「自然な指数」で置換する。季節パターンが保持される。

    支援期間:
      2022-10〜2022-12: 40%割引（上限8,000円）
      2023-01〜2023-06: 20%割引（上限5,000円、断続的）

    推定方法:
      2022-10〜12: 2021年同月 × (支援前Q1-Q3の平均前年比)
      2023-01〜06: 2022年同月 × (支援なし月の年率成長)
      2023-07以降: 実績値（支援終了後）
    """
    adjusted = cpi_index.copy()

    # 支援前トレンド: 2021→2022のQ1-Q3平均前年比
    pre_yoy_list = []
    for m in range(1, 10):
        ym22 = f"2022-{m:02d}"
        ym21 = f"2021-{m:02d}"
        if ym22 in cpi_index.index and ym21 in cpi_index.index:
            pre_yoy_list.append(cpi_index[ym22] / cpi_index[ym21] - 1)
    pre_yoy = sum(pre_yoy_list) / len(pre_yoy_list) if pre_yoy_list else 0

    # 2022→2024の年率成長（支援なし月、インバウンド回復を含む）
    growth_list = []
    for m in range(1, 10):
        ym24 = f"2024-{m:02d}"
        ym22 = f"2022-{m:02d}"
        if ym24 in cpi_index.index and ym22 in cpi_index.index:
            growth_list.append((cpi_index[ym24] / cpi_index[ym22]) ** 0.5 - 1)
    annual_growth = sum(growth_list) / len(growth_list) if growth_list else 0

    # 2022-10〜12: 2021年同月 × (1+支援前トレンド)
    for m in [10, 11, 12]:
        ym = f"2022-{m:02d}"
        prev_ym = f"2021-{m:02d}"
        if ym in adjusted.index and prev_ym in cpi_index.index:
            adjusted[ym] = cpi_index[prev_ym] * (1 + pre_yoy)

    # 2023-01〜06: 2022年同月 × (1+年率成長)
    for m in range(1, 7):
        ym = f"2023-{m:02d}"
        prev_ym = f"2022-{m:02d}"
        if ym in adjusted.index and prev_ym in cpi_index.index:
            adjusted[ym] = cpi_index[prev_ym] * (1 + annual_growth)

    return adjusted
