#!/usr/bin/env python3
"""
Fix mistaken Markdown where a body paragraph was written as H3 (###).

Common error: a short ### heading is immediately followed by another ### line
that contains a long paragraph (should be normal text, not a heading).

Usage:
  python3 tools/fix_consecutive_h3_body.py path/to/article.md
  python3 tools/fix_consecutive_h3_body.py path/to/article.md --dry-run
"""
from __future__ import annotations

import argparse
import difflib
import sys


def _prev_non_empty_h3(out: list[str]) -> bool:
    """True if the nearest non-empty line above is an H3 (### )."""
    for j in range(len(out) - 1, -1, -1):
        s = out[j].strip()
        if not s:
            continue
        return s.startswith("### ") and not s.startswith("####")
    return False


def fix_lines(lines: list[str], *, long_threshold: int = 80, ultra_long: int = 220) -> tuple[list[str], int]:
    out: list[str] = []
    changes = 0
    for line in lines:
        is_h3 = line.startswith("### ") and not line.startswith("####")
        prev_is_h3 = _prev_non_empty_h3(out)

        if is_h3 and prev_is_h3 and len(line) > long_threshold:
            out.append(line[4:])
            changes += 1
        elif is_h3 and len(line) > ultra_long:
            out.append(line[4:])
            changes += 1
        else:
            out.append(line)

    return out, changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix consecutive ### body paragraphs in Markdown drafts.")
    parser.add_argument("file", help="Path to .md file")
    parser.add_argument("--dry-run", action="store_true", help="Print unified diff only, do not write")
    parser.add_argument("--threshold", type=int, default=80, help="2nd ### line length to treat as body")
    args = parser.parse_args()

    path = args.file
    with open(path, encoding="utf-8") as f:
        content = f.read()
    bare_lines = content.split("\n")

    fixed, n = fix_lines(bare_lines, long_threshold=args.threshold)
    new_text = "\n".join(fixed)
    if content.endswith("\n"):
        new_text += "\n"

    if n == 0:
        print("No changes needed.", file=sys.stderr)
        return 0

    print(f"Demoted {n} mistaken H3 line(s).", file=sys.stderr)
    if args.dry_run:
        diff = difflib.unified_diff(
            content.splitlines(True),
            new_text.splitlines(True),
            fromfile="before",
            tofile="after",
        )
        sys.stdout.writelines(diff)
        return 0

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_text)
    print(f"Updated: {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
