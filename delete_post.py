import asyncio
import os
import sys

BASE_DIR = "/Users/rinmon/Library/CloudStorage/SynologyDrive-work/0000/BLOG"
sys.path.append(BASE_DIR)
from api_poster import api_request

def delete_item(endpoint, item_id):
    res = api_request(f"{endpoint}/{item_id}?force=true", method="DELETE")
    if res:
        print(f"Deleted {endpoint} {item_id}")
    else:
        print(f"Failed to delete {endpoint} {item_id}")

# 重複予約の削除（list_duplicate_scheduled.py で検出したIDを指定）
delete_item("posts", 57830)  # 山口ノロウイルス記事の重複
