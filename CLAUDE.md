# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

日銀「消費者物価のコア指標」の一部として公表される「特殊要因を除いたCPI」を自前で再現する計算パイプライン。日銀公表値との突合・検証を行う。

対象3系列: コアCPI、コアコアCPI、日銀コア（除く食料・エネルギー）

5つの特殊要因: 消費税率変更、教育無償化、携帯電話通信料引下げ、旅行支援策、エネルギー負担緩和策（ガソリン・電気代・ガス代）

## 開発環境

```bash
source .venv/bin/activate
python scripts/run_phase0.py    # Phase 0 全体テスト
python scripts/build_item_master.py  # 品目マスタ再生成
ruff check src/                 # lint
pytest                          # テスト
```

## コードアーキテクチャ

```
src/
  config.py          # パス・定数定義
  item_master.py     # 品目マスタ管理（582品目、分類フラグ、3系列フィルタ）
  fetch_cpi.py       # 総務省CPI月次指数パーサー（CSVベース）
  fetch_weights.py   # ウエイトパーサー（固定/連鎖）
  fetch_boj.py       # 日銀公表値パーサー
  aggregate.py       # 上位指数集計（公式値取得 + 加重平均）
  validate.py        # 検証レポート
  adjust_gasoline.py # ガソリン調整（Phase 1）

scripts/
  build_item_master.py  # 品目分類Excel→品目マスタCSV
  explore_estat.py      # e-Stat API探索
  run_phase0.py         # Phase 0動作確認

data/
  soumu/               # 総務省データ（.gitignore対象）
  meti/                # 資源エネルギー庁データ
  boj/                 # 日銀データ（.gitignore対象）
  policy_params/       # 政策パラメータCSV（git管理）
    item_master.csv    # 品目マスタ
    gasoline_subsidy.csv  # ガソリン補助金単価テーブル
```

## 重要な設計判断

- **品目コードは計画書と異なる**: ガソリン=7301（計画書7311）、都市ガス代=3600（計画書3510）、携帯通信料=7430（計画書7340）、宿泊料=9300（計画書9341）等。正しいコードは`item_master.py`のSPECIAL_FACTOR_ITEMSを参照
- **幼稚園保育料は2020年基準で品目消滅**: 幼保無償化が基準時に織込み済みのため調整不要
- **未調整の上位指数はCSV公式集計値を使用**: 品目別加重平均は固定ウエイトの制約で公式値と最大0.3乖離するため、未調整値は公式値（code: 0161, 0178, 0168）をそのまま使う
- **調整済の上位指数は固定ウエイト加重平均**: 特殊要因調整の精度が支配的なので固定ウエイトで十分
- **日銀公表値はcalibrateに使わない**: 検証のみ。パラメータは外生的に固定

## 主要データソース

| データ | URL | ファイル |
|---|---|---|
| CPI品目別月次指数 | stat.go.jp/data/cpi/2020/csv/zmi2020aa.csv | data/soumu/cpi_monthly_all.csv |
| 品目分類一覧 | stat.go.jp/.../zuhyou/4-1.xlsx | data/soumu/item_classification.xlsx |
| 連鎖ウエイト | stat.go.jp/.../rensa-wt_2020.xlsx | data/soumu/weight_chain.xlsx |
| 日銀コア指標 | boj.or.jp/.../cpirev.xlsx | data/boj/cpi_core_indicators.xlsx |

## 注意事項

- 日銀は特殊要因の定義を予告なく変更する可能性がある
- 2025年基準改定（2026年8月予定）で品目・ウエイト・モデル式が変わる
- 調整ロジックの詳細（数式、品目コード等）は `boj_cpi_workplan_v2.md` を参照
