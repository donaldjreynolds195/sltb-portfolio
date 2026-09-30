"""Compare the leadership roster printed in a volume with the current roster.

    python -m linkcheck.drift data/vol1-leadership.csv --out reports/leadership-drift.md

Input CSV columns: role_key, role, pdf_page, book_name, current_name.
Names are matched on surname + first initial, ignoring credentials,
middle initials and "(Acting)", so "Richard Hodes, M.D." and
"Richard J. Hodes, M.D." count as the same person.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path


def person_key(name: str) -> str:
    """'W. Kimryn Rathmell, M.D., Ph.D.' -> 'w rathmell'"""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"\(.*?\)", "", name)          # (Acting)
    name = name.split(",")[0]                    # drop credentials
    parts = [p for p in re.split(r"[\s.]+", name.lower()) if p]
    parts = [p for p in parts if p not in {"dr", "iii", "ii", "jr", "sr"}]
    if not parts:
        return ""
    return f"{parts[0][0]} {parts[-1]}"


def is_acting(name: str) -> bool:
    return "acting" in name.lower()


def compare(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        book, cur = r["book_name"].strip(), r.get("current_name", "").strip()
        if not cur:
            status = "UNKNOWN"
        elif person_key(book) == person_key(cur):
            status = "SAME"
        else:
            status = "CHANGED"
        out.append({**r, "status": status, "current_acting": is_acting(cur)})
    return out


def to_markdown(results: list[dict], source_note: str) -> str:
    changed = [r for r in results if r["status"] == "CHANGED"]
    same = [r for r in results if r["status"] == "SAME"]
    acting = [r for r in results if r["current_acting"]]
    total = len(results)
    lines = [
        "# Leadership drift report", "",
        source_note, "",
        f"**{len(changed)} of {total}** positions in the book now have a different "
        f"person ({len(changed) / total:.0%}). {len(same)} unchanged. "
        f"{len(acting)} positions are currently held in an acting capacity.", "",
        "| Role | PDF page | In the book | Current | Status |",
        "|---|---|---|---|---|",
    ]
    for r in sorted(results, key=lambda r: (r["status"] != "CHANGED", int(r["pdf_page"]))):
        lines.append(f"| {r['role_key']} | {r['pdf_page']} | {r['book_name']} | "
                     f"{r['current_name'] or '-'} | {r['status']} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="linkcheck.drift")
    p.add_argument("roster", type=Path)
    p.add_argument("--out", type=Path, default=Path("reports/leadership-drift.md"))
    p.add_argument("--source-note", default="")
    args = p.parse_args(argv)

    with open(args.roster, newline="", encoding="utf-8") as f:
        results = compare(list(csv.DictReader(f)))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(to_markdown(results, args.source_note), encoding="utf-8")
    changed = sum(r["status"] == "CHANGED" for r in results)
    print(f"{changed}/{len(results)} positions changed -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
