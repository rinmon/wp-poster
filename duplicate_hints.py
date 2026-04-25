"""
タイトル・タグ・メタディスクリプション（抜粋）を用いた重複候補検出。
api_poster / check_article_duplicates から利用する。純粋関数中心（api_poster を import しない）。
"""
from __future__ import annotations

import glob
import os
import re
import unicodedata
import difflib
from dataclasses import dataclass, field
from typing import Optional

# この値以上で「重複候補」とみなす（調整可）
DEFAULT_HINT_DUPLICATE_THRESHOLD = float(
    os.environ.get("DUP_HINT_THRESHOLD", "0.74")
)

# WP search の 1 リクエストあたりの候補件数（小さく保つ）
WP_HINT_SEARCH_PER_PAGE = int(os.environ.get("DUP_HINT_SEARCH_PER_PAGE", "18"))


@dataclass
class DraftHints:
    title: str
    tags: list[str] = field(default_factory=list)
    excerpt: str = ""  # メタディスクリプション。無い場合は本文先頭からの短い抜粋


def _strip_outer_md_title_emphasis(s: str) -> str:
    t = unicodedata.normalize("NFKC", (s or "").strip())
    outer = re.compile(r"^\*{2}(.+)\*{2}$", re.DOTALL)
    for _ in range(6):
        m = outer.fullmatch(t)
        if not m:
            break
        inner = m.group(1).strip()
        if not inner or inner == t:
            break
        t = inner
    return t


def _title_from_first_line(line: str) -> str:
    t = (line or "").strip()
    if t.startswith("\ufeff"):
        t = t.lstrip("\ufeff").strip()
    if t.startswith("# "):
        t = t[2:].strip()
    return _strip_outer_md_title_emphasis(t)


def _norm_title(s: str) -> str:
    if not s:
        return ""
    t = unicodedata.normalize("NFKC", str(s).strip())
    t = _strip_outer_md_title_emphasis(t)
    return " ".join(t.split())


def _norm_excerpt(s: str) -> str:
    if not s:
        return ""
    t = unicodedata.normalize("NFKC", s).strip()
    t = re.sub(r"\s+", " ", t)
    return t[:2000]


def normalize_excerpt_for_hint(s: str) -> str:
    """WordPress excerpt 等をヒント比較用に正規化（外部呼び出し用）。"""
    return _norm_excerpt(s)


def _parse_taxonomy_line(s: str) -> tuple[Optional[str], str]:
    s = unicodedata.normalize("NFKC", (s or "").strip())
    patterns = (
        (r"^([*＊]{2,}\s*タグ\s*[*＊]{0,}\s*[:：]?)\s*(.*)$", "tags"),
        (r"^([*＊]{2,}\s*カテゴリ\s*[*＊]{0,}\s*[:：]?)\s*(.*)$", "categories"),
        (r"^([*＊]{2,}\s*メタディスクリプション\s*[*＊]{0,}\s*[:：]?)\s*(.*)$", "meta"),
    )
    for pat, kind in patterns:
        m = re.match(pat, s, flags=re.DOTALL)
        if m:
            return kind, (m.group(2) or "").strip()
    return None, ""


def _split_tags(s: str) -> list[str]:
    if not s:
        return []
    parts = re.split(r"[,、，]\s*", s)
    return [unicodedata.normalize("NFKC", p).strip() for p in parts if p and p.strip()]


def _body_excerpt_fallback(text: str, max_len: int = 320) -> str:
    """メタが無いとき: IMAGE_BLOCK と先頭 # 行を除いた本文の先頭。"""
    t = text
    t = re.sub(r"\[IMAGE_BLOCK\].*?\[/IMAGE_BLOCK\]\s*", "", t, flags=re.DOTALL)
    lines = t.split("\n")
    i = 0
    if lines and lines[0].strip().startswith("# "):
        i = 1
    buf = []
    for line in lines[i:]:
        s = line.strip()
        if not s:
            continue
        if s.startswith("## ") or s.startswith("**タグ**") or s.startswith("**カテゴリ**"):
            break
        buf.append(s)
        if len("".join(buf)) >= max_len:
            break
    ex = " ".join(buf)
    return _norm_excerpt(ex[:max_len])


def parse_draft_hints_from_text(content: str) -> DraftHints:
    if not content or not content.strip():
        return DraftHints(title="")
    lines = content.splitlines()
    title = _title_from_first_line(lines[0]) if lines else ""

    tag_buf: list[str] = []
    meta_buf: list[str] = []

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        k, rest = _parse_taxonomy_line(line)
        if k == "tags":
            if rest:
                tag_buf.append(rest)
            i += 1
            while i < n:
                line2 = lines[i]
                k2, r2 = _parse_taxonomy_line(line2)
                if k2:
                    break
                if line2.strip():
                    tag_buf.append(line2.strip())
                i += 1
            continue
        if k == "meta":
            if rest:
                meta_buf.append(rest)
            i += 1
            while i < n:
                line2 = lines[i]
                k2, r2 = _parse_taxonomy_line(line2)
                if k2:
                    break
                if line2.strip():
                    meta_buf.append(line2.strip())
                i += 1
            continue
        i += 1

    raw_tags = _split_tags(" ".join(tag_buf))
    seen: set[str] = set()
    tags: list[str] = []
    for t in raw_tags:
        if not t or t in seen:
            continue
        seen.add(t)
        tags.append(t)

    excerpt = _norm_excerpt(" ".join(meta_buf))
    if not excerpt:
        excerpt = _body_excerpt_fallback(content)

    return DraftHints(title=title, tags=tags, excerpt=excerpt)


def read_draft_for_hint_metadata(path: str) -> str:
    """
    重複ヒント用にテキストを読む。末尾に **タグ** / メタがある前提で、
    大きい .md は先頭＋末尾だけ読み、全件フルスキャンを避ける（効率用）。
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return ""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return ""
    if size <= 120_000:
        return raw.decode("utf-8", errors="ignore")
    head = raw[:12_000].decode("utf-8", errors="ignore")
    tail = raw[-45_000:].decode("utf-8", errors="ignore")
    return head + "\n" + tail


def parse_draft_hints_from_path(path: str, max_bytes: int = 400_000) -> DraftHints:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            chunk = f.read(max_bytes + 1)
    except OSError:
        return DraftHints(title="")
    if len(chunk) > max_bytes:
        chunk = chunk[:max_bytes]
    return parse_draft_hints_from_text(chunk)


def parse_draft_hints_for_duplicate_scan(path: str) -> DraftHints:
    """ローカル重複・スキャン専用。大ファイルは先頭＋末尾読み。"""
    text = read_draft_for_hint_metadata(path)
    if not text:
        return DraftHints(title="")
    return parse_draft_hints_from_text(text)


def _seq_ratio(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def tag_jaccard(ta: list[str], tb: list[str]) -> float:
    sa = {unicodedata.normalize("NFKC", x).strip() for x in ta if x and x.strip()}
    sb = {unicodedata.normalize("NFKC", x).strip() for x in tb if x and x.strip()}
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def hint_duplicate_score(a: DraftHints, b: DraftHints, *, threshold: float = DEFAULT_HINT_DUPLICATE_THRESHOLD) -> float:
    """
    0〜1。threshold 以上で重複候補。タイトル完全一致相当は呼び出し側で先に判定。
    """
    t1 = _norm_title(a.title)
    t2 = _norm_title(b.title)
    title_r = _seq_ratio(t1, t2)

    e1 = _norm_excerpt(a.excerpt)
    e2 = _norm_excerpt(b.excerpt)
    ex_r = _seq_ratio(e1, e2) if (e1 or e2) else 1.0 if not e1 and not e2 else 0.0

    j = tag_jaccard(a.tags, b.tags)

    if not a.tags and not b.tags:
        w_t, w_e = 0.55, 0.45
        return w_t * title_r + w_e * ex_r

    if a.tags and b.tags and j == 0.0:
        # タグが明示的に交わらない: 抜粋の近さを重視
        return 0.3 * title_r + 0.1 * j + 0.6 * ex_r

    return 0.35 * title_r + 0.35 * j + 0.3 * ex_r


def is_hint_duplicate(
    a: DraftHints, b: DraftHints, *, threshold: float = DEFAULT_HINT_DUPLICATE_THRESHOLD
) -> bool:
    if _norm_title(a.title) and _norm_title(a.title) == _norm_title(b.title):
        return True
    return hint_duplicate_score(a, b, threshold=threshold) >= threshold


def _filter_paths_for_compare(
    hints: DraftHints, other_path: str, other: DraftHints
) -> bool:
    """比較コスト削減: 明らかに無関係なペアをスキップ。"""
    if _norm_title(hints.title) == _norm_title(other.title):
        return True
    if hints.tags and other.tags:
        sa = {x.strip() for x in hints.tags}
        sb = {x.strip() for x in other.tags}
        if sa & sb:
            return True
    # タグ片方空: タイトル接頭辞が近いか、抜粋が少しでも重なる
    p1 = _norm_title(hints.title)[:24]
    p2 = _norm_title(other.title)[:24]
    if p1 and p2 and (p1 in p2 or p2 in p1 or _seq_ratio(p1, p2) >= 0.55):
        return True
    if hints.excerpt and other.excerpt:
        if _seq_ratio(hints.excerpt[:80], other.excerpt[:80]) >= 0.25:
            return True
    return False


def wp_search_phrase(h: DraftHints) -> str:
    """WordPress /posts?search= に渡す短い語（効率用）。"""
    t = _norm_title(h.title)
    if len(t) >= 4:
        return t[: min(50, len(t))]
    if h.tags:
        return h.tags[0][: min(50, len(h.tags[0]))]
    e = h.excerpt.strip()
    if len(e) >= 4:
        return e[:40]
    return t


def _pairwise_paths_for_tag(
    paths: list[str], by_path: dict[str, DraftHints], max_direct: int = 48
) -> list[tuple[str, str]]:
    """巨大タグではタイトル先頭のバケット化でペア数を抑える。"""
    if len(paths) <= max_direct:
        out = []
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                out.append((paths[i], paths[j]))
        return out
    buckets: dict[str, list[str]] = {}
    for p in paths:
        key = _norm_title(by_path[p].title)[:12] or p[:8]
        buckets.setdefault(key, []).append(p)
    out = []
    for plist in buckets.values():
        for i in range(len(plist)):
            for j in range(i + 1, len(plist)):
                out.append((plist[i], plist[j]))
    return out


def collect_tag_sharing_similarity_pairs(
    draft_dirs: list[str], *, threshold: float = DEFAULT_HINT_DUPLICATE_THRESHOLD
) -> list[tuple[str, str, float]]:
    """
    少なくとも1つタグを共有する .md ペアのみを比較（全件×全件を避ける）。
    戻り値: (path_a, path_b, score) 降順ではない
    """
    by_path: dict[str, DraftHints] = {}
    for folder in draft_dirs:
        if not os.path.isdir(folder):
            continue
        for path in glob.glob(os.path.join(folder, "*.md")):
            bn = os.path.basename(path).upper()
            if bn == "README_DRAFTS.MD" or bn.startswith("."):
                continue
            by_path[path] = parse_draft_hints_for_duplicate_scan(path)
    tag_to_paths: dict[str, list[str]] = {}
    for p, h in by_path.items():
        for t in h.tags:
            tag_to_paths.setdefault(t, []).append(p)
    out: set[tuple[str, str, float]] = set()
    checked: set[tuple[str, str]] = set()
    for _t, plist in tag_to_paths.items():
        for a, b in _pairwise_paths_for_tag(list(dict.fromkeys(plist)), by_path):
            key = tuple(sorted((a, b)))
            if key in checked:
                continue
            checked.add(key)
            ha, hb = by_path[a], by_path[b]
            if not _filter_paths_for_compare(ha, b, hb):
                continue
            sc = hint_duplicate_score(ha, hb)
            if sc >= threshold:
                out.add((a, b, round(sc, 4)))
    return sorted(
        ((a, b, s) for (a, b, s) in out), key=lambda x: -x[2]
    )


def find_local_hint_duplicate(
    hints: DraftHints,
    exclude_path: str,
    draft_dirs: list[str],
    *,
    threshold: float = DEFAULT_HINT_DUPLICATE_THRESHOLD,
) -> Optional[tuple[str, float]]:
    """
    他の .md とヒント重複を検査。戻り値: (相手パス, スコア) または None
    """
    if not _norm_title(hints.title) and not hints.tags and not hints.excerpt:
        return None
    excl = os.path.abspath(exclude_path) if exclude_path else ""

    for folder in draft_dirs:
        if not os.path.isdir(folder):
            continue
        for path in glob.glob(os.path.join(folder, "*.md")):
            if os.path.abspath(path) == excl:
                continue
            bn = os.path.basename(path).upper()
            if bn == "README_DRAFTS.MD" or bn.startswith("."):
                continue
            try:
                oth = parse_draft_hints_for_duplicate_scan(path)
            except Exception:
                continue
            if not _filter_paths_for_compare(hints, path, oth):
                continue
            if _norm_title(hints.title) and _norm_title(hints.title) == _norm_title(oth.title):
                return (path, 1.0)
            sc = hint_duplicate_score(hints, oth, threshold=threshold)
            if sc >= threshold:
                return (path, sc)
    return None


__all__ = [
    "DraftHints",
    "DEFAULT_HINT_DUPLICATE_THRESHOLD",
    "WP_HINT_SEARCH_PER_PAGE",
    "parse_draft_hints_from_text",
    "parse_draft_hints_from_path",
    "parse_draft_hints_for_duplicate_scan",
    "read_draft_for_hint_metadata",
    "hint_duplicate_score",
    "is_hint_duplicate",
    "find_local_hint_duplicate",
    "tag_jaccard",
    "normalize_excerpt_for_hint",
    "wp_search_phrase",
]
