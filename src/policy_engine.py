"""政策イベントテーブル駆動の調整エンジン

policy_events.csvから政策イベントを読み込み、
adjustment_typeに応じた調整を品目別指数に適用する。

adjustment_type:
  step          — 指定月以降に段差(parameter)を累積加算
  hold_and_step — effective_from〜effective_toは保合、以降は固定段差
  trend_extend  — 支援期間中の指数を前年同月トレンドで延長
  tax_restore   — 指定月以降にparameter円/Lを加算（P₀で指数化）
"""

import pandas as pd

from src.config import POLICY_DIR, BASE_YEAR


def load_policy_events(base_year: int | None = None) -> pd.DataFrame:
    """政策イベントテーブルを読み込み、指定基準年に該当するイベントを返す"""
    by = base_year or BASE_YEAR
    path = POLICY_DIR / "policy_events.csv"
    df = pd.read_csv(path, dtype={"item_code": str, "parameter": str})

    # base_yearが空欄（両基準共通）または指定基準年に一致するものをフィルタ
    mask = df["base_year"].isna() | (df["base_year"] == by)
    return df[mask].copy()


def apply_step(cpi_index: pd.Series, events: pd.DataFrame) -> pd.Series:
    """段差加算（step型イベントを適用）"""
    adjusted = cpi_index.copy()
    for _, ev in events.iterrows():
        step = float(ev["parameter"])
        ym_from = ev["effective_from"]
        for ym in adjusted.index:
            if ym >= ym_from:
                adjusted[ym] += step
    return adjusted


def apply_hold_and_step(cpi_index: pd.Series, events: pd.DataFrame) -> pd.Series:
    """保合＋固定段差（hold_and_step型イベントを適用）

    effective_from〜effective_toは急落前水準で保合。
    effective_to以降は段差（急落前 - 年度末）を恒久的に加算。
    """
    adjusted = cpi_index.copy()
    for _, ev in events.iterrows():
        ym_from = ev["effective_from"]
        ym_to = ev["effective_to"]

        # 急落前月 = effective_fromの前月
        all_months = list(cpi_index.index)
        i_from = all_months.index(ym_from) if ym_from in all_months else None
        if i_from is None or i_from == 0:
            continue

        pre_ym = all_months[i_from - 1]
        val_pre = cpi_index[pre_ym]

        if ym_to not in all_months:
            # effective_toがデータ範囲外の場合、データの最終月を使う
            ym_to = all_months[-1]
        val_end = cpi_index[ym_to]
        step = val_pre - val_end

        for ym in adjusted.index:
            if ym_from <= ym <= ym_to:
                adjusted[ym] = val_pre
            elif ym > ym_to:
                adjusted[ym] = cpi_index[ym] + step

    return adjusted


def apply_trend_extend(cpi_index: pd.Series, events: pd.DataFrame) -> pd.Series:
    """前年同月トレンド延長（trend_extend型イベントを適用）"""
    adjusted = cpi_index.copy()
    for _, ev in events.iterrows():
        ym_from = ev["effective_from"]
        ym_to = ev["effective_to"]
        y_from = int(ym_from[:4])
        m_from = int(ym_from[5:7])
        y_to = int(ym_to[:4])
        m_to = int(ym_to[5:7])

        # 支援前のトレンド（前年Q1-Q3の平均前年比）
        pre_yoy_list = []
        for m in range(1, 10):
            ym_curr = f"{y_from}-{m:02d}"
            ym_prev = f"{y_from - 1}-{m:02d}"
            if ym_curr in cpi_index.index and ym_prev in cpi_index.index:
                pre_yoy_list.append(cpi_index[ym_curr] / cpi_index[ym_prev] - 1)
        pre_yoy = sum(pre_yoy_list) / len(pre_yoy_list) if pre_yoy_list else 0

        # 2年間の年率成長（支援なし月から推定）
        growth_list = []
        for m in range(1, 10):
            ym_post = f"{y_from + 2}-{m:02d}"
            ym_base = f"{y_from}-{m:02d}"
            if ym_post in cpi_index.index and ym_base in cpi_index.index:
                growth_list.append((cpi_index[ym_post] / cpi_index[ym_base]) ** 0.5 - 1)
        annual_growth = sum(growth_list) / len(growth_list) if growth_list else 0

        # 支援期間中を推定値で置換
        for m in range(m_from, 13):
            ym = f"{y_from}-{m:02d}"
            prev_ym = f"{y_from - 1}-{m:02d}"
            if ym in adjusted.index and prev_ym in cpi_index.index:
                adjusted[ym] = cpi_index[prev_ym] * (1 + pre_yoy)

        for y in range(y_from + 1, y_to + 1):
            end_m = m_to if y == y_to else 12
            for m in range(1, end_m + 1):
                ym = f"{y}-{m:02d}"
                base_ym = f"{y - 1}-{m:02d}"
                if ym in adjusted.index and base_ym in cpi_index.index:
                    adjusted[ym] = cpi_index[base_ym] * (1 + annual_growth)

    return adjusted


def apply_all_events(
    indices: pd.DataFrame,
    base_year: int | None = None,
) -> pd.DataFrame:
    """全政策イベントを指数DataFrameに適用

    Args:
        indices: 品目別CPI指数DataFrame
        base_year: 基準年

    Returns:
        調整済の指数DataFrame（元のindicesは変更しない）
    """
    events = load_policy_events(base_year)
    adjusted = indices.copy()

    # adjustment_typeごとにグルーピングして適用
    for item_code, item_events in events.groupby("item_code"):
        if item_code not in adjusted.columns:
            continue

        series = adjusted[item_code]

        for adj_type, type_events in item_events.groupby("adjustment_type"):
            # TBDのパラメータがあるイベントはスキップ
            valid = type_events[type_events["parameter"] != "TBD"]
            if valid.empty and adj_type not in ("hold_and_step", "trend_extend"):
                continue

            if adj_type == "step":
                series = apply_step(series, valid)
            elif adj_type == "hold_and_step":
                series = apply_hold_and_step(series, type_events)
            elif adj_type == "trend_extend":
                series = apply_trend_extend(series, type_events)
            # tax_restore はガソリン調整モジュール側で処理（P₀が必要なため）

        adjusted[item_code] = series

    return adjusted
