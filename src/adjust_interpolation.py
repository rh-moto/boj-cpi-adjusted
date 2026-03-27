"""携帯通信料・旅行支援の線形補間調整（Phase 5）

調整方式:
  政策による急激な指数変動を、変動前後の2点を結ぶ線形補間で代替する。
  「政策がなかった場合の指数」を補間直線で近似するアプローチ。

携帯通信料（7430）:
  2021年3月〜4月にahamo等の低価格プラン登場で指数が急落。
  政府の値下げ要請による事実上の政策誘導。
  補間区間: 2021-03（急落直前）〜 2022-01（安定後）
  2022-01以降は実績値をそのまま使用（影響が完全に織り込まれた後）

宿泊料（9300）:
  2022年10月〜2023年12月に旅行支援策で指数が低下。
  宿泊料は季節変動が大きいため、水準の補間ではなく
  支援期間中の指数に「割引分の推定復元額」を加算する方式も検討。
  ここでは月別の前年同月との比較で補間区間を特定する。
  補間区間: 2022-10（支援開始）〜 2023-12（支援終了）頃
"""

import numpy as np
import pandas as pd


def interpolate_index(
    cpi_index: pd.Series,
    start_ym: str,
    end_ym: str,
) -> pd.Series:
    """指定区間を線形補間で置き換え

    start_ymとend_ymの指数値を端点として、その間を線形補間する。
    区間外はそのまま。

    Args:
        cpi_index: 月次CPI指数
        start_ym: 補間開始月（この月の値を端点として使用）
        end_ym: 補間終了月（この月の値を端点として使用）

    Returns:
        調整済CPI指数
    """
    adjusted = cpi_index.copy()

    all_months = list(cpi_index.index)
    if start_ym not in all_months or end_ym not in all_months:
        return adjusted

    i_start = all_months.index(start_ym)
    i_end = all_months.index(end_ym)
    if i_end <= i_start:
        return adjusted

    val_start = cpi_index[start_ym]
    val_end = cpi_index[end_ym]
    n_months = i_end - i_start

    # 端点間を線形補間
    for i in range(i_start + 1, i_end):
        t = (i - i_start) / n_months
        adjusted.iloc[i] = val_start + (val_end - val_start) * t

    return adjusted


def adjust_mobile(cpi_index: pd.Series) -> pd.Series:
    """携帯通信料の調整

    2021年3月（急落直前）と2022年1月（安定後）を端点として線形補間。
    2022年1月以降は実績値を使用。
    """
    return interpolate_index(cpi_index, "2021-03", "2022-01")


def adjust_hotel(cpi_index: pd.Series) -> pd.Series:
    """宿泊料の調整

    旅行支援期間（2022-10〜2023-12）を補間。
    宿泊料は季節変動が大きいので、支援開始直前月（2022-09）と
    支援終了直後月（2024-01）を端点として線形補間。
    """
    return interpolate_index(cpi_index, "2022-09", "2024-01")
