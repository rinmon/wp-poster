#!/usr/bin/env python3
"""
予約投稿（future）の重複を検出・一覧表示するスクリプト
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# api_poster の設定を読み込む（sites.json, .env）
from api_poster import api_request, WP_API_URL

def get_all_future_posts():
    """予約済み投稿を全件取得"""
    all_posts = []
    page = 1
    while True:
        posts = api_request(
            f"posts?status=future&per_page=100&page={page}&_fields=id,title,date,status"
        )
        if not posts:
            break
        all_posts.extend(posts)
        if len(posts) < 100:
            break
        page += 1
    return all_posts


def main():
    print("=" * 60)
    print("📋 予約投稿の重複チェック")
    print("=" * 60)
    print(f"サイト: {WP_API_URL}\n")

    posts = get_all_future_posts()
    if not posts:
        print("予約投稿はありません。")
        return

    # タイトルでグループ化
    by_title = {}
    for p in posts:
        title_obj = p.get("title") or {}
        title = title_obj.get("raw") or title_obj.get("rendered", "").replace("&#8211;", "–")
        if title not in by_title:
            by_title[title] = []
        by_title[title].append(p)

    # 重複を表示
    duplicates = {t: plist for t, plist in by_title.items() if len(plist) > 1}
    if not duplicates:
        print("✅ 重複は見つかりませんでした。")
        print(f"\n予約投稿数: {len(posts)} 件")
        return

    print(f"⚠️  重複が {len(duplicates)} 件見つかりました:\n")
    for title, plist in duplicates.items():
        print(f"【{title[:50]}{'...' if len(title) > 50 else ''}】")
        for i, p in enumerate(sorted(plist, key=lambda x: x.get("date", ""))):
            pid = p.get("id")
            date = p.get("date", "")[:19].replace("T", " ")
            mark = "★ 残す" if i == 0 else "  → 削除候補"
            print(f"  ID:{pid}  {date}  {mark}")
        print()

    print("=" * 60)
    print("💡 重複を削除するには:")
    print("  delete_post.py を編集し、削除候補の Post ID を指定して実行")
    print("  例: delete_item('posts', 12345)")
    print("=" * 60)


if __name__ == "__main__":
    main()
