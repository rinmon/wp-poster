#!/usr/bin/env python3
"""Post 58017（SwitchBot記事）に画像を追加して更新"""
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

ASSETS = "/Users/rinmon/.cursor/projects/Users-rinmon-Library-CloudStorage-SynologyDrive-work-0000-BLOG/assets"

# (画像パス, alt, このテキストを含むブロックの直後に挿入)
IMAGES = [
    (
        os.path.join(ASSETS, "IMG_4792___-623df297-b142-41f6-a6c3-6865e4b558b5.png"),
        "Lock Ultraと顔認証パッドProのパッケージ。木目調化粧シートとNFCカード付属",
        "木目調化粧シート3種",
    ),
    (
        os.path.join(ASSETS, "IMG_4832___-247f6fb0-3650-416c-80ed-434c1ba08a54.png"),
        "SwitchBot Lock Ultra ドア内側設置例。楕円形ボディとオレンジのLEDインジケーター",
        "内側クイックキーは肘や指先でのプッシュ操作を想定したデザインで",
    ),
    (
        os.path.join(ASSETS, "IMG_4833___-55447028-fea1-4606-abd7-719eccf8e120.png"),
        "キーパッドと従来の鍵穴が共存。後付けで工事不要の導入例",
        "IP65防水防塵仕様で屋外対応",
    ),
]

POST_ID = 58017


def insert_after_block(content, marker, fig_html):
    """markerを含むブロック（<!-- /wp:xxx -->まで）の直後に画像を挿入"""
    idx = content.find(marker)
    if idx < 0:
        return content, False
    # そのブロックの終わり（<!-- /wp: の次）を探す
    block_end = content.find("<!-- /wp:", idx)
    if block_end < 0:
        insert_pos = idx + len(marker)
    else:
        # <!-- /wp:paragraph --> の直後
        line_end = content.find("\n", block_end)
        insert_pos = line_end + 1 if line_end >= 0 else block_end + 20
    new_content = content[:insert_pos] + "\n\n" + fig_html + "\n\n" + content[insert_pos:]
    return new_content, True


def main():
    from api_poster import api_request, upload_image

    uploaded = []
    first_media_id = None
    for path, alt, marker in IMAGES:
        if not os.path.isfile(path):
            print(f"❌ ファイルが見つかりません: {path}")
            sys.exit(1)
        media = upload_image(path)
        if not media:
            print(f"❌ アップロード失敗: {path}")
            sys.exit(1)
        wp_url = media.get("source_url", "")
        if first_media_id is None:
            first_media_id = media.get("id")
        uploaded.append((alt, wp_url, marker))

    post = api_request(f"posts/{POST_ID}?context=edit")
    if not post:
        print("❌ 投稿の取得に失敗しました")
        sys.exit(1)
    content = post.get("content", {}).get("raw", "")

    # 画像ブロック形式（Gutenberg）
    for alt, wp_url, marker in uploaded:
        fig = f"<!-- wp:image {{\"sizeSlug\":\"large\"}} -->\n<figure class=\"wp-block-image size-large\"><img src=\"{wp_url}\" alt=\"{alt}\"/></figure>\n<!-- /wp:image -->"
        content, ok = insert_after_block(content, marker, fig)
        if not ok:
            print(f"⚠ マーカー「{marker}」が見つかりません")

    data = {"content": content}
    if first_media_id:
        data["featured_media"] = first_media_id
    res = api_request(f"posts/{POST_ID}", method="POST", data=data)
    if res and res.get("id"):
        print(f"\n✅ Post {POST_ID} に3枚の画像を追加しました。")
    else:
        print("❌ 更新に失敗しました。", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
