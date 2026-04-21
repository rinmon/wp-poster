#!/usr/bin/env python3
"""
全サイトの予約投稿を 6:00〜23:00・1時間刻み（正時）の枠に沿って再調整するスクリプト。
api_poster.py の予約枠と整合させる。
"""
import json
import base64
import urllib.request
import ssl
import os
from datetime import datetime

from schedule_slots import iter_schedule_slots_from

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SITES_PATH = os.path.join(BASE_DIR, "sites.json")

MAX_PER_DAY = 18  # 1日最大18枠（6:00〜23:00・1時間刻み・正時、api_poster と同じ）


def iter_slots_from_now(now):
    """now より後の予約枠を時系列で yield（datetime）"""
    return iter_schedule_slots_from(now)


BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def api_request(api_url, user, app_pass, endpoint, method="GET", data=None):
    url = f"{api_url.rstrip('/')}/{endpoint.lstrip('/')}"
    req_headers = BROWSER_HEADERS.copy()
    req_headers["Authorization"] = "Basic " + base64.b64encode(
        f"{user}:{app_pass}".encode()
    ).decode()
    if data is not None:
        import json as _json
        body = _json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, method=method, headers=req_headers)
    else:
        req = urllib.request.Request(url, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  ❌ API Error: {e}")
        return None


def get_future_posts(api_url, user, app_pass):
    all_posts = []
    page = 1
    while True:
        posts = api_request(
            api_url, user, app_pass,
            f"posts?status=future&per_page=100&page={page}&order=asc&_fields=id,title,date"
        )
        if not posts:
            break
        all_posts.extend(posts)
        if len(posts) < 100:
            break
        page += 1
    return all_posts


def update_post_date(api_url, user, app_pass, post_id, new_date_str):
    return api_request(
        api_url, user, app_pass,
        f"posts/{post_id}",
        method="POST",
        data={"date": new_date_str}
    )


def reschedule_site(site_name, api_url, user, app_pass, dry_run=True):
    print(f"\n{'='*50}")
    print(f"📌 {site_name}")
    print("=" * 50)

    posts = get_future_posts(api_url, user, app_pass)
    if not posts:
        print("  予約投稿なし")
        return 0

    now = datetime.now()
    posts_sorted = sorted(posts, key=lambda x: x["date"])

    # 本日から全件を再配置。枠は 6:00〜23:00・1時間刻み（正時）、1 日最大 18 件。
    new_assignments = []
    slot_iter = iter_slots_from_now(now)

    for p in posts_sorted:
        new_dt = next(slot_iter)
        new_date_str = new_dt.strftime("%Y-%m-%dT%H:%M:%S")
        if new_date_str != p["date"][:19]:
            new_assignments.append((p["id"], new_date_str, p.get("title")))

    if not new_assignments:
        print(f"  変更不要（{len(posts)}件）")
        return 0

    print(f"  予約数: {len(posts)}件")
    print(f"  再配置対象: {len(new_assignments)}件（本日枠から順に割当）")
    if dry_run:
        print("\n  [DRY RUN] 以下の変更を適用します:")
        for pid, new_dt, title in new_assignments[:10]:
            t = (title or {}).get("raw", str(title))[:40] if isinstance(title, dict) else str(title)[:40]
            print(f"    Post {pid}: {new_dt[:16].replace('T',' ')} - {t}...")
        if len(new_assignments) > 10:
            print(f"    ... 他 {len(new_assignments)-10} 件")
        return len(new_assignments)

    updated = 0
    for pid, new_date_str, _ in new_assignments:
        res = update_post_date(api_url, user, app_pass, pid, new_date_str)
        if res and res.get("date"):
            updated += 1
            print(f"  ✓ Post {pid}: {new_date_str[:16].replace('T',' ')}")
        else:
            print(f"  ✗ Post {pid}: 更新失敗")
    print(f"  → {updated}件を更新しました")
    return updated


def main():
    import sys
    dry_run = "--apply" not in sys.argv
    if dry_run:
        print("※ --apply を付けると実際に更新します（省略時はドライラン）")

    with open(SITES_PATH, "r", encoding="utf-8") as f:
        sites = json.load(f)

    total = 0
    for key in ("chotto", "takashima", "fukuyama"):
        if key not in sites or key.startswith("_"):
            continue
        sc = sites[key]
        total += reschedule_site(
            key,
            sc["api_url"],
            sc["user"],
            sc["app_pass"],
            dry_run=dry_run,
        )

    print("\n" + "=" * 50)
    if dry_run:
        print("💡 実際に適用するには: python reschedule_posts.py --apply")
    else:
        print("✅ 再調整完了")
    print("=" * 50)


if __name__ == "__main__":
    main()
