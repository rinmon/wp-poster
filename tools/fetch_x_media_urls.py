#!/usr/bin/env python3
"""
X（Twitter）投稿 URL からメディア直 URL（pbs.twimg.com 等）を取得する。

api_poster.py は投稿時に urllib で画像を取得するため、ドラフト作成段階で
**メディアの HTTPS 直リンク**を用意する必要がある。FixTweet / vxTwitter の
公開 API を複数段で試し、Accept ヘッダ・リトライ・フォールバックで安定化する。

使い方:
  python3 tools/fetch_x_media_urls.py "https://x.com/NASA/status/2046686222379016663"
  python3 tools/fetch_x_media_urls.py --first "https://x.com/..."
  python3 tools/fetch_x_media_urls.py --json "https://x.com/..."   # 生 JSON（デバッグ）
  python3 tools/fetch_x_media_urls.py --include-video "https://x.com/..."  # 動画URLも列挙

Python から:
  from tools.fetch_x_media_urls import fetch_media_urls_for_status_url
  urls = fetch_media_urls_for_status_url("https://x.com/...")
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

STATUS_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.|mobile\.)?(?:twitter\.com|x\.com)/([^/]+)/status/(\d+)",
    re.I,
)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


def parse_status_url(url: str) -> tuple[str, str] | None:
    """Returns (username, numeric_status_id) or None."""
    m = STATUS_URL_RE.search(url.strip())
    if not m:
        return None
    return m.group(1), m.group(2)


def _http_get_json(api_url: str, timeout: float) -> dict[str, Any] | None:
    req = urllib.request.Request(api_url, headers=BROWSER_HEADERS, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return None
    if not raw.strip().startswith(b"{"):
        return None
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None


def _urls_from_fxtwitter_v2_status(status: dict[str, Any], *, include_video: bool) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    media = status.get("media")
    if not isinstance(media, dict):
        return out

    def add(u: str | None) -> None:
        if u and u.startswith("http") and u not in seen:
            seen.add(u)
            out.append(u)

    for photo in media.get("photos") or []:
        if isinstance(photo, dict):
            add(photo.get("url"))
    for item in media.get("all") or []:
        if not isinstance(item, dict):
            continue
        t = item.get("type")
        if t in ("photo", "gif") and item.get("url"):
            add(item["url"])
        elif include_video and t in ("video",) and item.get("url"):
            add(item.get("thumbnail_url") or item.get("url"))
            for fmt in item.get("formats") or []:
                if isinstance(fmt, dict) and fmt.get("url"):
                    add(fmt["url"])
    if include_video:
        for vid in media.get("videos") or []:
            if not isinstance(vid, dict):
                continue
            add(vid.get("thumbnail_url"))
            add(vid.get("url"))
            for fmt in vid.get("formats") or []:
                if isinstance(fmt, dict) and fmt.get("url"):
                    add(fmt["url"])
    for mos in (media.get("mosaic"),):
        if isinstance(mos, dict) and mos.get("url"):
            add(mos["url"])
    return out


def _urls_from_vxtwitter(data: dict[str, Any], *, include_video: bool) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def add(u: str | None) -> None:
        if u and u.startswith("http") and u not in seen:
            seen.add(u)
            out.append(u)

    for u in data.get("mediaURLs") or []:
        add(u)
    for ext in data.get("media_extended") or []:
        if not isinstance(ext, dict):
            continue
        t = (ext.get("type") or "").lower()
        if t == "video" and not include_video:
            continue
        add(ext.get("url") or ext.get("thumbnail_url"))
    qrt = data.get("qrt")
    if isinstance(qrt, dict):
        for u in qrt.get("mediaURLs") or []:
            add(u)
    return out


def _urls_from_fxtwitter_v1_legacy(data: dict[str, Any], *, include_video: bool) -> list[str]:
    """Legacy GET /user/status/id shape (tweet at top level)."""
    tweet = data.get("tweet")
    if not isinstance(tweet, dict):
        return []
    out: list[str] = []
    seen: set[str] = set()

    def add(u: str | None) -> None:
        if u and u.startswith("http") and u not in seen:
            seen.add(u)
            out.append(u)

    for u in tweet.get("mediaURLs") or []:
        add(u)
    for ext in tweet.get("media_extended") or []:
        if not isinstance(ext, dict):
            continue
        t = (ext.get("type") or "").lower()
        if t == "video" and not include_video:
            continue
        add(ext.get("url") or ext.get("thumbnail_url"))
    return out


def fetch_media_urls_for_status_url(
    page_url: str,
    *,
    timeout: float = 25.0,
    retries: int = 3,
    include_video: bool = False,
    raw_json_out: dict[str, Any] | None = None,
) -> list[str]:
    """
    ステータスページ URL からメディア HTTPS URL のリストを返す（重複除去順序維持）。
    raw_json_out に dict を渡すと、最初に成功した API の JSON を格納する（デバッグ用）。
    """
    parsed = parse_status_url(page_url)
    if not parsed:
        return []
    username, status_id = parsed

    backoff = 1.0
    for attempt in range(retries):
        # 1) FxTwitter API v2（ステータス ID のみで可）
        v2_url = f"https://api.fxtwitter.com/2/status/{status_id}"
        data = _http_get_json(v2_url, timeout)
        if data and data.get("code") == 200:
            status = data.get("status")
            if isinstance(status, dict):
                urls = _urls_from_fxtwitter_v2_status(status, include_video=include_video)
                if urls:
                    if raw_json_out is not None:
                        raw_json_out.clear()
                        raw_json_out.update(data)
                    return urls
                # メディアなしの成功: 他 API で補完しない（同一内容のため）
                if raw_json_out is not None:
                    raw_json_out.clear()
                    raw_json_out.update(data)
                return []

        # 2) vxTwitter（Accept: application/json が必須な場合がある）
        vx_url = f"https://api.vxtwitter.com/{username}/status/{status_id}"
        data = _http_get_json(vx_url, timeout)
        if data and ("tweetID" in data or "text" in data):
            urls = _urls_from_vxtwitter(data, include_video=include_video)
            if urls:
                if raw_json_out is not None:
                    raw_json_out.clear()
                    raw_json_out.update(data)
                return urls

        # 3) FxTwitter legacy v1
        leg_url = f"https://api.fxtwitter.com/{username}/status/{status_id}"
        data = _http_get_json(leg_url, timeout)
        if data and data.get("code") == 200 and isinstance(data.get("tweet"), dict):
            urls = _urls_from_fxtwitter_v1_legacy(data, include_video=include_video)
            if urls:
                if raw_json_out is not None:
                    raw_json_out.clear()
                    raw_json_out.update(data)
                return urls

        if attempt < retries - 1:
            time.sleep(backoff)
            backoff = min(backoff * 2, 8.0)

    return []


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch X/Twitter status media direct URLs (pbs.twimg.com, etc.).")
    p.add_argument("url", help="Tweet URL (x.com or twitter.com .../status/ID)")
    p.add_argument("--first", action="store_true", help="Print only the first URL (for shell scripts)")
    p.add_argument("--json", action="store_true", help="Print raw JSON from the first successful API response")
    p.add_argument("--include-video", action="store_true", help="Include video thumbnails / video format URLs")
    p.add_argument("--timeout", type=float, default=25.0, help="HTTP timeout seconds (default: 25)")
    p.add_argument("--retries", type=int, default=3, help="Retry count per API round (default: 3)")
    args = p.parse_args()

    if not parse_status_url(args.url):
        print("ERROR: Not a recognized X/Twitter status URL.", file=sys.stderr)
        return 2

    raw_holder: dict[str, Any] = {}
    urls = fetch_media_urls_for_status_url(
        args.url,
        timeout=args.timeout,
        retries=args.retries,
        include_video=args.include_video,
        raw_json_out=raw_holder,
    )

    if args.json:
        if not raw_holder:
            print("ERROR: No successful API response.", file=sys.stderr)
            return 1
        print(json.dumps(raw_holder, ensure_ascii=False, indent=2))
        return 0

    if not urls:
        print("ERROR: No media URLs found (text-only tweet, deleted/private, or APIs unavailable).", file=sys.stderr)
        return 1

    if args.first:
        print(urls[0])
    else:
        for u in urls:
            print(u)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
