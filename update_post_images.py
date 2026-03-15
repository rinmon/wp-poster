#!/usr/bin/env python3
"""
既存WordPress投稿に画像を追加するスクリプト。
使用例: python update_post_images.py --site takashima --post 3124
"""
import json
import base64
import urllib.request
import ssl
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
}

def api_request(endpoint, method="GET", data=None, headers=None, is_media=False):
    url = f"{WP_API_URL}/{endpoint}"
    req_headers = BROWSER_HEADERS.copy()
    req_headers["Authorization"] = f"Basic {base64.b64encode(f'{WP_USER}:{WP_APP_PASS}'.encode()).decode()}"
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
    res = api_request("media", method="POST", data=img_data, headers=headers, is_media=True)
    return res

def main():
    # 1. 画像をアップロード
    qr_path = os.path.join(BASE_DIR, "assets", "QRmousikomi-4740150b-4adc-42bd-a13c-79db98e20d9c.png")
    if not os.path.exists(qr_path):
        print(f"QRコードが見つかりません: {qr_path}", file=sys.stderr)
        sys.exit(1)

    # 3枚の写真URL（Wikimedia Commons 直接URL - サムネイルは429エラーになるため）
    image_urls = [
        ("https://upload.wikimedia.org/wikipedia/commons/a/a3/Toyotomi_Hideyoshi.jpg", "豊臣秀吉像"),
        ("https://upload.wikimedia.org/wikipedia/commons/1/11/Tokugawa_Ieyasu2.JPG", "徳川家康像"),
        ("https://upload.wikimedia.org/wikipedia/commons/b/bf/Symbol_of_Shiga_prefecture.png", "滋賀県と琵琶湖"),
    ]

    uploaded = []
    # QRコード
    print("QRコードをアップロード中...")
    res = upload_image(qr_path)
    if res:
        uploaded.append(("応募用QRコード（高島市HP申込フォーム）", res["source_url"], res["id"]))
        print(f"  OK: {res['source_url']}")

    # 3枚の写真をダウンロードしてアップロード
    import tempfile
    for url, alt in image_urls:
        try:
            req = urllib.request.Request(url, headers=BROWSER_HEADERS)
            with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                data = resp.read()
            ext = ".jpg" if "jpg" in url.lower() else ".png"
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tf:
                tf.write(data)
                tmp_path = tf.name
            res = upload_image(tmp_path)
            os.unlink(tmp_path)
            if res:
                uploaded.append((alt, res["source_url"], res["id"]))
                print(f"  OK: {alt}")
        except Exception as e:
            print(f"  失敗: {alt} - {e}")

    if not uploaded:
        print("アップロードできた画像がありません", file=sys.stderr)
        sys.exit(1)

    # 2. 現在の投稿を取得
    post = api_request(f"posts/{_post_id}")
    if not post:
        print(f"投稿 {_post_id} を取得できません", file=sys.stderr)
        sys.exit(1)

    content = post.get("content", {}).get("raw", "")
    if not content:
        content = post.get("content", {}).get("rendered", "")

    # 3. 画像を適切な位置に挿入
    # WordPressのcontentはGutenbergブロック形式の可能性あり。セクション見出しで検索
    img_html = lambda url, alt: f"<!-- wp:image {{\"sizeSlug\":\"large\"}} -->\n<figure class=\"wp-block-image size-large\"><img src=\"{url}\" alt=\"{alt}\"/></figure>\n<!-- /wp:image -->"

    # 冒頭に1枚目（豊臣秀吉）- 既に画像がある場合はスキップ
    first_img = img_html(uploaded[1][1], uploaded[1][0])
    if not (content.strip().startswith("<!-- wp:image") or content.strip().startswith("<figure")):
        if "<!-- wp:paragraph -->" in content:
            content = content.replace("<!-- wp:paragraph -->", first_img + "\n\n<!-- wp:paragraph -->", 1)
        elif "<p>" in content:
            content = content.replace("<p>", first_img + "\n\n<p>", 1)
        else:
            content = first_img + "\n\n" + content

    # 「高島トークライブの全貌」の前に2枚目（徳川家康、あれば）
    second_img = img_html(uploaded[2][1], uploaded[2][0]) if len(uploaded) > 2 else ""
    if second_img and "高島トークライブの全貌と参加方法" in content:
        content = content.replace("高島トークライブの全貌と参加方法", second_img + "\n\n高島トークライブの全貌と参加方法", 1)

    # 「申込フローと注意点」の前に3枚目（滋賀・琵琶湖、あれば）とQRコード
    third_img = img_html(uploaded[3][1], uploaded[3][0]) if len(uploaded) > 3 else ""
    qr_img = img_html(uploaded[0][1], uploaded[0][0])
    qr_note = "<!-- wp:paragraph -->\n<p><strong>上記QRコードから高島市ホームページの応募フォームにアクセスできます。スマートフォンで読み取ってお申し込みください。</strong></p>\n<!-- /wp:paragraph -->"
    insert_block = (third_img + "\n\n" if third_img else "") + qr_img + "\n\n" + qr_note + "\n\n"
    if "申込フローと注意点" in content:
        content = content.replace("申込フローと注意点", insert_block + "申込フローと注意点", 1)

    # 4. 投稿を更新（アイキャッチは1枚目＝豊臣秀吉）
    featured_id = uploaded[1][2]
    patch_data = {"content": content, "featured_media": featured_id}
    result = api_request(f"posts/{_post_id}", method="POST", data=patch_data)
    if result:
        print(f"\n✅ 投稿 {_post_id} を更新しました。画像 {len(uploaded)} 枚を追加。")
    else:
        print("更新に失敗しました", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
