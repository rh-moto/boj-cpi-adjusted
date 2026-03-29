"""2015年基準の品目分類Excelから品目マスタCSVを生成

入力: data/soumu/item_classification_2015.xls
出力: data/policy_params/item_master_2015.csv

2020年基準版(build_item_master.py)と同じロジックだが、
列構造が微妙に異なる（col 5=品目1, col 6=品目2）。
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import POLICY_DIR, SOUMU_DIR


def build_item_master_2015():
    filepath = SOUMU_DIR / "item_classification_2015.xls"
    if not filepath.exists():
        raise FileNotFoundError(f"品目分類Excelが見つかりません: {filepath}")

    df = pd.read_excel(filepath, sheet_name="品目情報一覧", header=None, skiprows=5)

    # 親品目を検出して除外（子品目と二重計上になるため）
    # 親品目: col 5(品目1)に値があり、直後の行のcol 6(品目2)に子品目がある
    parent_indices = set()
    for idx in df.index:
        if pd.notna(df.loc[idx, 9]) and pd.notna(df.loc[idx, 5]):
            next_idx = idx + 1
            if next_idx in df.index and pd.notna(df.loc[next_idx, 6]) and pd.notna(df.loc[next_idx, 9]):
                parent_indices.add(idx)

    records = []
    current_categories = {0: "", 1: "", 2: "", 3: "", 4: ""}

    for i, row in df.iterrows():
        # 分類行の更新（col 0-4が分類階層）
        for level in range(5):
            if pd.notna(row[level]):
                current_categories[level] = str(row[level]).strip()
                for lower in range(level + 1, 5):
                    current_categories[lower] = ""

        # 品目行（品目符号col[9]が存在し、親品目でない行）
        if pd.notna(row[9]) and i not in parent_indices:
            item_code = str(int(row[9]))
            # 品目名はcol 5またはcol 6
            item_name = ""
            if pd.notna(row[6]):
                item_name = str(row[6]).strip()
            elif pd.notna(row[5]):
                item_name = str(row[5]).strip()

            category_10 = current_categories[0]
            cat_mid1 = current_categories.get(1, "")
            cat_mid2 = current_categories.get(2, "")
            category_mid = cat_mid2 if cat_mid2 else cat_mid1
            cat_s1 = current_categories.get(3, "")
            cat_s2 = current_categories.get(4, "")
            category_small = cat_s2 if cat_s2 else cat_s1

            is_energy = str(row[23]).strip() == "○" if pd.notna(row[23]) else False
            is_education = str(row[24]).strip() == "○" if pd.notna(row[24]) else False
            is_info_comm = str(row[26]).strip() == "○" if pd.notna(row[26]) else False

            is_fresh = any(
                kw in (cat_s1 + cat_s2)
                for kw in ["生鮮魚介", "生鮮肉", "生鮮野菜", "生鮮果物"]
            )
            is_food = category_10 == "食料"
            is_alcohol = "酒類" in (cat_mid1 + cat_mid2)

            weight = int(row[12]) if pd.notna(row[12]) else 0

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
    print(f"  ウエイト合計: {master['weight_per_10000'].sum()} (10000であるべき)")

    print(f"\nエネルギー品目:")
    for _, r in master[master["is_energy"]].iterrows():
        print(f"  {r['item_code']}: {r['item_name']} (w={r['weight_per_10000']})")

    outpath = POLICY_DIR / "item_master_2015.csv"
    master.to_csv(outpath, index=False, encoding="utf-8")
    print(f"\n保存: {outpath}")
    return master


if __name__ == "__main__":
    build_item_master_2015()
