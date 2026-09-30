# Volumes

Put the four volume PDFs here to scan them locally:

    SLTB-vol-1.pdf  SLTB-vol-2.pdf  SLTB-vol-3.pdf  SLTB-vol-4.pdf

PDFs are git-ignored on purpose (licensed stock photos). The scheduled
GitHub Action re-checks `data/links-inventory.csv` instead, so it never
needs the PDFs.

**Best results:** re-export each volume from InDesign with
*File > Export > Adobe PDF (Interactive)*. That keeps every hyperlink as
a clickable link annotation, which the checker reads exactly. A "Microsoft
Print to PDF" copy is image-only, so only URLs printed on the page can be
recovered (by OCR).
