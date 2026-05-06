"""Extract likely job posting links from careers HTML (anchors + static embeds)."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

# Legacy anchor hints (supplement to scoring).
_JOB_HREF_KEYWORDS: tuple[str, ...] = (
    "job",
    "jobs",
    "career",
    "careers",
    "opening",
    "position",
    "role",
    "lever",
    "greenhouse",
    "ashby",
    "workday",
    "smartrecruiters",
)

# Substrings in URL (path/query/host combined, lowercased) treated as navigation/noise.
_NOISE_SUBSTRINGS: tuple[str, ...] = (
    "benefits",
    "life-at",
    "life_at",
    "career-pathways",
    "overlay",
    "privacy",
    "terms",
    "sign-in",
    "signin",
    "/students",
    "/student/",
)

# Embedded static HTML (no JS execution): Ashby, Greenhouse, Lever, Workday detail, Intel jobs.
_ASHBY_JOB_URL_RE = re.compile(
    r"https://jobs\.ashbyhq\.com/[a-zA-Z0-9_.-]+/[a-f0-9\-]{8,}(?:[/?][^\s\"'<>]*)?",
    re.IGNORECASE,
)
_GREENHOUSE_JOB_URL_RE = re.compile(
    r"https://(?:boards|job-boards)\.greenhouse\.io/[^\s\"'<>]+",
    re.IGNORECASE,
)
_LEVER_JOB_URL_RE = re.compile(
    r"https://jobs\.lever\.co/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:[/?][^\s\"'<>]*)?",
    re.IGNORECASE,
)
_WORKDAY_JOB_URL_RE = re.compile(
    r"https://[a-z0-9.-]+\.myworkdayjobs\.com[^\s\"'<>]*/job/[^\s\"'<>]+",
    re.IGNORECASE,
)
_INTEL_JOBS_URL_RE = re.compile(
    r"https://jobs\.intel\.com/[^\s\"'<>]+",
    re.IGNORECASE,
)

_EMBEDDED_URL_RES: tuple[re.Pattern[str], ...] = (
    _ASHBY_JOB_URL_RE,
    _GREENHOUSE_JOB_URL_RE,
    _LEVER_JOB_URL_RE,
    _WORKDAY_JOB_URL_RE,
    _INTEL_JOBS_URL_RE,
)


def _normalize_url(abs_url: str) -> str:
    return abs_url.split("#", 1)[0].rstrip("/")


def _is_noise_url(parsed_url, full_lower: str) -> bool:
    """True when URL is clearly nav/marketing, not a job detail page."""
    path = (parsed_url.path or "").lower()
    path_q = f"{parsed_url.path or ''}?{parsed_url.query or ''}".lower()

    for frag in _NOISE_SUBSTRINGS:
        if frag in path_q or frag in full_lower:
            return True

    if "/events" in path or path.endswith("/events"):
        return True
    if "/video" in path or "video" in path_q:
        return True
    if "/login" in path or path.endswith("/login"):
        return True

    if "internship" in path_q and "/job/" not in full_lower and "requisition" not in full_lower:
        return True

    return False


def _job_url_score(url: str) -> int:
    """Higher = more likely a job detail posting (heuristic, deterministic)."""
    u = url.lower()
    score = 0

    if "/job/" in u or "/jobs/" in u:
        score += 6
    if "/details/" in u:
        score += 4
    if "requisition" in u or "/req/" in u or "req_id" in u or "requisitionid" in u:
        score += 4
    if re.search(r"\bjr\d+", u):
        score += 3
    if "position" in u or "opening" in u:
        score += 2

    if "ashbyhq.com" in u:
        score += 4
    if "greenhouse.io" in u:
        score += 4
    if "lever.co" in u:
        score += 4
    if "myworkdayjobs.com" in u:
        score += 4
    if "jobs.intel.com" in u:
        score += 3

    for k in _JOB_HREF_KEYWORDS:
        if k in u:
            score += 1
            break

    return score


def _href_looks_job_related(href_lower: str) -> bool:
    return any(k in href_lower for k in _JOB_HREF_KEYWORDS)


def _should_include_candidate(url: str, score: int, from_anchor: bool) -> bool:
    """Include non-noise URLs that look like job postings."""
    u = url.lower()
    if score >= 3:
        return True
    if "/job/" in u or "/jobs/" in u:
        return True
    if score >= 2 and any(h in u for h in ("ashbyhq.com", "greenhouse.io", "lever.co", "myworkdayjobs.com")):
        return True
    if from_anchor and _href_looks_job_related(u) and score >= 1:
        return True
    if from_anchor and score >= 2:
        return True
    return False


def _extract_embedded_job_urls(html: str) -> list[str]:
    """Finds job URLs embedded in raw HTML (e.g. Ashby JSON in script tags)."""
    found: list[str] = []
    seen: set[str] = set()
    for rx in _EMBEDDED_URL_RES:
        for m in rx.finditer(html or ""):
            raw = m.group(0).rstrip(").,;]}'\"")
            n = _normalize_url(raw)
            if n not in seen:
                seen.add(n)
                found.append(n)
    return found


def _title_from_url(job_url: str) -> str:
    """Fallback title when only a bare URL is known."""
    parsed = urlparse(job_url)
    slug = parsed.path.rstrip("/").split("/")[-1]
    if slug and len(slug) > 3:
        return slug.replace("-", " ").title()
    return job_url


def _count_ashby_quoted_paths(html: str) -> int:
    if not html:
        return 0
    rx = re.compile(
        r'["\'](/[a-zA-Z0-9_.-]+/[a-f0-9]{8}-[a-f0-9-]{3,}(?:\?[^"\']*)?)["\']',
        re.IGNORECASE,
    )
    return len(rx.findall(html))


def find_job_links(base_url: str, html: str, *, stats: dict | None = None) -> list[dict]:
    """
    Returns deduplicated job link dicts: title, url, source — sorted by detail likelihood (score desc).

    Uses anchor hrefs plus static regex over HTML for embedded ATS URLs (no JS execution).

    When ``stats`` is a dict, it is cleared and filled with extraction diagnostics (debug/CLI).
    """
    parsed_base = urlparse((base_url or "").strip())
    source_host = parsed_base.netloc or "unknown"
    base = base_url.strip()
    soup = BeautifulSoup(html or "", "html.parser")

    if stats is not None:
        stats.clear()
        embedded_list = _extract_embedded_job_urls(html)
        ashby_q = _count_ashby_quoted_paths(html) if "jobs.ashbyhq.com" in parsed_base.netloc.lower() else 0
        stats.update(
            {
                "anchor_tags_total": len(soup.find_all("a", href=True)),
                "anchors_resolved_http": 0,
                "embedded_regex_matches": len(embedded_list),
                "ashby_quoted_paths": ashby_q,
                "embedded_urls_found": len(embedded_list) + ashby_q,
                "consider_attempts": 0,
                "removed_noise": 0,
                "removed_inclusion": 0,
            }
        )

    # url_norm -> {score, title, from_anchor}
    best: dict[str, dict] = {}

    def consider(url: str, title: str | None, from_anchor: bool) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return
        if stats is not None:
            stats["consider_attempts"] += 1
        full_lower = url.lower()
        if _is_noise_url(parsed, full_lower):
            if stats is not None:
                stats["removed_noise"] += 1
            return
        score = _job_url_score(url)
        if not _should_include_candidate(url, score, from_anchor):
            if stats is not None:
                stats["removed_inclusion"] += 1
            return
        norm = _normalize_url(url)
        label = " ".join((title or "").split()) or _title_from_url(norm)
        prev = best.get(norm)
        if prev is None or score > prev["score"] or (
            score == prev["score"] and len(label) > len(prev["title"])
        ):
            best[norm] = {"score": score, "title": label, "from_anchor": from_anchor}

    # Anchors
    for a in soup.find_all("a", href=True):
        href_raw = (a.get("href") or "").strip()
        if not href_raw or href_raw.startswith("#"):
            continue
        href_lower_start = href_raw.strip().lower()
        if href_lower_start.startswith(("javascript:", "mailto:", "tel:")):
            continue

        abs_url = urljoin(base, href_raw)
        parsed = urlparse(abs_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue

        if stats is not None:
            stats["anchors_resolved_http"] += 1

        title = " ".join(a.get_text(" ", strip=True).split()) or None
        consider(abs_url, title, from_anchor=True)

    # Embedded URLs (Ashby board JSON, etc.)
    for raw_u in _extract_embedded_job_urls(html):
        consider(raw_u, None, from_anchor=False)

    # Ashby listing pages: quoted relative paths like "/slug/uuid" in static payload.
    if "jobs.ashbyhq.com" in parsed_base.netloc.lower():
        for m in re.finditer(
            r'["\'](/[a-zA-Z0-9_.-]+/[a-f0-9]{8}-[a-f0-9-]{3,}(?:\?[^"\']*)?)["\']',
            html or "",
            re.IGNORECASE,
        ):
            rel = m.group(1)
            if "/api/" in rel.lower():
                continue
            abs_url = urljoin(base, rel)
            consider(abs_url, None, from_anchor=False)

    rows = [
        {"title": v["title"], "url": k, "source": source_host}
        for k, v in best.items()
    ]
    rows.sort(key=lambda r: (-_job_url_score(r["url"]), r["url"]))
    if stats is not None:
        stats["candidates_before_filter"] = stats["consider_attempts"]
        stats["candidates_after_filter"] = len(rows)
        stats["final_link_count"] = len(rows)
    return rows
