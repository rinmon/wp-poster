#!/usr/bin/env python3
"""
CHOTTO.NEWS のカテゴリ正式名を公開 REST API から取得し、
data/chotto_categories_reference.txt を更新する。

認証不要（categories は一般公開されている想定）。
サイト側でカテゴリを差し替えたあと、本スクリプトで一覧を再生成すること。
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request

CHOTTO_CATEGORIES_URL = "https://chotto.news/wp-json/wp/v2/categories?per_page=100"
OUT = "data/chotto_categories_reference.txt"
HEADER = """# CHOTTO.NEWS（chotto.news）WordPress 登録カテゴリの正式名一覧
# ドラフトの **カテゴリ** 行は、次のいずれかと完全一致させること（REST API では新規カテゴリを作成しない）。
# 更新手順: python3 tools/export_chotto_categories.py（公開 REST で取得）
"""


def main() -> int:
    req = urllib.request.Request(CHOTTO_CATEGORIES_URL, headers={"User-Agent": "BLOG-export-chotto-categories/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        cats = json.loads(r.read().decode("utf-8"))

    names = [c.get("name", "").strip() for c in cats if c.get("name")]

    def sort_key(n: str) -> tuple:
        m = re.match(r"^(\d+)\.", n)
        return (int(m.group(1)) if m else 999, n)

    names = sorted(set(names), key=sort_key)

    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")
    body = "\n".join(names)
    text = f"{HEADER}# 取得日: {today}（公開 GET /wp/v2/categories?per_page=100）\n\n{body}\n\n"

    root = __file__
    import os

    base = os.path.dirname(os.path.dirname(os.path.abspath(root)))
    path = os.path.join(base, OUT)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Wrote {len(names)} categories to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
