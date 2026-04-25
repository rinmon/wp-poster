#!/usr/bin/env python3
"""
既存WordPress投稿に画像を追加するスクリプト（高島・豊臣トークライブ向け初期投入用サンプル）。
使用例: python update_post_images.py --site takashima --post 3124
"""
from __future__ import annotations

import os
import ssl
import sys
import tempfile
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from tools.wp_client import from_sites_file  # noqa: E402

_site_name = "takashima"
_post_id = None
for i, arg in enumerate(sys.argv[1:], 1):
    if arg == "--site" and i + 1 <= len(sys.argv) - 1:
        _site_name = sys.argv[i + 1]
    elif arg == "--post" and i + 1 <= len(sys.argv) - 1:
        _post_id = int(sys.argv[i + 1])

if not _post_id:
    print("Usage: python update_post_images.py --site takashima --post 3124", file=sys.stderr)
    sys.exit(1)

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def main() -> None:
    wp = from_sites_file(BASE_DIR, _site_name)
    qr_path = os.path.join(BASE_DIR, "assets", "QRmousikomi-4740150b-4adc-42bd-a13c-79db98e20d9c.png")
    if not os.path.exists(qr_path):
        print(f"QRコードが見つかりません: {qr_path}", file=sys.stderr)
        sys.exit(1)

    image_urls = [
        ("https://upload.wikimedia.org/wikipedia/commons/a/a3/Toyotomi_Hideyoshi.jpg", "豊臣秀吉像"),
        ("https://upload.wikimedia.org/wikipedia/commons/1/11/Tokugawa_Ieyasu2.JPG", "徳川家康像"),
        ("https://upload.wikimedia.org/wikipedia/commons/b/bf/Symbol_of_Shiga_prefecture.png", "滋賀県と琵琶湖"),
    ]

    uploaded: list[tuple[str, str, int]] = []
    print("QRコードをアップロード中...")
    res = wp.upload_file(qr_path)
    if res:
        uploaded.append(("応募用QRコード（高島市HP申込フォーム）", res["source_url"], res["id"]))
        print(f"  OK: {res['source_url']}")

    for url, alt in image_urls:
        try:
            req = urllib.request.Request(url, headers=BROWSER_HEADERS)
            with urllib.request.urlopen(req, timeout=20, context=_ctx) as resp:
                data = resp.read()
            ext = ".jpg" if "jpg" in url.lower() else ".png"
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tf:
                tf.write(data)
                tmp_path = tf.name
            res = wp.upload_file(tmp_path)
            os.unlink(tmp_path)
            if res:
                uploaded.append((alt, res["source_url"], res["id"]))
                print(f"  OK: {alt}")
        except OSError as e:
            print(f"  失敗: {alt} - {e}", file=sys.stderr)

    if not uploaded:
        print("アップロードできた画像がありません", file=sys.stderr)
        sys.exit(1)

    post = wp.get_post(_post_id)
    if not post:
        print(f"投稿 {_post_id} を取得できません", file=sys.stderr)
        sys.exit(1)

    content = post.get("content", {}).get("raw", "")
    if not content:
        content = post.get("content", {}).get("rendered", "")

    def img_block(url: str, alt: str) -> str:
        return (
            f'<!-- wp:image {{"sizeSlug":"large"}} -->\n'
            f'<figure class="wp-block-image size-large"><img src="{url}" alt="{alt}"/></figure>\n'
            f"<!-- /wp:image -->"
        )

    first_img = img_block(uploaded[1][1], uploaded[1][0])
    if not (content.strip().startswith("<!-- wp:image") or content.strip().startswith("<figure")):
        if "<!-- wp:paragraph -->" in content:
            content = content.replace("<!-- wp:paragraph -->", first_img + "\n\n<!-- wp:paragraph -->", 1)
        elif "<p>" in content:
            content = content.replace("<p>", first_img + "\n\n<p>", 1)
        else:
            content = first_img + "\n\n" + content

    second = img_block(uploaded[2][1], uploaded[2][0]) if len(uploaded) > 2 else ""
    if second and "高島トークライブの全貌と参加方法" in content:
        content = content.replace("高島トークライブの全貌と参加方法", second + "\n\n高島トークライブの全貌と参加方法", 1)

    third = img_block(uploaded[3][1], uploaded[3][0]) if len(uploaded) > 3 else ""
    qr = img_block(uploaded[0][1], uploaded[0][0])
    qr_note = (
        "<!-- wp:paragraph -->\n"
        "<p><strong>上記QRコードから高島市ホームページの応募フォームにアクセスできます。"
        "スマートフォンで読み取ってお申し込みください。</strong></p>\n"
        "<!-- /wp:paragraph -->"
    )
    insert = (third + "\n\n" if third else "") + qr + "\n\n" + qr_note + "\n\n"
    if "申込フローと注意点" in content:
        content = content.replace("申込フローと注意点", insert + "申込フローと注意点", 1)

    featured_id = uploaded[1][2]
    result = wp.update_post(_post_id, {"content": content, "featured_media": featured_id})
    if result:
        print(f"\n✅ 投稿 {_post_id} を更新しました。画像 {len(uploaded)} 枚を追加。")
    else:
        print("更新に失敗しました", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
