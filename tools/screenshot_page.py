#!/usr/bin/env python3
"""
任意URLのスクリーンショット（Playwright sync）。ツイート1件の切り出しまたはページ／フルページ。

例:
  python3 tools/screenshot_page.py -o drafts/tweet.jpg --tweet "https://x.com/user/status/123"
  python3 tools/screenshot_page.py -o drafts/page.jpg --full-page "https://example.com/path"
"""
from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright


def main() -> None:
    ap = argparse.ArgumentParser(description="Playwright で URL を画像化")
    ap.add_argument("url", help="開く URL")
    ap.add_argument("-o", "--output", required=True, help="保存先（.png / .jpg）")
    ap.add_argument(
        "--tweet",
        action="store_true",
        help="先頭のツイート article のみ切り出し（x.com 等。見つからなければビューポート全体）",
    )
    ap.add_argument("--full-page", action="store_true", help="ツイートモードでないとき、全ページ高さ")
    ap.add_argument("--wait-ms", type=int, default=3000, help="描画待ち（ミリ秒）")
    ap.add_argument("--width", type=int, default=1200)
    ap.add_argument("--height", type=int, default=1600)
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        page.goto(args.url, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(args.wait_ms)
        if args.tweet:
            page.add_style_tag(
                content="div[data-testid='BottomBar'] { display: none !important; }"
            )
            loc = page.locator('article[data-testid="tweet"]')
            if loc.count() > 0:
                loc.first.screenshot(path=args.output)
            else:
                page.screenshot(path=args.output, full_page=args.full_page)
        else:
            page.screenshot(path=args.output, full_page=args.full_page)
        browser.close()
    print(args.output, file=sys.stderr)


if __name__ == "__main__":
    main()
