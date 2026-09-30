"""Check whether each URL still resolves, and classify the result."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

USER_AGENT = "Mozilla/5.0 (compatible; sltb-linkcheck/1.0; link-rot audit)"

# Status labels, in rough order of severity
OK = "OK"
REDIRECT = "REDIRECT"
SOFT_404 = "SOFT_404"      # redirected to a homepage / not-found page
RESTRICTED = "RESTRICTED"  # 401/403 - often intranet-only, not necessarily dead
BROKEN = "BROKEN"          # 404/410/5xx
ERROR = "ERROR"            # DNS, TLS, timeout, connection refused


@dataclass
class Result:
    url: str
    status: str
    http_code: int | None
    final_url: str
    hops: int
    note: str = ""
    elapsed_ms: int = 0


def _looks_like_soft_404(original: str, final: str) -> bool:
    o, f = urlparse(original), urlparse(final)
    final_path = f.path.rstrip("/")
    if any(k in final.lower() for k in ("page-not-found", "404", "notfound")):
        return True
    # A deep link that lands on a bare homepage usually means the page is gone
    return bool(o.path.strip("/")) and final_path == "" and o.netloc == f.netloc


LOGIN_HOSTS = ("login.microsoftonline.com", "auth.nih.gov", "iam.nih.gov", "login.gov")


def classify(url: str, code: int | None, final_url: str, hops: int) -> tuple[str, str]:
    if code is None:
        return ERROR, ""
    if code in (401, 403):
        return RESTRICTED, "access denied - may be intranet-only or bot-blocked"
    if code in (405, 429):
        # Some sites (nia.nih.gov) answer every scripted request, GET included,
        # with 405. The page may be fine in a browser, so don't call it dead.
        return RESTRICTED, f"{code} to automated requests - check in a browser"
    if hops and (urlparse(final_url).hostname or "") in LOGIN_HOSTS:
        return RESTRICTED, "now redirects to a sign-in page (moved behind login)"
    if code >= 400:
        return BROKEN, ""
    if hops and _looks_like_soft_404(url, final_url):
        return SOFT_404, "redirects to a homepage or not-found page"
    if hops and final_url.rstrip("/") != url.rstrip("/"):
        return REDIRECT, "update link to final URL"
    return OK, ""


def check_url(url: str, timeout: float = 20, retries: int = 1) -> Result:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    last_err = ""
    for attempt in range(retries + 1):
        start = time.monotonic()
        try:
            # Many government sites reject HEAD; fall back to GET.
            resp = session.head(url, allow_redirects=True, timeout=timeout)
            if resp.status_code in (403, 405, 501) or resp.status_code >= 500:
                resp = session.get(url, allow_redirects=True, timeout=timeout, stream=True)
                resp.close()
            elapsed = int((time.monotonic() - start) * 1000)
            status, note = classify(url, resp.status_code, resp.url, len(resp.history))
            return Result(url, status, resp.status_code, resp.url,
                          len(resp.history), note, elapsed)
        except requests.RequestException as exc:
            last_err = f"{type(exc).__name__}: {exc}"[:200]
            if attempt < retries:
                time.sleep(2)
    return Result(url, ERROR, None, "", 0, last_err)


def check_all(urls: list[str], workers: int = 8, **kw) -> dict[str, Result]:
    unique = sorted(set(urls))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda u: check_url(u, **kw), unique))
    return {r.url: r for r in results}
