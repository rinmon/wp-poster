#!/usr/bin/env python3
"""
WordPress REST 呼び出し（sites.json 前提）の共通薄ラッパー。

update_post_images / update_toyotomi_images 等から利用。
"""
from __future__ import annotations

import base64
import json
import os
import ssl
import sys
import urllib.request
from typing import Any

DEFAULT_UA = "Mozilla/5.0 (WordPress-CLI/1.0) AppleWebKit/537.36"


def resolve_site(sites: dict, site_name: str) -> dict:
    r = sites.get("_aliases", {}).get(site_name, site_name)
    if r in sites and r != "_aliases":
        return sites[r]
    if site_name in sites and site_name != "_aliases":
        return sites[site_name]
    raise KeyError(f"サイトが見つかりません: {site_name!r}")


class WordPressRest:
    def __init__(self, site: dict, *, verify_ssl: bool = False):
        self._api = site["api_url"].rstrip("/")
        self._user = site["user"]
        self._app_pass = site["app_pass"]
        self._ctx = ssl.create_default_context()
        if not verify_ssl:
            self._ctx.check_hostname = False
            self._ctx.verify_mode = ssl.CERT_NONE
        self._base_headers: dict[str, str] = {
            "User-Agent": DEFAULT_UA,
            "Accept": "application/json",
            "Authorization": "Basic "
            + base64.b64encode(f"{self._user}:{self._app_pass}".encode()).decode(),
        }

    def request(
        self,
        endpoint: str,
        method: str = "GET",
        data: bytes | dict | None = None,
        extra_headers: dict | None = None,
    ) -> Any:
        url = f"{self._api}/{endpoint}"
        h = self._base_headers.copy()
        if extra_headers:
            h.update(extra_headers)
        body: bytes | None
        if data is None:
            body = None
        elif isinstance(data, dict):
            body = json.dumps(data).encode("utf-8")
            h["Content-Type"] = "application/json"
        else:
            body = data
        req = urllib.request.Request(url, data=body, method=method, headers=h)
        with urllib.request.urlopen(req, timeout=60, context=self._ctx) as resp:
            res_body = resp.read().decode("utf-8")
        return json.loads(res_body) if res_body else None

    def upload_file(self, path: str) -> dict | None:
        ext = os.path.splitext(path)[1].lower()
        mime_map = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml"}
        mime = mime_map.get(ext, "image/jpeg")
        with open(path, "rb") as f:
            raw = f.read()
        name = os.path.basename(path)
        extra = {
            "Content-Type": mime,
            "Content-Disposition": f'attachment; filename="{name}"',
        }
        try:
            return self.request("media", method="POST", data=raw, extra_headers=extra)
        except Exception as e:  # noqa: BLE001
            print(f"Error: {e}", file=sys.stderr)
            return None

    def get_post(self, post_id: int) -> dict | None:
        try:
            return self.request(f"posts/{post_id}")
        except Exception as e:  # noqa: BLE001
            print(f"Error: {e}", file=sys.stderr)
            return None

    def update_post(self, post_id: int, payload: dict) -> dict | None:
        return self.request(f"posts/{post_id}", method="POST", data=payload)


def from_sites_file(base_dir: str, site_name: str) -> WordPressRest:
    path = os.path.join(base_dir, "sites.json")
    with open(path, "r", encoding="utf-8") as f:
        sites = json.load(f)
    return WordPressRest(resolve_site(sites, site_name))
