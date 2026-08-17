#!/usr/bin/env python3
"""
Combine a directory of HTML help files into a single Markdown document.

Built for FPWin Pro 7 help content (CHM extractions or saved InfoHub pages),
but works on any HTML doc tree.

Usage
-----
    python tools/html_to_md.py --input ./help --output docs/fpwin_help.md

    # keep tables, drop the nav sidebar and any block seen more than twice
    python tools/html_to_md.py -i ./help -o out.md --dedupe 2

    # see what would be produced without writing
    python tools/html_to_md.py -i ./help -o out.md --dry-run

Extracting a .chm first
-----------------------
    7z x FPWinPro7.chm -o./help          # Windows / Linux with p7zip
    # or on Linux:  extract_chmLib FPWinPro7.chm ./help

Dependencies
------------
    pip install beautifulsoup4 markdownify
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections import Counter
from pathlib import Path

try:
    from bs4 import BeautifulSoup, Comment
    from markdownify import markdownify
except ImportError:
    sys.exit(
        "Missing dependencies. Install them with:\n"
        "    pip install beautifulsoup4 markdownify"
    )


# Elements that are page furniture, never content.
_STRIP_TAGS = [
    "script", "style", "noscript", "nav", "header", "footer",
    "iframe", "form", "button", "svg",
]

# CSS selectors commonly used for nav chrome in CHM/help exports.
_STRIP_SELECTORS = [
    "#nav", "#navigation", "#sidebar", "#toc", "#breadcrumb", "#breadcrumbs",
    ".nav", ".navigation", ".sidebar", ".toc", ".breadcrumb", ".breadcrumbs",
    ".menu", ".site-header", ".site-footer", ".cookie", ".cookie-banner",
    ".privacy", ".skip-link", ".back-to-top",
]

_ENCODINGS = ("utf-8-sig", "utf-8", "windows-1252", "cp1252", "latin-1")


def read_html(path: Path) -> str:
    """Read a file, trying the encodings CHM exports actually use."""
    raw = path.read_bytes()
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def clean_soup(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(_STRIP_TAGS):
        tag.decompose()

    for selector in _STRIP_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()

    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    return soup


def page_title(soup: BeautifulSoup, path: Path) -> str:
    for sel in ("h1", "title", "h2"):
        el = soup.find(sel)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)
    return path.stem


def to_markdown(soup: BeautifulSoup) -> str:
    body = soup.body or soup
    md = markdownify(str(body), heading_style="ATX", bullets="-")
    md = re.sub(r"\n{3,}", "\n\n", md)          # collapse blank-line runs
    md = re.sub(r"[ \t]+\n", "\n", md)          # trailing whitespace
    # markdownify escapes _ and * — that mangles instruction names like F0_MV
    # and makes the output non-greppable. Unescape them.
    md = re.sub(r"\\([_*])", r"\1", md)
    return md.strip()


def block_key(block: str) -> str:
    """Normalised hash of a block, for duplicate detection."""
    norm = re.sub(r"\s+", " ", block).strip().lower()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


def split_blocks(md: str) -> list[str]:
    return [b for b in md.split("\n\n") if b.strip()]


# Boilerplate is short and prose-like. Real content — tables, code, long
# paragraphs — must never be deduped even when it repeats across pages,
# because operand tables and shared error notes are exactly what we want.
_DEDUPE_MAX_CHARS = 300


def dedupe_candidate(block: str) -> bool:
    """True if *block* is eligible for boilerplate removal."""
    if len(block) > _DEDUPE_MAX_CHARS:
        return False
    if "|" in block:            # markdown table
        return False
    if "```" in block:          # code fence
        return False
    if block.lstrip().startswith(("    ", "\t")):   # indented code
        return False
    if block.lstrip().startswith("#"):             # heading
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Combine a tree of HTML help files into one Markdown file.",
    )
    ap.add_argument("-i", "--input", required=True, type=Path,
                    help="Directory containing .html/.htm files (searched recursively).")
    ap.add_argument("-o", "--output", required=True, type=Path,
                    help="Output .md file.")
    ap.add_argument("--dedupe", type=int, default=0, metavar="N",
                    help="Drop short prose blocks appearing more than N times across "
                         "all pages (nav leftovers, copyright footers). Tables, code "
                         "and blocks over 300 chars are never dropped. Off by default; "
                         "try 2 if the output is full of repeated chrome. Note it can "
                         "also remove legitimately repeated short notes.")
    ap.add_argument("--min-chars", type=int, default=200, metavar="N",
                    help="Skip pages whose converted text is shorter than N chars "
                         "(default 200) — filters stubs and 'Not Found' pages.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would be written without creating the file.")
    args = ap.parse_args()

    if not args.input.is_dir():
        sys.exit(f"Not a directory: {args.input}")

    files = sorted(
        p for p in args.input.rglob("*")
        if p.suffix.lower() in (".html", ".htm")
    )
    if not files:
        sys.exit(f"No .html/.htm files found under {args.input}")

    print(f"Found {len(files)} HTML file(s)")

    # Pass 1 — convert everything
    pages: list[tuple[str, str, Path]] = []   # (title, markdown, path)
    skipped_short = 0
    for path in files:
        try:
            soup = clean_soup(read_html(path))
        except Exception as exc:                      # noqa: BLE001
            print(f"  ! {path.name}: {exc}", file=sys.stderr)
            continue

        md = to_markdown(soup)
        if len(md) < args.min_chars:
            skipped_short += 1
            continue
        pages.append((page_title(soup, path), md, path))

    print(f"  {len(pages)} page(s) with content, {skipped_short} skipped as too short")

    # Pass 2 — find boilerplate blocks repeated across pages
    dropped_blocks = 0
    if args.dedupe > 0:
        counts: Counter[str] = Counter()
        for _, md, _ in pages:
            for block in set(split_blocks(md)):       # once per page
                if dedupe_candidate(block):
                    counts[block_key(block)] += 1
        boilerplate = {k for k, c in counts.items() if c > args.dedupe}

        cleaned: list[tuple[str, str, Path]] = []
        for title, md, path in pages:
            keep = []
            for block in split_blocks(md):
                if dedupe_candidate(block) and block_key(block) in boilerplate:
                    dropped_blocks += 1
                    continue
                keep.append(block)
            cleaned.append((title, "\n\n".join(keep), path))
        pages = cleaned
        print(f"  dropped {dropped_blocks} repeated boilerplate block(s) "
              f"({len(boilerplate)} distinct)")

    # Assemble
    root = args.input.resolve()
    out: list[str] = [
        f"# {root.name} — combined help",
        "",
        f"Generated from {len(pages)} HTML page(s) in `{root}`.",
        "",
        "---",
        "",
    ]
    for title, md, path in pages:
        rel = path.relative_to(root)
        out.append(f"## {title}")
        out.append("")
        out.append(f"*Source: `{rel}`*")
        out.append("")
        out.append(md)
        out.append("")
        out.append("---")
        out.append("")

    result = "\n".join(out)
    size_kb = len(result.encode("utf-8")) / 1024

    if args.dry_run:
        print(f"\n[dry-run] would write {size_kb:.0f} KB to {args.output}")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result, encoding="utf-8")
    print(f"\nWrote {args.output}  ({size_kb:.0f} KB, {len(pages)} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
