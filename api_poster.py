import html
import json
import base64
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import ssl
import sys
import os
import hashlib
import glob
import shutil

# ----------------- 設定 -----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _normalize_title_from_first_line(line):
    """1行目からタイトルを取得（BOM除去・Markdown H1対応）。"""
    t = (line or "").strip()
    if t.startswith("\ufeff"):
        t = t.lstrip("\ufeff").strip()
    if t.startswith("# "):
        t = t[2:].strip()
    return t


def _rest_api_title_field(title_str):
    """WordPress REST API が post_title に確実に保存するよう raw オブジェクト形式で送る。"""
    return {"raw": title_str}


def _prepend_title_h1_block(block_html, title_str):
    """テーマが the_title を表示しない場合のフォールバックとして本文先頭に H1 を付与する。"""
    esc = html.escape(title_str)
    return (
        f'<!-- wp:heading {{"level":1}} -->\n'
        f'<h1 class="wp-block-heading api-poster-inline-title">{esc}</h1>\n'
        f'<!-- /wp:heading -->\n\n'
        + block_html
    )


def _should_prepend_title_h1():
    v = os.environ.get("API_POSTER_PREPEND_TITLE_H1", "1").strip().lower()
    return v not in ("0", "false", "no", "off")

# --site / --date / --draft 引数の解析（例: python api_poster.py --site takashima --date 2026-03-04）
_site_name = "chotto"  # デフォルト
_site_explicit = False  # --site が明示指定されたか（False なら記事内容から自動判定）
_target_date = None  # YYYY-MM-DD 指定時はその日の空き枠を優先
_post_as_draft = False  # True: ドラフト保存 / False: 投稿予約（デフォルト）
_target_file = None  # 指定時はそのファイルのみ処理
_update_post_id = None  # 指定時はその投稿を更新（新規作成しない）
for i, arg in enumerate(sys.argv[1:], 1):
    if arg == "--update" and i + 1 <= len(sys.argv) - 1:
        try:
            _update_post_id = int(sys.argv[i + 1])
        except ValueError:
            pass
for i, arg in enumerate(sys.argv[1:], 1):
    if arg == "--site" and i + 1 <= len(sys.argv) - 1:
        _site_name = sys.argv[i + 1]
        _site_explicit = True
        break
for i, arg in enumerate(sys.argv[1:], 1):
    if arg == "--date" and i + 1 <= len(sys.argv) - 1:
        _target_date = sys.argv[i + 1]
        break
for i, arg in enumerate(sys.argv[1:], 1):
    if arg == "--file" and i + 1 <= len(sys.argv) - 1:
        _target_file = sys.argv[i + 1]
        break
if "--draft" in sys.argv:
    _post_as_draft = True

# sites.json があればサイト設定を読み込む
_sites_path = os.path.join(BASE_DIR, "sites.json")
if os.path.isfile(_sites_path):
    with open(_sites_path, "r", encoding="utf-8") as _sf:
        _sites = json.load(_sf)
    # エイリアス解決（_aliases で 高島市 → takashima など）
    _resolved = _site_name
    if _site_name not in _sites or _site_name == "_aliases":
        _aliases = _sites.get("_aliases", {})
        if _site_name in _aliases:
            _resolved = _aliases[_site_name]
        elif _site_name not in _sites:
            _available = [k for k in _sites.keys() if not k.startswith("_")]
            print(f"❌ sites.json に '{_site_name}' が見つかりません。利用可能: {_available}", file=sys.stderr)
            sys.exit(1)
    if _resolved in _sites and _resolved != "_aliases":
        _sc = _sites[_resolved]
        WP_API_URL = _sc.get("api_url", "https://chotto.news/wp-json/wp/v2")
        WP_USER    = _sc.get("user", "rinmon")
        WP_APP_PASS = _sc.get("app_pass", "")
        if _site_explicit:
            _display = _resolved if _resolved == _site_name else f"{_site_name}（→{_resolved}）"
            print(f"🌐 投稿先サイト: [{_display}] {WP_API_URL}")
    else:
        _available = [k for k in _sites.keys() if not k.startswith("_")]
        print(f"❌ sites.json に '{_site_name}' が見つかりません。利用可能: {_available}", file=sys.stderr)
        sys.exit(1)
else:
    # sites.json がない場合は .env にフォールバック
    _env_path = os.path.join(BASE_DIR, ".env")
    if os.path.isfile(_env_path):
        with open(_env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip()
                    if v.startswith('"') and v.endswith('"') or v.startswith("'") and v.endswith("'"):
                        v = v[1:-1]
                    if k and k not in os.environ:
                        os.environ[k] = v
    WP_API_URL  = os.getenv("WP_API_URL", "https://chotto.news/wp-json/wp/v2")
    WP_USER     = os.getenv("WP_USER", "rinmon")
    WP_APP_PASS = os.getenv("WP_APP_PASS", "")

if not WP_APP_PASS:
    print("WP_APP_PASS が設定されていません。", file=sys.stderr)
    sys.exit(1)

DRAFTS_DIR = os.path.join(BASE_DIR, "drafts")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")
SKIP_DIR = os.path.join(BASE_DIR, "drafts", "trash")  # ゴミ箱：ここにあるmdは処理しない

# サイト別ドラフトフォルダ（site_detection.json で上書き可能）
SITE_SPECIFIC_DRAFTS = ("takashima", "fukuyama")
DEFAULT_SITE = "chotto"

def _load_site_detection_config():
    """site_detection.json を読み込む。なければ None。"""
    path = os.path.join(BASE_DIR, "site_detection.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _get_site_detection_config():
    """サイト自動判定の設定を返す。site_detection.json があればそれ、なければデフォルト。"""
    cfg = _load_site_detection_config()
    if cfg and "sites" in cfg:
        return {
            "default_site": cfg.get("_default_site", DEFAULT_SITE),
            "site_specific_drafts": cfg.get("_site_specific_drafts", list(SITE_SPECIFIC_DRAFTS)),
            "sites": cfg["sites"]
        }
    return None

def _get_site_specific_drafts():
    """サイト別ドラフトフォルダのリストを返す。"""
    cfg = _get_site_detection_config()
    if cfg:
        return tuple(cfg["site_specific_drafts"])
    return SITE_SPECIFIC_DRAFTS

# ----------------- サイト自動判定（設定ファイルでカスタマイズ可能） -----------------
def detect_site_from_content(title, content, tags_str, categories_str, filepath=""):
    """
    記事のタイトル・本文・タグ・ファイルパスから投稿先サイトを判定する。
    site_detection.json があればその設定を使用、なければ組み込みデフォルトを使用。
    """
    combined = f"{title}\n{content}\n{tags_str}\n{categories_str}\n{filepath}"
    combined_lower = combined.lower()
    basename = os.path.basename(filepath).lower() if filepath else ""

    config = _get_site_detection_config()
    if config:
        scores = {}
        for site_id, site_cfg in config["sites"].items():
            score = 0
            for kw, weight in site_cfg.get("keywords", []):
                if kw in combined or kw.lower() in combined_lower:
                    score += weight
            for pat in site_cfg.get("filename_patterns", []):
                if pat in basename or pat.lower() in basename:
                    score += 3
            scores[site_id] = score
        if scores:
            best = max(scores.items(), key=lambda x: x[1])
            if best[1] > 0:
                return best[0]
        return config["default_site"]

    # フォールバック: 組み込みデフォルト（従来の挙動）
    fukuyama_score = 0
    takashima_score = 0
    fukuyama_keywords = [
        ("福山市", 2), ("福山駅", 2), ("田尻町", 2), ("鞆の浦", 2),
        ("福山城", 1), ("備後", 1), ("福山アンバサダー", 1), ("芦田川", 1),
        ("福山ラーメン", 1), ("エクセル鞆の浦", 1), ("鞆鉄バス", 1),
        ("福山シティfc", 1), ("fukuyama", 1)
    ]
    takashima_keywords = [
        ("高島市", 2), ("大溝", 2), ("滋賀県立美術館", 2), ("琵琶湖", 2),
        ("高島", 1), ("近江高島", 1), ("湖北", 1), ("湖西", 1),
        ("マキノ", 1), ("朽木", 1), ("askプロジェクト", 1), ("takashima", 1)
    ]
    for kw, weight in fukuyama_keywords:
        if kw in combined or kw.lower() in combined_lower:
            fukuyama_score += weight
    for kw, weight in takashima_keywords:
        if kw in combined or kw.lower() in combined_lower:
            takashima_score += weight
    if "fukuyama" in basename or "福山" in basename:
        fukuyama_score += 3
    if "takashima" in basename or "高島" in basename:
        takashima_score += 3
    if fukuyama_score > takashima_score:
        return "fukuyama"
    if takashima_score > fukuyama_score:
        return "takashima"
    return DEFAULT_SITE

def collect_draft_files_from_all_sites():
    """全ドラフトフォルダ（drafts/, drafts/サイト名/）から処理対象ファイルを収集し、ソートして返す。"""
    all_files = []
    search_dirs = [DRAFTS_DIR]
    for site in _get_site_specific_drafts():
        d = os.path.join(BASE_DIR, "drafts", site)
        if os.path.isdir(d):
            search_dirs.append(d)
    for d in search_dirs:
        for ext in ("*.md", "*.txt"):
            for f in glob.glob(os.path.join(d, ext)):
                bn = os.path.basename(f)
                if bn.upper() == "README_DRAFTS.MD":
                    continue
                base_no_ext = os.path.splitext(bn)[0]
                if not glob.glob(os.path.join(PROCESSED_DIR, f"*_{base_no_ext}.md")):
                    all_files.append(f)
    all_files.sort()
    return all_files

def find_target_file_auto_mode():
    """自動判定モード時：全フォルダから対象ファイルを探し、(filepath, drafts_dir) を返す。見つからなければ (None, None)。"""
    if _target_file:
        # --file 指定時：全フォルダを検索
        for d in [DRAFTS_DIR] + [os.path.join(BASE_DIR, "drafts", s) for s in _get_site_specific_drafts()]:
            if os.path.isdir(d):
                cand = os.path.normpath(os.path.join(d, _target_file))
                if os.path.isfile(cand):
                    base_no_ext = os.path.splitext(os.path.basename(cand))[0]
                    if glob.glob(os.path.join(PROCESSED_DIR, f"*_{base_no_ext}.md")):
                        return None, None
                    return cand, d
        return None, None
    files = collect_draft_files_from_all_sites()
    if not files:
        return None, None
    f = files[0]
    return f, os.path.dirname(f)

# Cloudflareブロック回避のためのブラウザ偽装ヘッダー
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
    'Connection': 'keep-alive'
}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# ----------------- WordPressブロック形式変換 -----------------
def to_block_format(content):
    """
    HTML/マークダウン混在の本文をWordPressブロック形式（Gutenberg）に変換する。
    wp:paragraph, wp:image, wp:video, wp:heading のコメントでラップする。
    """
    import re
    blocks = []
    # 空行2つ以上で分割（ブロック境界）
    raw_blocks = re.split(r'\n\s*\n', content)
    
    def wrap_paragraph(text):
        """段落テキストを <p> でラップし、* → <em>, ** → <strong> を変換"""
        t = text.strip()
        if not t:
            return None
        # 簡易マークダウン変換（* → em, ** → strong）
        t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
        t = re.sub(r'\*(.+?)\*', r'<em>\1</em>', t)
        if not t.startswith('<'):
            t = f'<p>{t}</p>'
        return f"<!-- wp:paragraph -->\n{t}\n<!-- /wp:paragraph -->"
    
    for raw in raw_blocks:
        raw = raw.strip()
        if not raw:
            continue
        # 0. auto-gallery 内の figure を個別ブロックに（先に処理）
        if "auto-gallery" in raw:
            for m in re.finditer(
                r"<figure\s+class=['\"]wp-block-image[^'\"]*['\"][^>]*>.*?</figure>",
                raw, re.DOTALL | re.IGNORECASE
            ):
                blocks.append(f"<!-- wp:image {{\"sizeSlug\":\"large\"}} -->\n{m.group(0)}\n<!-- /wp:image -->")
            for m in re.finditer(
                r"<figure\s+class=['\"]wp-block-video[^'\"]*['\"][^>]*>.*?</figure>",
                raw, re.DOTALL | re.IGNORECASE
            ):
                blocks.append(f"<!-- wp:video -->\n{m.group(0)}\n<!-- /wp:video -->")
            continue
        # 1. 画像ブロック: <figure class='wp-block-image ...'>...</figure>
        fig_img = re.search(
            r"<figure\s+class=['\"]wp-block-image[^'\"]*['\"][^>]*>.*?</figure>",
            raw, re.DOTALL | re.IGNORECASE
        )
        if fig_img:
            fig_html = fig_img.group(0)
            # キャプション（*出典：...*）があれば figcaption に追加
            rest = raw[:fig_img.start()] + raw[fig_img.end():]
            caption_match = re.search(r'\*([^*]+)\*', rest)
            if caption_match and '出典' in caption_match.group(1):
                cap = caption_match.group(1)
                if '</figure>' in fig_html and '<figcaption' not in fig_html:
                    fig_html = fig_html.replace('</figure>', f'<figcaption>{cap}</figcaption></figure>')
            blocks.append(f"<!-- wp:image {{\"sizeSlug\":\"large\"}} -->\n{fig_html}\n<!-- /wp:image -->")
            # キャプション以外の残りがあれば段落に
            if caption_match:
                rest = rest[:caption_match.start()] + rest[caption_match.end():]
            if rest.strip():
                p = wrap_paragraph(rest)
                if p:
                    blocks.append(p)
            continue
        # 2. 動画ブロック: <figure class='wp-block-video ...'>...</figure>
        fig_vid = re.search(
            r"<figure\s+class=['\"]wp-block-video[^'\"]*['\"][^>]*>.*?</figure>",
            raw, re.DOTALL | re.IGNORECASE
        )
        if fig_vid:
            blocks.append(f"<!-- wp:video -->\n{fig_vid.group(0)}\n<!-- /wp:video -->")
            rest = raw[:fig_vid.start()] + raw[fig_vid.end():]
            if rest.strip():
                p = wrap_paragraph(rest)
                if p:
                    blocks.append(p)
            continue
        # 4. 見出し: ##, ###, ####
        h4 = re.match(r'^####\s+(.+)$', raw, re.DOTALL)
        h3 = re.match(r'^###\s+(.+)$', raw, re.DOTALL)
        h2 = re.match(r'^##\s+(.+)$', raw, re.DOTALL)
        h1 = re.match(r'^#\s+(.+)$', raw, re.DOTALL)
        for level, m in [(4, h4), (3, h3), (2, h2), (1, h1)]:
            if m:
                inner = m.group(1).strip()
                inner = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', inner)
                inner = re.sub(r'\*(.+?)\*', r'<em>\1</em>', inner)
                blocks.append(f'<!-- wp:heading {{"level":{level}}} -->\n<h{level}>{inner}</h{level}>\n<!-- /wp:heading -->')
                break
        else:
            # 3. Markdown表: | A | B | 形式の行が2行以上連続（末尾に注釈があっても分離して処理）
            lines = raw.split('\n')
            table_lines = []
            rest_after_table = []
            in_table = False
            table_ended = False
            for ln in lines:
                stripped = ln.strip()
                if not stripped:
                    if in_table:
                        table_ended = True
                    continue
                is_table_row = bool(re.match(r'^\|.+\|$', stripped))
                if is_table_row and not table_ended:
                    table_lines.append(stripped)
                    in_table = True
                else:
                    if in_table:
                        table_ended = True
                    rest_after_table.append(stripped)
            is_table = len(table_lines) >= 2 and all(re.match(r'^\|.+\|$', ln) for ln in table_lines)
            if is_table:
                rows = []
                for ln in table_lines:
                    parts = ln.split('|')
                    cells = [c.strip() for c in parts[1:-1]] if len(parts) >= 2 else []
                    if not cells:
                        continue
                    # 区切り行（---のみ）はスキップ
                    if all(re.match(r'^:?-+:?$', c) for c in cells):
                        continue
                    rows.append(cells)
                if rows:
                    # 1行目をヘッダー、残りをボディ
                    thead_cells = rows[0]
                    tbody_rows = rows[1:]
                    thead_html = '<thead><tr>' + ''.join(f'<th>{html.escape(c)}</th>' for c in thead_cells) + '</tr></thead>'
                    tbody_html = '<tbody>'
                    for row in tbody_rows:
                        # 列数がヘッダーと異なる場合は調整
                        cells = row[:len(thead_cells)] + [''] * (len(thead_cells) - len(row))
                        tbody_html += '<tr>' + ''.join(f'<td>{html.escape(str(c))}</td>' for c in cells[:len(thead_cells)]) + '</tr>'
                    tbody_html += '</tbody>'
                    # is-style-stripes: 明細行の縞模様 / has-dark-header: ヘッダー濃背景・白文字
                    table_html = f'<figure class="wp-block-table is-style-stripes has-dark-header"><table>{thead_html}{tbody_html}</table></figure>'
                    blocks.append(f'<!-- wp:table -->\n{table_html}\n<!-- /wp:table -->')
                    # 表の直後の注釈などを段落として追加
                    if rest_after_table:
                        rest_text = ' '.join(rest_after_table)
                        p = wrap_paragraph(rest_text)
                        if p:
                            blocks.append(p)
                    continue
            # 5. 通常の段落
            p = wrap_paragraph(raw)
            if p:
                blocks.append(p)
    
    return '\n\n'.join(blocks) if blocks else content

# ----------------- APIクライアント -----------------
def api_request(endpoint, method="GET", data=None, headers=None, is_media=False):
    """WordPress REST API リクエスト。dict は必ず Content-Type: application/json で送信。"""
    url = f"{WP_API_URL}/{endpoint}"
    req_headers = BROWSER_HEADERS.copy()
    req_headers["Authorization"] = f"Basic {base64.b64encode(f'{WP_USER}:{WP_APP_PASS}'.encode()).decode()}"
    
    encoded_data = None
    if data is not None:
        if isinstance(data, dict):
            encoded_data = json.dumps(data).encode('utf-8')
            req_headers["Content-Type"] = "application/json"
        else:
            # For raw bytes (image upload) - 呼び出し元の headers で Content-Type を指定すること
            encoded_data = data
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, data=encoded_data, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as response:
            res_body = response.read().decode('utf-8')
            return json.loads(res_body) if res_body else None
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error on {url}: {e}", file=sys.stderr)
        return None


# ----------------- タクソノミー（タグ・カテゴリ）処理 -----------------
# 高島市・福山市はカテゴリを新規作成せず既存のみ使用
NO_CREATE_CATEGORY_SITES = ("takashima", "fukuyama")
# chotto: slug-translaterプラグインが新規タグ作成時に500エラーを返すため、既存タグのみ使用
NO_CREATE_TAG_SITES = ("chotto",)

def get_default_category_id():
    """WordPressのデフォルトカテゴリ（未分類など）のIDを取得"""
    for slug in ("uncategorized", "mibunrui", "未分類"):
        terms = api_request(f"categories?slug={urllib.parse.quote(slug)}")
        if terms and len(terms) > 0:
            return [terms[0]["id"]]
    all_cats = api_request("categories?per_page=1")
    if all_cats:
        return [all_cats[0]["id"]]
    return [1]  # WordPress標準の未分類ID

def get_term_ids(taxonomy, names_str, create_new=True):
    if not names_str:
        return []
    names = [x.strip() for x in names_str.replace('、', ',').split(',') if x.strip()]
    ids = []
    for name in names:
        encoded_name = urllib.parse.quote(name)
        terms = api_request(f"{taxonomy}?search={encoded_name}")
        
        # Exact match logic
        exact_match = None
        if terms:
            for t in terms:
                if t['name'] == name:
                    exact_match = t
                    break
        
        if exact_match:
            ids.append(exact_match['id'])
            print(f"  [OK] 既存の{taxonomy}発見: {name} (ID: {exact_match['id']})")
        else:
            if not create_new:
                print(f"  [SKIP] 既存のみ使用のためスキップ: {name}（存在しません）")
                continue
            print(f"  [NEW] 新規{taxonomy}作成中: {name}")
            # slug-translaterプラグイン対策: 英語のMD5スラッグを強制指定して500エラーを回避
            slug = hashlib.md5(name.encode()).hexdigest()[:10]
            new_term = api_request(taxonomy, method="POST", data={"name": name, "slug": slug})
            if new_term and 'id' in new_term:
                ids.append(new_term['id'])
                print(f"  [SUCCESS] 作成完了: {name} (ID: {new_term['id']})")
            else:
                print(f"  [ERROR] 作成失敗: {name}")
    return ids

# ----------------- 画像アップロード処理 -----------------
def upload_image(img_path):
    print(f"⏳ 画像をアップロード中: {os.path.basename(img_path)}...")
    ext = os.path.splitext(img_path)[1].lower()
    mime_map = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp", ".mp4": "video/mp4"}
    mime_type = mime_map.get(ext, "image/jpeg")
    
    with open(img_path, "rb") as f:
        img_data = f.read()
        
    img_filename = os.path.basename(img_path)
    headers = {
        "Content-Type": mime_type,
        "Content-Disposition": f'attachment; filename="{img_filename}"'
    }
    media_res = api_request("media", method="POST", data=img_data, headers=headers, is_media=True)
    if media_res and 'id' in media_res:
        print(f"✅ 画像アップロード成功 (Media ID: {media_res['id']})")
        return media_res
    else:
        print(f"❌ 画像のアップロードに失敗しました: {img_filename}")
        return None

# ----------------- 二重投稿防止 -----------------
def is_already_processed(basename_no_ext):
    """processedフォルダに同名の記事が既にあるか（Synology同期で戻ってきた場合の検出）"""
    pattern = f"*_{basename_no_ext}.md"
    found = glob.glob(os.path.join(PROCESSED_DIR, pattern))
    return len(found) > 0

def _safe_move(src, dst, label=""):
    """ファイル移動。Synology同期等で失敗しても例外で落とさない。"""
    try:
        if os.path.exists(src):
            shutil.move(src, dst)
            print(f"📁 {label}を {PROCESSED_DIR} へ移動しました。")
        else:
            print(f"⚠️  {label}の移動をスキップ（元ファイルが既に存在しません。同期の可能性）")
    except Exception as e:
        print(f"⚠️  {label}の移動に失敗: {e}", file=sys.stderr)
        try:
            shutil.copy2(src, dst)
            os.remove(src)
            print(f"📁 copy+removeで代替完了")
        except Exception as e2:
            print(f"⚠️  代替移動も失敗: {e2}", file=sys.stderr)

def post_exists_with_title(title):
    """WordPressに同一タイトルの記事が既にあるか（publish/future/draft/private）"""
    encoded = urllib.parse.quote(title)
    
    # 1. まず高速なカスタムAPIを試す (デプロイされていない場合は404等でNoneが返る)
    custom_endpoint = f"custom/v1/check-title?title={encoded}"
    res = api_request(custom_endpoint)
    if isinstance(res, dict) and "exists" in res:
        if res["exists"]:
            return res.get("id")
        return None  # カスタムAPIで「存在しない」と確認できた
        
    # 2. フォールバック: カスタムAPIが使えない場合は従来の標準API（全文検索仕様のため遅い）で検索
    posts = api_request(f"posts?search={encoded}&status=publish,future,draft,private&per_page=50&_fields=title,id,status")
    if not posts:
        return None
    for p in posts:
        t = p.get("title") or {}
        raw_title = t.get("raw") or t.get("rendered", "")
        if raw_title == title:
            return p.get("id")
    return None

# ----------------- メインロジック -----------------
def main():
    global _resolved, WP_API_URL, WP_USER, WP_APP_PASS

    print("==========================================")
    print("WordPress API 自動投稿ツール (drafts監視)")
    print("==========================================\n")

    text_file = None
    drafts_dir = None

    if _site_explicit:
        drafts_dir = DRAFTS_DIR
        if _resolved in _get_site_specific_drafts():
            site_drafts = os.path.join(BASE_DIR, "drafts", _resolved)
            if os.path.isdir(site_drafts):
                drafts_dir = site_drafts
                print(f"📁 サイト別ドラフト: {drafts_dir}\n")
            else:
                os.makedirs(site_drafts, exist_ok=True)
                drafts_dir = site_drafts
                print(f"📁 サイト別ドラフト作成: {drafts_dir}\n")
    else:
        # 自動判定モード：記事内容から CHOTTO / 福山 / 高島 を判定
        text_file, drafts_dir = find_target_file_auto_mode()
        if not text_file:
            print(f"❌ 処理対象のテキストファイルがありません。（全ドラフトフォルダを検索済み）")
            return
        with open(text_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        if not lines:
            print("❌ ファイルが空です。")
            return
        title = _normalize_title_from_first_line(lines[0])
        content_lines = []
        tags_str = ""
        categories_str = ""
        current_section = "content"
        for line in lines[1:]:
            s = line.strip()
            if s == "**タグ**":
                current_section = "tags"
                continue
            elif s == "**カテゴリ**":
                current_section = "categories"
                continue
            elif s == "**メタディスクリプション**":
                break
            if current_section == "content":
                content_lines.append(line)
            elif current_section == "tags" and s:
                tags_str += s + ","
            elif current_section == "categories" and s:
                categories_str += s + ","
        content = "".join(content_lines).strip()
        detected = detect_site_from_content(title, content, tags_str, categories_str, text_file)
        if os.path.isfile(_sites_path):
            with open(_sites_path, "r", encoding="utf-8") as _sf:
                _sites = json.load(_sf)
            if detected in _sites and detected != "_aliases":
                _resolved = detected
                _sc = _sites[_resolved]
                WP_API_URL = _sc.get("api_url", "https://chotto.news/wp-json/wp/v2")
                WP_USER = _sc.get("user", "rinmon")
                WP_APP_PASS = _sc.get("app_pass", "")
        site_labels = {"chotto": "CHOTTO.NEWS", "fukuyama": "福山市", "takashima": "高島市"}
        print(f"🔍 記事内容から自動判定: {site_labels.get(_resolved, _resolved)}")
        print(f"🌐 投稿先サイト: [{_resolved}] {WP_API_URL}\n")
        if drafts_dir and drafts_dir != DRAFTS_DIR:
            print(f"📁 サイト別ドラフト: {drafts_dir}\n")

    if _site_explicit:
        # --site 指定時：ファイル検索
        os.makedirs(DRAFTS_DIR, exist_ok=True)
        os.makedirs(PROCESSED_DIR, exist_ok=True)
        os.makedirs(SKIP_DIR, exist_ok=True)
        all_md_files = glob.glob(os.path.join(drafts_dir, "*.md")) + glob.glob(os.path.join(drafts_dir, "*.txt"))
        md_files = [f for f in all_md_files if os.path.basename(f).upper() != "README_DRAFTS.MD"
                    and not is_already_processed(os.path.splitext(os.path.basename(f))[0])]
        md_files.sort()
        if _target_file:
            resolved = os.path.normpath(os.path.join(drafts_dir, _target_file)) if not os.path.isabs(_target_file) else _target_file
            if not os.path.isfile(resolved):
                print(f"❌ 指定ファイルが見つかりません: {_target_file}", file=sys.stderr)
                return
            if not _update_post_id and is_already_processed(os.path.splitext(os.path.basename(resolved))[0]):
                print(f"⏭  スキップ（既にprocessed済み）: {os.path.basename(resolved)}")
                return
            text_file = resolved
        elif not md_files:
            print(f"❌ 処理対象のテキストファイルがありません。（README/trash/processed済みを除く）")
            return
        else:
            text_file = md_files[0]

    os.makedirs(DRAFTS_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(SKIP_DIR, exist_ok=True)

    # 自動判定モード時は drafts_dir が None の可能性（find_target_file がルートを返す場合）
    if drafts_dir is None:
        drafts_dir = DRAFTS_DIR

    print(f"📂 処理対象ファイル: {os.path.basename(text_file)}")
    
    import re
    import urllib.request
    import urllib.parse
    
    # 2. テキストファイルを先読みして画像URLを抽出・ダウンロード
    with open(text_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    if not lines:
        print("❌ ファイルが空です。")
        return
        
    title = _normalize_title_from_first_line(lines[0])
    content_lines = []
    tags_str = ""
    categories_str = ""
    excerpt_str = ""
    
    current_section = "content"
    
    for line in lines[1:]: # 2行目以降
        stripped = line.strip()
        if stripped == "**タグ**":
            current_section = "tags"
            continue
        elif stripped == "**カテゴリ**":
            current_section = "categories"
            continue
        elif stripped == "**メタディスクリプション**":
            current_section = "excerpt"
            continue
            
        if current_section == "content":
            content_lines.append(line)
        elif current_section == "tags" and stripped:
            tags_str += stripped + ","
        elif current_section == "categories" and stripped:
            categories_str += stripped + ","
        elif current_section == "excerpt" and stripped:
            excerpt_str += stripped + " "

    content = "".join(content_lines).strip()
    
    # [IMAGE_BLOCK] 形式を ![]() 形式に変換（article_creation_guidelines.md 準拠）
    # 既存の画像パイプラインで処理するため、事前に正規化
    image_block_pattern = re.compile(
        r'\[IMAGE_BLOCK\]\s*\n'
        r'(?:説明:\s*([^\n]*)\s*\n)?'
        r'URL:\s*(https?://[^\s\n]+)\s*\n'
        r'(?:[^\]]*\n)*?'
        r'\[/IMAGE_BLOCK\]',
        re.MULTILINE
    )
    def _image_block_to_md(m):
        alt = (m.group(1) or "").strip()
        url = m.group(2).strip()
        return f"![{alt}]({url})"
    content = image_block_pattern.sub(_image_block_to_md, content)
    
    # 画像リンク抽出（![]() 形式）: URL とローカルパス両対応
    # URL: https?://... / ローカル: assets/xxx.png や ./assets/xxx.png
    pattern = r'!\[([^\]]*)\]\(([^\)]+)\)'
    all_matches = re.findall(pattern, content)
    url_to_local_path = {}
    local_ref_to_path = {}  # 本文での参照文字列 → 絶対パス
    
    text_file_dir = os.path.dirname(text_file)
    
    for alt, ref in all_matches:
        ref = ref.strip()
        if ref.startswith(('http://', 'https://')):
            # URL: ダウンロード
            if ref not in url_to_local_path:
                try:
                    print(f"  DL中: {ref[:80]}{'...' if len(ref) > 80 else ''}")
                    req = urllib.request.Request(ref, headers=BROWSER_HEADERS)
                    with urllib.request.urlopen(req, timeout=20, context=ctx) as response:
                        data = response.read()
                        parsed = urllib.parse.urlparse(ref)
                        filename = os.path.basename(parsed.path) or "image"
                        base = filename.split("?")[0]
                        # 画像・動画の拡張子を維持（動画は埋め込み用、アイキャッチは最初の画像を使用）
                        allowed_ext = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.webm')
                        if not base.lower().endswith(allowed_ext):
                            filename = base + '.jpg' if base else 'image.jpg'
                        else:
                            filename = base
                        filename = f"dl_img_{len(url_to_local_path) + 1:03d}_{filename}"
                        filepath = os.path.join(drafts_dir, filename)
                        with open(filepath, 'wb') as img_f:
                            img_f.write(data)
                        url_to_local_path[ref] = filepath
                except Exception as e:
                    print(f"  ❌ ダウンロード失敗: {e}", file=sys.stderr)
        else:
            # ローカルパス: ドラフトファイル基準で解決
            local_path = os.path.normpath(os.path.join(text_file_dir, ref))
            if os.path.isfile(local_path):
                local_ref_to_path[ref] = local_path
            else:
                print(f"  ⚠ ローカル画像が見つかりません: {ref}", file=sys.stderr)
    
    if all_matches:
        url_count = len(url_to_local_path)
        local_count = len(local_ref_to_path)
        url_refs = [ref for alt, ref in all_matches if ref.strip().startswith(('http://', 'https://'))]
        local_refs = [ref for alt, ref in all_matches if not ref.strip().startswith(('http://', 'https://'))]
        # 写真取り込み失敗時は報告して投稿中止
        failed_urls = [r for r in url_refs if r not in url_to_local_path]
        failed_locals = [r for r in local_refs if r not in local_ref_to_path]
        if failed_urls or failed_locals:
            print(f"\n❌ 写真の取り込みに失敗しました。投稿を中止します。", file=sys.stderr)
            if failed_urls:
                print(f"   取得できなかったURL画像: {len(failed_urls)} 件", file=sys.stderr)
                for u in failed_urls[:5]:
                    print(f"   - {u[:70]}...", file=sys.stderr)
                if len(failed_urls) > 5:
                    print(f"   ... 他 {len(failed_urls)-5} 件", file=sys.stderr)
            if failed_locals:
                print(f"   見つからないローカル画像: {len(failed_locals)} 件", file=sys.stderr)
                for p in failed_locals:
                    print(f"   - {p}", file=sys.stderr)
            return
        if url_count or local_count:
            print(f"\n🖼  Markdown内の画像: URL {url_count} 件, ローカル {local_count} 件")
    elif content.strip():
        print(f"\n⚠  本文に ![alt](url/path) 形式の画像がありません。アイキャッチは未設定になります。")

    # 3. 画像は「この記事のMarkdownから取得したもの」のみ使用（出現順を維持、先頭がアイキャッチ）
    img_files = []
    for alt, ref in all_matches:
        if ref.startswith(('http://', 'https://')):
            if ref in url_to_local_path:
                img_files.append(url_to_local_path[ref])
        elif ref in local_ref_to_path:
            img_files.append(local_ref_to_path[ref])
    
    uploaded_media = []
    featured_media_id = None
    local_path_to_uploaded = {}
    
    if img_files:
        print(f"\n🖼  アップロード対象のメディア数: {len(img_files)} 個")
        for i, img in enumerate(img_files):
            res = upload_image(img)
            if res:
                uploaded_media.append({"path": img, "data": res})
                local_path_to_uploaded[img] = res
        # アイキャッチは最初の画像を使用（動画はスキップ、テーマで画像が適切）。画像がなければ動画をフォールバック
        for um in uploaded_media:
            p = um["path"]
            if not p.lower().endswith(('.mp4', '.webm')):
                featured_media_id = um["data"]["id"]
                print(f"★ アイキャッチ画像に設定: {os.path.basename(p)}")
                break
        if featured_media_id is None and uploaded_media:
            featured_media_id = uploaded_media[0]["data"]["id"]
            print(f"★ アイキャッチに設定（動画フォールバック）: {os.path.basename(uploaded_media[0]['path'])}")
    else:
        print(f"⚠  メディアファイルなしで進行します。")

    used_media_indices = set()
    
    # 4-1. Markdownの ![alt](url/path) をWP HTMLに置換
    for alt, ref in all_matches:
        local_path = url_to_local_path.get(ref) if ref.startswith(('http://', 'https://')) else local_ref_to_path.get(ref)
        md_str = f"![{alt}]({ref})"
        if local_path and local_path in local_path_to_uploaded:
            res = local_path_to_uploaded[local_path]
            wp_url = res.get("source_url", "")
            if wp_url:
                if local_path.lower().endswith(('.mp4', '.webm')):
                    html = f"<figure class='wp-block-video'><video controls src='{wp_url}' style='max-width: 100%; height: auto;'></video></figure>"
                else:
                    html = f"<figure class='wp-block-image size-large'><img src='{wp_url}' alt='{alt}'/></figure>"
                content = content.replace(md_str, html)
                
                for idx, um in enumerate(uploaded_media):
                    if um["path"] == local_path:
                        used_media_indices.add(idx)
                        break
        else:
            # ダウンロード失敗時も元URLでimgタグを挿入（ホットリンクで表示される場合あり）
            if ref.startswith(('http://', 'https://')):
                html = f"<figure class='wp-block-image size-large'><img src='{ref}' alt='{alt}'/></figure>"
                content = content.replace(md_str, html)

    # 4-2. [IMG_x] の置換 (旧仕様サポート)
    if len(uploaded_media) > 1:
        for i, media in enumerate(uploaded_media):
            if i == 0: continue
            if i in used_media_indices: continue
            
            img_num = i + 1
            placeholder = f"\[IMG_{img_num}\]"
            wp_url = media["data"].get("source_url", "")
            
            if wp_url and f"[IMG_{img_num}]" in content:
                if media["path"].lower().endswith(".mp4"):
                    media_html = f"<figure class='wp-block-video'><video controls src='{wp_url}' style='max-width: 100%; height: auto;'></video></figure>"
                else:
                    media_html = f"<figure class='wp-block-image size-large'><img src='{wp_url}' alt='{title} - 関連メディア'/></figure>"
                content = content.replace(f"[IMG_{img_num}]", media_html)
                used_media_indices.add(i)

    # 4-3. 使われなかった画像を末尾にギャラリーとして配置
    unused_media = [media for i, media in enumerate(uploaded_media) if i != 0 and i not in used_media_indices]
    if unused_media:
        print(f"\n🖼  プレースホルダー指定のない {len(unused_media)} 点のメディアを本文末尾に挿入します。")
        content += "\n\n<!-- 添付メディア（自動挿入） -->\n<div class='auto-gallery'>\n"
        for media in unused_media:
            wp_url = media["data"].get("source_url", "")
            if wp_url:
                if media["path"].lower().endswith(".mp4"):
                    content += f"<figure class='wp-block-video'><video controls src='{wp_url}' style='max-width: 100%; height: auto;'></video></figure>\n"
                else:
                    content += f"<figure class='wp-block-image size-large'><img src='{wp_url}' alt='{title} - 関連メディア'/></figure>\n"
        content += "</div>\n"

    print("\n--- 📝 抽出データ ---")
    print(f"タイトル: {title}")
    print(f"タクソノミー:")
    print(f"  - カテゴリ: {categories_str}")
    print(f"  - タグ: {tags_str}")
    print(f"画像埋め込み数: {len(uploaded_media) - 1 if len(uploaded_media) > 1 else 0} 枚（本文内）")
            
    # 5. タグとカテゴリのID取得・生成
    print("\n⏳ カテゴリとタグを取得・生成中...")
    cat_create_new = _resolved not in NO_CREATE_CATEGORY_SITES
    if not cat_create_new:
        print("  ※ 高島市/福山市: カテゴリは既存のみ使用（新規作成しません）")
    # サイト別カテゴリマッピング適用（福山市など表記差対応）
    categories_str_resolved = categories_str
    if os.path.isfile(_sites_path):
        with open(_sites_path, "r", encoding="utf-8") as _sf:
            _sites_data = json.load(_sf)
        _sc = _sites_data.get(_resolved, {})
        category_map = _sc.get("category_map", {})
        if category_map:
            names = [x.strip() for x in categories_str.replace('、', ',').split(',') if x.strip()]
            mapped = [category_map.get(n, n) for n in names]
            categories_str_resolved = ",".join(mapped)
            if categories_str_resolved != categories_str:
                print(f"  ※ カテゴリマッピング適用: {categories_str} → {categories_str_resolved}")
    cat_ids = get_term_ids("categories", categories_str_resolved, create_new=cat_create_new)
    if not cat_ids and not cat_create_new:
        cat_ids = get_default_category_id()
        print(f"  [FALLBACK] マッチする既存カテゴリがなかったためデフォルトを使用 (ID: {cat_ids[0]})")
    tag_create_new = _resolved not in NO_CREATE_TAG_SITES
    if not tag_create_new:
        print("  ※ chotto: タグは既存のみ使用（slug-translater対策）")
    tag_ids = get_term_ids("tags", tags_str, create_new=tag_create_new)
    
    # 6. 次の予約時間を計算（予約投稿時のみ、更新時は既存の日付を維持）
    scheduled_date = None
    existing_post = None
    if _update_post_id:
        # 更新時：既存投稿の日付・ステータスを取得
        existing_post = api_request(f"posts/{_update_post_id}?_fields=date,status")
        if existing_post and existing_post.get("date"):
            scheduled_date = existing_post["date"]
            print(f"\n📝 更新モード: Post ID {_update_post_id} の日付を維持 ({scheduled_date.replace('T', ' ')})")
    elif not _post_as_draft:
        print("\n⏳ スケジュール枠を検索中...")
        posts = api_request("posts?status=future&per_page=100&_fields=date")
        taken_slots = set()
        if posts:
            taken_slots = {p['date'] for p in posts}
            
        now = datetime.now()
        # 予約枠：1日18件（6時〜23時、1時間毎）
        # 基本は「今日」から検索し、利用可能な最も早い枠を優先
        fallback_slots = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]
        if _target_date:
            try:
                y, m, d = [int(x) for x in _target_date.strip().split("-")]
                check_date = datetime(y, m, d, 0, 0, 0)
                print(f"  📅 --date 指定: {check_date.date()} から空き枠を優先検索")
            except (ValueError, IndexError):
                check_date = now.replace(minute=0, second=0, microsecond=0)
                print(f"  ⚠ --date 解釈失敗（{_target_date}）、現在時刻を基準にします。", file=sys.stderr)
        else:
            check_date = now.replace(minute=0, second=0, microsecond=0)
        day_range = 30
        
        for day_offset in range(day_range):
            current_day = check_date + timedelta(days=day_offset)
            for h in fallback_slots:
                slot_candidate = current_day.replace(hour=h)
                if slot_candidate <= now:
                    continue # 過去の時間はスキップ
                slot_str = slot_candidate.strftime("%Y-%m-%dT%H:%M:%S")
                if slot_str not in taken_slots:
                    scheduled_date = slot_str
                    break
            if scheduled_date:
                break
                
        if not scheduled_date:
            scheduled_date = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:00:00")
            
        print(f"✅ 次の空き枠: {scheduled_date.replace('T', ' ')}")
    
    # 6.5. 二重投稿防止：同一タイトル（完全一致）の投稿が既にあるか確認。本文・抜粋の内容照合は行わない。更新時はスキップしない。
    if not _update_post_id:
        existing_id = post_exists_with_title(title)
        if existing_id:
            print(f"\n⚠️  二重投稿防止: 同一タイトルの記事が既に存在します (Post ID: {existing_id})")
            print(f"    対象タイトル: {title}")
            print(f"    スキップし、ファイルをprocessedへ移動します。")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            processed_text = os.path.join(PROCESSED_DIR, f"{timestamp}_SKIP_DUP_{os.path.basename(text_file)}")
            _safe_move(text_file, processed_text, "テキスト（重複のためスキップ）")
            print()
            print("=" * 62)
            print(f"📰 記事タイトル: {title}")
            print("=" * 62)
            return
    
    # 6.9. 本文をWordPressブロック形式（Gutenberg）に変換
    content = to_block_format(content)
    if title and _should_prepend_title_h1():
        content = _prepend_title_h1_block(content, title)
        print("  ℹ 本文先頭に H1 タイトルを挿入しました（テーマと二重になる場合は API_POSTER_PREPEND_TITLE_H1=0）")

    # 7. 記事の投稿（または更新）
    if _update_post_id:
        print("\n⏳ 既存記事を更新中...")
        post_data = {
            "title": _rest_api_title_field(title),
            "content": content,
            "categories": cat_ids,
            "tags": tag_ids
        }
        if scheduled_date:
            post_data["date"] = scheduled_date
        # 日付取得に失敗しても status だけは必ず送る（未指定だと公開扱いになるのを防ぐ）
        if existing_post and existing_post.get("status"):
            post_data["status"] = existing_post["status"]
        if excerpt_str:
            post_data["excerpt"] = excerpt_str
        if featured_media_id:
            post_data["featured_media"] = featured_media_id
        post_res = api_request(f"posts/{_update_post_id}", method="POST", data=post_data)
    elif _post_as_draft:
        print("\n⏳ 記事をドラフト保存中...")
        post_data = {
            "title": _rest_api_title_field(title),
            "content": content,
            "status": "draft",
            "categories": cat_ids,
            "tags": tag_ids
        }
        if excerpt_str:
            post_data["excerpt"] = excerpt_str
        if featured_media_id:
            post_data["featured_media"] = featured_media_id
        post_res = api_request("posts", method="POST", data=post_data)
    else:
        print("\n⏳ 記事を予約投稿中...")
        post_data = {
            "title": _rest_api_title_field(title),
            "content": content,
            "status": "future",
            "date": scheduled_date,
            "categories": cat_ids,
            "tags": tag_ids
        }
        if excerpt_str:
            post_data["excerpt"] = excerpt_str
        if featured_media_id:
            post_data["featured_media"] = featured_media_id
        post_res = api_request("posts", method="POST", data=post_data)
    
    if post_res and 'id' in post_res:
        post_id = post_res['id']
        # タイトルが空で返ってきた場合は raw 形式で再送（プラグイン・REST の組み合わせ対策）
        _tobj = post_res.get("title") or {}
        _saved_title = (_tobj.get("raw") or "").strip()
        if not _saved_title and title:
            _rend = _tobj.get("rendered") or ""
            if _rend:
                _saved_title = re.sub(r"<[^>]+>", "", _rend).strip()
        if title and not _saved_title:
            _fix = api_request(f"posts/{post_id}", method="POST", data={"title": _rest_api_title_field(title)})
            if _fix and (_fix.get("title") or {}).get("raw"):
                print(f"  ✓ タイトルが空だったため再設定しました。")
            else:
                print(f"  ⚠ タイトルの再設定に失敗しました。管理画面で確認してください。", file=sys.stderr)
        # アイキャッチは別リクエストで確実に設定（初回POSTで反映されないケース対策）
        if featured_media_id:
            patch_res = api_request(f"posts/{post_id}", method="POST", data={"featured_media": featured_media_id})
            if patch_res and int(patch_res.get("featured_media", 0)) == int(featured_media_id):
                print(f"  ✓ アイキャッチ画像を設定しました (Media ID: {featured_media_id})")
            else:
                print(f"  ⚠ アイキャッチ設定が反映されていません。手動で Media ID {featured_media_id} を設定してください。", file=sys.stderr)
    
    if post_res and 'id' in post_res:
        if _update_post_id:
            print(f"\n🎉 成功！ 記事が更新されました。")
        elif _post_as_draft:
            print(f"\n🎉 成功！ 記事がドラフト保存されました。")
        else:
            print(f"\n🎉 成功！ 記事が予約されました。")
        print(f"タイトル:   {title}")
        print(f"Post ID:   {post_res['id']}")
        if not _post_as_draft and post_res.get('date'):
            print(f"Schedule:  {post_res['date'].replace('T', ' ')}")
        print(f"Status:    {post_res['status']}")
        # 要約・ログでタイトルが落ちないよう、末尾に再掲（エージェント報告用）
        _sched = ""
        if not _post_as_draft and post_res.get('date'):
            _sched = post_res["date"].replace("T", " ")
        print()
        print("=" * 62)
        print("📌 投稿サマリー（タイトル必ずここに表示）")
        print(f"   タイトル: {title}")
        print(f"   Post ID: {post_res['id']}")
        if _sched:
            print(f"   予約日時: {_sched}")
        print(f"   ステータス: {post_res['status']}")
        print("=" * 62)
        
        # 8. 成功したらファイルをprocessedへ移動（_safe_moveでSynology同期時の失敗に耐える）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = f"{timestamp}_UPDATE" if _update_post_id else timestamp
        processed_text = os.path.join(PROCESSED_DIR, f"{prefix}_{os.path.basename(text_file)}")
        _safe_move(text_file, processed_text, "テキスト")
        
        # 全てのアップロード成功した画像を移動
        for img_obj in uploaded_media:
            img_path = img_obj["path"]
            processed_img = os.path.join(PROCESSED_DIR, f"{prefix}_{os.path.basename(img_path)}")
            _safe_move(img_path, processed_img, f"画像 {os.path.basename(img_path)}")
            
        # READMEを作り直す（次回用）
        readme_content = """1行目にタイトルを書く
2行目から本文を開始

**タグ**
タグ1,タグ2

**カテゴリ**
01.【社会】

**メタディスクリプション**
抜粋テキスト

※投稿しない記事は drafts/trash/ に移動すると処理対象外になります。
"""
        with open(os.path.join(DRAFTS_DIR, 'README_drafts.md'), 'w', encoding='utf-8') as f:
            f.write(readme_content)
        print()
        print("=" * 62)
        print(f"📰 記事タイトル: {title}")
        print("=" * 62)
    else:
        if _update_post_id:
            print("\n❌ 記事の更新に失敗しました。")
        elif _post_as_draft:
            print("\n❌ 記事のドラフト保存に失敗しました。")
        else:
            print("\n❌ 記事の予約に失敗しました。")

if __name__ == "__main__":
    main()
