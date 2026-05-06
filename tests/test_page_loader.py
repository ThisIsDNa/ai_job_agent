"""Tests for page URL validation (no network)."""

import pytest

from app.extract.page_loader import load_page_html


def test_load_page_html_rejects_invalid_scheme() -> None:
    with pytest.raises(ValueError, match="Invalid URL"):
        load_page_html("ftp://example.com/jobs")


def test_load_page_html_rejects_missing_host() -> None:
    with pytest.raises(ValueError, match="Invalid URL"):
        load_page_html("https:///nohost")
