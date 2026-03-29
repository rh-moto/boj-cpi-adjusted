"""月次更新パイプライン

毎月CPI公表後に実行する。手動でCSVを更新してから実行すること。

使い方:
  # 1. まずCSVを手動更新（下記チェックリスト参照）
  # 2. パイプライン実行
  python scripts/monthly_update.py

  # 強制的にCPIデータを再ダウンロード
  python scripts/monthly_update.py --refresh

手動更新チェックリスト（実行前に完了すること）:
  □ data/policy_params/gasoline_subsidy_monthly.csv に新月の行を追加
    → ソース: https://nenryo-teigakuhikisage.go.jp/current_graph.pdf (1ページ目)
  □ data/policy_params/kerosene_subsidy_monthly.csv に新月の行を追加
    → ソース: 同PDF (3ページ目)
  □ data/policy_params/tepco_fuel_adjustment.csv に新月の行を追加
    → ソース: https://www.tepco.co.jp/ep/private/fuelcost2/newlist/index-j.html
  □ data/boj/cpi_core_indicators.xlsx を最新版に差し替え
    → ソース: https://www.boj.or.jp/research/research_data/cpi/cpirev.xlsx

政策変更時のみ更新:
  □ data/policy_params/electricity_subsidy.csv（電気代補助の開始/終了/単価変更）
  □ data/policy_params/gas_subsidy.csv（ガス代補助の開始/終了/単価変更）
  □ data/policy_params/tepco_rates.csv（TEPCO料金改定時）
  □ data/policy_params/renew_energy_surcharge.csv（毎年5月、再エネ賦課金改定）
  □ src/adjust_education.py のEDUCATION_STEPS（新たな無償化政策時）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.fetch_cpi import parse_cpi_csv, get_fixed_weights, download_cpi_csv
from src.fetch_boj import parse_boj
from src.item_master import load_item_master
from src.aggregate import compute_weighted_index, compute_yoy, get_official_series
from src.validate import compare_series, print_validation_report
from src.adjust_gasoline import compute_adjusted_index as adjust_gasoline
from src.adjust_kerosene import compute_adjusted_index as adjust_kerosene
from src.model_electricity import compute_adjusted_index as adjust_electricity
from src.model_gas import compute_adjusted_index as adjust_gas
from src.policy_engine import apply_all_events
from src.config import OUTPUT_DIR


def check_data_freshness(indices, boj):
    """データの鮮度を確認"""
    cpi_latest = indices.index[-1]
    boj_latest = max(max(s.index) for s in boj.values())
    print(f"CPI最新月: {cpi_latest}")
    print(f"日銀最新月: {boj_latest}")
    if cpi_latest != boj_latest:
        print(f"⚠ CPI({cpi_latest})と日銀({boj_latest})の最新月が異なります")

    # 補助金CSVの最新月を確認
    for csv_name, label in [
        ("gasoline_subsidy_monthly.csv", "ガソリン補助"),
        ("kerosene_subsidy_monthly.csv", "灯油補助"),
        ("tepco_fuel_adjustment.csv", "TEPCO燃調"),
    ]:
        path = Path("data/policy_params") / csv_name
        if path.exists():
            df = pd.read_csv(path)
            latest = df["year_month"].max()
            if latest < cpi_latest:
                print(f"⚠ {label}の最新月({latest})がCPI({cpi_latest})より古い → 要更新")
            else:
                print(f"✓ {label}: {latest}")


def build_adjusted_indices(indices):
    """全調整を適用"""
    adj = indices.copy()
    # エネルギー系（CSVデータ駆動、個別モジュール）
    adj["7301"] = adjust_gasoline(indices["7301"])
    adj["3701"] = adjust_kerosene(indices["3701"])
    adj["3500"] = adjust_electricity(indices["3500"])
    adj["3600"] = adjust_gas(indices["3600"])
    # 教育・携帯・宿泊（政策イベントテーブル駆動）
    adj = apply_all_events(adj)
    return adj


def main():
    refresh = "--refresh" in sys.argv

    print("=" * 60)
    print("月次更新パイプライン")
    print("=" * 60)

    # 1. データ取得
    print("\n--- 1. データ取得 ---")
    if refresh:
        download_cpi_csv(force=True)
    indices, meta = parse_cpi_csv()
    weights = get_fixed_weights(meta)
    master = load_item_master()
    boj = parse_boj()

    # 2. データ鮮度チェック
    print("\n--- 2. データ鮮度チェック ---")
    check_data_freshness(indices, boj)

    # 3. 全調整適用
    print("\n--- 3. 全調整適用 ---")
    indices_adj = build_adjusted_indices(indices)
    print("調整完了")

    # 4. 3系列の前年比計算・日銀値との比較
    print("\n--- 4. 日銀公表値との比較 ---")
    boj_map = {
        "core": "core_ex_special",
        "core_core": "core_core_ex_special",
        "boj_core": "boj_core_ex_special",
    }

    for series_name, boj_name in boj_map.items():
        adj = compute_weighted_index(indices_adj, weights, series_name, master)
        yoy_adj = compute_yoy(adj)
        boj_s = boj[boj_name]
        common = sorted(set(yoy_adj.index) & set(boj_s.index))

        if not common:
            print(f"\n{series_name}: 共通期間なし")
            continue

        recent = common[-6:]
        diffs = [abs(yoy_adj[ym] - boj_s[ym]) for ym in recent]
        mae = sum(diffs) / len(diffs)

        print(f"\n{series_name} (直近6ヶ月MAE={mae:.2f}pp):")
        print(f"  {'年月':>8s}  {'調整済':>8s}  {'日銀':>8s}  {'差':>8s}")
        for ym in recent:
            diff = yoy_adj[ym] - boj_s[ym]
            print(f"  {ym:>8s}  {yoy_adj[ym]:>8.2f}  {boj_s[ym]:>8.1f}  {diff:>+8.2f}")

    # 5. 結果CSV出力
    print("\n--- 5. 結果出力 ---")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 調整済前年比CSV
    records = []
    for series_name in ["core", "core_core", "boj_core"]:
        adj = compute_weighted_index(indices_adj, weights, series_name, master)
        yoy = compute_yoy(adj)
        for ym in yoy.index:
            if pd.notna(yoy[ym]):
                records.append({
                    "year_month": ym,
                    "series": series_name,
                    "yoy_adjusted": round(yoy[ym], 2),
                })

    result_df = pd.DataFrame(records)
    result_path = OUTPUT_DIR / "adjusted_cpi_yoy.csv"
    result_df.to_csv(result_path, index=False, encoding="utf-8")
    print(f"保存: {result_path}")

    # 6. グラフ生成
    print("\n--- 6. グラフ生成 ---")
    import scripts.plot_results
    scripts.plot_results.main()

    print("\n" + "=" * 60)
    print("月次更新完了")
    print("=" * 60)


if __name__ == "__main__":
    main()
