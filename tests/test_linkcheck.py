from pathlib import Path

import pytest

from linkcheck.check import BROKEN, OK, REDIRECT, RESTRICTED, SOFT_404, classify
from linkcheck.drift import compare, person_key
from linkcheck.extract import drop_truncated, find_urls, normalize_url


# --- URL extraction and OCR cleanup -------------------------------------

def test_find_urls_basic():
    text = "See https://www.nih.gov/about-nih/visitor-information for details."
    assert find_urls(text) == ["https://www.nih.gov/about-nih/visitor-information"]


def test_www_gets_scheme():
    assert normalize_url("www.nih.gov/") == "https://www.nih.gov/"


def test_trailing_punctuation_stripped():
    assert normalize_url("https://hr.nih.gov/about).") == "https://hr.nih.gov/about"


def test_ocr_question_mark_repair():
    # Real OCR slip from Vol 1, page 17: "?" read as "I"
    assert normalize_url("https://hr.nih.gov/about/hr-contactsIic=All") == \
        "https://hr.nih.gov/about/hr-contacts?ic=All"


def test_ocr_repair_leaves_normal_paths_alone():
    url = "https://www.nih.gov/institutes-nih/list-institutes-centers"
    assert normalize_url(url) == url


def test_single_slash_scheme_fixed():
    assert normalize_url("https:/www.nih.gov/x") == "https://www.nih.gov/x"


def test_drop_truncated_keeps_longest():
    found = {"https://www.nih.gov/", "https://www.nih.gov/research-training/training-opportunities"}
    assert drop_truncated(found) == {"https://www.nih.gov/research-training/training-opportunities"}


# --- Status classification ----------------------------------------------

@pytest.mark.parametrize("url,code,final,hops,expected", [
    ("https://a.gov/x", 200, "https://a.gov/x", 0, OK),
    ("https://a.gov/x", 200, "https://a.gov/y", 1, REDIRECT),
    ("https://a.gov/deep/page", 200, "https://a.gov/", 1, SOFT_404),
    ("https://a.gov/x", 200, "https://a.gov/page-not-found", 1, SOFT_404),
    ("https://a.gov/x", 404, "https://a.gov/x", 0, BROKEN),
    ("https://a.gov/x", 403, "https://a.gov/x", 0, RESTRICTED),
])
def test_classify(url, code, final, hops, expected):
    assert classify(url, code, final, hops)[0] == expected


def test_bot_block_405_is_restricted_not_broken():
    # Real case from the first CI run: every nia.nih.gov page returned 405
    assert classify("https://www.nia.nih.gov/research/dab", 405,
                    "https://www.nia.nih.gov/research/dab", 0)[0] == RESTRICTED


def test_redirect_to_sign_in_is_restricted():
    # Real case: hr.nih.gov dismissal procedures now bounce to NIH's Microsoft login
    status, note = classify("https://hr.nih.gov/working-nih/dismissal-and-closures/procedures", 200,
                            "https://login.microsoftonline.com:443/abc/oauth2", 3)
    assert status == RESTRICTED and "sign-in" in note


def test_trailing_slash_redirect_is_ok():
    assert classify("https://a.gov/x", 200, "https://a.gov/x/", 1)[0] == OK


# --- Leadership drift ---------------------------------------------------

def test_person_key_ignores_credentials_and_middle_initials():
    assert person_key("Richard Hodes, M.D.") == person_key("Richard J. Hodes, M.D.")
    assert person_key("Stephen Sherry, Ph.D. (Acting)") == person_key("Stephen Sherry, Ph.D.")
    assert person_key("Eliseo J. Pérez-Stable, M.D.") == "e perez-stable"


def test_compare_flags_changes():
    rows = [
        {"role_key": "NEI", "book_name": "Michael F. Chiang, M.D.", "current_name": "Michael F. Chiang, M.D."},
        {"role_key": "NCI", "book_name": "W. Kimryn Rathmell, M.D., Ph.D.", "current_name": "Anthony Letai, M.D., Ph.D."},
        {"role_key": "X", "book_name": "Someone", "current_name": ""},
    ]
    assert [r["status"] for r in compare(rows)] == ["SAME", "CHANGED", "UNKNOWN"]


# --- End to end on the real volume (skipped if the PDF isn't present) ----

VOL1 = Path(__file__).parent.parent / "volumes" / "SLTB-vol-1.pdf"


@pytest.mark.skipif(not VOL1.exists(), reason="volume PDF not committed")
def test_vol1_extracts_all_footer_urls():
    from linkcheck.extract import extract
    vol = extract(VOL1)
    assert vol["flattened"]
    urls = {l.url for l in vol["links"]}
    assert "https://www.nih.gov/research-training/training-opportunities" in urls
    assert "https://hr.nih.gov/about/hr-contacts?ic=All" in urls
    assert len(urls) == 11
    assert len(vol["links"]) == 22  # one footer URL per content page


def test_drift_report_counts_only_verified_rows():
    from linkcheck.drift import to_markdown
    rows = compare([
        {"role_key": "A", "pdf_page": "1", "book_name": "Ann Smith", "current_name": "Bob Jones"},
        {"role_key": "B", "pdf_page": "2", "book_name": "Cy Lee", "current_name": "Cy Lee"},
        {"role_key": "C", "pdf_page": "3", "book_name": "Di Park", "current_name": ""},
    ])
    md = to_markdown(rows, "")
    assert "**1 of 2** verified positions" in md
    assert "1 not verified" in md


# --- Manifest --------------------------------------------------------------

def test_manifest_filters_by_volume(tmp_path):
    from linkcheck.extract import from_manifest
    m = tmp_path / "m.csv"
    m.write_text(
        "volume,page,anchor,url\n"
        "vol-2.pdf,4,footer,https://a.gov/x\n"
        "vol-3.pdf,4,footer,https://b.gov/y\n"
        ",9,any volume,https://c.gov/z\n"
    )
    urls = {l.url for l in from_manifest(m, "vol-2.pdf")}
    assert urls == {"https://a.gov/x", "https://c.gov/z"}


# --- Inventory round trip ------------------------------------------------

def test_inventory_round_trip(tmp_path):
    from linkcheck.cli import load_inventory, save_inventory
    from linkcheck.extract import Link
    vols = [{"file": "v.pdf", "pages": 3, "producer": "PDFBase,WanCai.GZ", "flattened": True,
             "links": [Link("https://a.gov/", 2, "ocr")]}]
    p = tmp_path / "inv.csv"
    save_inventory(vols, p)
    back = load_inventory(p)
    assert back[0]["producer"] == "PDFBase,WanCai.GZ"   # comma survives CSV quoting
    assert back[0]["links"][0].url == "https://a.gov/"


# --- End to end on the other volumes --------------------------------------

VOLS = Path(__file__).parent.parent / "volumes"
MANIFEST = Path(__file__).parent.parent / "data" / "footer-manifest.csv"


@pytest.mark.skipif(not (VOLS / "SLTB-vol-4.pdf").exists(), reason="volume PDF not committed")
def test_vol4_reads_clickable_links():
    # DAB Essentials was exported with live links, some stored as indirect
    # /Annots arrays - the case that crashed the first version.
    from linkcheck.extract import extract
    vol = extract(VOLS / "SLTB-vol-4.pdf")
    annots = [l for l in vol["links"] if l.method == "annotation"]
    assert len(annots) == 76
    assert "https://www.nia.nih.gov/about/staff/hodes-richard" in {l.url for l in annots}


@pytest.mark.skipif(not (VOLS / "SLTB-vol-3.pdf").exists(), reason="volume PDF not committed")
def test_manifest_overrides_ocr_on_covered_pages():
    from linkcheck.extract import extract
    vol = extract(VOLS / "SLTB-vol-3.pdf", manifest=MANIFEST)
    by_page = {}
    for l in vol["links"]:
        by_page.setdefault(l.page, set()).add(l.method)
    assert by_page[4] == {"manifest"} and by_page[5] == {"manifest"}
