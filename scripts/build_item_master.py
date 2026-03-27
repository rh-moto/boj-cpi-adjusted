"""品目分類Excelから品目マスタCSVを生成する

入力: data/soumu/item_classification.xlsx
出力: data/policy_params/item_master.csv

品目情報一覧シートの列構造:
  0=大分類, 1=中分類1, 2=中分類2, 3=小分類1, 4=小分類2, 5=品目
  6=（空白）, 7=類符号, 8=品目符号, 9=含類総連番
  10=ウエイト実数(全国), 11=ウエイト1万分比(全国)
  22=エネルギー(○/-), 23=教育関係費, 24=教養娯楽関係費, 25=情報通信関係費
"""

import sys
from pathlib import Path

import pandas as pd

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import POLICY_DIR, SOUMU_DIR


def build_item_master():
    filepath = SOUMU_DIR / "item_classification.xlsx"
    if not filepath.exists():
        raise FileNotFoundError(f"品目分類Excelが見つかりません: {filepath}")

    df = pd.read_excel(filepath, sheet_name="品目情報一覧", header=None, skiprows=5)

    # 品目行に対応する分類を手動追跡で取得
    # （ffillは階層リセットを壊すため使わない）
    records = []
    current_categories = {0: "", 1: "", 2: "", 3: "", 4: ""}

    for i, row in df.iterrows():
        # 分類行の更新
        for level in range(6):
            if pd.notna(row[level]) and level < 5:
                current_categories[level] = str(row[level]).strip()
                # 下位分類をリセット
                for lower in range(level + 1, 5):
                    current_categories[lower] = ""

        # 品目行（品目符号がある行）
        if pd.notna(row[8]):
            item_code = str(int(row[8]))
            item_name = str(row[5]).strip() if pd.notna(row[5]) else ""
            category_10 = current_categories[0]
            category_mid = current_categories.get(1, "") or current_categories.get(2, "")
            if not category_mid:
                category_mid = current_categories.get(2, "")
            # 中分類は col 1 または col 2
            cat_mid1 = current_categories.get(1, "")
            cat_mid2 = current_categories.get(2, "")
            category_mid = cat_mid2 if cat_mid2 else cat_mid1

            category_small = current_categories.get(3, "") or current_categories.get(4, "")
            cat_s1 = current_categories.get(3, "")
            cat_s2 = current_categories.get(4, "")
            category_small = cat_s2 if cat_s2 else cat_s1

            is_energy = str(row[22]).strip() == "○" if pd.notna(row[22]) else False
            is_education = str(row[23]).strip() == "○" if pd.notna(row[23]) else False
            is_info_comm = str(row[25]).strip() == "○" if pd.notna(row[25]) else False

            # 生鮮食品フラグ: 小分類が「生鮮魚介」「生鮮肉」「生鮮野菜」「生鮮果物」
            is_fresh = any(
                kw in (cat_s1 + cat_s2)
                for kw in ["生鮮魚介", "生鮮肉", "生鮮野菜", "生鮮果物"]
            )

            # 食料フラグ: 大分類が「食料」
            is_food = category_10 == "食料"

            # 酒類フラグ: 中分類が「酒類」
            is_alcohol = "酒類" in (cat_mid1 + cat_mid2)

            weight = int(row[11]) if pd.notna(row[11]) else 0

            records.append({
                "item_code": item_code,
                "item_name": item_name,
                "category_10": category_10,
                "category_mid": category_mid,
                "category_small": category_small,
                "weight_per_10000": weight,
                "is_fresh": is_fresh,
                "is_energy": is_energy,
                "is_food": is_food,
                "is_alcohol": is_alcohol,
                "is_education": is_education,
                "is_info_comm": is_info_comm,
            })

    master = pd.DataFrame(records)
    print(f"品目数: {len(master)}")
    print(f"  生鮮食品: {master['is_fresh'].sum()}")
    print(f"  エネルギー: {master['is_energy'].sum()}")
    print(f"  食料: {master['is_food'].sum()}")
    print(f"  酒類: {master['is_alcohol'].sum()}")
    print(f"  教育関係: {master['is_education'].sum()}")

    # ウエイト合計の検証
    total_w = master["weight_per_10000"].sum()
    print(f"  ウエイト合計: {total_w} (10000であるべき)")

    # エネルギー品目の一覧
    print(f"\nエネルギー品目:")
    for _, r in master[master["is_energy"]].iterrows():
        print(f"  {r['item_code']}: {r['item_name']} (w={r['weight_per_10000']})")

    # 保存
    outpath = POLICY_DIR / "item_master.csv"
    outpath.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(outpath, index=False, encoding="utf-8-sig")
    print(f"\n保存: {outpath}")

    return master


if __name__ == "__main__":
    build_item_master()
