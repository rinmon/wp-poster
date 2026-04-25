#!/usr/bin/env python3
"""
互換エントリ: X ページ先頭のツイート本文＋画像（旧名）。実装は tools/x_fetch.py --page。

例:
  python3 fetch_x_data.py "https://x.com/elonmusk" --cookies x_cookies.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.x_fetch import main

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="互換: tools/x_fetch.py --page に委譲")
    p.add_argument("url")
    p.add_argument("--cookies", default="x_cookies.json")
    ns = p.parse_args()
    raise SystemExit(main(["--page", ns.url, "--cookies", ns.cookies]))
