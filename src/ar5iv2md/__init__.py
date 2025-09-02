from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from markdownify import markdownify as md


def _to_ar5iv_url(source: str) -> str:
    if source.startswith("http://") or source.startswith("https://"):
        return source
    return f"https://ar5iv.org/html/{source}"


def _guess_basename(url: str) -> str:
    p = urlparse(url)
    m = re.search(r"/html/([^/?#]+)", p.path)
    if m:
        return m.group(1).replace("/", "_")
    return Path(p.path).name or "ar5iv"


def main() -> None:
    ap = argparse.ArgumentParser(prog="ar5iv2md")
    ap.add_argument("source")
    ap.add_argument("--output-dir", default=".")
    args = ap.parse_args()

    url = _to_ar5iv_url(args.source)

    try:
        req = Request(url, headers={"User-Agent": "ar5iv2md/0.1"})
        with urlopen(req) as res:
            charset = res.headers.get_content_charset() or "utf-8"
            html = res.read().decode(charset, errors="replace")
    except Exception as e:
        print(f"failed to fetch: {e}", file=sys.stderr)
        sys.exit(1)

    md_text = md(html)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{_guess_basename(url)}.md"
    out_path.write_text(md_text, encoding="utf-8")
    print(str(out_path))
