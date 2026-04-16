#!/usr/bin/env python3
"""CHOTTO の WordPress タグ一覧を data/chotto_tags_reference.txt に書き出す（sites.json 必須）。"""
import json
import os
import ssl
import sys
import urllib.request
import base64


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    path_sites = os.path.join(root, "sites.json")
    if not os.path.isfile(path_sites):
        print("sites.json が見つかりません。", file=sys.stderr)
        sys.exit(1)
    with open(path_sites) as f:
        sites = json.load(f)
    sc = sites.get("chotto")
    if not sc:
        print("sites.json に chotto がありません。", file=sys.stderr)
        sys.exit(1)
    url_base = sc["api_url"].rstrip("/")
    auth = base64.b64encode(f"{sc['user']}:{sc['app_pass']}".encode()).decode()
    ctx = ssl.create_default_context()
    headers = {"Authorization": f"Basic {auth}", "User-Agent": "Mozilla/5.0 (export_chotto_tags)"}
    all_tags = []
    page = 1
    while True:
        u = f"{url_base}/tags?per_page=100&page={page}&_fields=id,name,slug,count"
        req = urllib.request.Request(u, headers=headers)
        with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
            batch = json.loads(r.read().decode())
        if not batch:
            break
        all_tags.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    all_tags.sort(key=lambda x: (-x.get("count", 0), x.get("name") or ""))
    out_dir = os.path.join(root, "data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "chotto_tags_reference.txt")
    lines = [
        "# CHOTTO WordPress タグ名一覧（利用回数の多い順）。ドラフトのタグはこの表記と完全一致が必要。",
        f"# total: {len(all_tags)}",
        "",
    ]
    for t in all_tags:
        name = (t.get("name") or "").strip()
        if not name or "\n" in name or "\r" in name:
            continue
        lines.append(name)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {len(lines) - 3} tag names to {out_path}")


if __name__ == "__main__":
    main()
