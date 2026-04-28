#!/usr/bin/env python3
"""
予約投稿（future）の重複を検出・一覧表示するスクリプト

例: python3 list_duplicate_scheduled.py --site takashima
（--site 省略時は api_poster と同様 CHOTTO 既定）
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# api_poster は import 時に sys.argv の --site だけを見る
_orig_argv = sys.argv[:]
_prog = _orig_argv[0] if _orig_argv else "list_duplicate_scheduled.py"
_site_for_import = None
_i = 1
while _i < len(_orig_argv):
    if _orig_argv[_i] == "--site" and _i + 1 < len(_orig_argv):
        _site_for_import = _orig_argv[_i + 1]
        break
    _i += 1
sys.argv = [_prog, "--site", _site_for_import] if _site_for_import else [_prog]

from api_poster import WP_API_URL, _normalize_title_for_duplicate, _wp_title_plain, api_request

sys.argv = _orig_argv

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

    # 正規化タイトルでグループ化（api_poster / check_article_duplicates と同じ基準）
    by_key = {}
    for p in posts:
        k = _normalize_title_for_duplicate(_wp_title_plain(p))
        if not k:
            k = f"__empty_{p.get('id', '')}"
        if k not in by_key:
            by_key[k] = []
        by_key[k].append(p)

    # 重複を表示
    duplicates = {t: plist for t, plist in by_key.items() if len(plist) > 1}
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
