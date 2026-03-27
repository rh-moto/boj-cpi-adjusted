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
    """携帯通信料の調整（恒久的レベルシフト除去）

    急落前（2021-03: 99.4）と安定後（2022-01: 47.0）の段差を:
    1. 過渡期は線形補間
    2. 安定後は恒久的に加算
    """
    adjusted = cpi_index.copy()
    all_months = list(cpi_index.index)

    start_ym = "2021-03"
    end_ym = "2022-01"
    if start_ym not in all_months or end_ym not in all_months:
        return adjusted

    val_start = cpi_index[start_ym]  # 急落前水準
    val_end = cpi_index[end_ym]      # 安定後水準
    full_step = val_start - val_end   # 段差（正値）
    # 急落の全額が政策由来ではなく、一部は自然な市場競争による値下げ。
    # 政策寄与分を9割と推定。
    step = full_step * 0.9

    i_start = all_months.index(start_ym)
    i_end = all_months.index(end_ym)
    n_months = i_end - i_start

    for i in range(len(all_months)):
        ym = all_months[i]
        if ym <= start_ym:
            # 急落前: 調整なし
            pass
        elif i < i_end:
            # 過渡期: 線形補間（急落前水準から段差加算後の安定水準へスムーズに移行）
            t = (i - i_start) / n_months
            # 補間: 急落前水準から、安定後+段差の水準へスムーズに移行
            target_start = val_start
            target_end = val_end + step
            adjusted.iloc[i] = target_start + (target_end - target_start) * t
        else:
            # 安定後: 段差を恒久的に加算
            adjusted.iloc[i] = cpi_index.iloc[i] + step

    return adjusted


def adjust_hotel(cpi_index: pd.Series) -> pd.Series:
    """宿泊料の調整（一時的な旅行支援の除去）

    旅行支援期間（2022-10〜2023-12）の指数に段差を加算。
    支援開始直前月（2022-09）と支援終了直後月（2024-01）の指数を端点とし、
    期間中の値を線形補間で置換する。
    支援終了後は実績値をそのまま使用。
    """
    adjusted = cpi_index.copy()
    all_months = list(cpi_index.index)

    start_ym = "2022-09"
    end_ym = "2024-01"
    if start_ym not in all_months or end_ym not in all_months:
        return adjusted

    i_start = all_months.index(start_ym)
    i_end = all_months.index(end_ym)
    val_start = cpi_index[start_ym]
    val_end = cpi_index[end_ym]
    n_months = i_end - i_start

    # 端点間を線形補間（支援期間のみ）
    for i in range(i_start + 1, i_end):
        t = (i - i_start) / n_months
        adjusted.iloc[i] = val_start + (val_end - val_start) * t

    return adjusted
