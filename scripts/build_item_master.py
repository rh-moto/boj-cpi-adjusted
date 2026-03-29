"""Build item master CSV from Statistics Bureau item classification Excel.

Usage:
  python scripts/build_item_master.py          # 2020 base (default)
  python scripts/build_item_master.py --2015   # 2015 base
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import POLICY_DIR, SOUMU_DIR

# Base-year-specific column schemas
SCHEMAS = {
    2020: {
        "filepath": SOUMU_DIR / "item_classification.xlsx",
        "item_code_col": 8,      # Column with item code
        "item_name_col": 5,      # Column with item name
        "item_name_col2": None,   # No secondary name column
        "weight_col": 11,         # Weight (per 10000)
        "energy_col": 22,
        "education_col": 23,
        "info_comm_col": 25,
        "category_loop": range(6),  # Columns 0-5 for classification hierarchy
        "category_levels": 5,       # Number of category levels to track
        "has_parent_items": False,
        "output": POLICY_DIR / "item_master.csv",
    },
    2015: {
        "filepath": SOUMU_DIR / "item_classification_2015.xls",
        "item_code_col": 9,
        "item_name_col": 5,
        "item_name_col2": 6,      # Secondary name column (品目2)
        "weight_col": 12,
        "energy_col": 23,
        "education_col": 24,
        "info_comm_col": 26,
        "category_loop": range(5),
        "category_levels": 5,
        "has_parent_items": True,  # Need to exclude parent items
        "output": POLICY_DIR / "item_master_2015.csv",
    },
}


def _detect_parent_indices(df, schema):
    """Detect parent items that have child items (2015 base only)."""
    if not schema["has_parent_items"]:
        return set()
    parent_indices = set()
    code_col = schema["item_code_col"]
    for idx in df.index:
        if pd.notna(df.loc[idx, code_col]) and pd.notna(df.loc[idx, 5]):
            next_idx = idx + 1
            if next_idx in df.index and pd.notna(df.loc[next_idx, 6]) and pd.notna(df.loc[next_idx, code_col]):
                parent_indices.add(idx)
    return parent_indices


def build_item_master(base_year: int = 2020):
    schema = SCHEMAS[base_year]
    filepath = schema["filepath"]

    if not filepath.exists():
        raise FileNotFoundError(f"Item classification Excel not found: {filepath}")

    df = pd.read_excel(filepath, sheet_name="品目情報一覧", header=None, skiprows=5)

    parent_indices = _detect_parent_indices(df, schema)
    code_col = schema["item_code_col"]
    name_col = schema["item_name_col"]
    name_col2 = schema["item_name_col2"]
    weight_col = schema["weight_col"]

    records = []
    current_categories = {i: "" for i in range(schema["category_levels"])}

    for i, row in df.iterrows():
        # Update classification hierarchy
        for level in schema["category_loop"]:
            if pd.notna(row[level]) and level < schema["category_levels"]:
                current_categories[level] = str(row[level]).strip()
                for lower in range(level + 1, schema["category_levels"]):
                    current_categories[lower] = ""

        # Item row (has item code, not a parent item)
        if pd.notna(row[code_col]) and i not in parent_indices:
            item_code = str(int(row[code_col]))

            # Item name
            item_name = ""
            if name_col2 is not None and pd.notna(row[name_col2]):
                item_name = str(row[name_col2]).strip()
            elif pd.notna(row[name_col]):
                item_name = str(row[name_col]).strip()

            category_10 = current_categories[0]
            cat_mid1 = current_categories.get(1, "")
            cat_mid2 = current_categories.get(2, "")
            category_mid = cat_mid2 if cat_mid2 else cat_mid1
            cat_s1 = current_categories.get(3, "")
            cat_s2 = current_categories.get(4, "")
            category_small = cat_s2 if cat_s2 else cat_s1

            is_energy = str(row[schema["energy_col"]]).strip() == "○" if pd.notna(row[schema["energy_col"]]) else False
            is_education = str(row[schema["education_col"]]).strip() == "○" if pd.notna(row[schema["education_col"]]) else False
            is_info_comm = str(row[schema["info_comm_col"]]).strip() == "○" if pd.notna(row[schema["info_comm_col"]]) else False

            is_fresh = any(
                kw in (cat_s1 + cat_s2)
                for kw in ["生鮮魚介", "生鮮肉", "生鮮野菜", "生鮮果物"]
            )
            is_food = category_10 == "食料"
            is_alcohol = "酒類" in (cat_mid1 + cat_mid2)

            weight = int(row[weight_col]) if pd.notna(row[weight_col]) else 0

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
    print(f"Base year: {base_year}")
    print(f"Items: {len(master)}")
    print(f"  Fresh: {master['is_fresh'].sum()}")
    print(f"  Energy: {master['is_energy'].sum()}")
    print(f"  Food: {master['is_food'].sum()}")
    print(f"  Alcohol: {master['is_alcohol'].sum()}")
    print(f"  Education: {master['is_education'].sum()}")
    print(f"  Weight sum: {master['weight_per_10000'].sum()}")

    print(f"\nEnergy items:")
    for _, r in master[master["is_energy"]].iterrows():
        print(f"  {r['item_code']}: {r['item_name']} (w={r['weight_per_10000']})")

    outpath = schema["output"]
    outpath.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(outpath, index=False, encoding="utf-8")
    print(f"\nSaved: {outpath}")
    return master


if __name__ == "__main__":
    if "--2015" in sys.argv:
        build_item_master(2015)
    else:
        build_item_master(2020)
