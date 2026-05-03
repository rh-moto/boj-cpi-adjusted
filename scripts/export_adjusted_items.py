"""2015基準・2020基準の品目別調整済指数をCSVに出力

出力:
- output/cpi_2015base_adjusted_items.csv (2015-01〜2021-06)
- output/cpi_2020base_adjusted_items.csv (2020-01〜最新月)

調整内容:
- ガソリン/灯油/電気/ガス: src.pipeline.build_adjusted_indices
- 教育/モバイル/旅行支援等: policy_events.csv
- 消費税調整: 2015基準のみ (2020基準には2020以降の税率変更が無い)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adjust_tax import apply_tax_adjustment
from src.config import OUTPUT_DIR
from src.fetch_cpi import parse_cpi_csv
from src.item_master import load_item_master
from src.pipeline import build_adjusted_indices


def export_base(base_year: int):
    indices, _ = parse_cpi_csv(base_year=base_year)
    master = load_item_master(base_year=base_year)

    adj = indices.copy()
    if base_year == 2015:
        # 1997-04, 2014-04 (and 2019-10 for the partial period within 2015-base)
        adj = apply_tax_adjustment(adj, master['item_code'].tolist(), master)
    adj = build_adjusted_indices(adj, base_year=base_year)

    out_path = OUTPUT_DIR / f'cpi_{base_year}base_adjusted_items.csv'
    out = adj.reset_index().rename(columns={'index': 'ym'})
    if 'ym' not in out.columns:
        out = adj.copy()
        out.index.name = 'ym'
        out = out.reset_index()
    out.to_csv(out_path, index=False)
    print(f"保存: {out_path}  shape={out.shape}  期間={out['ym'].iloc[0]}〜{out['ym'].iloc[-1]}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for base in (2015, 2020):
        print(f"\n--- {base}基準 ---")
        export_base(base)


if __name__ == '__main__':
    main()
