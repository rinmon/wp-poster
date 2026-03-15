#!/usr/bin/env python3
"""Post 57998の404画像をWikimedia Commonsの利用可能画像に差し替え、WordPressにアップロードして更新"""
import os
import re
import sys
import urllib.request
import ssl

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# 元の404 URL → 差し替え用Wikimedia画像（CC BY-SA等、出典表記済み）
REPLACEMENTS = [
    # 1. 阪急電車車内 朝のラッシュ時
    (
        "https://business.nikkei.com/atcl/seminar/19/00083/090400005/eye.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/7/74/Hankyu_7300_Series_7324F%2B7310F.jpg",
        "阪急7300系 通勤特急（Wikimedia Commons, HNKYU, CC BY-SA 4.0）",
    ),
    # 2. 阪急電車特急の外観と駅ホーム
    (
        "https://rail20000.jpn.org/wp/2024/09/24/privace/privace-9305.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/9/91/Hankyu-Koyo-Line.jpg",
        "阪急甲陽線6000系（Wikimedia Commons, MaedaAkihiko, CC BY-SA 4.0）",
    ),
    # 3. 阪急電車プレミアムカー車内
    (
        "https://filmscan-print-s.com/0330.1-BOU_Q-2018-001/premium-car.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/a/aa/20201227_JR_East_E235-1000_inside.jpg",
        "電車車内（Wikimedia Commons, Rsa, CC BY-SA 3.0）",
    ),
    # 4. 電車内座席占領事例
    (
        "https://j-town.net/2021/07/27324985/empty-seats.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/3/3d/On_the_Keio_Line.jpg",
        "京王線車内（Wikimedia Commons, Kichiverde, Public Domain）",
    ),
]

ASSETS_DIR = os.path.join(BASE_DIR, "assets", "hankyu_fix")
POST_ID = 57998


def download(url, path):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        with open(path, "wb") as f:
            f.write(r.read())


def main():
    os.makedirs(ASSETS_DIR, exist_ok=True)

    # api_poster を import（WP_API_URL 等が設定される）
    from api_poster import api_request, to_block_format, upload_image

    # 1. 画像をダウンロードしてWordPressにアップロード
    wp_urls = []
    for i, (old_url, new_url, caption) in enumerate(REPLACEMENTS):
        ext = ".jpg"
        local_path = os.path.join(ASSETS_DIR, f"img_{i+1}{ext}")
        print(f"⏳ ダウンロード: {os.path.basename(new_url.split('/')[-1])}...")
        try:
            download(new_url, local_path)
        except Exception as e:
            print(f"❌ ダウンロード失敗: {e}")
            sys.exit(1)
        media = upload_image(local_path)
        if not media:
            print(f"❌ アップロード失敗: {local_path}")
            sys.exit(1)
        wp_url = media.get("source_url") or media.get("guid", {}).get("rendered", "")
        wp_urls.append((old_url, wp_url, caption))

    # 2. 現在の投稿を取得
    post = api_request(f"posts/{POST_ID}?context=edit")
    if not post:
        print("❌ 投稿の取得に失敗しました")
        sys.exit(1)
    content = post.get("content", {}).get("raw", "")

    # 3. 本文内の古い画像URLをWordPressのURLに置換
    for old_url, wp_url, _caption in wp_urls:
        content = content.replace(f"src='{old_url}'", f"src='{wp_url}'")
        content = content.replace(f'src="{old_url}"', f'src="{wp_url}"')

    # 4. 更新
    res = api_request(f"posts/{POST_ID}", method="POST", data={"content": content})
    if res and res.get("id"):
        print(f"\n✅ Post {POST_ID} を更新しました。4枚の画像をWordPressメディアに差し替えました。")
    else:
        print("❌ 更新に失敗しました。", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
