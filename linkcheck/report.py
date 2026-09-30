"""Write CSV and Markdown reports."""

from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .check import Result

STATUS_ORDER = ["BROKEN", "SOFT_404", "ERROR", "RESTRICTED", "REDIRECT", "OK", "NOT_CHECKED"]


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["volume", "page", "method", "anchor", "url", "status",
              "http_code", "final_url", "hops", "note"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_rows(volumes: list[dict], results: dict[str, Result] | None) -> list[dict]:
    rows = []
    for vol in volumes:
        for link in vol["links"]:
            r = results.get(link.url) if results else None
            rows.append({
                "volume": vol["file"],
                "page": link.page,
                "method": link.method,
                "anchor": link.anchor,
                "url": link.url,
                "status": r.status if r else "NOT_CHECKED",
                "http_code": r.http_code if r else "",
                "final_url": r.final_url if r else "",
                "hops": r.hops if r else "",
                "note": r.note if r else "",
            })
    return rows


def write_markdown(volumes: list[dict], rows: list[dict], path: Path) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Link audit report", "", f"Generated {now}.", ""]

    lines += ["## Volumes scanned", "",
              "| Volume | Pages | Producer | Flattened? | Links found |",
              "|---|---|---|---|---|"]
    for v in volumes:
        lines.append(f"| {v['file']} | {v['pages']} | {v['producer'] or '-'} | "
                     f"{'yes (OCR used)' if v['flattened'] else 'no'} | {len(v['links'])} |")
    lines.append("")

    flattened = [v["file"] for v in volumes if v["flattened"]]
    if flattened:
        lines += [
            "> **Note:** " + ", ".join(flattened) + " has no text layer or clickable "
            "links, so only URLs printed on the page could be recovered (by OCR). "
            "Hyperlinked anchor text lost its targets when the PDF was flattened. "
            "Re-export from InDesign as *Adobe PDF (Interactive)* to audit every link.",
            "",
        ]

    unique: dict[str, dict] = {}
    for row in rows:
        unique.setdefault(row["url"], row)
    counts = Counter(r["status"] for r in unique.values())
    lines += ["## Summary (unique URLs)", "", "| Status | Count |", "|---|---|"]
    for s in STATUS_ORDER:
        if counts.get(s):
            lines.append(f"| {s} | {counts[s]} |")
    lines.append(f"| **Total** | **{len(unique)}** |")
    lines.append("")

    lines += ["## Detail", "", "| Status | Code | URL | Pages | Final URL / note |",
              "|---|---|---|---|---|"]
    pages: dict[str, list[str]] = {}
    for row in rows:
        pages.setdefault(row["url"], []).append(f"{row['volume'].rsplit('.', 1)[0]} p{row['page']}")
    ordered = sorted(unique.values(),
                     key=lambda r: (STATUS_ORDER.index(r["status"]), r["url"]))
    for r in ordered:
        detail = r["final_url"] if r["status"] in ("REDIRECT", "SOFT_404") else r["note"]
        lines.append(f"| {r['status']} | {r['http_code'] or '-'} | {r['url']} | "
                     f"{', '.join(pages[r['url']])} | {detail or ''} |")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
