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
from src.adjust_gasoline import compute_adjusted_index as adjust_gasoline
from src.adjust_kerosene import compute_adjusted_index as adjust_kerosene
from src.adjust_energy import compute_adjusted_index as adjust_energy
from src.adjust_education import get_all_education_adjusted
from src.adjust_interpolation import adjust_mobile, adjust_hotel
from src.config import OUTPUT_DIR

plt.rcParams["font.family"] = ["Hiragino Sans", "Hiragino Kaku Gothic Pro", "Arial Unicode MS", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False


def build_adjusted_indices():
    """全調整を適用した指数を構築"""
    indices, meta = parse_cpi_csv()
    weights = get_fixed_weights(meta)
    master = load_item_master()
    boj = parse_boj()

    indices_adj = indices.copy()
    indices_adj["7301"] = adjust_gasoline(indices["7301"])
    indices_adj["3701"] = adjust_kerosene(indices["3701"])
    indices_adj["3500"] = adjust_energy(indices["3500"], "electricity")
    indices_adj["3600"] = adjust_energy(indices["3600"], "gas")
    for code, adj in get_all_education_adjusted(indices).items():
        indices_adj[code] = adj
    indices_adj["7430"] = adjust_mobile(indices["7430"])
    indices_adj["9300"] = adjust_hotel(indices["9300"])

    return indices, indices_adj, weights, master, boj


def ym_to_date(ym_index):
    """YYYY-MM文字列をdatetimeに変換"""
    return pd.to_datetime(ym_index, format="%Y-%m")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    indices, indices_adj, weights, master, boj = build_adjusted_indices()

    boj_map = {
        "core": ("core_ex_special", "コアCPI（除く生鮮食品）"),
        "core_core": ("core_core_ex_special", "コアコアCPI（除く生鮮食品・エネルギー）"),
        "boj_core": ("boj_core_ex_special", "日銀コア（除く食料・エネルギー）"),
    }

    # --- 図1: 3系列の前年比比較 ---
    fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)
    fig.suptitle("特殊要因を除いたCPI前年比: 自前計算 vs 日銀公表値", fontsize=14, fontweight="bold")

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

        ax.plot(dates, orig_vals, color="#BBBBBB", linewidth=1, label="未調整", linestyle="--")
        ax.plot(dates, adj_vals, color="#2196F3", linewidth=1.8, label="自前計算（調整済）")
        ax.plot(dates, boj_vals, color="#F44336", linewidth=1.8, label="日銀公表値", linestyle=":")
        ax.set_title(title, fontsize=11)
        ax.set_ylabel("前年比（%）")
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
    fig.suptitle("残差（自前計算 − 日銀公表値、%pt）", fontsize=14, fontweight="bold")

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
        ax.set_title(f"{title}  (直近12ヶ月MAE={mae:.2f}pp)", fontsize=11)
        ax.set_ylabel("残差（%pt）")
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
    fig.suptitle("品目別調整の効果（指数水準）", fontsize=14, fontweight="bold")

    items = [
        ("7301", "ガソリン", axes[0, 0]),
        ("3500", "電気代", axes[0, 1]),
        ("8020", "高校授業料（公立）", axes[1, 0]),
        ("7430", "通信料（携帯電話）", axes[1, 1]),
    ]

    for code, name, ax in items:
        dates_all = ym_to_date(indices.index)
        ax.plot(dates_all, indices[code].values, color="#BBBBBB", linewidth=1.5, label="公表値")
        ax.plot(dates_all, indices_adj[code].values, color="#2196F3", linewidth=1.5, label="調整済")
        ax.fill_between(dates_all, indices[code].values, indices_adj[code].values,
                        alpha=0.2, color="#2196F3")
        ax.set_title(f"{name}（{code}）", fontsize=11)
        ax.set_ylabel("指数（2020年=100）")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.xaxis.set_major_locator(mdates.YearLocator())

    plt.tight_layout()
    path3 = OUTPUT_DIR / "fig3_item_adjustments.png"
    fig.savefig(path3, dpi=150, bbox_inches="tight")
    print(f"保存: {path3}")
    plt.close()


if __name__ == "__main__":
    main()
