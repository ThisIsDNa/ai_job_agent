"""Tests for text cleaning and job page parsing."""

import json

from app.parse.job_parser import parse_job_page
from app.parse.text_cleaner import clean_text
from app.validation.validator import MIN_JOB_DESCRIPTION_CHARS, validate_job_posting_draft


def test_clean_text_whitespace_normalization() -> None:
    raw = "  hello   world  \n\n\n  next  "
    assert clean_text(raw) == "hello world\n\nnext"


def test_clean_text_empty_returns_empty() -> None:
    assert clean_text("") == ""
    assert clean_text("   \n  \t  ") == ""


def test_parse_job_page_title_from_h1() -> None:
    html = """
    <html><head><title>Wrong Title</title></head>
    <body>
      <h1>Senior Widget Engineer</h1>
      <p>""" + ("x" * 120) + """</p>
    </body></html>
    """
    out = parse_job_page("https://jobs.example.com/role/1", html)
    assert out["title"] == "Senior Widget Engineer"
    assert out["url"] == "https://jobs.example.com/role/1"
    assert len(out["description"]) >= 100


def test_parse_job_page_fallback_title_from_title_tag() -> None:
    html = f"""
    <html><head><title>  Page Title Here  </title></head>
    <body><p>{'word ' * 80}</p></body></html>
    """
    out = parse_job_page("https://example.com/job/no-h1", html)
    assert out["title"] == "Page Title Here"


def test_parse_job_page_merges_jobposting_ld_when_ssr_body_thin() -> None:
    """Workday-like pages: little visible body, rich JobPosting.description in JSON-LD."""
    ld_html = "<p>" + ("word " * 80) + "</p>"
    blob = json.dumps({"@type": "JobPosting", "description": ld_html})
    html = f"""
    <html><head>
    <script type="application/ld+json">{blob}</script>
    </head><body><div>Enable JavaScript to view.</div></body></html>
    """
    out = parse_job_page("https://intel.wd1.myworkdayjobs.com/job/123", html)
    assert len(out["description"]) >= MIN_JOB_DESCRIPTION_CHARS
    draft = validate_job_posting_draft(out)
    assert len(draft.description) >= MIN_JOB_DESCRIPTION_CHARS


def test_parse_job_page_merges_og_description_when_body_thin() -> None:
    og = "Role summary: " + ("detail " * 40)
    html = f"""
    <html><head>
    <meta property="og:description" content="{og}"/>
    </head><body><p>Thin shell.</p></body></html>
    """
    out = parse_job_page("https://example.com/job/thin", html)
    assert len(out["description"]) >= MIN_JOB_DESCRIPTION_CHARS
    draft = validate_job_posting_draft(out)
    assert "detail" in draft.description
