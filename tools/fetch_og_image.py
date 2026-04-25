#!/usr/bin/env python3
"""
公式・報道ページの og:image / twitter:image を取得する補助ツール。

背景: Cursor / MCP の HTTP fetch はデフォルトUAで 403/401 になり、HTML が取れず
公式画像URLに辿り着けないことがある。アイキャッチはブラウザ相当の User-Agent で
再試行するのが定石。

使い方:
  python3 tools/fetch_og_image.py "https://www.whitehouse.gov/releases/2026/04/..."
  python3 tools/fetch_og_image.py --list-images "https://..."   # img の src を列挙（デバッグ用）

IMAGE_BLOCK の URL: に貼り付ける前に、返った URL をブラウザまたは curl -I で確認すること。
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import urllib.request

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def fetch_html(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_og_images(page: str) -> list[str]:
    out: list[str] = []
    for prop in ("og:image:secure_url", "og:image", "twitter:image"):
        for m in re.finditer(
            rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']',
            page,
            re.I,
        ):
            out.append(html.unescape(m.group(1).strip()))
        for m in re.finditer(
            rf'<meta[^>]+name=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']',
            page,
            re.I,
        ):
            out.append(html.unescape(m.group(1).strip()))
    # 重複除去（順序維持）
    seen: set[str] = set()
    uniq: list[str] = []
    for u in out:
        if u and u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def list_img_srcs(page: str, limit: int = 40) -> list[str]:
    urls: list[str] = []
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', page, re.I):
        urls.append(html.unescape(m.group(1).strip()))
        if len(urls) >= limit:
            break
    return urls


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch og:image from a page (browser-like UA).")
    p.add_argument("url", help="Page URL (e.g. White House release)")
    p.add_argument(
        "--list-images",
        action="store_true",
        help="List first <img src=...> URLs (for picking a specific official asset)",
    )
    args = p.parse_args()
    try:
        body = fetch_html(args.url)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if args.list_images:
        for u in list_img_srcs(body):
            print(u)
        return 0
    imgs = extract_og_images(body)
    if not imgs:
        print("No og:image / twitter:image found. Try: --list-images", file=sys.stderr)
        return 2
    for u in imgs:
        print(u)
    if any("Social-Share" in u or "WH47-Social" in u for u in imgs):
        print(
            "# 注意: 上の1枚目はサイト共通のOGPカードの可能性があります。",
            "公式肖像・会場写真を使う場合は: --list-images で本文埋め込みの wp-content URL を選んでください。",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
