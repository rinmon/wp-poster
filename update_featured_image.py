#!/usr/bin/env python3
"""指定記事にアイキャッチ画像を設定するスクリプト

使用例:
  python update_featured_image.py --site chotto --post 57944 --image path/to/image.jpg
  python update_featured_image.py --site chotto --post 57944 --media-id 57965  # 既存メディアを指定
"""
import json
import base64
import urllib.request
import ssl
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_sites_path = os.path.join(BASE_DIR, "sites.json")

_site_name = "chotto"
_post_id = None
_image_path = None
_media_id = None
for i, arg in enumerate(sys.argv[1:], 1):
    if arg == "--site" and i + 1 <= len(sys.argv) - 1:
        _site_name = sys.argv[i + 1]
    elif arg == "--post" and i + 1 <= len(sys.argv) - 1:
        _post_id = int(sys.argv[i + 1])
    elif arg == "--image" and i + 1 <= len(sys.argv) - 1:
        _image_path = sys.argv[i + 1]
    elif arg == "--media-id" and i + 1 <= len(sys.argv) - 1:
        _media_id = int(sys.argv[i + 1])

if not _post_id:
    print("Usage: python update_featured_image.py --site SITE --post POST_ID --image IMAGE_PATH | --media-id MEDIA_ID")
    sys.exit(1)
if not _image_path and not _media_id:
    print("--image または --media-id のいずれかが必要です。")
    sys.exit(1)
if _image_path and not os.path.isfile(_image_path):
    print(f"画像ファイルが見つかりません: {_image_path}")
    sys.exit(1)

with open(_sites_path, "r", encoding="utf-8") as f:
    sites = json.load(f)
aliases = sites.get("_aliases", {})
resolved = aliases.get(_site_name, _site_name) if _site_name not in sites else _site_name
if resolved not in sites or resolved == "_aliases":
    resolved = _site_name
sc = sites.get(resolved, {})
WP_API_URL = sc.get("api_url", "")
WP_USER = sc.get("user", "rinmon")
WP_APP_PASS = sc.get("app_pass", "")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def api_request(endpoint, method="GET", data=None, headers=None):
    url = f"{WP_API_URL}/{endpoint}"
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Authorization": f"Basic {base64.b64encode(f'{WP_USER}:{WP_APP_PASS}'.encode()).decode()}",
    }
    if headers:
        req_headers.update(headers)
    encoded = json.dumps(data).encode("utf-8") if isinstance(data, dict) else data
    if isinstance(data, dict):
        req_headers["Content-Type"] = "application/json"
    elif data is not None:
        req_headers.pop("Content-Type", None)
    req = urllib.request.Request(url, data=encoded, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode()}", file=sys.stderr)
        return None

# 1. 画像アップロード（--media-id 指定時はスキップ）
if _media_id:
    media_id = _media_id
    print(f"既存メディア ID {media_id} を使用します。")
else:
    ext = os.path.splitext(_image_path)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    with open(_image_path, "rb") as f:
        img_data = f.read()
    img_headers = {
        "Content-Type": mime,
        "Content-Disposition": f'attachment; filename="{os.path.basename(_image_path)}"',
    }
    media_res = api_request("media", method="POST", data=img_data, headers=img_headers)
    if not media_res or "id" not in media_res:
        print("❌ 画像アップロード失敗")
        sys.exit(1)
    media_id = media_res["id"]
    print(f"✅ 画像アップロード成功 (Media ID: {media_id})")

# 2. 記事の featured_media を更新（Content-Type: application/json 必須）
update_res = api_request(f"posts/{_post_id}", method="POST", data={"featured_media": media_id})
if not update_res or "id" not in update_res:
    print("❌ 記事の更新に失敗しました。")
    sys.exit(1)

# 3. 反映確認
actual_fm = int(update_res.get("featured_media", 0))
if actual_fm == media_id:
    print(f"✅ 記事 {_post_id} のアイキャッチ画像を設定しました。")
else:
    print(f"⚠  API応答では featured_media={actual_fm} です。再試行します...")
    retry_res = api_request(f"posts/{_post_id}", method="POST", data={"featured_media": media_id})
    if retry_res and int(retry_res.get("featured_media", 0)) == media_id:
        print(f"✅ 再試行でアイキャッチ画像を設定しました。")
    else:
        print(f"❌ アイキャッチが反映されません。WordPress管理画面で手動設定してください (Media ID: {media_id})")
        sys.exit(1)
