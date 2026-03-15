# wp-poster

WordPress 記事投稿ワークフロー。Markdownドラフトから WordPress REST API へ記事を予約投稿するツール群。[chotto.news](https://chotto.news/) 等の複数サイトに対応。

## 主な機能

- **api_poster.py** … ドラフト（Markdown）を WordPress に投稿予約
- **Markdown表の自動変換** … `| A | B |` 形式を WordPress 表ブロックに変換
- **複数サイト対応** … chotto / 高島市 / 福山市 を記事内容から自動判定
- **画像・動画** … IMAGE_BLOCK 形式、ローカル画像、URL に対応

## 認証情報の設定

**重要**: `.env` と `sites.json` は `.gitignore` で除外されています。認証情報は GitHub に含まれません。

### 方法A: 複数サイト（推奨）

1. `sites.json.example` を `sites.json` にコピー
2. 各サイトの値を記入:

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
# 今日の空き枠に投稿予約
python api_poster.py --site chotto --date 2026-03-15 --file 記事.md

# 既存記事を更新
python api_poster.py --site chotto --update 58491 --file 記事.md
```

## ドラフト形式

- 1行目: タイトル
- 本文: Markdown（IMAGE_BLOCK、表、見出し対応）
- 末尾: `**タグ**` `**カテゴリ**` `**メタディスクリプション**`

## セキュリティ（公開リポジトリにする場合）

以下のファイルは `.gitignore` で除外されており、**コミットされません**:

| ファイル | 内容 |
|----------|------|
| `.env` | WordPress API認証、SSH認証 |
| `sites.json` | 各サイトの api_url, user, app_pass |

テンプレート（`sites.json.example`、`.env.example`）のみリポジトリに含まれます。クローン後に手動でコピー・記入すれば安全に利用できます。

## GitHub

- リポジトリ: [rinmon/wp-poster](https://github.com/rinmon/wp-poster)
- 更新時: `git add -A && git commit -m "メッセージ" && git push`

## ライセンス

Private / 個人利用
