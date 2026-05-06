"""Tests for deterministic fit scoring."""

from app.schemas.job_schema import JobPostingDraft
from app.score.fit_scorer import score_job_fit


def _job() -> JobPostingDraft:
    return JobPostingDraft(
        title="Senior Business Analyst",
        company="Acme",
        location="Remote",
        url="https://jobs.example.com/fit/1",
        description=(
            "Looking for a Business Analyst with SQL, Excel, and stakeholder communication. "
            "Experience with requirements gathering and UAT preferred. 5+ years required."
        ),
        source="jobs.example.com",
        validation_warnings=[],
    )


def test_score_job_fit_consistent_output() -> None:
    profile = {
        "target_roles": ["Business Analyst", "Product Analyst"],
        "core_skills": ["SQL", "Excel", "Power BI", "UAT"],
        "years_experience": 6,
    }
    out = score_job_fit(_job(), profile)
    assert isinstance(out["fit_score"], int)
    assert 0 <= out["fit_score"] <= 100
    assert out["matched_groups"] == ["sql", "excel", "uat"]
    assert out["missing_groups"] == ["bi"]
    assert out["matched_skills"] == ["SQL", "Excel", "UAT"]
    assert out["missing_skills"] == ["Power BI"]
    assert "Matched 3/4 skill groups" in out["short_reason"]


def test_grouped_skills_do_not_inflate_missing_count() -> None:
    """Several profile lines in the same group count as one unit for scoring."""
    job = JobPostingDraft(
        title="Analyst",
        company="Co",
        location="Remote",
        url="https://jobs.example.com/fit/2",
        description="We need SQL and reporting for dashboards.",
        source="jobs.example.com",
        validation_warnings=[],
    )
    profile = {
        "target_roles": [],
        "core_skills": [
            "SQL querying",
            "data analysis with SQL",
            "Power BI dashboards",
        ],
        "years_experience": 6,
    }
    out = score_job_fit(job, profile)
    # sql + bi = 2 groups; JD matches sql variants and bi variants -> 2/2 groups
    assert out["matched_groups"] == ["sql", "bi"]
    assert out["missing_groups"] == []
    assert out["fit_score"] == 75  # 60 skill + 15 years (no role match)


def test_score_job_fit_deterministic_same_input_same_output() -> None:
    profile = {
        "target_roles": ["Business Analyst"],
        "core_skills": ["SQL", "Excel"],
        "years_experience": 6,
    }
    a = score_job_fit(_job(), profile)
    b = score_job_fit(_job(), profile)
    assert a == b
