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
