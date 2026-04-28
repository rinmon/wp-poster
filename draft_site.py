"""
ローカル .md の「投稿先サイト」推定（パス＋任意メタデータ）。
同サイト内だけで重複を見る、フォルダ運用の指針に使う。

推奨:
  - 高島・福山: drafts/takashima/ / drafts/fukuyama/ に置く
  - CHOTTO: 従来どおり drafts/ 直下、または明示したい場合は drafts/chotto/
  - 混在フォルダ（特に processed/）で明示したいとき: 次のいずれかを先頭付近に
      <!-- wp-poster-site: takashima -->
      **投稿先サイト** takashima
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

# HTML コメント（1 行、先頭 8KB 以内を走査）
_RE_SITE_COMMENT = re.compile(
    r"<!--\s*wp-poster-site:\s*([a-zA-Z0-9_.-]+)\s*-->", re.IGNORECASE
)
# **投稿先サイト** chotto 形式（全角＊・全角：も許容）
_RE_SITE_LINE = re.compile(
    r"(?m)^\s*[*＊]{0,2}\s*投稿先サイト\s*[*＊]{0,2}\s*[:：]?\s*([a-zA-Z0-9_.-]+)\s*$",
)


@dataclass(frozen=True)
class DraftSiteContext:
    base_dir: str
    drafts_dir: str
    processed_dir: str
    """
    site_detection / api_poster の _get_site_specific_drafts()（例: takashima, fukuyama）。
    chotto 用の名前付きサブフォルダは chotto_subfolder で別途指定。
    """
    site_subfolders: tuple[str, ...] = ("takashima", "fukuyama")
    chotto_subfolder: str = "chotto"
    default_site: str = "chotto"


def read_declared_site_from_draft(path: str, max_bytes: int = 8_192) -> str | None:
    """
    ドラフト先頭付近から明示の投稿先サイトキーを返す。無ければ None。
    """
    try:
        with open(path, "rb") as f:
            raw = f.read(max_bytes + 1)
    except OSError:
        return None
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        return None
    m = _RE_SITE_COMMENT.search(text)
    if m:
        return m.group(1).strip().lower()
    m = _RE_SITE_LINE.search(text)
    if m:
        return m.group(1).strip().lower()
    return None


def resolve_draft_site(
    path: str,
    ctx: DraftSiteContext,
) -> str:
    """
    sites.json / api_poster のサイトキー（chotto, takashima, fukuyama 等）を返す。

    優先順位:
      1) ファイル内の <!-- wp-poster-site:... --> または **投稿先サイト**
      2) drafts/<識別子>/ 以下のパス（site_subfolders + chotto 名付きフォルダ）
      3) それ以外の drafts/ 直下 → default_site（通常 chotto）
      4) processed/ 等: メタがなければ default_site
    """
    abs_p = os.path.normpath(os.path.abspath(path))
    ddir = os.path.normpath(ctx.drafts_dir)
    pdir = os.path.normpath(ctx.processed_dir)

    declared = read_declared_site_from_draft(abs_p)
    if declared:
        return declared

    # 有名サブフォルダ（takashima, fukuyama + 任意の chotto）
    for name in list(ctx.site_subfolders) + [ctx.chotto_subfolder]:
        sub = os.path.normpath(os.path.join(ddir, name))
        if abs_p.startswith(sub + os.sep) or abs_p == sub:
            return name

    if abs_p.startswith(ddir + os.sep) or abs_p == ddir:
        return ctx.default_site
    if abs_p.startswith(pdir + os.sep) or abs_p == pdir:
        return ctx.default_site
    # リポジトリ内の他パス
    b = os.path.normpath(ctx.base_dir)
    if abs_p.startswith(b + os.sep):
        return ctx.default_site
    return ctx.default_site


def _site_specific_drafts_from_site_detection_json(base_dir: str) -> tuple[str, ...]:
    """site_detection.json の _site_specific_drafts。無ければ api_poster 既定に合わせる。"""
    path = os.path.join(base_dir, "site_detection.json")
    if not os.path.isfile(path):
        return ("takashima", "fukuyama")
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        v = cfg.get("_site_specific_drafts")
        if isinstance(v, list) and v:
            return tuple(str(x) for x in v)
    except Exception:
        pass
    return ("takashima", "fukuyama")


def infer_site_key_from_file_arg(file_arg: str, base_dir: str) -> str:
    """
    --file のパスから sites.json キー（chotto / takashima / fukuyama）を推定。
    api_poster を import する前に --site を付ける用途。メタ（wp-poster-site）も読む。
    """
    p = (file_arg or "").strip()
    if not p:
        return "chotto"
    abs_p = os.path.normpath(p if os.path.isabs(p) else os.path.join(base_dir, p))
    ctx = DraftSiteContext(
        base_dir=base_dir,
        drafts_dir=os.path.join(base_dir, "drafts"),
        processed_dir=os.path.join(base_dir, "processed"),
        site_subfolders=_site_specific_drafts_from_site_detection_json(base_dir),
        chotto_subfolder="chotto",
        default_site="chotto",
    )
    return resolve_draft_site(abs_p, ctx)
