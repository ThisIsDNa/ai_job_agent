from __future__ import annotations

import requests

from app.integrations.resume_tailor_client import (
    ResumeTailorApiUnavailableError,
    ResumeTailorClient,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = "{}"

    def json(self) -> dict:
        return self._payload


def test_tailor_job_builds_expected_payload_and_stable_idempotency() -> None:
    client = ResumeTailorClient("http://localhost:8000", "profile_example")
    captured: dict = {}

    def _fake_request(*, method, url, json, timeout):  # type: ignore[no-untyped-def]
        captured["method"] = method
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse(200, {"application_id": "app_123", "fit_score": 88})

    client._session.request = _fake_request  # type: ignore[method-assign]
    out = client.tailor_job(
        job_id="42",
        title="Data Analyst",
        company="Acme",
        description="Analyze data and build dashboards.",
        url="https://jobs.example.com/42",
    )

    assert out["application_id"] == "app_123"
    assert captured["method"] == "POST"
    assert captured["url"] == "http://localhost:8000/agent/tailor-job"
    assert captured["json"]["idempotency_key"] == "profile_example:42"
    assert captured["json"]["source"] == "ai_job_agent"
    assert captured["json"]["source_job_id"] == "42"
    assert captured["json"]["source_url"] == "https://jobs.example.com/42"


def test_resume_tailor_api_unavailable_error_is_friendly() -> None:
    client = ResumeTailorClient("http://localhost:8000", "profile_example")

    def _raise_request(*, method, url, json, timeout):  # type: ignore[no-untyped-def]
        raise requests.RequestException("connection refused")

    client._session.request = _raise_request  # type: ignore[method-assign]
    try:
        client.tailor_job(
            job_id="1",
            title="Analyst",
            company="Acme",
            description="desc",
            url=None,
        )
    except ResumeTailorApiUnavailableError as exc:
        assert "Resume Tailor API is not available" in str(exc)
    else:
        raise AssertionError("Expected ResumeTailorApiUnavailableError")
