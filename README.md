# BLOG - WordPress 記事投稿ワークフロー

Markdownドラフトから WordPress REST API へ記事を予約投稿するツール群。[chotto.news](https://chotto.news/) 等の複数サイトに対応。

## 主な機能

- **api_poster.py** … ドラフト（Markdown）を WordPress に投稿予約
- **Markdown表の自動変換** … `| A | B |` 形式を WordPress 表ブロックに変換
- **複数サイト対応** … chotto / 高島市 / 福山市 を記事内容から自動判定
- **画像・動画** … IMAGE_BLOCK 形式、ローカル画像、URL に対応

## セットアップ

1. `sites.json.example` を `sites.json` にコピー
2. 各サイトの `api_url`、`user`、`app_pass` を記入
3. または `.env.example` を `.env` にコピーし、単一サイト用に設定

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

## ライセンス

Private / 個人利用
