#!/usr/bin/env python3
"""
X（旧Twitter）関連の取得をまとめたエントリ。

- デフォルト: 単一ツイート URL からメディア直 URL（tools/fetch_x_media_urls.py）
- --timeline: タイムラインを開き pbs.twimg.com/media の URL を列挙（Cookie 要）
- --page: 任意 X ページを開き、先頭ツイート最大10件の本文と画像 URL を表示（旧 fetch_x_data.py）

使用例:
  python3 tools/x_fetch.py "https://x.com/NASA/status/123"
  python3 tools/x_fetch.py --first "https://x.com/.../status/123"
  python3 tools/x_fetch.py --json "https://x.com/.../status/123"
  python3 tools/x_fetch.py --timeline "https://x.com/NASA" --cookies x_cookies.json
  python3 tools/x_fetch.py --page "https://x.com/elonmusk" --cookies x_cookies.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.fetch_x_media_urls import fetch_media_urls_for_status_url, parse_status_url  # noqa: E402


def _load_cookies_file(cookie_file: str) -> list[dict[str, Any]]:
    if not os.path.exists(cookie_file):
        print(f"エラー: Cookieファイル ({cookie_file}) が見つかりません。", file=sys.stderr)
        print("x_cookies_template.json を参考に、ブラウザからエクスポートして保存してください。", file=sys.stderr)
        sys.exit(1)
    with open(cookie_file, encoding="utf-8") as f:
        raw = json.load(f)
    valid: list[dict[str, Any]] = []
    for c in raw:
        vc: dict[str, Any] = {
            "name": c.get("name"),
            "value": c.get("value"),
            "domain": c.get("domain"),
            "path": c.get("path", "/"),
        }
        if c.get("expires") is not None:
            try:
                vc["expires"] = float(c["expires"])
            except (TypeError, ValueError):
                pass
        valid.append(vc)
    return valid


async def _timeline_image_urls(url: str, cookie_file: str) -> None:
    from playwright.async_api import async_playwright

    valid_cookies = _load_cookies_file(cookie_file)
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--headless=new", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            )
        )
        await context.add_cookies(valid_cookies)
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_selector('article[data-testid="tweet"]', timeout=20000)
            await page.wait_for_timeout(3000)
            images = await page.evaluate(
                """() => Array.from(document.querySelectorAll('img'))
                .map(img => img.src)
                .filter(src => src && src.includes('pbs.twimg.com/media'))"""
            )
            seen: set[str] = set()
            for src in images:
                if src not in seen:
                    seen.add(src)
                    print(src)
        except Exception as e:
            print(f"取得エラー: {e}", file=sys.stderr)
            await page.screenshot(path="x_debug_screenshot.png")
            print("デバッグ用: x_debug_screenshot.png を保存しました。", file=sys.stderr)
        finally:
            await browser.close()


async def _page_scrape_tweets(url: str, cookie_file: str) -> int:
    """先頭10ツイートの本文・画像（旧 fetch_x_data）。"""
    from playwright.async_api import async_playwright

    valid_cookies = _load_cookies_file(cookie_file)
    print(f"🚀 {url} から取得中 (headless)…", file=sys.stderr)
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--headless=new", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        await context.add_cookies(valid_cookies)
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_selector('article[data-testid="tweet"]', timeout=15000)
            await page.wait_for_timeout(3000)
            tweets = await page.query_selector_all('article[data-testid="tweet"]')
            print(f"\n取得ツイート数: {len(tweets)} 件\n" + "=" * 40)
            for index, tweet in enumerate(tweets[:10]):
                print(f"\n--- ツイート {index + 1} ---")
                text_div = await tweet.query_selector('div[data-testid="tweetText"]')
                text = await text_div.inner_text() if text_div else "（テキストなし）"
                print(f"本文:\n{text}")
                images = await tweet.query_selector_all('div[data-testid="tweetPhoto"] img')
                img_urls: list[str] = []
                for img in images:
                    src = await img.get_attribute("src")
                    if src:
                        img_urls.append(src)
                if img_urls:
                    print("画像URL:")
                    for u in img_urls:
                        print(f"  - {u}")
                print("-" * 20)
        except Exception as e:
            print(f"取得エラー: {e}", file=sys.stderr)
            await page.screenshot(path="x_debug_screenshot.png")
            print("x_debug_screenshot.png を保存しました。", file=sys.stderr)
            return 1
        finally:
            await browser.close()
            print("\n完了。", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description="X/Twitter: メディアURL取得・タイムライン・ページスクレイプ")
    p.add_argument("url", nargs="?", help="ツイート or 開く X の URL")
    p.add_argument(
        "--timeline",
        action="store_true",
        help="タイムラインを開き pbs.twimg.com の画像 URL を列挙（要 --cookies）",
    )
    p.add_argument(
        "--page",
        action="store_true",
        help="ページ先頭10ツイートの本文と画像を表示（要 --cookies）",
    )
    p.add_argument("--cookies", default="x_cookies.json", help="Playwright 用 Cookie JSON")
    p.add_argument("--include-video", action="store_true", help="status モード: 動画系も含む")
    p.add_argument("--first", action="store_true", help="status モード: 先頭1件のみ")
    p.add_argument("--json", action="store_true", help="status モード: API 生JSON（デバッグ）")
    p.add_argument("--timeout", type=float, default=25.0)
    p.add_argument("--retries", type=int, default=3)
    args = p.parse_args(argv)

    if args.page:
        if not args.url:
            p.print_help()
            return 2
        return asyncio.run(_page_scrape_tweets(args.url, args.cookies))

    if args.timeline:
        if not args.url:
            p.print_help()
            return 2
        asyncio.run(_timeline_image_urls(args.url, args.cookies))
        return 0

    if not args.url:
        p.print_help()
        return 2

    if not parse_status_url(args.url):
        print(
            "ERROR: URL がツイート（…/status/数字）形式ではありません。"
            "タイムラインなら --timeline、本文スクレイプなら --page を使ってください。",
            file=sys.stderr,
        )
        return 2

    raw_holder: dict[str, Any] = {}
    urls = fetch_media_urls_for_status_url(
        args.url,
        timeout=args.timeout,
        retries=args.retries,
        include_video=args.include_video,
        raw_json_out=raw_holder if args.json else None,
    )
    if args.json:
        if not raw_holder:
            print("ERROR: API レスポンスを取得できませんでした。", file=sys.stderr)
            return 1
        print(json.dumps(raw_holder, ensure_ascii=False, indent=2))
        return 0
    if not urls:
        print("ERROR: メディア URL を取得できませんでした。", file=sys.stderr)
        return 1
    if args.first:
        print(urls[0])
    else:
        for u in urls:
            print(u)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
