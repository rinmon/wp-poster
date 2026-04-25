# wp-poster

**v1.2.0**

WordPress 記事投稿ワークフロー。Markdownドラフトから WordPress REST API へ記事を予約投稿するツール群。複数のWordPressサイトに対応。

## 主な機能

### api_poster.py（コアスクリプト）

- **投稿予約** … ドラフト（Markdown）を WordPress に予約投稿
- **記事更新** … `--update POST_ID` で既存記事を上書き
- **ドラフト保存** … `--draft` で公開せず下書きとして保存
- **Markdown表の自動変換** … `| A | B |` 形式を WordPress 表ブロック（wp:table）に変換
- **複数サイト対応** … 記事内容から投稿先を自動判定（`site_detection.json` でキーワード・サイトを設定可能）
- **サイト別ドラフト** … `drafts/サイト名/` を `--site` 指定時に使用（設定で変更可）
- **二重投稿防止** … 同一タイトルの記事が既にある場合はスキップ

### 画像・動画

- **IMAGE_BLOCK** … 説明・URL・出典を記載する専用形式（`![alt](url)` に自動変換）
- **URL画像** … 外部URLからダウンロードして WordPress メディアにアップロード
- **ローカル画像** … `drafts/` 内のファイルを `![alt](filename.jpg)` で参照
- **動画** … mp4 / webm に対応（埋め込みブロックとして挿入）
- **取得失敗時** … 画像URLが403/404等で取得できない場合は投稿を中止

### その他スクリプト

| スクリプト | 用途 |
|------------|------|
| `process_all_drafts.py` | drafts 内の全ドラフトを順次処理 |
| `reschedule_posts.py` | 全サイトの予約投稿を 5:00〜24:00・1時間刻み（正時）の枠に沿って再調整 |
| `check_article_duplicates.py` | 投稿前チェック（ローカル md + WP 同一タイトル、`--scheduled` で予約重複も） |
| `duplicate_hints.py` | 重複検出の類似度ヒント（`check_article_duplicates` から利用） |
| `list_duplicate_scheduled.py` | 予約重複を検出・表示 |
| `get_posts.py` / `search_posts.py` | 投稿一覧・検索（REST） |
| `create_draft.py` / `create_late_uncle_draft.py` | ドラフト雛形の生成 |
| `get_x_images.py` | 互換ラッパ（実体は `tools/x_fetch.py`）。ツイートのメディアURL / `--timeline` |
| `fetch_x_data.py` | 互換ラッパ。`tools/x_fetch.py --page`（Cookie 付きで先頭ツイート列の本文・画像） |
| `tools/x_fetch.py` | X 取得の集約。単一ツイートURL（既定） / `--timeline` / `--page`（`x_cookies_template.json` 参照） |
| `tools/wp_client.py` | `sites.json` ベースの WordPress REST（メディアアップロード・投稿更新） |
| `update_featured_image.py` | 既存投稿のアイキャッチを差し替え（`sites.json` 認証・`--site` `--post`） |
| `update_post_images.py` | 高島・豊臣系の初回投入用サンプル（Wikimedia 図＋QR。`tools/wp_client.py`・`--site` `--post`） |
| `update_toyotomi_images.py` | 同上記事の本文画像一括差し替え（`tools/wp_client.py`・`--site` `--post`） |
| `enrich_recent_chotto_tags.py` / `export_chotto_tags.py` | CHOTTO タグ周り |
| `check_server_health.py` | サーバー診断（SSH経由） |
| `test_ssh.py` | SSH 接続テスト |
| `wp_version_snapshot.py` | WordPress バージョン取得の補助 |
| `delete_post.py` | 指定IDの投稿を削除 |
| `tools/fetch_og_image.py` | 公式・報道ページの og:image URL 取得（IMAGE_BLOCK 用） |
| `tools/fetch_x_media_urls.py` | ツイート URL からメディア URL 列挙 |
| `tools/screenshot_page.py` | 任意 URL のスクリーンショット（`--tweet` で先頭ツイートのみ、`--full-page`） |
| `tools/fix_consecutive_h3_body.py` | 誤って `###` になった本文行を通常段落に戻す（`--dry-run`） |
| `tools/export_chotto_categories.py` | CHOTTO カテゴリ一覧のエクスポート |
| `tools/fix_chotto_categories_by_publish_date.py` | 公開日基準のカテゴリ修正 |
| `tools/move_chotto_post_to_fukuyama.py` | サイト間移動の補助 |

**整理メモ（2026-04）**: 使い捨ての一括修正（特定 Post ID・日付固定の `fix_*.py`）、認証をファイルに直書きしたアップロード系、未完成の断片スクリプト、重複していたスクリーンショット用の短いスクリプトは削除済み。アイキャッチの更新は **`update_featured_image.py` + `sites.json`** を使うこと。

## 認証情報の設定

**重要**: `.env` と `sites.json` は `.gitignore` で除外されています。認証情報は GitHub に含まれません。

### 方法A: 複数サイト（推奨）

1. `sites.json.example` を `sites.json` にコピーし、各サイトの API 認証を記入
2. （任意）`site_detection.json.example` を `site_detection.json` にコピーし、記事内容からの自動判定キーワードをカスタマイズ。未設定の場合は組み込みデフォルトで動作
3. 各サイトの値を記入:

```json
{
  "chotto": {
    "api_url": "https://example.com/wp-json/wp/v2",
    "user": "WordPressのユーザー名",
    "app_pass": "アプリケーションパスワード（WordPress管理画面で発行）"
  }
}
```

- **api_url**: `https://サイトドメイン/wp-json/wp/v2`
- **user**: WordPress のログインID
- **app_pass**: ユーザー設定 → アプリケーションパスワードで発行（通常パスワードは使用不可）

### 方法B: 単一サイト

1. `.env.example` を `.env` にコピー
2. `WP_API_URL`、`WP_USER`、`WP_APP_PASS` を記入

### SSH（サーバー診断用・任意）

`check_server_health.py` 等で使用。`.env` に `SSH_HOST`、`SSH_USER`、`SSH_PASS` を追加。

## 使い方

```bash
# 指定日の空き枠に投稿予約
python api_poster.py --site chotto --date 2026-03-15 --file 記事.md

# 既存記事を更新（日付・ステータスは維持）
python api_poster.py --site chotto --update 58491 --file 記事.md

# ドラフトとして保存（予約しない）
python api_poster.py --site chotto --draft --file 記事.md

# サイト指定なし＝記事内容から自動判定
python api_poster.py --file 記事.md
```

### 引数

| 引数 | 説明 |
|------|------|
| `--site` | 投稿先サイト（chotto / takashima / fukuyama またはエイリアス「福山市」等） |
| `--date` | 予約日（YYYY-MM-DD）。※空き枠は常に今日から検索し、最も早い枠を優先 |
| `--file` | 処理するドラフトファイル名 |
| `--update` | 既存投稿ID。新規作成せず更新 |
| `--draft` | 予約せずドラフト保存 |

## ドラフト形式

- **1行目**: タイトル（`# ` で始めても自動除去）
- **本文**: Markdown（IMAGE_BLOCK、`![alt](url)`、表、見出し対応）
- **末尾**: `**タグ**` → `**カテゴリ**` → `**メタディスクリプション**`

### IMAGE_BLOCK 形式

```
[IMAGE_BLOCK]
説明: altテキスト（120文字程度）
URL: https://画像のURL
出典名: 出典元
出典URL: https://元投稿のURL
[/IMAGE_BLOCK]
```

内部で `![説明](URL)` に変換され、URLからダウンロード→WordPressメディアにアップロードされます。

### sites.json の拡張

- **\_aliases** … 「福山市」→「fukuyama」など日本語名で指定可能
- **category_map** … カテゴリ名のマッピング（例: `"15.【訃報】"` → サイト固有の表記）

### site_detection.json（記事内容からの自動判定）

`site_detection.json.example` をコピーして `site_detection.json` を作成。GitHub にはサンプルのみ公開され、実設定は `.gitignore` で除外されます。

| キー | 説明 |
|------|------|
| `_default_site` | キーワードに該当しない場合の投稿先 |
| `_site_specific_drafts` | サイト別ドラフトフォルダ名のリスト（例: `["takashima", "fukuyama"]`） |
| `sites.サイトID.keywords` | `[["キーワード", 重み], ...]` で記事内出現時にスコア加算 |
| `sites.サイトID.filename_patterns` | ファイル名に含まれるとスコア+3 のパターン |

サイトを追加・削除・変更する場合は `site_detection.json` を編集してください。

## セキュリティ（公開リポジトリにする場合）

以下のファイルは `.gitignore` で除外されており、**コミットされません**:

| ファイル | 内容 |
|----------|------|
| `.env` | WordPress API認証、SSH認証 |
| `sites.json` | 各サイトの api_url, user, app_pass |
| `site_detection.json` | 記事内容からの投稿先自動判定（キーワード・サイト一覧） |

テンプレート（`sites.json.example`、`site_detection.json.example`、`.env.example`）のみリポジトリに含まれます。クローン後に手動でコピー・記入すれば安全に利用できます。

## GitHub

- リポジトリ: [rinmon/wp-poster](https://github.com/rinmon/wp-poster)
- バージョン: `VERSION` ファイルで管理（Semantic Versioning）
- 更新時: `git add -A && git commit -m "メッセージ" && git push`
- タグ付きリリース: `git tag v1.0.0 && git push origin v1.0.0`

## ライセンス

Private / 個人利用
