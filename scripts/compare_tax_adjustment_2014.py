"""2014-04消費税調整: 2010基準データ vs 2020基準長期ファイル

テスト目的: 同じ品目別調整ロジックを2つのデータソースで適用し、
集計結果の差を測定する。

比較対象:
  Option β: 2010基準の品目別データ（cpi_2010base_items.csv）→ 当時の品目セット
  Option α: 2020基準長期ファイル（cpi_longterm_2020base.csv）→ 2020で生き残った品目のみ
  公表値:    tax_adjusted.xlsx の0161 (core), 0168 (BOJ core)

Methodology:
  1. 各データソースの品目を税区分（standard/exempt/transitional）に分類
  2. 各品目に税調整factor適用
     - standard: 1.05/1.08 ≈ 0.9722 (2014-04+)
     - exempt: 1.0
     - transitional: 2014-05+から1.05/1.08（1ヶ月遅延）
  3. 0161（生鮮食品除く）と0168（食料・エネルギー除く）に集計
  4. 公表値とのMAE算出
"""

import pandas as pd
import numpy as np

OLD_RATE = 1.05
NEW_RATE = 1.08
FACTOR = OLD_RATE / NEW_RATE  # 0.9722

# ===== 税区分分類（名称ベース） =====
EXEMPT_KWDS = [
    '家賃', '帰属家賃', '保健医療サービス', '出産入院料', '介護料',
    '学校給食', 'ＰＴＡ会費',
    '公立高校授業料', '公立高等学校授業料', '国立大学授業料',
    '幼稚園保育料', '保育所保育料',
    '生命保険料', '損害保険料', '火災・地震保険料', '自動車保険料',
    'ＮＨＫ放送料',  # 受信料は課税
]

TRANSITIONAL_KWDS = [
    '電気代', '都市ガス代', 'プロパンガス', 'ガス代', '上下水道料', '水道料',
]

def tax_factor(name: str, year_month: str) -> float:
    """2014-04税変更の品目別factor"""
    if year_month < '2014-04':
        return 1.0
    if any(kw in name for kw in EXEMPT_KWDS):
        return 1.0
    if any(kw in name for kw in TRANSITIONAL_KWDS):
        # 経過措置: 2014-04は旧税率、2014-05以降から新税率
        if year_month <= '2014-04':
            return 1.0
        else:
            return FACTOR
    # 固定電話通信料: 2014-04にウエイトで2/3が新税率
    if '固定電話通信料' in name or '固定電話料' in name:
        if year_month <= '2014-03':
            return 1.0
        elif year_month == '2014-04':
            return FACTOR * (2/3) + 1.0 * (1/3)
        else:
            return FACTOR
    if '携帯電話通信料' in name or '携帯電話料' in name:
        if year_month <= '2014-03':
            return 1.0
        elif year_month == '2014-04':
            return FACTOR * (4/5) + 1.0 * (1/5)
        else:
            return FACTOR
    return FACTOR


# ===== 2010基準データロード =====
def load_2010_items():
    files = ['000011288577.csv', '000011288578.csv', '000011288579.csv',
             '000011288580.csv', '000011288581.csv']
    items_info = {}
    for f in files:
        full = pd.read_csv(f'data/soumu/2010base/{f}', encoding='shift_jis', header=None)
        codes = [str(c) for c in full.iloc[2, 1:].tolist()]
        names = [str(n) for n in full.iloc[0, 1:].tolist()]
        weights = [float(w) if str(w) not in ('nan', '') else 0
                   for w in full.iloc[5, 1:].tolist()]
        for c, n, w in zip(codes, names, weights):
            if c not in items_info and not c.startswith('0') and w > 0:
                items_info[c] = {'name': n, 'weight_10000': w}
    df = pd.read_csv('data/soumu/cpi_2010base_items.csv')
    df['ym'] = df['year_month'].astype(str).str[:4] + '-' + df['year_month'].astype(str).str[4:]
    return df, items_info


# ===== 2020基準長期データロード =====
def load_2020_longterm():
    df = pd.read_csv('data/soumu/cpi_longterm_2020base.csv', encoding='utf-8-sig')
    df.columns = [c.strip().lstrip('﻿') for c in df.columns]
    df['ym'] = df['year_month']
    # Item master for weights
    master = pd.read_csv('data/policy_params/item_master.csv', dtype={'item_code': str})
    items_info = {}
    for _, r in master.iterrows():
        c = r['item_code']
        if not c.startswith('0') and c in df.columns:
            w = float(r.get('weight_per_10000', 0))
            if w > 0:
                items_info[c] = {'name': r['item_name'], 'weight_10000': w,
                                 'is_fresh': bool(r.get('is_fresh', False)),
                                 'is_energy': bool(r.get('is_energy', False)),
                                 'is_food': bool(r.get('is_food', False)),
                                 'is_alcohol': bool(r.get('is_alcohol', False))}
    return df, items_info


# ===== 生鮮食品/エネルギー判定（簡易） =====
FRESH_FOOD_KWDS = ['生鮮']
# 厳密な生鮮食品リスト: 0157 includes specific items
# Use names like まぐろ, あじ, いわし, さんま, キャベツ, トマト, etc.
FRESH_ITEM_KWDS = [
    'まぐろ', 'かつお', 'あじ', 'いわし', 'さんま', 'さば', 'さけ', 'たい', 'いか',
    'たこ', 'えび', 'かに', 'あさり', 'はまぐり', 'しじみ', 'かき',
    '牛肉', '豚肉', '鶏肉',  # 生鮮肉
    'キャベツ', 'ほうれんそう', 'はくさい', 'ねぎ', 'レタス', 'もやし', 'ブロッコリー',
    'たまねぎ', 'にんじん', 'だいこん', 'じゃがいも', 'さつまいも', 'さといも',
    'きゅうり', 'なす', 'トマト', 'ピーマン', 'かぼちゃ',
    'りんご', 'みかん', 'バナナ', 'なし', 'ぶどう', 'もも', 'いちご', 'メロン',
    'すいか', 'グレープフルーツ', 'オレンジ', 'キウイフルーツ',
]

ENERGY_NAMES = ['電気代', '都市ガス代', 'プロパンガス', 'ガソリン', '灯油']

FOOD_KWDS = ['食料', '食パン', 'パン', '米', '麺', '魚', '肉', '野菜', '果物', '菓子',
             '飲料', '茶', 'コーヒー', '調味料', '酒', 'ビール', 'ワイン', 'ジュース',
             '弁当', 'すし', 'カレー', 'ラーメン', 'うどん', 'そば']
ALCOHOL_KWDS = ['酒', 'ビール', 'ワイン', 'ウイスキー', '清酒', '焼酎', 'チューハイ', '発泡酒']


def classify_item(code: str, name: str) -> dict:
    """品目を fresh_food / energy / food / alcohol のフラグに分類"""
    is_fresh = any(kw in name for kw in FRESH_ITEM_KWDS) and '加工' not in name and '冷凍' not in name and '缶詰' not in name
    is_energy = name in ENERGY_NAMES or any(kw == name for kw in ENERGY_NAMES)
    is_alcohol = any(kw in name for kw in ALCOHOL_KWDS)
    return {'is_fresh': is_fresh, 'is_energy': is_energy, 'is_alcohol': is_alcohol}


# ===== 集計: core (生鮮食品除く) と BOJ-core (食料・エネルギー除く) =====
def compute_aggregate(df: pd.DataFrame, items_info: dict, ym_range: tuple,
                      apply_tax: bool, name: str) -> pd.DataFrame:
    """品目別データから core/boj_core を算出"""
    rows = []
    df_sub = df[df['ym'].between(ym_range[0], ym_range[1])].copy()
    for _, row in df_sub.iterrows():
        ym = row['ym']
        sums = {'all_w': 0, 'all_v': 0, 'core_w': 0, 'core_v': 0, 'bojcore_w': 0, 'bojcore_v': 0}
        for code, info in items_info.items():
            if code not in df.columns:
                continue
            v = row.get(code)
            if pd.isna(v):
                continue
            w = info['weight_10000']
            # Use info flags if available (2020 master), else name-based (2010)
            if 'is_fresh' in info:
                is_fresh = info['is_fresh']
                is_energy = info['is_energy']
                is_food = info['is_food']
                is_alcohol = info['is_alcohol']
            else:
                cls = classify_item(code, info['name'])
                is_fresh = cls['is_fresh']
                is_energy = cls['is_energy']
                is_alcohol = cls['is_alcohol']
                is_food = is_fresh or any(kw in info['name'] for kw in FOOD_KWDS)
            factor = tax_factor(info['name'], ym) if apply_tax else 1.0
            v_adj = v * factor
            sums['all_w'] += w
            sums['all_v'] += w * v_adj
            if not is_fresh:
                sums['core_w'] += w
                sums['core_v'] += w * v_adj
            # BOJ core: excl food (less alcohol) and energy
            is_food_nonalcohol = is_food and not is_alcohol
            if not is_food_nonalcohol and not is_energy:
                sums['bojcore_w'] += w
                sums['bojcore_v'] += w * v_adj
        rows.append({
            'ym': ym,
            f'{name}_all': sums['all_v'] / sums['all_w'] if sums['all_w'] else None,
            f'{name}_core': sums['core_v'] / sums['core_w'] if sums['core_w'] else None,
            f'{name}_bojcore': sums['bojcore_v'] / sums['bojcore_w'] if sums['bojcore_w'] else None,
        })
    return pd.DataFrame(rows)


def main():
    print("Loading data...")
    df10, info10 = load_2010_items()
    df20, info20 = load_2020_longterm()

    print(f"  2010基準: {len(info10)} 品目, {len(df10)} ヶ月")
    print(f"  2020基準長期: {len(info20)} 品目, {len(df20)} ヶ月")

    # 2014年前後の比較
    ym_range = ('2013-01', '2015-12')

    print(f"\nComputing β (2010-base item-level)...")
    beta_unadj = compute_aggregate(df10, info10, ym_range, apply_tax=False, name='b_unadj')
    beta_adj = compute_aggregate(df10, info10, ym_range, apply_tax=True, name='b_adj')

    print(f"Computing α (2020-base spliced item-level)...")
    alpha_unadj = compute_aggregate(df20, info20, ym_range, apply_tax=False, name='a_unadj')
    alpha_adj = compute_aggregate(df20, info20, ym_range, apply_tax=True, name='a_adj')

    # Merge
    out = beta_unadj.merge(beta_adj, on='ym').merge(alpha_unadj, on='ym').merge(alpha_adj, on='ym')

    # Compute YoY
    def yoy(s):
        return ((s / s.shift(12)) - 1) * 100
    for col in ['b_unadj_core', 'b_adj_core', 'a_unadj_core', 'a_adj_core',
                'b_unadj_bojcore', 'b_adj_bojcore', 'a_unadj_bojcore', 'a_adj_bojcore']:
        out[col + '_yoy'] = yoy(out[col])

    # Tax adjustment effect (調整による前年比押し下げ pp)
    out['β_core_taxeffect_pp'] = out['b_adj_core_yoy'] - out['b_unadj_core_yoy']
    out['α_core_taxeffect_pp'] = out['a_adj_core_yoy'] - out['a_unadj_core_yoy']
    out['α-β_core_diff_pp'] = out['α_core_taxeffect_pp'] - out['β_core_taxeffect_pp']

    out['β_bojcore_taxeffect_pp'] = out['b_adj_bojcore_yoy'] - out['b_unadj_bojcore_yoy']
    out['α_bojcore_taxeffect_pp'] = out['a_adj_bojcore_yoy'] - out['a_unadj_bojcore_yoy']
    out['α-β_bojcore_diff_pp'] = out['α_bojcore_taxeffect_pp'] - out['β_bojcore_taxeffect_pp']

    # Compare with official tax_adjusted.xlsx
    tax = pd.read_excel('data/soumu/tax_adjusted.xlsx', sheet_name='zmi', header=None)
    tax_data = tax.iloc[6:].copy()
    tax_data.columns = ['ym_raw', 'all', 'core', 'less_imp', 'less_imp_fresh', 'core_core', 'boj_core']
    tax_data['ym'] = tax_data['ym_raw'].astype(str).str[:4] + '-' + tax_data['ym_raw'].astype(str).str[4:]

    # Get unadjusted core/boj_core from tax_adjusted (these are at 2020-base spliced)
    # From long-term file directly
    df20['ym'] = df20['year_month']
    off_core = df20[['ym', '0161', '0168']].rename(columns={'0161': 'official_core', '0168': 'official_bojcore'})
    out = out.merge(off_core, on='ym', how='left')
    out = out.merge(tax_data[['ym', 'core', 'boj_core']].rename(columns={'core': 'taxadj_core', 'boj_core': 'taxadj_bojcore'}), on='ym', how='left')

    # Display 2014-04+
    print(f"\n=== 2014-04税調整効果 (前年比、pp) ===")
    show = out[out['ym'].between('2014-04', '2015-06')][[
        'ym', 'β_core_taxeffect_pp', 'α_core_taxeffect_pp', 'α-β_core_diff_pp',
        'β_bojcore_taxeffect_pp', 'α_bojcore_taxeffect_pp', 'α-β_bojcore_diff_pp'
    ]]
    print(show.to_string(index=False, float_format='%.3f'))

    out.to_csv('output/compare_2014_tax.csv', index=False)
    print(f"\n保存: output/compare_2014_tax.csv")


if __name__ == '__main__':
    main()
