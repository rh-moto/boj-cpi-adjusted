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

# 基準年設定
# 2015: 2015年基準（2015-01〜2021-06）
# 2020: 2020年基準（2020-01〜最新月）
BASE_YEAR = 2020

# 基準年別のCPI CSVデータソース
CPI_CSV_URLS = {
    2015: "https://www.stat.go.jp/data/cpi/2015/csv/zmi2015aa.csv",
    2020: "https://www.stat.go.jp/data/cpi/2020/csv/zmi2020aa.csv",
}

CPI_CSV_FILENAMES = {
    2015: "cpi_monthly_2015.csv",
    2020: "cpi_monthly_all.csv",
}

# 日銀Excelの基準年別列インデックス
# chartシート: col 0=日付, 以降は基準年別にペア
BOJ_SERIES_COLS = {
    2015: {
        "core_ex_special": 2,       # 除く生鮮食品、特殊要因（15年基準）
        "core_core_ex_special": 5,  # 除く生鮮食品・エネルギー、特殊要因（15年基準）
        "boj_core_ex_special": 8,   # 除く食料・エネルギー、特殊要因（15年基準）
    },
    2020: {
        "core_ex_special": 1,       # 除く生鮮食品、特殊要因（20年基準）
        "core_core_ex_special": 4,  # 除く生鮮食品・エネルギー、特殊要因（20年基準）
        "boj_core_ex_special": 7,   # 除く食料・エネルギー、特殊要因（20年基準）
    },
}

# 3系列の定義
SERIES_NAMES = {
    "core": "総合除く生鮮食品",
    "core_core": "総合除く生鮮食品・エネルギー",
    "boj_core": "総合除く食料（酒類を除く）・エネルギー",
}
