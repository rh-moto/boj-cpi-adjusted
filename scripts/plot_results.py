"""全調整結果の時系列グラフを生成"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

from src.fetch_cpi import parse_cpi_csv, get_fixed_weights
from src.fetch_boj import parse_boj
from src.item_master import load_item_master
from src.aggregate import compute_weighted_index, compute_yoy, get_official_series
from src.pipeline import build_adjusted_indices
from src.policy_engine import apply_all_events
from src.config import OUTPUT_DIR

plt.rcParams["font.family"] = ["Hiragino Sans", "Hiragino Kaku Gothic Pro", "Arial Unicode MS", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False


def load_and_adjust():
    """Load CPI data and apply all adjustments."""
    indices, meta = parse_cpi_csv()
    weights = get_fixed_weights(meta)
    master = load_item_master()
    boj = parse_boj()
    indices_adj = build_adjusted_indices(indices)
    return indices, indices_adj, weights, master, boj


def ym_to_date(ym_index):
    """YYYY-MM文字列をdatetimeに変換"""
    return pd.to_datetime(ym_index, format="%Y-%m")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    indices, indices_adj, weights, master, boj = load_and_adjust()

    boj_map = {
        "core": ("core_ex_special", "Core CPI (excl. fresh food)"),
        "boj_core": ("boj_core_ex_special", "BOJ Core CPI (excl. fresh food & energy)"),
        "core_core": ("core_core_ex_special", "Core-core CPI (excl. food & energy)"),
    }

    # --- 図1: 3系列の前年比比較 ---
    fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)
    fig.suptitle("CPI YoY excl. Special Factors: Our estimates vs BOJ estimates", fontsize=14, fontweight="bold")

    for ax, (series_name, (boj_name, title)) in zip(axes, boj_map.items()):
        # 未調整
        orig = compute_weighted_index(indices, weights, series_name, master)
        yoy_orig = compute_yoy(orig)
        # 調整済
        adj = compute_weighted_index(indices_adj, weights, series_name, master)
        yoy_adj = compute_yoy(adj)
        # 日銀
        boj_s = boj[boj_name]

        # 共通期間
        common = sorted(set(yoy_adj.index) & set(boj_s.index))
        dates = ym_to_date(common)
        orig_vals = [yoy_orig.get(ym, np.nan) for ym in common]
        adj_vals = [yoy_adj[ym] for ym in common]
        boj_vals = [boj_s[ym] for ym in common]

        ax.plot(dates, orig_vals, color="#BBBBBB", linewidth=1, label="Unadjusted", linestyle="--")
        ax.plot(dates, adj_vals, color="#2196F3", linewidth=1.8, label="Our estimates")
        ax.plot(dates, boj_vals, color="#F44336", linewidth=1.8, label="BOJ estimates", linestyle=":")
        ax.set_title(title, fontsize=11)
        ax.set_ylabel("YoY (%)")
        ax.legend(loc="upper left", fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color="black", linewidth=0.5)

    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(axes[-1].xaxis.get_majorticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    path1 = OUTPUT_DIR / "fig1_yoy_comparison.png"
    fig.savefig(path1, dpi=150, bbox_inches="tight")
    print(f"保存: {path1}")
    plt.close()

    # --- 図2: 残差（自前計算 - 日銀公表値） ---
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    fig.suptitle("Residuals (Our estimates - BOJ estimates, %pt)", fontsize=14, fontweight="bold")

    for ax, (series_name, (boj_name, title)) in zip(axes, boj_map.items()):
        adj = compute_weighted_index(indices_adj, weights, series_name, master)
        yoy_adj = compute_yoy(adj)
        boj_s = boj[boj_name]
        common = sorted(set(yoy_adj.index) & set(boj_s.index))
        dates = ym_to_date(common)
        residuals = [yoy_adj[ym] - boj_s[ym] for ym in common]
        mae = np.mean(np.abs(residuals[-12:]))

        ax.bar(dates, residuals, width=25, color=["#F44336" if r < 0 else "#2196F3" for r in residuals], alpha=0.7)
        ax.axhline(y=0, color="black", linewidth=0.8)
        ax.set_title(f"{title}  (Last 12m MAE={mae:.2f}pp)", fontsize=11)
        ax.set_ylabel("Residual (%pt)")
        ax.set_ylim(-1.0, 1.0)
        ax.grid(True, alpha=0.3)

    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(axes[-1].xaxis.get_majorticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    path2 = OUTPUT_DIR / "fig2_residuals.png"
    fig.savefig(path2, dpi=150, bbox_inches="tight")
    print(f"保存: {path2}")
    plt.close()

    # --- 図3: 品目別調整の効果（指数水準） ---
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Item-level Adjustment Effects (Index Level)", fontsize=14, fontweight="bold")

    items = [
        ("7301", "Gasoline", axes[0, 0]),
        ("3500", "Electricity", axes[0, 1]),
        ("8020", "HS Tuition (Public)", axes[1, 0]),
        ("7430", "Mobile Phone Fees", axes[1, 1]),
    ]

    for code, name, ax in items:
        dates_all = ym_to_date(indices.index)
        ax.plot(dates_all, indices[code].values, color="#BBBBBB", linewidth=1.5, label="Published")
        ax.plot(dates_all, indices_adj[code].values, color="#2196F3", linewidth=1.5, label="Adjusted")
        ax.fill_between(dates_all, indices[code].values, indices_adj[code].values,
                        alpha=0.2, color="#2196F3")
        ax.set_title(f"{name}（{code}）", fontsize=11)
        ax.set_ylabel("Index (2020=100)")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.xaxis.set_major_locator(mdates.YearLocator())

    plt.tight_layout()
    path3 = OUTPUT_DIR / "fig3_item_adjustments.png"
    fig.savefig(path3, dpi=150, bbox_inches="tight")
    print(f"保存: {path3}")
    plt.close()

    # --- Fig 4: Full period (2015-base + 2020-base) ---
    from src.adjust_tax import apply_tax_adjustment

    indices_15, meta_15 = parse_cpi_csv(base_year=2015)
    weights_15 = get_fixed_weights(meta_15)
    master_15 = load_item_master(base_year=2015)
    boj_15 = parse_boj(base_year=2015)

    indices_15_adj = apply_tax_adjustment(indices_15, master_15["item_code"].tolist(), master_15)
    indices_15_adj = apply_all_events(indices_15_adj, base_year=2015)

    fig, axes = plt.subplots(3, 1, figsize=(16, 14), sharex=True)
    fig.suptitle("CPI YoY excl. Special Factors: 2016-2026 (2015-base + 2020-base)", fontsize=14, fontweight="bold")

    for ax, (series_name, (boj_name, title)) in zip(axes, boj_map.items()):
        adj_15 = compute_weighted_index(indices_15_adj, weights_15, series_name, master_15)
        yoy_15 = compute_yoy(adj_15)
        orig_15 = compute_weighted_index(indices_15, weights_15, series_name, master_15)
        yoy_orig_15 = compute_yoy(orig_15)

        adj_20 = compute_weighted_index(indices_adj, weights, series_name, master)
        yoy_20 = compute_yoy(adj_20)
        orig_20 = compute_weighted_index(indices, weights, series_name, master)
        yoy_orig_20 = compute_yoy(orig_20)

        boj_15_s = boj_15[boj_name]
        boj_20_s = boj[boj_name]

        def combine(s15, s20):
            part1 = s15[(s15.index >= "2016-01") & (s15.index <= "2020-12")]
            part2 = s20[s20.index >= "2021-01"]
            return pd.concat([part1, part2])

        yoy_orig_c = combine(yoy_orig_15, yoy_orig_20)
        yoy_adj_c = combine(yoy_15, yoy_20)
        boj_c = combine(boj_15_s, boj_20_s)

        ax.plot(ym_to_date(yoy_orig_c.index), yoy_orig_c.values, color="#BBBBBB", linewidth=1, label="Unadjusted", linestyle="--")
        ax.plot(ym_to_date(yoy_adj_c.index), yoy_adj_c.values, color="#2196F3", linewidth=1.8, label="Our estimates")
        ax.plot(ym_to_date(boj_c.index), boj_c.values, color="#F44336", linewidth=1.8, label="BOJ estimates", linestyle=":")

        ax.axvline(x=pd.Timestamp("2021-01"), color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
        ax.set_title(title, fontsize=11)
        ax.set_ylabel("YoY (%)")
        ax.legend(loc="upper left", fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color="black", linewidth=0.5)

    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.setp(axes[-1].xaxis.get_majorticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    path4 = OUTPUT_DIR / "fig_full_period_comparison.png"
    fig.savefig(path4, dpi=150, bbox_inches="tight")
    print(f"保存: {path4}")
    plt.close()

    # --- Fig 5: Full period extended back to 1991 (2010-base + 2015-base + 2020-base) ---
    # Pre-2016: 公表tax_adjusted.xlsx (1990-2019, 2015基準スプライス済) を tax-adjusted の代理として使用
    # 1990-2015年は他の特殊要因(教育/モバイル等)が無いため、tax調整=our-estimates 相当
    tax_xlsx = pd.read_excel("data/soumu/tax_adjusted.xlsx", sheet_name="zmi", header=None)
    tax_data = tax_xlsx.iloc[6:].copy()
    # cols: 0=ym, 1=all, 2=core(161), 3=less_imp(163), 4=less_imp_fresh(166), 5=core_core(178), 6=boj_core(168)
    tax_data.columns = ["ym_raw", "all", "core", "less_imp", "less_imp_fresh", "core_core", "boj_core"]
    tax_data["ym"] = tax_data["ym_raw"].astype(str).str[:4] + "-" + tax_data["ym_raw"].astype(str).str[4:]
    tax_adj_series = {
        "core": pd.Series(tax_data["core"].values, index=tax_data["ym"].values, dtype=float),
        "core_core": pd.Series(tax_data["core_core"].values, index=tax_data["ym"].values, dtype=float),
        "boj_core": pd.Series(tax_data["boj_core"].values, index=tax_data["ym"].values, dtype=float),
    }

    # 2010基準の生CPI（未調整）: 0161=core, 0168=boj_core (core_core=0178は2010基準に存在しない)
    cpi_2010 = pd.read_csv("data/soumu/cpi_2010base_items.csv")
    cpi_2010["ym"] = cpi_2010["year_month"].astype(str).str[:4] + "-" + cpi_2010["year_month"].astype(str).str[4:]
    cpi_2010 = cpi_2010.set_index("ym")
    raw_2010 = {
        "core": cpi_2010["0161"].astype(float),
        "boj_core": cpi_2010["0168"].astype(float),
        # core_core: 2010基準に該当集計符号なし
    }

    fig, axes = plt.subplots(3, 1, figsize=(18, 14), sharex=True)
    fig.suptitle("CPI YoY excl. Special Factors: 1991-2026 (2010-base + 2015-base + 2020-base)", fontsize=14, fontweight="bold")

    for ax, (series_name, (boj_name, title)) in zip(axes, boj_map.items()):
        # Our-estimates: tax_adjusted.xlsx (1991-2015) + 2015-base pipeline (2016-2020) + 2020-base (2021+)
        adj_15 = compute_weighted_index(indices_15_adj, weights_15, series_name, master_15)
        yoy_15 = compute_yoy(adj_15)
        adj_20 = compute_weighted_index(indices_adj, weights, series_name, master)
        yoy_20 = compute_yoy(adj_20)
        yoy_taxadj = compute_yoy(tax_adj_series[series_name])

        # Splice: 1991-01..2015-12 from tax_adjusted, 2016-01..2020-12 from 2015-base, 2021-01+ from 2020-base
        part_pre = yoy_taxadj[(yoy_taxadj.index >= "1991-01") & (yoy_taxadj.index <= "2015-12")]
        part_15 = yoy_15[(yoy_15.index >= "2016-01") & (yoy_15.index <= "2020-12")]
        part_20 = yoy_20[yoy_20.index >= "2021-01"]
        yoy_adj_full = pd.concat([part_pre, part_15, part_20])

        # 総務省公表 tax-adjusted (1991-2019, 全期間で表示)
        yoy_soumu = yoy_taxadj[(yoy_taxadj.index >= "1991-01") & (yoy_taxadj.index <= "2019-12")]

        # Unadjusted: 2010-base (1991-2015) + 2015-base + 2020-base
        orig_15 = compute_weighted_index(indices_15, weights_15, series_name, master_15)
        yoy_orig_15 = compute_yoy(orig_15)
        orig_20 = compute_weighted_index(indices, weights, series_name, master)
        yoy_orig_20 = compute_yoy(orig_20)

        if series_name in raw_2010:
            yoy_raw_2010 = compute_yoy(raw_2010[series_name])
            part_pre_raw = yoy_raw_2010[(yoy_raw_2010.index >= "1991-01") & (yoy_raw_2010.index <= "2015-12")]
            part_15_raw = yoy_orig_15[(yoy_orig_15.index >= "2016-01") & (yoy_orig_15.index <= "2020-12")]
            part_20_raw = yoy_orig_20[yoy_orig_20.index >= "2021-01"]
            yoy_orig_full = pd.concat([part_pre_raw, part_15_raw, part_20_raw])
            ax.plot(ym_to_date(yoy_orig_full.index), yoy_orig_full.values, color="#BBBBBB", linewidth=0.8, label="Unadjusted", linestyle="--")

        # BOJ (2016+ only)
        boj_c = pd.concat([
            boj_15[boj_name][(boj_15[boj_name].index >= "2016-01") & (boj_15[boj_name].index <= "2020-12")],
            boj[boj_name][boj[boj_name].index >= "2021-01"],
        ])

        ax.plot(ym_to_date(yoy_adj_full.index), yoy_adj_full.values, color="#2196F3", linewidth=1.2, label="Our estimates")
        ax.plot(ym_to_date(boj_c.index), boj_c.values, color="#F44336", linewidth=1.2, label="BOJ estimates", linestyle=":")
        ax.plot(ym_to_date(yoy_soumu.index), yoy_soumu.values, color="#4CAF50", linewidth=1.0, label="Soumu tax-adjusted (1991-2019)", linestyle="-.")

        # Splice boundaries
        for boundary in ["2016-01", "2021-01"]:
            ax.axvline(x=pd.Timestamp(boundary), color="gray", linewidth=0.6, linestyle="--", alpha=0.4)
        # Tax events
        for tax_evt in ["1997-04", "2014-04", "2019-10"]:
            ax.axvline(x=pd.Timestamp(tax_evt), color="orange", linewidth=0.5, linestyle=":", alpha=0.4)

        ax.set_title(title, fontsize=11)
        ax.set_ylabel("YoY (%)")
        ax.legend(loc="upper left", fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color="black", linewidth=0.5)

    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[-1].xaxis.set_major_locator(mdates.YearLocator(2))
    plt.setp(axes[-1].xaxis.get_majorticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    path5 = OUTPUT_DIR / "fig_full_period_1991.png"
    fig.savefig(path5, dpi=150, bbox_inches="tight")
    print(f"保存: {path5}")
    plt.close()


if __name__ == "__main__":
    main()
