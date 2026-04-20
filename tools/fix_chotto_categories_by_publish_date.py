#!/usr/bin/env python3
"""
公開日（サイト timezone の post `date` の日付部分）が指定日の CHOTTO 投稿の
カテゴリを、手動レビュー済みのマッピングで一括更新する。

使い方:
  python3 tools/fix_chotto_categories_by_publish_date.py --date 2026-04-20 --dry-run
  python3 tools/fix_chotto_categories_by_publish_date.py --date 2026-04-20 --apply

--apply は REST PUT で categories のみ更新（他フィールドは触れない）。
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_site() -> tuple[str, str, str]:
    sites = json.loads((ROOT / "sites.json").read_text(encoding="utf-8"))
    sc = sites["chotto"]
    return sc["api_url"].rstrip("/"), sc["user"], sc["app_pass"]


def api(
    base: str,
    user: str,
    pw: str,
    path: str,
    method: str = "GET",
    data: dict | None = None,
    timeout: int = 120,
):
    auth = base64.b64encode(f"{user}:{pw}".encode()).decode()
    ctx = ssl.create_default_context()
    hdr = {
        "Authorization": f"Basic {auth}",
        "User-Agent": "fix_chotto_categories_by_publish_date/1",
    }
    body = None
    if data is not None:
        hdr["Content-Type"] = "application/json; charset=utf-8"
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{base}/{path}", data=body, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        print(e.read().decode("utf-8", errors="replace"), file=sys.stderr)
        raise


def fetch_name_to_cat_id(base: str, user: str, pw: str) -> dict[str, int]:
    out: dict[str, int] = {}
    page = 1
    while True:
        batch = api(base, user, pw, f"categories?per_page=100&page={page}&_fields=id,name")
        if not batch:
            break
        for c in batch:
            if c.get("name"):
                out[c["name"].strip()] = int(c["id"])
        if len(batch) < 100:
            break
        page += 1
    return out


def cat_sort_key(name: str) -> int:
    m = re.match(r"^(\d+)\.", name)
    return int(m.group(1)) if m else 999


def sort_cat_names(names: list[str]) -> list[str]:
    return sorted(names, key=cat_sort_key)


# 公開日 2026-04-20 の Post ID → 新カテゴリ（最大2・表記は WP 正式名・番号昇順で並べ替え前の論理順でも可）
# 内容・見出し趣旨に基づく編集判断（自動スクレイピングではない）
SUGGESTED_2026_04_20: dict[int, tuple[str, ...]] = {
    61786: ("05.【IT・AI】", "09.【教育】"),
    61827: ("05.【IT・AI】", "06.【科学・技術】"),
    61833: ("02.【政治】", "08.【健康・医療】"),
    61838: ("05.【IT・AI】", "12.【エンタメ】"),
    61843: ("04.【経済・ビジネス】", "13.【グルメ】"),
    61848: ("01.【社会】", "03.【外交・安全保障】"),
    61853: ("01.【社会】", "12.【エンタメ】"),
    61885: ("04.【経済・ビジネス】", "05.【IT・AI】"),
    61891: ("01.【社会】", "14.【スポーツ】"),
    61910: ("04.【経済・ビジネス】", "05.【IT・AI】"),
    61913: ("12.【エンタメ】",),
    61918: ("02.【政治】", "06.【科学・技術】"),
    61921: ("05.【IT・AI】", "06.【科学・技術】"),
    61926: ("04.【経済・ビジネス】", "05.【IT・AI】"),
    61949: ("01.【社会】", "05.【IT・AI】"),
    61959: ("01.【社会】",),
    61965: ("01.【社会】", "10.【ライフスタイル】"),
    61971: ("01.【社会】",),
    61977: ("02.【政治】",),
    61983: ("03.【外交・安全保障】", "15.【訃報】"),
    61989: ("04.【経済・ビジネス】", "05.【IT・AI】"),
    61995: ("06.【科学・技術】",),
    62001: ("08.【健康・医療】",),
    62007: ("14.【スポーツ】",),
    62013: ("10.【ライフスタイル】", "13.【グルメ】"),
    62019: ("04.【経済・ビジネス】", "11.【アート・デザイン】"),
    62025: ("12.【エンタメ】",),
    62031: ("01.【社会】",),
    62037: ("02.【政治】",),
    62043: ("01.【社会】", "03.【外交・安全保障】"),
    62049: ("05.【IT・AI】", "12.【エンタメ】"),
    62055: ("05.【IT・AI】",),
    62061: ("05.【IT・AI】", "09.【教育】"),
    62067: ("01.【社会】", "09.【教育】"),
}


def fetch_posts_for_date(base: str, user: str, pw: str, ymd: str) -> list[dict]:
    posts: list[dict] = []
    page = 1
    while True:
        path = (
            f"posts?status=publish&per_page=100&page={page}"
            "&_fields=id,date,title,categories"
        )
        batch = api(base, user, pw, path)
        if not batch:
            break
        for p in batch:
            d = (p.get("date") or "")[:10]
            if d == ymd:
                posts.append(p)
        if len(batch) < 100:
            break
        page += 1
        if page > 80:
            break
    return posts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD（post.date の日付部分）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.dry_run == args.apply:
        print("いずれか一方: --dry-run または --apply", file=sys.stderr)
        return 2

    base, user, pw = load_site()
    name_to_id = fetch_name_to_cat_id(base, user, pw)
    posts = fetch_posts_for_date(base, user, pw, args.date)
    id_to_post = {int(p["id"]): p for p in posts}

    # 指定日のマッピングテーブル（日付専用ファイルにしたい場合は拡張）
    if args.date != "2026-04-20":
        print("このスクリプトには当該日の SUGGESTED マップがありません。--date を見直すかマップを追加してください。", file=sys.stderr)
        return 2
    suggested = SUGGESTED_2026_04_20

    missing = [pid for pid in suggested if pid not in id_to_post]
    if missing:
        print("警告: マップにあるが API の該当日投稿に無い ID:", missing, file=sys.stderr)

    extra = [p["id"] for p in posts if int(p["id"]) not in suggested]
    if extra:
        print("警告: 該当日投稿だがマップに無い ID（手動で追加要）:", extra, file=sys.stderr)

    cat_id_to_name = {v: k for k, v in name_to_id.items()}

    for pid in sorted(id_to_post.keys()):
        if pid not in suggested:
            continue
        p = id_to_post[pid]
        title = re.sub(r"<[^>]+>", "", p["title"]["rendered"])
        title = title.replace("&#8211;", "–").replace("&#8220;", "“").replace("&#8221;", "”").replace("&amp;", "&")
        old_ids = p.get("categories") or []
        old_names = sort_cat_names([cat_id_to_name.get(i, f"?{i}") for i in old_ids])
        new_names = sort_cat_names(list(suggested[pid]))
        new_ids = [name_to_id[n] for n in new_names if n in name_to_id]
        if not new_ids or len(new_ids) != len(new_names):
            print("カテゴリ名解決失敗:", pid, new_names, file=sys.stderr)
            return 1
        old_s = ",".join(old_names)
        new_s = ",".join(new_names)
        flag = "変更なし" if old_names == new_names else "UPDATE"
        print(f"{pid}\t{flag}\t{old_s}\t=>\t{new_s}\t{title[:55]}")

        if args.apply and old_names != new_names:
            api(base, user, pw, f"posts/{pid}", method="PUT", data={"categories": new_ids})

    if args.apply:
        print("\n✅ --apply 完了（categories のみ PUT）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
