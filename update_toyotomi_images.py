#!/usr/bin/env python3
"""
豊臣兄弟トークライブ記事（Post 3124）の写真を新しい5枚＋QRコードに差し替える。
使用例: python update_toyotomi_images.py --site takashima --post 3124
"""
import json
import base64
import urllib.request
import ssl
import sys
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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

_sites_path = os.path.join(BASE_DIR, "sites.json")
with open(_sites_path, "r", encoding="utf-8") as f:
    _sites = json.load(f)
_resolved = _sites.get("_aliases", {}).get(_site_name, _site_name)
_sc = _sites[_resolved]
WP_API_URL = _sc["api_url"]
WP_USER = _sc["user"]
WP_APP_PASS = _sc["app_pass"]

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def api_request(endpoint, method="GET", data=None, headers=None):
    url = f"{WP_API_URL}/{endpoint}"
    req_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        "Authorization": f"Basic {base64.b64encode(f'{WP_USER}:{WP_APP_PASS}'.encode()).decode()}"
    }
    encoded_data = None
    if data is not None:
        if isinstance(data, dict):
            encoded_data = json.dumps(data).encode('utf-8')
            req_headers["Content-Type"] = "application/json"
        else:
            encoded_data = data
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=encoded_data, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as response:
            res_body = response.read().decode('utf-8')
            return json.loads(res_body) if res_body else None
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return None

def upload_image(img_path):
    ext = os.path.splitext(img_path)[1].lower()
    mime_map = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/jpeg")
    with open(img_path, "rb") as f:
        img_data = f.read()
    img_filename = os.path.basename(img_path)
    headers = {
        "Content-Type": mime_type,
        "Content-Disposition": f'attachment; filename="{img_filename}"'
    }
    return api_request("media", method="POST", data=img_data, headers=headers)

def remove_existing_images(content):
    """既存のwp:imageブロックを削除"""
    # wp:image ブロック全体を削除（<!-- wp:image ... --> ... <!-- /wp:image -->）
    content = re.sub(
        r'<!-- wp:image[^>]*-->.*?<!-- /wp:image -->\s*',
        '',
        content,
        flags=re.DOTALL
    )
    # 残った空のfigureタグも削除
    content = re.sub(
        r'<figure[^>]*class=["\']wp-block-image[^"\']*["\'][^>]*>.*?</figure>\s*',
        '',
        content,
        flags=re.DOTALL
    )
    return content

def main():
    assets_dir = os.path.join(BASE_DIR, "assets")
    # 5枚の新写真（alt, ファイル名）
    new_images = [
        ("大河ドラマ「豊臣兄弟！」キャラクター相関図", "20251219_163854_p_o_33756555-20818603-921d-4256-b08d-8d63c9ebfe04.png"),
        ("NHK大河ドラマ・ガイド 豊臣兄弟！ 前編 表紙", "20260123-01016661-lmaga-001-1-view-b811d7a5-eb44-43af-b96d-96ed1f12afbd.png"),
        ("豊臣兄弟！キャスト（手鞠と鎧姿）", "18219-1215-8edbc36afed6e0ab2de6d59b101c2717-1920x1280-46048185-a2c8-4b00-9a8f-dfc16e2f7d87.png"),
        ("豊臣兄弟！甲冑姿のキャスト", "20260110s10041000292000p_view-91bb3fa1-c61f-49ad-9096-5cf3c6837266.png"),
        ("大河ドラマ 豊臣兄弟！プロモーションポスター（豊臣秀長）", "0c920f3ac1a44e9eb1cdf6651fc9bf7e_52_11-d7980e38-96f5-4634-baca-88db27c84f13.png"),
    ]
    qr_path = os.path.join(assets_dir, "QRmousikomi-4740150b-4adc-42bd-a13c-79db98e20d9c.png")

    uploaded = []
    for alt, fname in new_images:
        path = os.path.join(assets_dir, fname)
        if not os.path.exists(path):
            print(f"⚠ 画像が見つかりません: {path}", file=sys.stderr)
            continue
        print(f"アップロード中: {alt[:30]}...")
        res = upload_image(path)
        if res:
            uploaded.append((alt, res["source_url"], res["id"]))
            print(f"  OK")
        else:
            print(f"  失敗")

    if not uploaded:
        print("アップロードできた画像がありません", file=sys.stderr)
        sys.exit(1)

    # QRコード
    if os.path.exists(qr_path):
        print("QRコードをアップロード中...")
        res = upload_image(qr_path)
        if res:
            uploaded.append(("応募用QRコード（高島市HP申込フォーム）", res["source_url"], res["id"]))
            print("  OK")

    # 投稿取得
    post = api_request(f"posts/{_post_id}")
    if not post:
        print(f"投稿 {_post_id} を取得できません", file=sys.stderr)
        sys.exit(1)

    content = post.get("content", {}).get("raw", "")
    if not content:
        content = post.get("content", {}).get("rendered", "")

    # 既存画像を削除
    content = remove_existing_images(content)
    # 連続空行を2つに正規化
    content = re.sub(r'\n{3,}', '\n\n', content)

    img_html = lambda url, alt: f'<!-- wp:image {{"sizeSlug":"large"}} -->\n<figure class="wp-block-image size-large"><img src="{url}" alt="{alt}"/></figure>\n<!-- /wp:image -->'

    # 1枚目（相関図）: 冒頭
    first_img = img_html(uploaded[0][1], uploaded[0][0])
    if "<!-- wp:paragraph -->" in content:
        content = content.replace("<!-- wp:paragraph -->", first_img + "\n\n<!-- wp:paragraph -->", 1)
    elif "<p>" in content:
        content = content.replace("<p>", first_img + "\n\n<p>", 1)
    else:
        content = first_img + "\n\n" + content

    def insert_after_heading(content, heading_text, img_block):
        """見出しブロック（wp:heading）の直後に画像を挿入。Markdown(##)とHTML(h2/h3)両対応"""
        # classic形式: <h2 class="wp-block-heading">見出し</h2> または改行あり
        for tag in ("h2", "h3"):
            pattern = f"(<{tag}[^>]*>\\s*)" + re.escape(heading_text) + f"(\\s*</{tag}>)"
            if re.search(pattern, content):
                return re.sub(pattern, r"\1" + heading_text + r"\2\n\n" + img_block, content, count=1)
        # Gutenberg形式: <!-- wp:heading --><h2>見出し</h2><!-- /wp:heading -->
        for tag in ("h2", "h3"):
            pattern = f"({re.escape(heading_text)})(\\s*</{tag}>\\s*<!-- /wp:heading -->)"
            if re.search(pattern, content):
                return re.sub(pattern, r"\1\2\n\n" + img_block, content, count=1)
        # Markdown形式
        for prefix in ("## ", "### "):
            if prefix + heading_text in content:
                return content.replace(
                    prefix + heading_text,
                    prefix + heading_text + "\n\n" + img_block,
                    1
                )
        return content

    # 2枚目（ガイド表紙）: 「ドラマ「豊臣兄弟！」の核心と制作背景」の直後
    if len(uploaded) > 1:
        second_img = img_html(uploaded[1][1], uploaded[1][0])
        content = insert_after_heading(content, "ドラマ「豊臣兄弟！」の核心と制作背景", second_img)

    # 3枚目（手鞠と鎧）: 「松下洸平演じる徳川家康の新解釈」の直後
    if len(uploaded) > 2:
        third_img = img_html(uploaded[2][1], uploaded[2][0])
        content = insert_after_heading(content, "松下洸平演じる徳川家康の新解釈", third_img)

    # 4枚目（甲冑2人）: 「高島トークライブの全貌と参加方法」の直後
    if len(uploaded) > 3:
        fourth_img = img_html(uploaded[3][1], uploaded[3][0])
        content = insert_after_heading(content, "高島トークライブの全貌と参加方法", fourth_img)

    # 5枚目（ポスター）＋QR: 「申込フローと注意点」の直前
    fifth_img = img_html(uploaded[4][1], uploaded[4][0]) if len(uploaded) > 4 else ""
    qr_img = img_html(uploaded[5][1], uploaded[5][0]) if len(uploaded) > 5 else ""
    qr_note = '<!-- wp:paragraph -->\n<p><strong>上記QRコードから高島市ホームページの応募フォームにアクセスできます。スマートフォンで読み取ってお申し込みください。</strong></p>\n<!-- /wp:paragraph -->'
    insert_block = (fifth_img + "\n\n" if fifth_img else "") + (qr_img + "\n\n" if qr_img else "") + (qr_note + "\n\n" if qr_img else "")

    # 5枚目＋QR: 「申込フローと注意点」見出しブロックの直前に挿入
    qr_anchor = "申込フローと注意点"
    # 壊れたh3（中にpタグが入ったもの）を正しい形に修復
    content = re.sub(
        r'<h3([^>]*)>.*?' + re.escape(qr_anchor) + r'\s*</h3>',
        r'<h3\1>' + qr_anchor + r'</h3>',
        content,
        count=1,
        flags=re.DOTALL
    )
    # 修復したh3の直前に挿入
    m = re.search(r'<h3[^>]*>\s*' + re.escape(qr_anchor) + r'\s*</h3>', content)
    if m:
        content = content[:m.start()] + insert_block.rstrip() + "\n\n" + content[m.start():]
    elif "### " + qr_anchor in content:
        content = content.replace("### " + qr_anchor, insert_block.rstrip() + "\n\n### " + qr_anchor, 1)

    # 投稿更新（アイキャッチは1枚目＝相関図）
    featured_id = uploaded[0][2]
    patch_data = {"content": content, "featured_media": featured_id}
    result = api_request(f"posts/{_post_id}", method="POST", data=patch_data)
    if result:
        print(f"\n✅ 投稿 {_post_id} を更新しました。画像 {len(uploaded)} 枚に差し替え。")
    else:
        print("更新に失敗しました", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
