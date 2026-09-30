"""Pull every URL out of a PDF.

Three sources, tried in order of reliability:

1. Link annotations - the clickable hyperlinks a proper InDesign
   "Adobe PDF (Interactive)" export keeps. Exact URLs.
2. Text layer - URLs printed as text on a page that still has real text.
3. OCR - for flattened PDFs (e.g. "Microsoft: Print To PDF") where every
   page is an image. Recovers printed URLs only; clickable anchor text
   ("Read More", "Office of Budget") loses its target when a PDF is
   flattened, and no tool can get it back from the image.

Each hit is returned as a Link record with the page it came from and the
method that found it, so the report shows how much to trust each row.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>\"'()\[\]{}|\\^`]+", re.IGNORECASE
)
TRAILING_JUNK = ".,;:!?'\")]}>"


@dataclass
class Link:
    url: str
    page: int
    method: str  # annotation | text | ocr | manifest
    anchor: str = ""
    raw: str = field(default="", repr=False)


def normalize_url(raw: str) -> str:
    """Clean a URL candidate, including common OCR slips."""
    url = raw.strip().rstrip(TRAILING_JUNK)
    # OCR frequently reads "?" in a query string as "I" or "l"
    # e.g. hr-contactsIc=All -> hr-contacts?ic=All
    url = re.sub(r"([a-z0-9-])[Il]([a-z]{1,10}=)", r"\1?\2", url)
    if url.lower().startswith("www."):
        url = "https://" + url
    url = re.sub(r"^(https?):/(?!/)", r"\1://", url, flags=re.IGNORECASE)
    return url


def find_urls(text: str) -> list[str]:
    return [normalize_url(m.group(0)) for m in URL_RE.finditer(text or "")]


def drop_truncated(urls: set[str]) -> set[str]:
    """When OCR passes disagree, one often reads a URL only partway
    (https://www.nih.gov/ vs https://www.nih.gov/research-training/...).
    Drop any URL that is a strict prefix of another found on the same page."""
    return {u for u in urls if not any(o != u and o.startswith(u) for o in urls)}


def from_annotations(reader: PdfReader) -> list[Link]:
    links: list[Link] = []
    for i, page in enumerate(reader.pages, start=1):
        annots = page.get("/Annots")
        annots = annots.get_object() if annots is not None else []
        for annot in annots or []:
            obj = annot.get_object()
            action = obj.get("/A")
            if action is None:
                continue
            uri = action.get_object().get("/URI")
            if uri:
                links.append(Link(url=str(uri).strip(), page=i, method="annotation"))
    return links


def from_text_layer(reader: PdfReader) -> tuple[list[Link], int]:
    """Return links found in the text layer and how many pages had any text."""
    links: list[Link] = []
    pages_with_text = 0
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages_with_text += 1
        for url in find_urls(text):
            links.append(Link(url=url, page=i, method="text"))
    return links, pages_with_text


def _ocr(image_path: Path, psm: int) -> str:
    result = subprocess.run(
        ["tesseract", str(image_path), "-", "--psm", str(psm)],
        capture_output=True, text=True, check=False,
        env={**os.environ, "OMP_THREAD_LIMIT": "1"},
    )
    return result.stdout


def from_ocr(pdf_path: Path, dpi: int = 200, footer_band: float = 0.045) -> list[Link]:
    """OCR each page. Also OCRs an inverted strip at the bottom of the page,
    because light-on-dark footers (common in designed layouts) OCR poorly
    as-is. Set footer_band=0 to skip that pass."""
    if not shutil.which("tesseract") or not shutil.which("pdftoppm"):
        raise RuntimeError(
            "OCR needs tesseract and poppler-utils (pdftoppm) installed."
        )
    from PIL import Image, ImageOps

    links: list[Link] = []
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "page"
        subprocess.run(
            ["pdftoppm", "-r", str(dpi), "-png", str(pdf_path), str(prefix)],
            check=True,
        )
        def ocr_page(img_path: Path) -> list[Link]:
            page_no = int(img_path.stem.split("-")[-1])
            found: set[str] = set(find_urls(_ocr(img_path, psm=3)))
            if footer_band > 0:
                im = Image.open(img_path)
                w, h = im.size
                gray = im.crop((0, int(h * (1 - footer_band)), w, h)).convert("L")
                # Two passes: plain inversion, and a hard threshold that keeps
                # only near-white text (beats busy background artwork).
                variants = {
                    "inv": ImageOps.invert(gray),
                    "thr": gray.point(lambda v: 0 if v > 230 else 255),
                }
                for name, strip in variants.items():
                    strip = strip.resize((strip.width * 2, strip.height * 2))
                    strip_path = img_path.with_name(f"{img_path.stem}-{name}.png")
                    strip.save(strip_path)
                    found |= set(find_urls(_ocr(strip_path, psm=7)))
            found = drop_truncated(found)
            return [Link(url=u, page=page_no, method="ocr") for u in sorted(found)]

        from concurrent.futures import ThreadPoolExecutor
        pages = sorted(Path(tmp).glob("page-*.png"))
        with ThreadPoolExecutor(max_workers=os.cpu_count() or 2) as pool:
            for page_links in pool.map(ocr_page, pages):
                links += page_links
    return links


def from_manifest(path: Path, volume: str | None = None) -> list[Link]:
    """Optional CSV of links recovered by hand or exported from InDesign's
    Hyperlinks panel. Columns: volume (optional), page, anchor, url.
    Rows whose volume doesn't match this PDF's file name are skipped, so one
    manifest can cover several volumes."""
    import csv

    links: list[Link] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row_vol = (row.get("volume") or "").strip()
            if volume and row_vol and row_vol != volume:
                continue
            if row.get("url"):
                links.append(Link(
                    url=row["url"].strip(),
                    page=int(row.get("page") or 0),
                    method="manifest",
                    anchor=(row.get("anchor") or "").strip(),
                ))
    return links


def extract(pdf_path: Path, use_ocr: str = "auto", manifest: Path | None = None) -> dict:
    """Extract links from one PDF.

    use_ocr: "auto" (only if the PDF has no text layer), "always", or "never".
    Manifest rows take precedence: on any page the manifest covers, OCR
    guesses for that page are dropped.
    """
    reader = PdfReader(str(pdf_path))
    n_pages = len(reader.pages)
    annots = from_annotations(reader)
    text_links, pages_with_text = from_text_layer(reader)

    flattened = pages_with_text == 0
    ocr_links: list[Link] = []
    if use_ocr == "always" or (use_ocr == "auto" and flattened):
        ocr_links = from_ocr(pdf_path)

    manifest_links = from_manifest(manifest, pdf_path.name) if manifest else []
    covered = {l.page for l in manifest_links}
    ocr_links = [l for l in ocr_links if l.page not in covered]

    meta = reader.metadata or {}
    return {
        "file": pdf_path.name,
        "pages": n_pages,
        "producer": str(meta.get("/Producer", "")),
        "flattened": flattened,
        "links": annots + text_links + ocr_links + manifest_links,
    }
