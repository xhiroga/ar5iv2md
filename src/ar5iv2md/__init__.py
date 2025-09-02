from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup, NavigableString
from markdownify import markdownify as md

UA = "ar5iv2md/0.1"


def _extract_arxiv_id(text: str) -> str | None:
    t = text.strip()
    if not t:
        return None

    if t.lower().startswith("arxiv:"):
        t = t.split(":", 1)[1]

    if t.startswith("http://") or t.startswith("https://"):
        p = urlparse(t)
        path = p.path or "/"
        m = re.search(r"/(?:html|abs|pdf)/([^/?#]+)", path)
        if m:
            part = m.group(1)
            if part.endswith(".pdf"):
                part = part[:-4]
            return part
        return None

    t = t.split("?", 1)[0].split("#", 1)[0]
    if t.endswith(".pdf"):
        t = t[:-4]

    if re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", t):
        return t
    if re.fullmatch(r"[a-zA-Z-]+(?:\.[a-zA-Z-]+)?/\d{7}(v\d+)?", t):
        return t
    return None


def _to_ar5iv_url(source: str) -> str:
    arxid = _extract_arxiv_id(source)
    if arxid:
        return f"https://ar5iv.org/html/{arxid}"
    if source.startswith("http://") or source.startswith("https://"):
        return source
    return f"https://ar5iv.org/html/{source}"


def _guess_basename(url: str) -> str:
    p = urlparse(url)
    # capture everything after /html/ up to ? or # (allowing '/')
    m = re.search(r"/html/([^?#]+)", p.path)
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
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30) as res:
        return res.read()


def _fetch(url: str) -> tuple[str, str]:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30) as res:
        charset = res.headers.get_content_charset() or "utf-8"
        return res.read().decode(charset, errors="replace"), res.geturl()


def _rewrite_images(soup: BeautifulSoup, base_url: str, assets_dir: Path) -> None:
    assets_dir.mkdir(parents=True, exist_ok=True)
    cache: dict[str, str] = {}
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src or src.startswith("data:"):
            continue
        abs_url = urljoin(base_url, src)
        if abs_url in cache:
            img["src"] = cache[abs_url]
            continue
        filename = os.path.basename(urlparse(abs_url).path) or "image"
        name = _unique_name(assets_dir, filename)
        try:
            data = _download(abs_url)
        except Exception as e:
            print(f"warn: failed to download image: {abs_url} ({e})", file=sys.stderr)
            continue
        rel = f"assets/{name}"
        (assets_dir / name).write_bytes(data)
        img["src"] = rel
        cache[abs_url] = rel


def _mathml_to_tex(soup: BeautifulSoup) -> None:
    for m in soup.find_all("math"):
        tex = None
        for ann in m.find_all(["annotation", "annotation-xml"]):
            enc = (ann.get("encoding") or "").lower()
            if "tex" in enc:
                tex = ann.get_text()
                break
        if tex is None:
            tex = m.get("alttext") or m.get("data-tex")
        if not tex:
            continue
        disp = (m.get("display") or "").lower()
        is_block = disp == "block"
        if not is_block:
            p = m.parent
            if p and isinstance(p, (BeautifulSoup,)) is False:
                classes = " ".join(p.get("class", []))
                if any(
                    k in classes
                    for k in ["ltx_display", "ltx_equation", "ltx_equationgroup"]
                ):
                    is_block = True
        tex = tex.strip()
        rep = f"\n$$\n{tex}\n$$\n" if (is_block or "\n" in tex) else f"${tex}$"
        m.replace_with(NavigableString(rep))


def _strip_footer(soup: BeautifulSoup) -> None:
    # Remove semantic footer blocks by class/tag.
    for el in list(
        soup.select(".ar5iv-footer, footer.ltx_page_footer, .ltx_page_footer")
    ):
        el.decompose()


def _add_md_bib_anchors(md_text: str, ids_in_order: list[str]) -> str:
    lines = md_text.splitlines()
    in_refs = False
    idx = 0
    replacements: dict[int, str] = {}
    for i, line in enumerate(lines):
        if not in_refs:
            if line.strip().lower() == "references":
                in_refs = True
            continue
        mnum = re.match(r"^[\*-] \[(\d{1,3})\]", line)
        if mnum:
            rid = f"bib.bib{mnum.group(1)}"
            mlead = re.match(r"^([\*-]\s+)(.*)$", line)
            if mlead:
                bullet, rest = mlead.group(1), mlead.group(2)
                replacements[i] = f'{bullet}<a id="{rid}" name="{rid}"></a>{rest}'
        else:
            if ids_in_order and re.match(r"^[\*-] ", line):
                if idx < len(ids_in_order):
                    rid = ids_in_order[idx]
                    idx += 1
                    mlead = re.match(r"^([\*-]\s+)(.*)$", line)
                    if mlead:
                        bullet, rest = mlead.group(1), mlead.group(2)
                        replacements[i] = (
                            f'{bullet}<a id="{rid}" name="{rid}"></a>{rest}'
                        )
    for i, new_line in replacements.items():
        lines[i] = new_line
    return "\n".join(lines) + ("\n" if not md_text.endswith("\n") else "")


def main() -> None:
    ap = argparse.ArgumentParser(prog="ar5iv2md")
    ap.add_argument("source")
    ap.add_argument("--download-dir", default=".")
    args = ap.parse_args()

    url = _to_ar5iv_url(args.source)

    try:
        html, base_url = _fetch(url)
    except Exception as e:
        print(f"failed to fetch: {e}", file=sys.stderr)
        sys.exit(1)

    soup = BeautifulSoup(html, "html.parser")
    basename = _guess_basename(url)
    base_dir = Path(args.download_dir) / basename
    # skip if target directory already has contents
    if base_dir.exists() and any(base_dir.iterdir()):
        out_path = base_dir / "README.md"
        print(str(out_path))
        print(f"warn: output directory not empty, skip: {base_dir}", file=sys.stderr)
        return
    assets_dir = base_dir / "assets"
    _strip_footer(soup)
    _rewrite_images(soup, base_url, assets_dir)
    _mathml_to_tex(soup)

    bib_ids = [
        el.get("id")
        for el in soup.find_all(id=re.compile(r"^bib\.bib\d+$"))
        if el.get("id")
    ]

    md_text = md(str(soup))
    if bib_ids:
        md_text = _add_md_bib_anchors(md_text, bib_ids)

    out_path = base_dir / "README.md"
    base_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md_text, encoding="utf-8")
    print(str(out_path))
