#!/usr/bin/env python3
"""既存記事の画像が消えた場合、元URLでfigureタグを復元して更新する"""
import json
import base64
import urllib.request
import ssl
import sys
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from api_poster import api_request, to_block_format

def fix_post_content_from_markdown(md_path):
    """Markdownファイルを読み、![alt](url)をfigureに変換してcontentを返す"""
    with open(md_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    content_lines = []
    for line in lines[1:]:
        stripped = line.strip()
        if stripped in ("**タグ**", "**カテゴリ**", "**メタディスクリプション**"):
            break
        content_lines.append(line)

    content = "".join(content_lines).strip()
    pattern = r'!\[([^\]]*)\]\((https?://[^\)]+)\)'
    for alt, url in re.findall(pattern, content):
        md_str = f"![{alt}]({url})"
        html = f"<figure class='wp-block-image size-large'><img src='{url}' alt='{alt}'/></figure>"
        content = content.replace(md_str, html)
    return content

def main():
    post_id = 57998  # 阪急バケモン記事
    md_path = os.path.join(BASE_DIR, "processed", "20260307_220802_20260307_hankyu_bakemon_viral_video.md")
    if not os.path.isfile(md_path):
        print(f"File not found: {md_path}")
        sys.exit(1)

    content = fix_post_content_from_markdown(md_path)
    content = to_block_format(content)

    res = api_request(f"posts/{post_id}", method="POST", data={"content": content})
    if res and res.get("id"):
        print(f"✅ Post {post_id} を更新しました。画像（元URL）を復元しました。")
    else:
        print("❌ 更新に失敗しました。", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
