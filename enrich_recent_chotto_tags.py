#!/usr/bin/env python3
"""
直近 N 日の CHOTTO 公開・予約投稿のタグを、既存タグ名との照合で増やす（既定12個以上）。

- タイトル部分文字列と既存タグ名の一致（長さ・利用回数で優先）
- 投稿日の「YYYY年M月」、カテゴリ名と一致するタグ
- タイトル語とキーワード対応（速報・国際・AI 等）
- 不足分はサイトに存在する汎用タグを投稿IDで順序回転させて補完（再実行で上書きしやすい）

使い方:
  python enrich_recent_chotto_tags.py --days 30 --dry-run
  python enrich_recent_chotto_tags.py --days 30 --apply
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import quote
from datetime import datetime, timedelta, timezone


def load_site():
    root = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(root, "sites.json")) as f:
        sites = json.load(f)
    sc = sites["chotto"]
    return sc["api_url"].rstrip("/"), sc["user"], sc["app_pass"]


def api_json(
    url_base: str,
    user: str,
    pw: str,
    path: str,
    method: str = "GET",
    data=None,
    timeout: int = 240,
    retries: int = 4,
):
    auth = base64.b64encode(f"{user}:{pw}".encode()).decode()
    ctx = ssl.create_default_context()
    last_err = None
    for attempt in range(retries):
        headers = {"Authorization": f"Basic {auth}", "User-Agent": "Mozilla/5.0 (enrich_recent_chotto_tags)"}
        body = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(f"{url_base}/{path}", data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return json.loads(r.read().decode())
        except (TimeoutError, urllib.error.URLError, OSError) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise last_err from None
    raise last_err  # pragma: no cover


def fetch_all_tags(url_base: str, user: str, pw: str):
    all_tags = []
    page = 1
    while True:
        path = f"tags?per_page=100&page={page}&_fields=id,name,count"
        batch = api_json(url_base, user, pw, path)
        if not batch:
            break
        all_tags.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return all_tags


def fetch_recent_posts(url_base: str, user: str, pw: str, after_iso: str):
    posts = []
    page = 1
    while True:
        path = (
            f"posts?after={quote(after_iso)}&per_page=100&page={page}"
            "&_fields=id,date,title,tags,categories,status&status=publish,future"
        )
        batch = api_json(url_base, user, pw, path)
        if not batch:
            break
        posts.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return posts


def fetch_categories_by_ids(url_base: str, user: str, pw: str, ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    out: dict[int, str] = {}
    # REST: include はカンマ区切り、件数が多いときは分割
    chunk = 80
    for i in range(0, len(ids), chunk):
        part = ids[i : i + chunk]
        q = ",".join(str(x) for x in part)
        path = f"categories?include={q}&per_page={chunk}&_fields=id,name"
        batch = api_json(url_base, user, pw, path)
        for c in batch or []:
            if c.get("id") is not None and c.get("name"):
                out[int(c["id"])] = c["name"].strip()
    return out


def strip_title(html: str) -> str:
    t = re.sub(r"<[^>]+>", "", html or "")
    return t.replace("**", "").strip()


def month_tag_from_date(date_str: str, by_name: dict[str, dict]) -> str | None:
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return None
    y, m = dt.year, dt.month
    label = f"{y}年{m}月"
    if label in by_name:
        return label
    return None


def tag_matches_title(name: str, title: str) -> bool:
    if len(name) < 2:
        return False
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.\-]*", name):
        return bool(re.search(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])", title, re.I))
    return name in title


def suggest_tag_ids(
    title: str,
    existing: list[int],
    tags_sorted: list[dict],
    by_name: dict[str, dict],
    month_label: str | None,
    min_tags: int,
    max_total: int = 22,
    category_names: list[str] | None = None,
    post_id: int | None = None,
) -> list[int]:
    have = set(existing)
    out: list[int] = []

    def add_by_id(tid: int):
        if tid not in have and len(have) < max_total:
            have.add(tid)
            out.append(tid)

    if month_label and month_label in by_name:
        add_by_id(by_name[month_label]["id"])

    if category_names:
        for cn in category_names:
            hit = by_name.get(cn)
            if hit:
                add_by_id(hit["id"])

    # タイトル部分文字列と既存タグ名の一致をすべて集め、長さ→利用回数の順で追加
    n = len(title)
    candidates: list[tuple[int, int, int, str]] = []
    for i in range(n):
        upper = min(80, n - i)
        for L in range(2, upper + 1):
            s = title[i : i + L]
            hit = by_name.get(s)
            if hit:
                candidates.append((L, hit.get("count", 0), hit["id"], s))
    candidates.sort(key=lambda x: (-x[0], -x[1], x[3]))
    seen_ids: set[int] = set()
    for L, _cnt, tid, _s in candidates:
        if tid in seen_ids:
            continue
        seen_ids.add(tid)
        add_by_id(tid)
        if len(have) >= min_tags or len(have) >= max_total:
            break

    for t in tags_sorted:
        if len(have) >= min_tags or len(have) >= max_total:
            break
        tid, name = t["id"], (t.get("name") or "").strip()
        if not name or tid in have:
            continue
        if tag_matches_title(name, title):
            add_by_id(tid)

    # タイトルを短いセグメントに分け、既存タグ名と完全一致するものを追加
    if len(have) < min_tags and len(have) < max_total:
        parts = re.split(r"[\s　、・,/|]+", title)
        for p in parts:
            if len(have) >= min_tags or len(have) >= max_total:
                break
            p = p.strip(" 　、・[]「」『』()（）")
            if len(p) < 2:
                continue
            hit = by_name.get(p)
            if hit and hit["id"] not in have:
                add_by_id(hit["id"])

    # タイトルに語が含まれる場合の定番タグ（完全一致のみ）
    keyword_pairs = [
        ("速報", "速報"),
        ("国際", "国際情勢"),
        ("中東", "中東情勢"),
        ("イラン", "イラン"),
        ("ウクライナ", "ウクライナ"),
        ("イスラエル", "イスラエル"),
        ("テスラ", "テスラ"),
        ("AI", "AI"),
        ("生成AI", "生成AI"),
        ("OpenAI", "OpenAI"),
        ("野球", "野球"),
        ("大谷", "大谷翔平"),
    ]
    for kw, tname in keyword_pairs:
        if len(have) >= min_tags or len(have) >= max_total:
            break
        if kw in title and tname in by_name:
            add_by_id(by_name[tname]["id"])

    # カテゴリに応じた補助（カテゴリ名に部分一致）
    cat_joined = " ".join(category_names or [])
    cat_extra: list[str] = []
    if "エンタメ" in cat_joined or "芸能" in cat_joined:
        cat_extra.extend(["エンタメ", "芸能ニュース", "芸能界", "ニュース"])
    elif "AI" in cat_joined or "テクノロジー" in cat_joined:
        cat_extra.extend(["テクノロジー", "生成AI", "AI", "ニュース"])
    elif "経済" in cat_joined or "ビジネス" in cat_joined:
        cat_extra.extend(["ニュース", "社会問題", "経済安全保障"])
    elif "スポーツ" in cat_joined:
        cat_extra.extend(["野球", "ニュース"])
    for tname in cat_extra:
        if len(have) >= min_tags or len(have) >= max_total:
            break
        if tname in by_name:
            add_by_id(by_name[tname]["id"])

    # 最終フォールバック（投稿IDで順序を回転し、全記事が同一タグ列にならないようにする）
    fallback_order = [
        "ニュース",
        "社会問題",
        "国際情勢",
        "テクノロジー",
        "芸能ニュース",
        "SNS",
        "ソーシャルメディア",
        "メディアリテラシー",
        "ファクトチェック",
        "速報",
        "米国",
        "中東情勢",
        "人工知能",
        "生成AI",
        "エンタメ",
        "芸能界",
        "地政学",
        "安全保障",
        "テスラ",
        "電気自動車",
    ]
    if post_id is not None and fallback_order:
        r = post_id % len(fallback_order)
        fallback_order = fallback_order[r:] + fallback_order[:r]
    for tname in fallback_order:
        if len(have) >= min_tags or len(have) >= max_total:
            break
        if tname in by_name:
            add_by_id(by_name[tname]["id"])

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--min-tags", type=int, default=12)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="各投稿の追加内容を表示")
    args = ap.parse_args()
    if args.dry_run and args.apply:
        print("--dry-run と --apply は同時に指定しないでください。", file=sys.stderr)
        sys.exit(1)
    if not args.dry_run and not args.apply:
        args.dry_run = True

    url_base, user, pw = load_site()
    print("Fetching tag list…")
    all_tags = fetch_all_tags(url_base, user, pw)
    by_name = {(t.get("name") or "").strip(): t for t in all_tags if (t.get("name") or "").strip()}
    tags_sorted = sorted(
        all_tags,
        key=lambda t: (-len((t.get("name") or "").strip()), -t.get("count", 0)),
    )

    after = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%dT%H:%M:%S")
    print(f"Fetching posts since {after} …")
    posts = fetch_recent_posts(url_base, user, pw, after)
    print(f"Posts: {len(posts)}")

    cat_ids = sorted({cid for p in posts for cid in (p.get("categories") or [])})
    print(f"Resolving {len(cat_ids)} category ids…")
    cat_id_to_name = fetch_categories_by_ids(url_base, user, pw, cat_ids)

    still_short: list[tuple[int, str, int, int]] = []
    updates = 0

    for n, p in enumerate(posts, 1):
        pid = p["id"]
        raw_title = (p.get("title") or {}).get("rendered") or ""
        title = strip_title(raw_title)
        existing = list(p.get("tags") or [])
        date_str = p.get("date") or ""
        month_label = month_tag_from_date(date_str, by_name)
        cnames = [cat_id_to_name[c] for c in (p.get("categories") or []) if c in cat_id_to_name]
        new_ids = suggest_tag_ids(
            title,
            existing,
            tags_sorted,
            by_name,
            month_label,
            args.min_tags,
            category_names=cnames,
            post_id=pid,
        )
        merged = existing + [x for x in new_ids if x not in existing]
        if len(merged) < args.min_tags:
            still_short.append((pid, title[:80], len(existing), len(merged)))

        if not new_ids:
            continue

        updates += 1
        if args.apply:
            try:
                api_json(url_base, user, pw, f"posts/{pid}", method="POST", data={"tags": merged})
            except urllib.error.HTTPError as e:
                print(f"HTTP {e.code} post {pid}: {e.read()[:500]!r}", file=sys.stderr)
                continue
            except (TimeoutError, OSError) as e:
                print(f"network error post {pid}: {e}", file=sys.stderr)
                continue
            time.sleep(0.2)
            if n % 40 == 0:
                print(f"  … applied {n}/{len(posts)}")
        elif args.verbose:
            print(f"[dry-run] id={pid} +{len(new_ids)} tags -> total {len(merged)} | {title[:70]}…")

    print(f"Posts with suggested additions: {updates}")
    print(f"Still under --min-tags ({args.min_tags}) after suggestions: {len(still_short)}")
    if still_short[:20] and args.dry_run:
        for row in still_short[:20]:
            print(f"  id={row[0]} before={row[2]} after={row[3]} | {row[1]}")
    if args.apply:
        print("Applied updates (tags merged with existing).")


if __name__ == "__main__":
    main()
