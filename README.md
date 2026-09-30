# Senior Leader Transition Book: case study and link-rot audit

A four-volume onboarding guide I designed and built in Adobe InDesign for incoming
senior leaders at the NIH National Institute on Aging (NIA), plus a Python tool
that audits how the book's links and leadership content have aged since I left.

> **Snapshot, not maintained.** The book reflects nih.gov as of its publication date.
> Names, org charts, and links are shown as they were then. I no longer work at NIH
> and this repository is not an official NIH resource.

![Volume 1: cover, table of contents, institute list, payroll FAQ](docs/images/vol1-pages.jpg)

---

## The problem

New senior leaders at NIA had to piece together who ran what, how the budget
worked, and how to handle HR and payroll from dozens of separate nih.gov and
intranet pages. There was no single place to start.

## What I built

| | |
|---|---|
| **Format** | 4 volumes, designed in Adobe InDesign, distributed as PDF and as online flipbooks |
| **Structure** | Tiered from agency to division: NIH (Vol 1) → NIA (Vol 2) → Division of Aging Biology (Vol 3), with a DAB Essentials hub that summarizes all three and links into each. Every volume puts critical core content first and supplementary content after |
| **Design system** | Consistent page template: section banner, source URL in every footer, page number, linked anchor text for every referenced office or form |
| **Traceability** | Every page cites the nih.gov page its content came from, so readers can check anything against the source |
| **My role** | <!-- EDIT: e.g. "Sole designer and content lead. Scoped content with the Deputy Director's office, ..." --> |
| **Audience / use** | <!-- EDIT: who received it, how many leaders onboarded with it, any feedback --> |

### Volumes

| Volume | Contents |
|---|---|
| Vol 1: NIH | NIH leadership, organization, IC directors, budget, Office of Budget, HR contacts, payroll FAQ, visitor info, training |
| Vol 2: NIA (current as of 22 Oct 2024) | About NIA, offices and divisions, leadership and division director biographies, budget and testimony, HR contacts, staff directory, dismissal and closure procedures, funding opportunities |
| Vol 3: Division of Aging Biology (current as of 1 Dec 2024) | Intro to DAB, who we are, portfolios and programs, staff meetings, top-25 funding charts |
| DAB Essentials | One-stop summary: NIH and NIA leadership, workforce and budget dashboards, DAB team, with links out to the other three volumes |

---

## The audit tool

Documents full of links decay. This repo includes `linkcheck`, a small Python
package that measures that decay.

**What it does**

1. **Extracts every URL from a PDF**, four ways: clickable link annotations
   (exact), the text layer, **OCR for flattened PDFs**, and a hand-made manifest
   for anything OCR can't read. The four volumes arrived in three different
   states, which is why all four are needed:

   | Volume | How the PDF was made | Method | Links recovered |
   |---|---|---|---|
   | Vol 1 | Microsoft Print to PDF (image only) | OCR | 22 of 22 footers, zero errors |
   | Vol 2 | Image-only, 72 dpi | Manifest (OCR too blurry) | 20 footers |
   | Vol 3 | Image-only, 72 dpi | Manifest | 2 footers (most pages have none) |
   | DAB Essentials | Interactive export | Link annotations | 76 clickable links |
2. **Checks each URL** (HEAD with GET fallback, redirects followed) and classifies
   it: `OK`, `REDIRECT`, `SOFT_404` (a deep link that now lands on a homepage),
   `RESTRICTED` (401/403, often intranet-only), `BROKEN`, or `ERROR`.
3. **Compares the leadership roster** in the book with the current nih.gov roster
   and reports who has changed (`linkcheck.drift`).
4. **Runs monthly in GitHub Actions** against a saved URL inventory, so the PDFs
   never need to be in the repo, and commits the updated report.

### First-run findings (all four volumes, 2026-09-30)

- nih.gov moved `/about-nih/who-we-are/` and `/about-nih/what-we-do/` under
  `/about-nih/organization/`. That one restructuring affects **8 of 22** content
  pages in Vol 1 and several director links in DAB Essentials.
- **22 of 33** NIH leadership positions (67%) now have a different person,
  including the NIH Director, 4 of 5 Deputy Directors, and 17 of 27 IC directors.
  DAB Essentials repeats this roster and links to each director's bio page;
  15 of those URLs have a person's name in them, the kind of link most likely to break.
- At NIA the Director and Deputy Director are unchanged; the Division of Aging
  Biology has a new director, and the Division of Neuroscience is recruiting one.
- **A typo the audit caught:** Vol 2's "About NIA" pages cite `www.nih.nih.gov/about`
  instead of `www.nia.nih.gov/about`.
- Hundreds of anchor-text links in Vols 1–3 could not be audited because those PDFs
  were flattened. Re-exporting from InDesign as *Adobe PDF (Interactive)* fixes that.

Details: [reports/2026-09-30-first-run.md](reports/2026-09-30-first-run.md) ·
[leadership-drift.md](reports/leadership-drift.md) (NIH) ·
[leadership-drift-nia.md](reports/leadership-drift-nia.md) (NIA/DAB) ·
[report.md](reports/report.md) (live link status, updated monthly by CI)

### Run it yourself

```bash
pip install -r requirements.txt
sudo apt-get install tesseract-ocr poppler-utils   # only needed for image-only PDFs

# Scan PDFs, check links, save the URL inventory for CI
python -m linkcheck volumes/*.pdf --manifest data/footer-manifest.csv \
    --save-inventory data/links-inventory.csv

# Re-check the saved inventory (what CI runs)
python -m linkcheck --inventory data/links-inventory.csv

# Leadership drift
python -m linkcheck.drift data/vol1-leadership.csv
python -m linkcheck.drift data/vol2-3-nia-leadership.csv --out reports/leadership-drift-nia.md

# Tests
python -m pytest -q
```

Output lands in `reports/`: `links.csv` (one row per link per page) and
`report.md` (summary plus detail table).

### Repository layout

```
linkcheck/        extract.py (annotations, text, OCR) · check.py (HTTP + classify)
                  report.py (CSV/Markdown) · drift.py (roster comparison) · cli.py
data/             links-inventory.csv (URLs found per page) · footer-manifest.csv
                  (hand-transcribed footers) · vol1 / vol2-3 leadership rosters
reports/          generated audit reports
tests/            unit tests + end-to-end tests that run when the PDFs are present
volumes/          PDFs go here locally (git-ignored, see volumes/README.md)
.github/workflows monthly link audit
```

## Skills shown

Program and content management (scoping, stakeholder sourcing, information
architecture) · InDesign layout and a reusable page system · Python, OCR, HTTP
automation, and data comparison · CI/CD with scheduled GitHub Actions.

## Possible next steps

- Re-export Vols 1–3 as interactive PDFs and audit every anchor link.
- Move the monthly check to an Azure Function on a timer trigger, with results
  written to Blob Storage and a Power BI or static dashboard.
