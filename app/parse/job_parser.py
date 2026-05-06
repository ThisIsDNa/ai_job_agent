"""Parses a job detail HTML page into a draft dict (no validation)."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.parse.text_cleaner import clean_text
from app.validation.validator import MIN_JOB_DESCRIPTION_CHARS


def _types_of(d: dict[str, Any]) -> list[str]:
    t = d.get("@type")
    if isinstance(t, str):
        return [t]
    if isinstance(t, list):
        return [str(x) for x in t if x]
    return []


def _ld_candidates(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and "@graph" in data:
        g = data["@graph"]
        if isinstance(g, list):
            return [x for x in g if isinstance(x, dict)]
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _extract_from_job_posting_ld(soup: BeautifulSoup) -> tuple[str | None, str | None, str | None]:
    """Returns (company, location, description) hints from JSON-LD JobPosting if obvious."""
    company: str | None = None
    location: str | None = None
    ld_description: str | None = None

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        blob = (script.string or script.get_text() or "").strip()
        if not blob:
            continue
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        for obj in _ld_candidates(data):
            if "JobPosting" not in _types_of(obj):
                continue
            org = obj.get("hiringOrganization")
            if isinstance(org, dict):
                name = org.get("name")
                if isinstance(name, str) and name.strip():
                    company = company or name.strip()
            loc = obj.get("jobLocation")
            if isinstance(loc, dict):
                addr = loc.get("address")
                if isinstance(addr, dict):
                    parts = [
                        addr.get("addressLocality"),
                        addr.get("addressRegion"),
                        addr.get("addressCountry"),
                    ]
                    loc_str = ", ".join(str(p).strip() for p in parts if p and str(p).strip())
                    if loc_str:
                        location = location or loc_str
                elif isinstance(loc.get("name"), str) and str(loc["name"]).strip():
                    location = location or str(loc["name"]).strip()
            raw_desc = obj.get("description")
            if isinstance(raw_desc, str) and raw_desc.strip():
                inner = BeautifulSoup(raw_desc, "html.parser").get_text("\n")
                cand = clean_text(inner)
                if cand and (ld_description is None or len(cand) > len(ld_description)):
                    ld_description = cand

    return company, location, ld_description


def _first_h1_text(soup: BeautifulSoup) -> str | None:
    h1 = soup.find("h1")
    if not h1:
        return None
    t = " ".join(h1.get_text(" ", strip=True).split())
    return t or None


def _title_tag_text(soup: BeautifulSoup) -> str | None:
    tag = soup.find("title")
    if not tag:
        return None
    t = " ".join(tag.get_text(" ", strip=True).split())
    return t or None


def _meta_content(soup: BeautifulSoup, **attrs: str) -> str | None:
    m = soup.find("meta", attrs=attrs)
    if not m:
        return None
    content = (m.get("content") or "").strip()
    return content or None


def _longest_seo_meta_description(soup: BeautifulSoup) -> str | None:
    """Picks the longest cleaned SEO meta description (og / standard / twitter)."""
    candidates: list[str] = []
    for attrs in (
        {"property": "og:description"},
        {"name": "description"},
        {"name": "twitter:description"},
    ):
        raw = _meta_content(soup, **attrs)
        if raw:
            c = clean_text(raw)
            if c:
                candidates.append(c)
    if not candidates:
        return None
    return max(candidates, key=len)


def parse_job_page(url: str, html: str) -> dict:
    """
    Extracts title, company, location, description, url from HTML.

    Does not invent missing fields: unknown company/location remain None.
    """
    soup = BeautifulSoup(html or "", "html.parser")

    ld_company, ld_location, ld_description = _extract_from_job_posting_ld(soup)

    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()

    title = _first_h1_text(soup) or _title_tag_text(soup)

    company = _meta_content(soup, property="og:site_name")
    if not company and ld_company:
        company = ld_company
    location = ld_location

    body_text = soup.get_text("\n")
    body_clean = clean_text(body_text)
    meta_desc = _longest_seo_meta_description(soup)

    parts: list[str] = []
    if body_clean:
        parts.append(body_clean)
    if len(body_clean) < MIN_JOB_DESCRIPTION_CHARS:
        ld_c = clean_text(ld_description) if ld_description else ""
        meta_c = clean_text(meta_desc) if meta_desc else ""
        for extra in (ld_c, meta_c):
            if not extra:
                continue
            if all(extra != p for p in parts):
                parts.append(extra)

    description = clean_text("\n\n".join(parts))

    netloc = urlparse((url or "").strip()).netloc or None

    return {
        "title": title,
        "company": company,
        "location": location,
        "description": description,
        "url": url.strip(),
        "source": netloc,
    }
