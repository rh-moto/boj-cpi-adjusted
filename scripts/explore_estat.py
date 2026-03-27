"""e-Stat APIのCPI統計表メタ情報を探索するスクリプト

使い方:
  python scripts/explore_estat.py

e-Stat APIはアプリIDなしでも統計表の検索が可能。
品目分類の階層構造を取得して品目マスタ作成に利用する。
"""

import json
import sys

import requests


def search_cpi_tables():
    """CPIの統計表一覧を検索"""
    url = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsList"
    params = {
        "appId": "guest",  # ゲストアクセス
        "searchWord": "消費者物価指数 2020年基準",
        "statsField": "0703",  # 物価
        "lang": "J",
    }
    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code != 200:
        print(f"HTTP {resp.status_code}")
        return

    data = resp.json()
    result = data.get("GET_STATS_LIST", {}).get("DATALIST_INF", {})
    tables = result.get("TABLE_INF", [])
    if not isinstance(tables, list):
        tables = [tables]

    print(f"検索結果: {len(tables)}件\n")
    for t in tables[:20]:
        table_id = t.get("@id", "")
        title = t.get("TITLE", {})
        if isinstance(title, dict):
            title = title.get("$", "")
        cycle = t.get("CYCLE", "")
        print(f"  ID: {table_id}")
        print(f"  タイトル: {title}")
        print(f"  周期: {cycle}")
        print()


def get_table_meta(table_id: str = "0003427113"):
    """統計表のメタ情報（分類項目）を取得"""
    url = "https://api.e-stat.go.jp/rest/3.0/app/json/getMetaInfo"
    params = {
        "appId": "guest",
        "statsDataId": table_id,
        "lang": "J",
    }
    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code != 200:
        print(f"HTTP {resp.status_code}")
        print(resp.text[:500])
        return

    data = resp.json()
    meta = data.get("GET_META_INFO", {}).get("METADATA_INF", {})
    class_inf = meta.get("CLASS_INF", {}).get("CLASS_OBJ", [])

    for cls in class_inf:
        cls_id = cls.get("@id", "")
        cls_name = cls.get("@name", "")
        items = cls.get("CLASS", [])
        if not isinstance(items, list):
            items = [items]

        print(f"\n=== {cls_id}: {cls_name} ({len(items)}件) ===")
        for item in items[:30]:
            code = item.get("@code", "")
            name = item.get("@name", "")
            level = item.get("@level", "")
            parent = item.get("@parentCode", "")
            print(f"  {code:>10s}  L{level}  parent={parent:>10s}  {name}")
        if len(items) > 30:
            print(f"  ... 他 {len(items) - 30}件")

    # 品目分類のJSONを保存
    for cls in class_inf:
        if "品目" in cls.get("@name", "") or "cat" in cls.get("@id", "").lower():
            items = cls.get("CLASS", [])
            if not isinstance(items, list):
                items = [items]
            outpath = "data/soumu/estat_item_classes.json"
            with open(outpath, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            print(f"\n品目分類を {outpath} に保存 ({len(items)}件)")
            break


if __name__ == "__main__":
    print("=" * 60)
    print("e-Stat API: CPI統計表メタ情報の探索")
    print("=" * 60)

    if len(sys.argv) > 1 and sys.argv[1] == "search":
        search_cpi_tables()
    else:
        get_table_meta()
