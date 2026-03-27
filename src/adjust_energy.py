"""電気代・ガス代調整（Phase 2）

調整方式:
  補助金は従量一律（円/kWh, 円/m³）なので:
    I_adj(t) = I_公表(t) + subsidy(使用月) × sensitivity

  sensitivityは補助金導入時のCPI指数変動から独立推定:
    電気代: 7円/kWhで24.6pt下落 → 1円/kWhあたり3.51pt
    ガス代: 30円/m³で13.9pt下落 → 1円/m³あたり0.464pt

  ※日銀公表値へのcalibrateは行わない

補助金のCPIへの反映タイミング:
  補助金は「使用月」ベースで適用されるが、CPIに反映されるのは
  翌月の検針・請求タイミング。
    使用月N → CPI反映月N+1
  例: 2023年1月使用分の補助金 → CPI 2023-02に反映

  補助金単価CSVは「使用月」ベースで記録。
  CPI月への変換はコード側で+1ヶ月ラグを適用。
"""

import pandas as pd

from src.config import POLICY_DIR

# 品目コード
ELECTRICITY_ITEM_CODE = "3500"
CITY_GAS_ITEM_CODE = "3600"

# CPI指数への感応度（補助金1単位あたりのCPI指数変動幅）
# 補助金導入時（使用月2023-01→CPI月2023-02）のCPI指数変動から独立推定
ELEC_SENSITIVITY = 3.51   # CPI pts per yen/kWh
GAS_SENSITIVITY = 0.464   # CPI pts per yen/m³

# 使用月→CPI反映月のラグ（検針タイミングによる）
CPI_LAG_MONTHS = 1


def load_subsidy_table(kind: str) -> pd.DataFrame:
    """補助金単価テーブルを読み込み

    Args:
        kind: "electricity" or "gas"

    Returns:
        DataFrame（使用月ベース）
    """
    if kind == "electricity":
        path = POLICY_DIR / "electricity_subsidy.csv"
    elif kind == "gas":
        path = POLICY_DIR / "gas_subsidy.csv"
    else:
        raise ValueError(f"未知の種類: {kind}")

    df = pd.read_csv(path)
    return df


def _shift_month(ym: str, delta: int) -> str:
    """YYYY-MM形式の年月をdelta月ずらす"""
    y, m = int(ym[:4]), int(ym[5:7])
    m += delta
    while m > 12:
        y += 1
        m -= 12
    while m <= 0:
        y -= 1
        m += 12
    return f"{y:04d}-{m:02d}"


def get_monthly_subsidy_by_cpi_month(kind: str) -> pd.Series:
    """補助金単価をCPI反映月ベースの月次Seriesに変換

    CSVは使用月ベース → +1ヶ月してCPI反映月に変換

    Returns:
        月次の補助金単価（index=YYYY-MM、CPI反映月ベース）
    """
    df = load_subsidy_table(kind)
    col = "subsidy_yen_per_kwh" if kind == "electricity" else "subsidy_yen_per_m3"

    records = {}
    for _, row in df.iterrows():
        start = pd.Period(row["usage_month_start"], freq="M")
        end = pd.Period(row["usage_month_end"], freq="M")
        for period in pd.period_range(start, end, freq="M"):
            usage_ym = str(period)
            # 使用月+1 = CPI反映月
            cpi_ym = _shift_month(usage_ym, CPI_LAG_MONTHS)
            records[cpi_ym] = row[col]

    return pd.Series(records, name=f"subsidy_{kind}")


def compute_adjusted_index(
    cpi_index: pd.Series,
    kind: str,
) -> pd.Series:
    """電気代またはガス代の調整済CPI指数を算出

    Args:
        cpi_index: CPIの電気代/ガス代指数（月次）
        kind: "electricity" or "gas"

    Returns:
        調整済CPI指数（補助金がなかった場合の指数）
    """
    monthly_sub = get_monthly_subsidy_by_cpi_month(kind)
    sensitivity = ELEC_SENSITIVITY if kind == "electricity" else GAS_SENSITIVITY

    adjusted = cpi_index.copy()
    for ym in cpi_index.index:
        sub = monthly_sub.get(ym, 0.0)
        if sub > 0:
            adjusted[ym] = cpi_index[ym] + sub * sensitivity

    return adjusted
