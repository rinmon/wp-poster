#!/usr/bin/env python3
"""
投稿前の重複チェック: api_poster と同じタイトル正規化で、ローカル（drafts/processed/サイト別）
と WordPress（publish/future/draft/private の同一タイトル）を確認する。

api_poster は import 時に sys.argv を解釈するため、先に --site だけ抽出してから読み込む。
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))


def _argv_for_api_poster_import(full_argv: list[str]) -> list[str]:
    """--site のみ api_poster に渡す（chotto 既定かつ未指定なら site 行を付けず、起動時の余計な出力を避ける）。"""
    prog = full_argv[0] if full_argv else "check_article_duplicates.py"
    site = None
    i = 1
    while i < len(full_argv):
        if full_argv[i] == "--site" and i + 1 < len(full_argv):
            site = full_argv[i + 1]
            i += 2
            continue
        i += 1
    if site:
        return [prog, "--site", site]
    return [prog]


_saved_argv = sys.argv[:]
sys.argv = _argv_for_api_poster_import(_saved_argv)

from api_poster import (  # noqa: E402
    DRAFTS_DIR,
    PROCESSED_DIR,
    WP_API_URL,
    _get_site_specific_drafts,
    _normalize_title_for_duplicate,
    _normalize_title_from_first_line,
    find_local_duplicate_title,
    post_exists_with_hints,
    post_exists_with_title,
)
from duplicate_hints import (  # noqa: E402
    DEFAULT_HINT_DUPLICATE_THRESHOLD,
    collect_tag_sharing_similarity_pairs,
    find_local_hint_duplicate,
    parse_draft_hints_from_path,
)

sys.argv = _saved_argv


def _iter_local_md_paths():
    dirs = [DRAFTS_DIR, PROCESSED_DIR]
    for name in _get_site_specific_drafts():
        dirs.append(os.path.join(BASE, "drafts", name))
    for folder in dirs:
        if not os.path.isdir(folder):
            continue
        for path in glob.glob(os.path.join(folder, "*.md")):
            bn = os.path.basename(path).upper()
            if bn == "README_DRAFTS.MD" or bn.startswith("."):
                continue
            yield path


def _title_from_md(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            first = f.readline()
    except OSError:
        return None
    return _normalize_title_from_first_line(first).strip() or None


def collect_local_duplicate_groups() -> dict[str, list[str]]:
    """正規化タイトル -> ファイルパス一覧（2件以上がローカル重複）"""
    key_paths: dict[str, list[str]] = {}
    for path in sorted(_iter_local_md_paths()):
        title = _title_from_md(path)
        if not title:
            continue
        k = _normalize_title_for_duplicate(title)
        if not k:
            continue
        key_paths.setdefault(k, []).append(path)
    return {k: v for k, v in key_paths.items() if len(v) > 1}


def run_scheduled_future_duplicate_check() -> bool:
    """list_duplicate_scheduled と同様: future 同タイトルが複数件あるか"""
    all_posts = []
    page = 1
    from api_poster import api_request

    while True:
        posts = api_request(
            f"posts?status=future&per_page=100&page={page}&_fields=id,title,date,status"
        )
        if not posts:
            break
        all_posts.extend(posts)
        if len(posts) < 100:
            break
        page += 1

    if not all_posts:
        print("予約投稿（future）: なし\n")
        return True

    by_title: dict[str, list] = {}
    for p in all_posts:
        title_obj = p.get("title") or {}
        title = title_obj.get("raw") or title_obj.get("rendered", "").replace("&#8211;", "–")
        if title not in by_title:
            by_title[title] = []
        by_title[title].append(p)

    dups = {t: plist for t, plist in by_title.items() if len(plist) > 1}
    if not dups:
        print(f"予約投稿（future）: {len(all_posts)} 件 — 同一タイトルの重複なし\n")
        return True

    print(f"⚠️  予約投稿（future）で同一タイトルが {len(dups)} 件あります:\n")
    for title, plist in dups.items():
        tshow = title[:50] + ("..." if len(title) > 50 else "")
        print(f"【{tshow}】")
        for i, p in enumerate(sorted(plist, key=lambda x: x.get("date", ""))):
            pid = p.get("id")
            date = (p.get("date", "") or "")[:19].replace("T", " ")
            mark = "★残す候補" if i == 0 else "→削除候補"
            print(f"  ID:{pid}  {date}  {mark}")
        print()
    return False


def _hint_draft_dirs() -> list[str]:
    d = [DRAFTS_DIR, PROCESSED_DIR]
    for name in _get_site_specific_drafts():
        d.append(os.path.join(BASE, "drafts", name))
    return d


def check_one(title: str, exclude_path: str | None, site_label: str) -> int:
    """単一ファイル/タイトル: ローカル（タイトル・タグ・抜粋）→ WP の順。重複があれば exit 1"""
    t = title.strip()
    if not t:
        print("タイトルが空です。", file=sys.stderr)
        return 2

    print(f"サイト: [{site_label}] {WP_API_URL}")
    print(f"タイトル: {t}")
    print(
        f"重複判定: タイトル正規化一致 または 類似度 >= {DEFAULT_HINT_DUPLICATE_THRESHOLD} "
        f"（タイトル・タグ・メタディスクリプション。環境変数 DUP_HINT_THRESHOLD で変更可）\n"
    )

    code = 0
    hints = None
    if exclude_path and os.path.isfile(exclude_path):
        hints = parse_draft_hints_from_path(exclude_path)
        local_hint = find_local_hint_duplicate(
            hints, exclude_path, _hint_draft_dirs(), threshold=DEFAULT_HINT_DUPLICATE_THRESHOLD
        )
    else:
        local_hint = None
    if local_hint:
        o_path, sc = local_hint
        print("❌ ローカル重複候補: 別 .md がタイトル一致、またはタグ・抜粋が近い")
        print(f"    → {o_path}（類似度 {sc:.2f}）")
        code = 1
    else:
        if exclude_path and os.path.isfile(exclude_path):
            print("✅ ローカル: 重複候補の別ファイルなし（タイトル・タグ・抜粋）")
        else:
            local_other = find_local_duplicate_title(t, exclude_path or "")
            if local_other:
                print("❌ ローカル: 同一（正規化）タイトルの別ファイルあり")
                print(f"    → {local_other}")
                code = 1
            else:
                print("✅ ローカル: 同一タイトルの別ファイルなし（--title のみのためタグ比較は未実施）")

    if hints is not None:
        wp_h = post_exists_with_hints(hints)
        if wp_h:
            wid, reason = wp_h
            print(f"❌ WordPress: 重複候補（{reason}） post ID: {wid}")
            code = 1
        else:
            print("✅ WordPress: 重複候補なし（publish/future/draft/private）")
    else:
        wp_id = post_exists_with_title(t)
        if wp_id:
            print(f"❌ WordPress: 既に同一タイトルの投稿があります（post ID: {wp_id}）")
            code = 1
        else:
            print("✅ WordPress: 同一タイトル未検出（--title のみ; タグ抜粋は未使用）")

    return code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="記事タイトルの重複チェック（ローカル md + WordPress）。api_poster と同一ロジック。"
    )
    parser.add_argument("--site", default=None, help="sites.json のサイトキー（chotto / takashima / fukuyama 等）")
    parser.add_argument("--file", "-f", help="ドラフト .md（1行目をタイトルとして検査）")
    parser.add_argument("--title", "-t", help="ファイルなしでタイトル文字列だけ検査")
    parser.add_argument(
        "--scan-drafts",
        action="store_true",
        help="drafts/processed/サイト別の全 .md を走査し、ローカル同タイトルグループを表示",
    )
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="予約投稿（future）の同一タイトル重複も確認（list_duplicate_scheduled 相当）。他モードと併用可",
    )
    args = parser.parse_args()

    if bool(args.file) + bool(args.title) + bool(args.scan_drafts) > 1:
        print("--file / --title / --scan-drafts は同時に指定しないでください。", file=sys.stderr)
        return 2

    site_label = args.site or "chotto（既定）"
    exit_code = 0

    def run_scheduled_block():
        nonlocal exit_code
        print("=" * 60)
        print("予約投稿（future）のタイトル重複")
        print("=" * 60)
        if not run_scheduled_future_duplicate_check():
            exit_code = 1

    if args.scan_drafts:
        print("=" * 60)
        print("ローカル全 .md のタイトル重複（正規化一致）")
        print("=" * 60)
        groups = collect_local_duplicate_groups()
        if not groups:
            print("✅ ローカルに同一タイトル（正規化）の重複ファイルはありません。\n")
        else:
            exit_code = 1
            print(f"⚠️  {len(groups)} 組の重複があります:\n")
            for k, paths in sorted(groups.items(), key=lambda x: x[0]):
                print(f"「{k[:60]}{'...' if len(k) > 60 else ''}」")
                for p in paths:
                    print(f"  - {p}")
                t0 = _title_from_md(paths[0])
                wid = post_exists_with_title(t0) if t0 else None
                if wid:
                    print(f"  WordPress には既に同一タイトル相当の投稿があります（ID: {wid}）")
                print()
        print("=" * 60)
        print("タグを共有する .md 同士の重複候補（タイトル・タグ・抜粋）")
        print("=" * 60)
        hint_dirs = _hint_draft_dirs()
        pairs = collect_tag_sharing_similarity_pairs(
            hint_dirs, threshold=DEFAULT_HINT_DUPLICATE_THRESHOLD
        )
        if not pairs:
            print(
                f"✅ 閾値 {DEFAULT_HINT_DUPLICATE_THRESHOLD} 以上の重複候補ペアはありません"
                f"（少なくとも1タグ共有のペアのみ比較）。\n"
            )
        else:
            exit_code = 1
            print(
                f"⚠️  {len(pairs)} 件の重複候補ペア（共有タグ経由。同一タイトル以外も含みます）:\n"
            )
            for a, b, sc in pairs:
                print(f"  類似度 {sc:.2f}")
                print(f"    {a}")
                print(f"    {b}\n")
        if args.scheduled:
            run_scheduled_block()
        return exit_code

    if args.file:
        path = os.path.abspath(args.file)
        if not os.path.isfile(path):
            print(f"ファイルがありません: {path}", file=sys.stderr)
            return 2
        title = _title_from_md(path)
        if not title:
            print("1行目からタイトルを読めませんでした。", file=sys.stderr)
            return 2
        print("=" * 60)
        print("単一ファイルの重複チェック")
        print("=" * 60)
        exit_code = check_one(title, path, site_label)
        if args.scheduled:
            print()
            run_scheduled_block()
        return exit_code

    if args.title:
        print("=" * 60)
        print("タイトル文字列の重複チェック")
        print("=" * 60)
        exit_code = check_one(args.title, None, site_label)
        if args.scheduled:
            print()
            run_scheduled_block()
        return exit_code

    if args.scheduled:
        run_scheduled_block()
        return exit_code

    parser.print_help()
    print(
        "\n例:\n"
        "  python3 check_article_duplicates.py --file drafts/foo.md\n"
        "  python3 check_article_duplicates.py --file drafts/foo.md --scheduled\n"
        "  python3 check_article_duplicates.py --title '記事タイトル'\n"
        "  python3 check_article_duplicates.py --site takashima --file drafts/takashima/foo.md\n"
        "  python3 check_article_duplicates.py --scan-drafts\n"
        "  python3 check_article_duplicates.py --scheduled\n",
        end="",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
