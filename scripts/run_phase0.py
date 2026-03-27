"""Phase 0: 共通基盤の動作確認スクリプト

データ取得→パース→集計→検証のパイプライン全体をテスト。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.fetch_cpi import parse_cpi_csv, get_fixed_weights, download_cpi_csv
from src.fetch_boj import parse_boj, download_boj
from src.fetch_weights import parse_weights
from src.item_master import load_item_master, SPECIAL_FACTOR_ITEMS
from src.aggregate import compute_weighted_index, compute_yoy, get_official_series
from src.validate import compare_series, print_validation_report, save_validation_csv
from src.config import OUTPUT_DIR


def main():
    print("=" * 60)
    print("Phase 0: 共通基盤の動作確認")
    print("=" * 60)

    # 1. データ読み込み
    print("\n--- 1. データ読み込み ---")
    indices, meta = parse_cpi_csv()
    weights = get_fixed_weights(meta)
    master = load_item_master()
    boj = parse_boj()
    print(f"CPI指数: {indices.shape} ({indices.index[0]}〜{indices.index[-1]})")
    print(f"品目マスタ: {len(master)}品目")
    print(f"日銀公表値: {len(boj)}系列")

    # 2. 公式集計値の確認
    print("\n--- 2. 公式集計値（前年比）---")
    for name in ["core", "core_core", "boj_core"]:
        official = get_official_series(indices, name)
        yoy = compute_yoy(official)
        recent = yoy.dropna().tail(3)
        print(f"{name}: {', '.join(f'{ym}={v:.1f}%' for ym, v in recent.items())}")

    # 3. 品目別加重平均での再現精度
    print("\n--- 3. 品目別加重平均 vs 公式値（固定ウエイト）---")
    for name, official_code in [("core", "0161"), ("core_core", "0178"), ("boj_core", "0168")]:
        computed = compute_weighted_index(indices, weights, name, master)
        official = indices[official_code]
        diff = (computed - official).dropna()
        print(f"{name}: 平均絶対差={diff.abs().mean():.3f}, "
              f"最大={diff.abs().max():.3f} ({diff.abs().idxmax()})")

    # 4. 日銀公表値との比較準備
    # （Phase 1以降の調整済指数ができるまでは、未調整前年比との比較）
    print("\n--- 4. 日銀公表値（特殊要因除外）の概要 ---")
    for name, s in boj.items():
        recent = s.tail(3)
        print(f"{name}: {', '.join(f'{ym}={v:.1f}%' for ym, v in recent.items())}")

    # 5. 未調整前年比との差（= 特殊要因の影響度）
    print("\n--- 5. 特殊要因の影響度（未調整 - 日銀公表、直近） ---")
    series_map = {
        "core_ex_special": "core",
        "core_core_ex_special": "core_core",
        "boj_core_ex_special": "boj_core",
    }
    for boj_name, cpi_name in series_map.items():
        if boj_name not in boj:
            continue
        official = get_official_series(indices, cpi_name)
        yoy_official = compute_yoy(official)
        boj_s = boj[boj_name]
        # 共通期間の直近3ヶ月
        common = yoy_official.index.intersection(boj_s.index)
        if len(common) == 0:
            continue
        for ym in sorted(common)[-3:]:
            diff = yoy_official[ym] - boj_s[ym]
            print(f"  {ym} {cpi_name}: 未調整={yoy_official[ym]:.2f}% "
                  f"特殊要因除外={boj_s[ym]:.1f}% 差={diff:+.2f}pp")

    # 6. 特殊要因対象品目の現在値
    print("\n--- 6. 特殊要因対象品目（直近月）---")
    latest = indices.index[-1]
    for factor_name, codes in SPECIAL_FACTOR_ITEMS.items():
        for code in codes:
            if code in indices.columns:
                val = indices.loc[latest, code]
                item = master.loc[master["item_code"] == code, "item_name"]
                name = item.iloc[0] if len(item) > 0 else code
                w = weights[code] if code in weights.index else 0
                print(f"  {factor_name}: {code} {name} = {val:.1f} (w={w})")

    print("\n" + "=" * 60)
    print("Phase 0 完了。Phase 1（ガソリン調整）に進む準備ができました。")
    print("=" * 60)


if __name__ == "__main__":
    main()
