"""Tests for job link discovery from HTML (anchors + static embeds)."""

from app.extract.job_link_finder import find_job_links


def test_find_job_links_resolves_relative_urls() -> None:
    html = """
    <html><body>
      <a href="/careers/opening/123">Apply</a>
      <a href="https://other.example/jobs/99">Other</a>
    </body></html>
    """
    base = "https://corp.example.com"
    links = find_job_links(base, html)
    urls = {x["url"] for x in links}
    assert "https://corp.example.com/careers/opening/123" in urls
    assert "https://other.example/jobs/99" in urls


def test_find_job_links_deduplicates_by_url() -> None:
    html = """
    <a href="/jobs/1">First</a>
    <a href="/jobs/1">Duplicate text</a>
    """
    links = find_job_links("https://x.example/", html)
    assert len(links) == 1
    assert links[0]["url"] == "https://x.example/jobs/1"


def test_find_job_links_prefers_job_like_hrefs() -> None:
    html = """
    <a href="/about">About</a>
    <a href="/careers/role?id=5">Role</a>
    """
    links = find_job_links("https://co.example", html)
    assert len(links) == 1
    assert "careers" in links[0]["url"]


def test_ashby_extracts_embedded_job_urls_from_script() -> None:
    job_url = "https://jobs.ashbyhq.com/happyrobot.ai/67c117e2-4a9c-40db-b68c-c0da10350270"
    html = f"""
    <html><head><script type="application/json">
    {{"listings": [{{"url": "{job_url}?src=web"}}]}}
    </script></head>
    <body><a href="/about">About</a></body></html>
    """
    base = "https://jobs.ashbyhq.com/happyrobot.ai"
    links = find_job_links(base, html)
    urls = [x["url"] for x in links]
    assert any(job_url.split("?")[0] in u for u in urls)


def test_ashby_quoted_relative_paths() -> None:
    html = """
    <script>window.__DATA__ = {"href": "/happyrobot.ai/67c117e2-4a9c-40db-b68c-c0da10350270"};</script>
    """
    base = "https://jobs.ashbyhq.com/happyrobot.ai"
    links = find_job_links(base, html)
    urls = {x["url"] for x in links}
    assert "https://jobs.ashbyhq.com/happyrobot.ai/67c117e2-4a9c-40db-b68c-c0da10350270" in urls


def test_intel_style_filters_nav_keeps_workday_job() -> None:
    html = """
    <html><body>
      <a href="/en-US/External/life-at-intel">Life at Intel</a>
      <a href="/en-US/External/benefits">Benefits</a>
      <a href="/en-US/External/events">Events</a>
      <a href="/en-US/External/students">Students</a>
      <a href="https://intel.wd1.myworkdayjobs.com/en-US/External/job/Santa-Clara-CA/Senior-Engineer_12345">
        Senior Engineer
      </a>
    </body></html>
    """
    base = "https://intel.wd1.myworkdayjobs.com/en-US/External"
    links = find_job_links(base, html)
    urls = {x["url"] for x in links}
    assert any("myworkdayjobs.com" in u and "/job/" in u for u in urls)
    assert not any("life-at" in u for u in urls)
    assert not any("benefits" in u.lower() for u in urls)
    assert not any("/events" in u for u in urls)
    assert not any("/students" in u for u in urls)


def test_greenhouse_job_link() -> None:
    html = """
    <a href="https://boards.greenhouse.io/acme/jobs/998877">Software Engineer</a>
    """
    links = find_job_links("https://boards.greenhouse.io/acme", html)
    assert len(links) == 1
    assert "greenhouse.io" in links[0]["url"]
    assert "998877" in links[0]["url"]


def test_lever_job_link() -> None:
    html = """
    <a href="https://jobs.lever.co/acme-corp/senior-analyst">Senior Analyst</a>
    """
    links = find_job_links("https://jobs.lever.co/acme-corp", html)
    assert len(links) == 1
    assert links[0]["url"].startswith("https://jobs.lever.co/acme-corp/")
    assert links[0]["title"] == "Senior Analyst"


def test_duplicate_links_merged_single_entry() -> None:
    u = "https://jobs.lever.co/acme/backend-eng"
    html = f"""
    <a href="{u}">Backend</a>
    <script>applyUrl = "{u}"</script>
    """
    links = find_job_links("https://jobs.lever.co/acme", html)
    assert len(links) == 1
    assert links[0]["url"] == u


def test_prioritizes_higher_score_job_detail_urls() -> None:
    """Job-detail path should sort before generic careers link when both match."""
    html = """
    <a href="/careers/overview">Overview</a>
    <a href="/job/999-senior">Senior Role</a>
    """
    links = find_job_links("https://corp.example.com", html)
    assert len(links) >= 1
    assert "/job/" in links[0]["url"]
