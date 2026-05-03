"""2010基準と2015基準の品目コード対応表を自動生成

出力: data/policy_params/crosswalk_2010_2015.csv
方針: 同一コードを同一品目とみなす1:1対応が基本
- match: 両基準に存在し名称も一致
- renamed: 両基準に同コードあるが名称が異なる (要マニュアル確認)
- abolished: 2010のみに存在
- new: 2015で新設
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.config import POLICY_DIR


def load_2010_items() -> dict:
    """2010基準の品目コード→名称辞書 (集計符号を除く品目のみ)"""
    files = ['000011288577.csv', '000011288578.csv', '000011288579.csv',
             '000011288580.csv', '000011288581.csv']
    item_names = {}
    for f in files:
        full = pd.read_csv(f'data/soumu/2010base/{f}', encoding='shift_jis', header=None)
        codes = [str(c) for c in full.iloc[2, 1:].tolist()]
        names = [str(n) for n in full.iloc[0, 1:].tolist()]
        for c, n in zip(codes, names):
            if c.startswith('0') or c == 'nan':
                continue
            if c not in item_names:
                item_names[c] = n
    return item_names


def main():
    items_2010 = load_2010_items()
    print(f"2010基準: {len(items_2010)} 品目")

    master_2015 = pd.read_csv(POLICY_DIR / 'item_master_2015.csv', dtype={'item_code': str})
    items_2015 = dict(zip(master_2015['item_code'], master_2015['item_name']))
    weights_2015 = dict(zip(master_2015['item_code'], master_2015['weight_per_10000']))
    print(f"2015基準: {len(items_2015)} 品目")

    rows = []
    all_codes = sorted(set(items_2010) | set(items_2015))
    for code in all_codes:
        n10 = items_2010.get(code)
        n15 = items_2015.get(code)
        w15 = weights_2015.get(code, 0)
        if n10 and n15:
            relation = '1:1' if n10 == n15 else 'renamed'
            rows.append({'code_2010': code, 'name_2010': n10, 'code_2015': code,
                         'name_2015': n15, 'weight_2015': w15, 'relation': relation})
        elif n10 and not n15:
            rows.append({'code_2010': code, 'name_2010': n10, 'code_2015': '',
                         'name_2015': '', 'weight_2015': 0, 'relation': 'abolished'})
        elif n15 and not n10:
            rows.append({'code_2010': '', 'name_2010': '', 'code_2015': code,
                         'name_2015': n15, 'weight_2015': w15, 'relation': 'new'})

    out = pd.DataFrame(rows)
    out_path = POLICY_DIR / 'crosswalk_2010_2015.csv'
    out.to_csv(out_path, index=False)

    print(f"\n保存: {out_path}")
    print(f"  total: {len(out)}")
    print(out['relation'].value_counts().to_string())

    print("\n=== renamed (同コード・名称違い) サンプル ===")
    print(out[out['relation'] == 'renamed'].head(15).to_string(index=False))


if __name__ == '__main__':
    main()
