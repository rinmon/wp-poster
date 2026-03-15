#!/usr/bin/env python3
"""既存WordPress記事に画像を追加するスクリプト
画像ファイルをアップロードし、指定位置に挿入。アイキャッチも設定。
"""
import json
import base64
import urllib.request
import ssl
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WP_API = "https://chotto.news/wp-json/wp/v2"
auth = base64.b64encode(b'rinmon:Xdr6 Entp HsDz TdOZ cdSS 1QdX').decode()
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def upload_img(path):
    with open(path, 'rb') as f:
        data = f.read()
    ext = os.path.splitext(path)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    req = urllib.request.Request(
        f"{WP_API}/media",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": mime,
            "Content-Disposition": f'attachment; filename="{os.path.basename(path)}"',
            "User-Agent": "Mozilla/5.0"
        }
    )
    with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
        return json.loads(r.read().decode())

def get_post(pid):
    req = urllib.request.Request(
        f"{WP_API}/posts/{pid}?context=edit",
        headers={"Authorization": f"Basic {auth}", "User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return json.loads(r.read().decode())

def update_post(pid, content=None, featured_media=None):
    data = {}
    if content is not None:
        data["content"] = content
    if featured_media is not None:
        data["featured_media"] = featured_media
    if not data:
        return None
    req = urllib.request.Request(
        f"{WP_API}/posts/{pid}",
        data=json.dumps(data).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
    )
    with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
        return json.loads(r.read().decode())

def main():
    assets = "/Users/rinmon/.cursor/projects/Users-rinmon-Library-CloudStorage-SynologyDrive-work-0000-BLOG/assets"

    # === 57962 スカーレット錯視: 強制遠近法セクションに画像追加 ===
    print("--- Post 57962 (スカーレット錯視) ---")
    fp_path = f"{assets}/scarlett_forced_perspective.jpg"
    if os.path.isfile(fp_path):
        m = upload_img(fp_path)
        wp_url = m["source_url"]
        print(f"  Uploaded: {wp_url}")
        post = get_post(57962)
        content = post["content"]["raw"]
        insert = f'<figure class="wp-block-image size-large"><img src="{wp_url}" alt="強制遠近法の写真例"/></figure>\n\n'
        marker = "<p>## 映画と芸術における強制遠近法の歴史と技法</p>"
        if marker in content and wp_url not in content:
            content = content.replace(marker, marker + "\n\n" + insert, 1)
            update_post(57962, content=content)
            print("  Inserted forced perspective image")
    else:
        print(f"  Skip: {fp_path} not found")

    # === 57960 ソラヤ: 複数画像 + アイキャッチ ===
    print("\n--- Post 57960 (ソラヤ・マヌチェハリ) ---")
    imgs = [
        (f"{assets}/soraya_featured.jpg", "アイキャッチ・冒頭", "1986年イラン・クフパイェ村の記録"),
        (f"{assets}/soraya_iran_village.jpg", "背景セクション", "イラン農村の風景"),
        (f"{assets}/soraya_human_rights.jpg", "映画化セクション", "人権と記憶の象徴"),
    ]
    uploaded = []
    for path, _, alt in imgs:
        if os.path.isfile(path):
            m = upload_img(path)
            uploaded.append((m["source_url"], m["id"], alt))
            print(f"  Uploaded: {os.path.basename(path)} -> {m['id']}")

    if uploaded:
        post = get_post(57960)
        content = post["content"]["raw"]
        wp_url0, media_id0, alt0 = uploaded[0]

        # 冒頭に1枚目
        insert0 = f'<figure class="wp-block-image size-large"><img src="{wp_url0}" alt="{alt0}"/></figure>\n\n'
        if wp_url0 not in content:
            content = insert0 + content

        # 背景セクション（クフパイェ村の社会構造）に2枚目（57960はMarkdown形式）
        if len(uploaded) >= 2:
            wp_url1, _, alt1 = uploaded[1]
            marker1 = "クフパイェ村はイラン中央部イスファハン州に位置する典型的な農村で"
            if marker1 in content and wp_url1 not in content:
                insert1 = f'<figure class="wp-block-image size-large"><img src="{wp_url1}" alt="{alt1}"/></figure>\n\n'
                content = content.replace(marker1, insert1 + marker1, 1)

        # 映画化セクションに3枚目
        if len(uploaded) >= 3:
            wp_url2, _, alt2 = uploaded[2]
            marker2 = "サイラス・ナウラステ監督（イラン系アメリカ人）は書籍を10年温め、2008年映画化。"
            if marker2 in content and wp_url2 not in content:
                insert2 = f'<figure class="wp-block-image size-large"><img src="{wp_url2}" alt="{alt2}"/></figure>\n\n'
                content = content.replace(marker2, insert2 + marker2, 1)

        update_post(57960, content=content, featured_media=media_id0)
        print(f"  Updated post 57960: {len(uploaded)} images, featured_media={media_id0}")

    print("\nDone.")

if __name__ == "__main__":
    main()
