"""プロジェクト共通の定数・パス定義"""

from pathlib import Path

# ルートディレクトリ
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# データディレクトリ
DATA_DIR = PROJECT_ROOT / "data"
SOUMU_DIR = DATA_DIR / "soumu"
METI_DIR = DATA_DIR / "meti"
POLICY_DIR = DATA_DIR / "policy_params"
BOJ_DIR = DATA_DIR / "boj"
OUTPUT_DIR = PROJECT_ROOT / "output"

# 基準年
BASE_YEAR = 2020

# 3系列の定義
# コアCPI: 総合除く生鮮食品
# コアコアCPI: 総合除く生鮮食品・エネルギー
# 日銀コア: 総合除く食料（酒類を除く）・エネルギー
SERIES_NAMES = {
    "core": "総合除く生鮮食品",
    "core_core": "総合除く生鮮食品・エネルギー",
    "boj_core": "総合除く食料（酒類を除く）・エネルギー",
}
