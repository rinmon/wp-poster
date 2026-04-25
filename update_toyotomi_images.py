#!/usr/bin/env python3
"""
豊臣兄弟トークライブ記事の写真を新しい5枚＋QRコードに差し替える。
使用例: python update_toyotomi_images.py --site takashima --post 3124
"""
from __future__ import annotations

import os
import re
import sys

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
    print("Usage: python update_toyotomi_images.py --site takashima --post 3124", file=sys.stderr)
    sys.exit(1)


def remove_existing_images(content: str) -> str:
    content = re.sub(
        r"<!-- wp:image[^>]*-->.*?<!-- /wp:image -->\s*",
        "",
        content,
        flags=re.DOTALL,
    )
    content = re.sub(
        r"<figure[^>]*class=[\"']wp-block-image[^\"']*[\"'][^>]*>.*?</figure>\s*",
        "",
        content,
        flags=re.DOTALL,
    )
    return content


def insert_after_heading(content: str, heading_text: str, img_block: str) -> str:
    for tag in ("h2", "h3"):
        pattern = f"(<{tag}[^>]*>\\s*)" + re.escape(heading_text) + f"(\\s*</{tag}>)"
        if re.search(pattern, content):
            return re.sub(pattern, r"\1" + heading_text + r"\2\n\n" + img_block, content, count=1)
    for tag in ("h2", "h3"):
        pattern = f"({re.escape(heading_text)})(\\s*</{tag}>\\s*<!-- /wp:heading -->)"
        if re.search(pattern, content):
            return re.sub(pattern, r"\1\2\n\n" + img_block, content, count=1)
    for prefix in ("## ", "### "):
        if prefix + heading_text in content:
            return content.replace(prefix + heading_text, prefix + heading_text + "\n\n" + img_block, 1)
    return content


def main() -> None:
    wp = from_sites_file(BASE_DIR, _site_name)
    assets_dir = os.path.join(BASE_DIR, "assets")
    new_images = [
        ("大河ドラマ「豊臣兄弟！」キャラクター相関図", "20251219_163854_p_o_33756555-20818603-921d-4256-b08d-8d63c9ebfe04.png"),
        ("NHK大河ドラマ・ガイド 豊臣兄弟！ 前編 表紙", "20260123-01016661-lmaga-001-1-view-b811d7a5-eb44-43af-b96d-96ed1f12afbd.png"),
        ("豊臣兄弟！キャスト（手鞠と鎧姿）", "18219-1215-8edbc36afed6e0ab2de6d59b101c2717-1920x1280-46048185-a2c8-4b00-9a8f-dfc16e2f7d87.png"),
        ("豊臣兄弟！甲冑姿のキャスト", "20260110s10041000292000p_view-91bb3fa1-c61f-49ad-9096-5cf3c6837266.png"),
        ("大河ドラマ 豊臣兄弟！プロモーションポスター（豊臣秀長）", "0c920f3ac1a44e9eb1cdf6651fc9bf7e_52_11-d7980e38-96f5-4634-baca-88db27c84f13.png"),
    ]
    qr_path = os.path.join(assets_dir, "QRmousikomi-4740150b-4adc-42bd-a13c-79db98e20d9c.png")

    uploaded: list[tuple[str, str, int]] = []
    for alt, fname in new_images:
        path = os.path.join(assets_dir, fname)
        if not os.path.exists(path):
            print(f"⚠ 画像が見つかりません: {path}", file=sys.stderr)
            continue
        print(f"アップロード中: {alt[:30]}...")
        res = wp.upload_file(path)
        if res:
            uploaded.append((alt, res["source_url"], res["id"]))
            print("  OK")
        else:
            print("  失敗")

    if not uploaded:
        print("アップロードできた画像がありません", file=sys.stderr)
        sys.exit(1)

    if os.path.exists(qr_path):
        print("QRコードをアップロード中...")
        res = wp.upload_file(qr_path)
        if res:
            uploaded.append(("応募用QRコード（高島市HP申込フォーム）", res["source_url"], res["id"]))
            print("  OK")

    post = wp.get_post(_post_id)
    if not post:
        print(f"投稿 {_post_id} を取得できません", file=sys.stderr)
        sys.exit(1)

    content = post.get("content", {}).get("raw", "")
    if not content:
        content = post.get("content", {}).get("rendered", "")

    content = remove_existing_images(content)
    content = re.sub(r"\n{3,}", "\n\n", content)

    def img_html(url: str, alt: str) -> str:
        return f'<!-- wp:image {{"sizeSlug":"large"}} -->\n<figure class="wp-block-image size-large"><img src="{url}" alt="{alt}"/></figure>\n<!-- /wp:image -->'

    first = img_html(uploaded[0][1], uploaded[0][0])
    if "<!-- wp:paragraph -->" in content:
        content = content.replace("<!-- wp:paragraph -->", first + "\n\n<!-- wp:paragraph -->", 1)
    elif "<p>" in content:
        content = content.replace("<p>", first + "\n\n<p>", 1)
    else:
        content = first + "\n\n" + content

    if len(uploaded) > 1:
        content = insert_after_heading(
            content, "ドラマ「豊臣兄弟！」の核心と制作背景", img_html(uploaded[1][1], uploaded[1][0])
        )
    if len(uploaded) > 2:
        content = insert_after_heading(
            content, "松下洸平演じる徳川家康の新解釈", img_html(uploaded[2][1], uploaded[2][0])
        )
    if len(uploaded) > 3:
        content = insert_after_heading(
            content, "高島トークライブの全貌と参加方法", img_html(uploaded[3][1], uploaded[3][0])
        )

    fifth = img_html(uploaded[4][1], uploaded[4][0]) if len(uploaded) > 4 else ""
    qr = img_html(uploaded[5][1], uploaded[5][0]) if len(uploaded) > 5 else ""
    qr_note = (
        "<!-- wp:paragraph -->\n"
        "<p><strong>上記QRコードから高島市ホームページの応募フォームにアクセスできます。"
        "スマートフォンで読み取ってお申し込みください。</strong></p>\n"
        "<!-- /wp:paragraph -->"
    )
    insert_block = (fifth + "\n\n" if fifth else "") + (qr + "\n\n" if qr else "") + (qr_note + "\n\n" if qr else "")

    qr_anchor = "申込フローと注意点"
    content = re.sub(
        r"<h3([^>]*)>.*?" + re.escape(qr_anchor) + r"\s*</h3>",
        r"<h3\1>" + qr_anchor + r"</h3>",
        content,
        count=1,
        flags=re.DOTALL,
    )
    m = re.search(r"<h3[^>]*>\s*" + re.escape(qr_anchor) + r"\s*</h3>", content)
    if m:
        content = content[: m.start()] + insert_block.rstrip() + "\n\n" + content[m.start() :]
    elif "### " + qr_anchor in content:
        content = content.replace("### " + qr_anchor, insert_block.rstrip() + "\n\n### " + qr_anchor, 1)

    featured_id = uploaded[0][2]
    result = wp.update_post(_post_id, {"content": content, "featured_media": featured_id})
    if result:
        print(f"\n✅ 投稿 {_post_id} を更新しました。画像 {len(uploaded)} 枚に差し替え。")
    else:
        print("更新に失敗しました", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
