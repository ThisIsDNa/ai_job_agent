"""HTTP client for Resume Tailor's agent-facing API."""

from __future__ import annotations

from typing import Any

import requests


class ResumeTailorApiError(RuntimeError):
    """Base error for Resume Tailor integration failures."""


class ResumeTailorApiUnavailableError(ResumeTailorApiError):
    """Raised when Resume Tailor API is unavailable."""


class ResumeTailorClient:
    """Thin client that treats Resume Tailor as an external service."""

    def __init__(self, base_url: str, profile_id: str) -> None:
        self.base_url = (base_url or "http://localhost:8000").rstrip("/")
        self.profile_id = (profile_id or "profile_example").strip() or "profile_example"
        self._session = requests.Session()
        self._timeout_seconds = 20

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = self._session.request(
                method=method,
                url=url,
                json=json_payload,
                timeout=self._timeout_seconds,
            )
        except requests.RequestException as exc:
            raise ResumeTailorApiUnavailableError(
                "Resume Tailor API is not available. Start resume-tailor backend on port 8000."
            ) from exc

        try:
            payload = response.json() if response.text else {}
        except ValueError:
            payload = {"detail": response.text.strip()}

        if response.status_code >= 400:
            detail = payload.get("detail")
            if isinstance(detail, dict):
                message = str(detail.get("message") or detail.get("error") or detail)
                suggestion = detail.get("suggested_action")
            else:
                message = str(detail or payload or f"HTTP {response.status_code}")
                suggestion = payload.get("suggested_action")
            if suggestion:
                message = f"{message} Suggested action: {suggestion}"
            raise ResumeTailorApiError(message)
        return payload if isinstance(payload, dict) else {"data": payload}

    def resolve_resume(self, preference: str = "auto") -> dict[str, Any]:
        return self._request(
            "POST",
            "/agent/resolve-resume",
            json_payload={
                "profile_id": self.profile_id,
                "resume_version_preference": preference,
            },
        )

    def get_profile_strategy(self) -> dict[str, Any]:
        return self._request("GET", f"/agent/profile/{self.profile_id}/strategy")

    def tailor_job(
        self,
        job_id: str,
        title: str,
        company: str,
        description: str,
        url: str | None = None,
        resume_version_preference: str = "auto",
    ) -> dict[str, Any]:
        job_id_clean = (job_id or "").strip()
        if not job_id_clean:
            raise ValueError("job_id is required")
        if not str(description or "").strip():
            raise ValueError("Job description is missing. Cannot tailor without a description.")

        payload = {
            "profile_id": self.profile_id,
            "job_id": job_id_clean,
            "title": title,
            "company": company,
            "description": description,
            "url": url,
            "resume_version_preference": resume_version_preference,
            "idempotency_key": f"{self.profile_id}:{job_id_clean}",
            "source": "ai_job_agent",
            "source_job_id": job_id_clean,
            "source_url": url,
        }
        return self._request("POST", "/agent/tailor-job", json_payload=payload)

    def get_application(self, application_id: str) -> dict[str, Any]:
        app_id = (application_id or "").strip()
        if not app_id:
            raise ValueError("application_id is required")
        return self._request("GET", f"/agent/application/{app_id}")
