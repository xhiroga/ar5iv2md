from __future__ import annotations

import argparse
import mimetypes
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
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


def _unique_name(directory: Path, base: str) -> str:
    stem, ext = os.path.splitext(base)
    if not ext:
        ext = ".bin"
    candidate = f"{stem}{ext}"
    i = 1
    while (directory / candidate).exists():
        candidate = f"{stem}-{i}{ext}"
        i += 1
    return candidate


def _download(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "ar5iv2md/0.1"})
    with urlopen(req, timeout=30) as res:
        return res.read()


def main() -> None:
    ap = argparse.ArgumentParser(prog="ar5iv2md")
    ap.add_argument("source")
    ap.add_argument("--download-dir", default=".")
    args = ap.parse_args()

    url = _to_ar5iv_url(args.source)

    try:
        req = Request(url, headers={"User-Agent": "ar5iv2md/0.1"})
        with urlopen(req, timeout=30) as res:
            charset = res.headers.get_content_charset() or "utf-8"
            html = res.read().decode(charset, errors="replace")
            base_url = res.geturl()
    except Exception as e:
        print(f"failed to fetch: {e}", file=sys.stderr)
        sys.exit(1)

    soup = BeautifulSoup(html, "html.parser")

    basename = _guess_basename(url)
    base_dir = Path(args.download_dir) / basename
    assets_dir = base_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src or src.startswith("data:"):
            continue
        abs_url = urljoin(base_url, src)
        filename = os.path.basename(urlparse(abs_url).path)
        if not filename:
            filename = "image"
        name = _unique_name(assets_dir, filename)
        try:
            data = _download(abs_url)
        except Exception as e:
            print(f"warn: failed to download image: {abs_url} ({e})", file=sys.stderr)
            continue
        (assets_dir / name).write_bytes(data)
        img["src"] = f"assets/{name}"

    md_text = md(str(soup))

    out_path = base_dir / "README.md"
    base_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md_text, encoding="utf-8")
    print(str(out_path))
