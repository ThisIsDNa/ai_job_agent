"""HTTP page loading for deterministic HTML/text extraction."""

from __future__ import annotations

from urllib.parse import urlparse

import requests

from app.utils.logger import get_logger

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AIJobAgent/0.1; +https://example.invalid) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
_DEFAULT_TIMEOUT_SEC = 15

_log = get_logger("page_loader")


def _validate_http_url(url: str) -> None:
    """Raises ValueError when URL is not a usable http(s) URL."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Invalid URL (must be http(s) with host): {url!r}")


def load_page_html(url: str, *, debug: bool = False) -> str:
    """Fetches raw HTML for a URL. Raises on invalid URL, transport, status, or empty body."""
    try:
        _validate_http_url(url)
    except ValueError as exc:
        _log.warning("request failed url=%r reason=invalid_url detail=%s", url, exc)
        raise
    if debug:
        _log.debug("request start url=%r", url)
    try:
        resp = requests.get(
            url,
            headers=_DEFAULT_HEADERS,
            timeout=_DEFAULT_TIMEOUT_SEC,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        _log.warning(
            "request failed url=%r reason=request_exception exc=%r",
            url,
            exc,
        )
        raise RuntimeError(f"Request failed for {url!r}: {exc}") from exc

    if resp.status_code != 200:
        _log.warning(
            "request failed url=%r reason=non_200 status=%r body_len=%s",
            url,
            resp.status_code,
            len(resp.text or ""),
        )
        raise RuntimeError(
            f"Non-200 response for {url!r}: status={resp.status_code!r}"
        )

    body = resp.text or ""
    if not body.strip():
        _log.warning(
            "request failed url=%r reason=empty_body status=%r",
            url,
            resp.status_code,
        )
        raise RuntimeError(f"Empty response body for {url!r}")

    if debug:
        _log.info(
            "request ok url=%r status=%s html_chars=%s",
            url,
            resp.status_code,
            len(body),
        )
    return body


def load_page_text(url: str, *, debug: bool = False) -> str:
    """Fetches HTML then returns visible text (no tags). Same error contract as load_page_html."""
    from app.parse.text_cleaner import clean_text

    html = load_page_html(url, debug=debug)
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:  # pragma: no cover - guarded by requirements
        raise RuntimeError("beautifulsoup4 is required for load_page_text") from exc

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    raw_text = soup.get_text("\n")
    return clean_text(raw_text)
