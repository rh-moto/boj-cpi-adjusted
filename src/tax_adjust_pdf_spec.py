"""総務省PDF仕様準拠の品目別消費税調整

仕様書: data/soumu/2015taxadj.pdf
（消費者物価指数における「消費税調整済指数」の作成について、令和元年10月29日）

対応する税変更イベント:
  - 1997-04: 3% → 5%
  - 2014-04: 5% → 8%
  - 2019-10: 8% → 10% (既存 src/adjust_tax.py が担当)

注: 1989-04 (3%導入) は仕様書で明示的に「行わない」とされているため対応外。
"""

import pandas as pd
from pathlib import Path

from src.config import POLICY_DIR


# ===== 税変更イベント定義 =====
TAX_EVENTS = {
    1997: {'effective': '1997-04', 'old_rate': 1.03, 'new_rate': 1.05,
           'category_csv': 'tax_category_1997.csv'},
    2014: {'effective': '2014-04', 'old_rate': 1.05, 'new_rate': 1.08,
           'category_csv': 'tax_category_2014.csv'},
}


def _normalize_name(name: str) -> str:
    """全角・半角・括弧の差を吸収"""
    if pd.isna(name):
        return ''
    n = str(name)
    # 全角括弧を半角に
    n = n.replace('（', '(').replace('）', ')')
    n = n.replace('，', ',').replace('、', ',')
    n = n.replace(' ', '').replace('　', '')
    return n


def load_tax_categories(year: int) -> pd.DataFrame:
    """税変更イベントの品目別区分CSVを読み込み"""
    if year not in TAX_EVENTS:
        raise ValueError(f"未対応の税変更イベント: {year}")
    csv_path = POLICY_DIR / TAX_EVENTS[year]['category_csv']
    df = pd.read_csv(csv_path)
    df['_norm_name'] = df['item_name'].apply(_normalize_name)
    return df


def _next_survey_month(detail: str, change_ym: str) -> str:
    """季節調査品目: 改定月の次の調査開始月を返す

    detail例: 'Sep-Feb' = 9月～2月調査、'Mar-Aug' = 3月～8月調査
    """
    if not detail or '-' not in detail:
        return change_ym  # 不明な場合は遅延なし
    months_map = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                  'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
    start_str, end_str = detail.split('-')
    start = months_map.get(start_str, 1)
    end = months_map.get(end_str, 12)
    yr = int(change_ym[:4])
    mo = int(change_ym[5:])
    # 改定月mo以降で、survey期間に入る最初の月
    in_survey = lambda m: (start <= m <= end) if start <= end else (m >= start or m <= end)
    if in_survey(mo):
        return change_ym  # すでに調査中
    # 翌月から探索
    for offset in range(1, 13):
        nm = mo + offset
        ny = yr + (nm - 1) // 12
        nm = ((nm - 1) % 12) + 1
        if in_survey(nm):
            return f"{ny:04d}-{nm:02d}"
    return change_ym


def compute_factor(item_name: str, year_month: str, event_year: int,
                   tax_cats: pd.DataFrame | None = None) -> float:
    """品目×月の調整係数 v(i,t) を返す

    PDF仕様:
      - 非課税品目: v = 1
      - 経過措置 type1 (電気代等): 改定当月旧、翌月以降新
      - 経過措置 type2 (固定電話等): 改定当月にウエイト按分
      - 季節調査 type1 (改定当月非調査): 次回調査開始月から新
      - 季節調査 type2 (改定月以前から継続調査): 保合期間に月数平均
      - 軽減税率 (2019のみ): v = 1
      - 通常課税: 改定当月以降に旧/新
    """
    if event_year not in TAX_EVENTS:
        return 1.0
    ev = TAX_EVENTS[event_year]
    eff_ym = ev['effective']
    if year_month < eff_ym:
        return 1.0
    if tax_cats is None:
        tax_cats = load_tax_categories(event_year)

    factor = ev['old_rate'] / ev['new_rate']  # 旧/新

    # 品目名で照合
    norm = _normalize_name(item_name)
    row = tax_cats[tax_cats['_norm_name'] == norm]
    if row.empty:
        # 部分一致を試す（PDFと2010基準で名称表記が異なる場合）
        for _, r in tax_cats.iterrows():
            if r['_norm_name'] and (r['_norm_name'] in norm or norm in r['_norm_name']):
                row = pd.DataFrame([r])
                break

    if row.empty:
        # 未登録 → デフォルト: 通常課税
        return factor

    cat = row.iloc[0]['category']
    detail = str(row.iloc[0].get('detail', '') or '')

    if cat == 'exempt':
        return 1.0

    if cat == 'reduced':
        # 軽減税率（2019-10のみ。1997/2014では使われない）
        return 1.0

    if cat == 'trans1':
        # 経過措置 type1: 改定当月は旧税率、翌月以降は新税率
        if year_month <= eff_ym:
            return 1.0
        return factor

    if cat == 'trans2':
        # 経過措置 type2: 改定当月にウエイトで一部のみ新税率
        # detail = "2/3" などのウエイト
        if year_month < eff_ym:
            return 1.0
        if year_month == eff_ym:
            # 部分適用
            try:
                num, den = detail.split('/')
                w_new = float(num) / float(den)
            except Exception:
                w_new = 0.5
            return factor * w_new + 1.0 * (1 - w_new)
        return factor

    if cat == 'trans2_2mo':
        # 経過措置 type2 の2ヶ月版（清掃代の1997-04）
        next_eff_ym = _add_months(eff_ym, 1)
        if year_month < eff_ym:
            return 1.0
        if year_month <= next_eff_ym:
            try:
                num, den = detail.split('/')
                w_new = float(num) / float(den)
            except Exception:
                w_new = 0.5
            return factor * w_new + 1.0 * (1 - w_new)
        return factor

    if cat == 'seasonal1':
        # 改定当月非調査 → 次回調査開始月から新税率
        next_survey = _next_survey_month(detail, eff_ym)
        if year_month < next_survey:
            return 1.0
        return factor

    if cat == 'seasonal2':
        # 改定月以前から継続調査 → 保合期間に月数平均
        # detail = "Mar-Aug" など survey period
        # 改定月から survey 終了までは新税率
        # 保合期間は (改定前月数 × 1 + 改定後月数 × factor) / 全月数
        # 次のsurvey期間は新税率
        if not detail or '-' not in detail:
            # 不明な場合は通常扱い
            return factor
        months_map = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                      'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
        start_str, end_str = detail.split('-')
        start = months_map.get(start_str, 1)
        end = months_map.get(end_str, 12)
        eff_mo = int(eff_ym[5:])
        cur_yr = int(year_month[:4])
        cur_mo = int(year_month[5:])

        in_survey = lambda m: (start <= m <= end) if start <= end else (m >= start or m <= end)
        if not in_survey(eff_mo):
            # 改定月が調査期間外 → seasonal1 と同じ扱い
            next_survey = _next_survey_month(detail, eff_ym)
            return 1.0 if year_month < next_survey else factor

        # 改定月が調査期間内（type 2）
        if year_month < eff_ym:
            return 1.0

        # 改定後の同年survey期間内: 新税率
        if cur_yr == int(eff_ym[:4]) and in_survey(cur_mo):
            return factor

        # survey終了後の保合期間 → 月数平均
        # survey期間内の改定前月数: eff_mo - start
        # survey期間内の改定後月数: end - eff_mo + 1
        n_pre = eff_mo - start  # 改定月含まないので
        n_post = end - eff_mo + 1  # 改定月含む
        n_total = end - start + 1
        if n_pre == 0:
            avg_factor = factor
        else:
            avg_factor = (n_pre * 1.0 + n_post * factor) / n_total

        # 保合期間: survey終了月の翌月から、次回survey開始の前月まで
        # 簡易: 改定後survey終了直後から翌年survey開始月の前月まで
        next_survey = _next_survey_month(detail, f"{int(eff_ym[:4])}-{end:02d}")
        next_survey = _add_months(f"{int(eff_ym[:4])}-{end:02d}", 1)
        # cycle: 翌survey期間に入ったら新税率に戻る
        years_after = cur_yr - int(eff_ym[:4])
        if years_after >= 1 and in_survey(cur_mo):
            return factor
        return avg_factor

    # その他: デフォルト通常課税
    return factor


def _add_months(ym: str, n: int) -> str:
    yr = int(ym[:4])
    mo = int(ym[5:]) + n
    yr += (mo - 1) // 12
    mo = ((mo - 1) % 12) + 1
    return f"{yr:04d}-{mo:02d}"


def apply_all_tax_adjustments(indices: pd.DataFrame, item_names: dict[str, str],
                              events: tuple = (1997, 2014)) -> pd.DataFrame:
    """品目別指数に複数の税調整を順次適用

    Args:
        indices: 品目別CPI指数 (index=YYYY-MM, columns=item_code)
        item_names: {item_code: item_name} の辞書
        events: 適用する税変更イベント年のタプル

    Returns:
        調整済み品目別指数
    """
    # 各イベントの税区分テーブルを事前ロード
    cats_by_event = {ev: load_tax_categories(ev) for ev in events}

    adjusted = indices.copy()

    # 各品目について全イベントのfactor積を計算して適用
    for code in adjusted.columns:
        name = item_names.get(code, '')
        if not name:
            continue
        # 各月のfactor
        for ym in adjusted.index:
            v_total = 1.0
            for ev in events:
                v_total *= compute_factor(name, ym, ev, cats_by_event[ev])
            if v_total != 1.0:
                v = adjusted.at[ym, code]
                if pd.notna(v):
                    adjusted.at[ym, code] = v * v_total

    return adjusted
