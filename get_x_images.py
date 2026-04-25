#!/usr/bin/env python3
"""
互換エントリ: 実装は tools/x_fetch.py。

例:
  python3 get_x_images.py "https://x.com/NASA/status/123"
  python3 get_x_images.py --timeline "https://x.com/NASA" --cookies x_cookies.json
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.x_fetch import main

if __name__ == "__main__":
    raise SystemExit(main())
