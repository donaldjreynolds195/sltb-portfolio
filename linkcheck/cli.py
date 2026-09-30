"""Audit the links in one or more PDFs.

    # First run, locally: extract links (OCR if needed), check them, save an inventory
    python -m linkcheck volumes/*.pdf --save-inventory data/links-inventory.csv

    # Later / in CI: re-check the saved inventory, no PDFs or OCR needed
    python -m linkcheck --inventory data/links-inventory.csv

    # Extract only, no network
    python -m linkcheck volumes/*.pdf --offline
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from .check import check_all
from .extract import Link, extract
from .report import build_rows, write_csv, write_markdown


def save_inventory(volumes: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["volume", "pages", "producer", "flattened", "page", "method", "anchor", "url"])
        for v in volumes:
            for l in v["links"]:
                w.writerow([v["file"], v["pages"], v["producer"], int(v["flattened"]),
                            l.page, l.method, l.anchor, l.url])


def load_inventory(path: Path) -> list[dict]:
    vols: dict[str, dict] = {}
    links = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row["volume"]
            vols.setdefault(name, {"file": name, "pages": int(row["pages"]),
                                   "producer": row["producer"],
                                   "flattened": row["flattened"] == "1"})
            links[name].append(Link(url=row["url"], page=int(row["page"]),
                                    method=row["method"], anchor=row["anchor"]))
    return [{**v, "links": links[k]} for k, v in vols.items()]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="linkcheck", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("pdfs", nargs="*", type=Path, help="PDF files to scan")
    p.add_argument("--inventory", type=Path, help="re-check a saved inventory CSV instead of PDFs")
    p.add_argument("--save-inventory", type=Path, help="write extracted links to this CSV")
    p.add_argument("--out", type=Path, default=Path("reports"), help="output folder")
    p.add_argument("--ocr", choices=["auto", "always", "never"], default="auto")
    p.add_argument("--manifest", type=Path, help="CSV of extra links (page,anchor,url)")
    p.add_argument("--offline", action="store_true", help="skip HTTP checks")
    p.add_argument("--timeout", type=float, default=20)
    p.add_argument("--fail-on-broken", action="store_true",
                   help="exit 1 if any link is BROKEN or SOFT_404 (for CI)")
    args = p.parse_args(argv)

    if args.inventory:
        volumes = load_inventory(args.inventory)
    elif args.pdfs:
        volumes = []
        for pdf in args.pdfs:
            print(f"Scanning {pdf.name} ...", file=sys.stderr)
            vol = extract(pdf, use_ocr=args.ocr, manifest=args.manifest)
            print(f"  {vol['pages']} pages, {len(vol['links'])} links"
                  f"{' (flattened PDF, OCR used)' if vol['flattened'] else ''}", file=sys.stderr)
            volumes.append(vol)
    else:
        p.error("give one or more PDFs, or --inventory")

    if args.save_inventory:
        save_inventory(volumes, args.save_inventory)
        print(f"Saved inventory to {args.save_inventory}", file=sys.stderr)

    results = None
    if not args.offline:
        urls = [l.url for v in volumes for l in v["links"]]
        print(f"Checking {len(set(urls))} unique URLs ...", file=sys.stderr)
        results = check_all(urls, timeout=args.timeout)

    rows = build_rows(volumes, results)
    write_csv(rows, args.out / "links.csv")
    write_markdown(volumes, rows, args.out / "report.md")
    print(f"Wrote {args.out / 'links.csv'} and {args.out / 'report.md'}", file=sys.stderr)

    if args.fail_on_broken and any(r["status"] in ("BROKEN", "SOFT_404") for r in rows):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
