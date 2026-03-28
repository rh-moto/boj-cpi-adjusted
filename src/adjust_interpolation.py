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
    """携帯通信料の調整（年度保合＋固定段差方式）

    1. 急落前（〜2021-03）: 実績値そのまま
    2. 急落年度（2021-04〜2022-03）: 急落前水準で保合
    3. 2022-04以降: 固定段差を加算
       step = 2021-03の水準 - 2022-03の水準（年度末時点の段差）
       adjusted[t] = actual[t] + step

    日銀は前年比ベースで寄与度を差し引く方式の可能性があり、
    指数水準ベースの調整では2021-2022年の完全一致は困難。
    """
    adjusted = cpi_index.copy()

    start_ym = "2021-03"
    end_ym = "2022-03"
    if start_ym not in cpi_index.index or end_ym not in cpi_index.index:
        return adjusted

    val_pre = cpi_index[start_ym]
    step = val_pre - cpi_index[end_ym]

    for ym in adjusted.index:
        if ym <= start_ym:
            pass
        elif ym <= end_ym:
            adjusted[ym] = val_pre
        else:
            adjusted[ym] = cpi_index[ym] + step

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
