#!/usr/bin/env python3
"""
CHOTTO の単一投稿を福山市サイト（fukuyama.website）へ移動する。
本文内およびアイキャッチの chotto.news メディアを福山市へ再アップロードし URL を差し替える。
成功後、CHOTTO 元投稿を force 削除する。
"""
from __future__ import annotations

import base64
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SITES = json.loads((BASE_DIR / "sites.json").read_text(encoding="utf-8"))

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


def _auth_header(user: str, app_pass: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{app_pass}".encode()).decode()


def wp_json(api_base: str, path: str, user: str, app_pass: str, method="GET", data=None):
    url = f"{api_base.rstrip('/')}/{path.lstrip('/')}"
    headers = {**BROWSER_HEADERS, "Authorization": _auth_header(user, app_pass)}
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, context=CTX, timeout=120) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}


def wp_media_bytes(api_base: str, user: str, app_pass: str, filename: str, mime: str, blob: bytes) -> dict:
    url = f"{api_base.rstrip('/')}/media"
    headers = {
        **BROWSER_HEADERS,
        "Authorization": _auth_header(user, app_pass),
        "Content-Type": mime,
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    req = urllib.request.Request(url, data=blob, method="POST", headers=headers)
    with urllib.request.urlopen(req, context=CTX, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download(url: str) -> tuple[bytes, str, str]:
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(req, context=CTX, timeout=60) as resp:
        blob = resp.read()
    path = urllib.parse.urlparse(url).path
    fn = path.rsplit("/", 1)[-1].split("?")[0] or "image.jpg"
    ext = Path(fn).suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/jpeg")
    return blob, fn, mime


def resolve_or_create_tags(fk_api: str, fk_user: str, fk_pass: str, names: list[str]) -> list[int]:
    ids: list[int] = []
    for name in names:
        name = (name or "").strip()
        if not name:
            continue
        q = urllib.parse.quote(name)
        found = wp_json(fk_api, f"tags?search={q}&per_page=20", fk_user, fk_pass)
        match = None
        for t in found if isinstance(found, list) else []:
            if t.get("name") == name:
                match = t
                break
        if match:
            ids.append(int(match["id"]))
            continue
        created = wp_json(fk_api, "tags", fk_user, fk_pass, method="POST", data={"name": name})
        if created.get("id"):
            ids.append(int(created["id"]))
    return ids


def main():
    chotto_id = int(sys.argv[1]) if len(sys.argv) > 1 else 62297

    ch = SITES["chotto"]
    fk = SITES["fukuyama"]
    ch_api = ch["api_url"]
    fk_api = fk["api_url"]
    ch_u, ch_p = ch["user"], ch["app_pass"]
    fk_u, fk_p = fk["user"], fk["app_pass"]

    post = wp_json(ch_api, f"posts/{chotto_id}?context=edit", ch_u, ch_p)
    title_raw = (post.get("title") or {}).get("raw") or ""
    content_raw = (post.get("content") or {}).get("raw") or ""
    excerpt_raw = (post.get("excerpt") or {}).get("raw") or ""
    status = post.get("status") or "future"
    date_gmt = post.get("date_gmt") or post.get("date")

    embedded = wp_json(ch_api, f"posts/{chotto_id}?_embed=1", ch_u, ch_p)
    tag_names: list[str] = []
    for block in embedded.get("_embedded", {}).get("wp:term", []):
        for t in block:
            if t.get("taxonomy") == "post_tag":
                tag_names.append(t["name"])

    fk_categories = [1, 13]

    chotto_upload_re = re.compile(r"https://chotto\.news/wp-content/uploads/[^\"'\s>]+")
    urls = list(dict.fromkeys(chotto_upload_re.findall(content_raw)))

    featured_old_url = ""
    fid = post.get("featured_media") or 0
    if fid:
        m = wp_json(ch_api, f"media/{int(fid)}", ch_u, ch_p)
        featured_old_url = m.get("source_url") or ""
        if featured_old_url and featured_old_url not in urls:
            urls.append(featured_old_url)

    old_to_new: dict[str, str] = {}
    old_to_media_id: dict[str, int] = {}
    for u in urls:
        try:
            blob, fn, mime = download(u)
        except Exception as e:
            print(f"⚠ 画像DL失敗（スキップ）: {u} ({e})", file=sys.stderr)
            continue
        up = wp_media_bytes(fk_api, fk_u, fk_p, fn, mime, blob)
        new_url = up.get("source_url") or (up.get("guid") or {}).get("raw")
        mid = int(up["id"])
        if new_url:
            old_to_new[u] = new_url
            old_to_media_id[u] = mid
            print(f"  ↑ {fn} -> media {mid}")

    new_content = content_raw
    for old, new in old_to_new.items():
        new_content = new_content.replace(old, new)

    featured_new = 0
    if featured_old_url and featured_old_url in old_to_media_id:
        featured_new = old_to_media_id[featured_old_url]
    elif old_to_media_id:
        featured_new = next(iter(old_to_media_id.values()))

    me = wp_json(fk_api, "users/me", fk_u, fk_p)
    author_id = int(me["id"])
    tag_ids = resolve_or_create_tags(fk_api, fk_u, fk_p, tag_names)

    payload = {
        "title": title_raw,
        "content": new_content,
        "excerpt": excerpt_raw,
        "status": status,
        "date": post.get("date"),
        "date_gmt": date_gmt,
        "author": author_id,
        "categories": fk_categories,
        "tags": tag_ids,
    }
    if featured_new:
        payload["featured_media"] = featured_new

    created = wp_json(fk_api, "posts", fk_u, fk_p, method="POST", data=payload)
    new_id = created.get("id")
    print(
        f"✅ 福山市サイトに作成: Post ID {new_id} "
        f"status={created.get('status')} date={created.get('date')}"
    )

    wp_json(ch_api, f"posts/{chotto_id}?force=true", ch_u, ch_p, method="DELETE")
    print(f"✅ CHOTTO 元投稿を削除しました: Post ID {chotto_id}")


if __name__ == "__main__":
    main()
