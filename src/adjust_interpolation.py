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
    """携帯通信料の調整（保合＋前月比延長方式）

    1. 急落前（〜2021-03）: 実績値そのまま
    2. 急落期間（2021-04〜2021-12）: 急落前水準で保合（横ばい）
    3. 安定後（2022-01〜）: 実績の前月比で延長
       adjusted[t] = adjusted[t-1] × actual[t] / actual[t-1]

    恒久的な固定段差加算ではなく、安定後の自然な価格変動を
    調整済水準からの前月比で反映する。
    """
    adjusted = cpi_index.copy()
    all_months = list(cpi_index.index)

    start_ym = "2021-03"
    end_ym = "2022-01"
    if start_ym not in all_months or end_ym not in all_months:
        return adjusted

    val_start = cpi_index[start_ym]  # 急落前水準
    i_start = all_months.index(start_ym)
    i_end = all_months.index(end_ym)

    for i in range(len(all_months)):
        if i <= i_start:
            # 急落前: 実績値
            pass
        elif i <= i_end:
            # 急落期間: 保合（急落前水準を維持）
            adjusted.iloc[i] = val_start
        else:
            # 安定後: 前月比で延長
            mom = cpi_index.iloc[i] / cpi_index.iloc[i - 1]
            adjusted.iloc[i] = adjusted.iloc[i - 1] * mom

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
