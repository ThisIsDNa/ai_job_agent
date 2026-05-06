"""One-page Streamlit UI for discovery, extraction, pipeline status, and CSV export."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import streamlit as st

# Streamlit runs this file directly, so add project root for absolute app.* imports.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app.storage.repository as repository
from app.agent.agent_runner import discover_jobs_from_careers_page, extract_job_from_url
from app.agent.batch_pipeline_runner import BatchPipelineRunner
from app.agent.job_pipeline_runner import JobPipelineRunner
from app.integrations.resume_tailor_client import (
    ResumeTailorApiError,
    ResumeTailorApiUnavailableError,
    ResumeTailorClient,
)
from app.score.fit_scorer import score_job_fit
from app.storage.exporter import export_jobs_to_csv
from app.storage.repository import (
    ALLOWED_STATUSES,
    list_review_ready_jobs,
    list_jobs,
    update_job_resume_tailor_result,
    update_job_status,
    upsert_job,
)


def _init_state() -> None:
    if "discovered_links" not in st.session_state:
        st.session_state.discovered_links = []
    if "latest_job" not in st.session_state:
        st.session_state.latest_job = None
    if "last_export_path" not in st.session_state:
        st.session_state.last_export_path = ""
    if "last_export_count" not in st.session_state:
        st.session_state.last_export_count = 0
    if "latest_score" not in st.session_state:
        st.session_state.latest_score = None
    if "tailor_preview" not in st.session_state:
        st.session_state.tailor_preview = None


def main() -> None:
    """Renders one-page thin UI over existing backend functions."""
    _init_state()

    st.set_page_config(page_title="AI Job Agent", layout="wide")
    st.title("AI Job Agent")
    st.caption("Discover -> Extract -> Save -> Update Status -> Export")

    db_path = st.text_input(
        "SQLite DB Path",
        value="data/processed/jobs.sqlite",
        help="Local storage path used by save/list/status/export actions.",
    )
    export_path = st.text_input(
        "CSV Export Path",
        value="data/processed/jobs_export.csv",
    )
    profile_path = st.text_input(
        "Profile JSON Path (for optional scoring)",
        value="config/profile.json",
    )
    resume_tailor_api_base_url = st.text_input(
        "Resume Tailor API Base URL",
        value=os.getenv("RESUME_TAILOR_API_BASE_URL", "http://localhost:8000"),
    )
    resume_tailor_profile_id = st.text_input(
        "Resume Tailor Profile ID",
        value=os.getenv("RESUME_TAILOR_PROFILE_ID", "profile_example"),
    )

    st.divider()
    st.subheader("A. Discover Jobs")
    careers_url = st.text_input("Careers URL", key="careers_url_input")
    if st.button("Discover Jobs", use_container_width=True):
        if not careers_url.strip():
            st.warning("Enter a careers URL first.")
        else:
            trace: dict = {}
            try:
                links = discover_jobs_from_careers_page(careers_url.strip(), debug=False, trace=trace)
                st.session_state.discovered_links = links
                if links:
                    st.success(f"Discovered {len(links)} candidate links.")
                else:
                    st.warning(
                        "No candidate job links found. Try another careers page URL or run CLI with --debug."
                    )
            except Exception as exc:  # noqa: BLE001 - surface backend errors directly
                st.error(f"Discovery failed: {exc}")

    links = st.session_state.discovered_links
    if links:
        st.dataframe(links, use_container_width=True, hide_index=True)
    else:
        st.info("No discovered links yet.")

    st.divider()
    st.subheader("B. Extract Job")
    job_url = st.text_input("Job URL", key="job_url_input")
    if st.button("Extract Job", use_container_width=True):
        if not job_url.strip():
            st.warning("Enter a job URL first.")
        else:
            trace = {}
            try:
                draft = extract_job_from_url(job_url.strip(), debug=False, trace=trace)
                st.session_state.latest_job = draft
                st.success("Job extracted and validated.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Extraction failed: {exc}")

    latest_job = st.session_state.latest_job
    score_before_save = st.checkbox("Score job before saving", value=False)
    if latest_job is not None:
        st.markdown("**Latest Extracted Job**")
        st.write(f"title: {latest_job.title!r}")
        st.write(f"company: {latest_job.company!r}")
        st.write(f"location: {latest_job.location!r}")
        st.write(f"url: {latest_job.url!r}")
        st.write(f"description_char_count: {len(latest_job.description)}")
        st.write(f"validation_warnings: {latest_job.validation_warnings}")
        if score_before_save:
            p = Path(profile_path)
            if not p.exists():
                st.warning(f"Profile file not found: {profile_path!r}")
                st.session_state.latest_score = None
            else:
                try:
                    profile_obj = json.loads(p.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    st.warning(f"Invalid profile JSON: {exc}")
                    st.session_state.latest_score = None
                else:
                    if isinstance(profile_obj, dict):
                        st.session_state.latest_score = score_job_fit(latest_job, profile_obj)
                    else:
                        st.warning("Profile JSON must be an object.")
                        st.session_state.latest_score = None
        else:
            st.session_state.latest_score = None

        if st.session_state.latest_score:
            sc = st.session_state.latest_score
            st.markdown("**Fit Scoring (heuristic)**")
            st.write(f"fit_score: {sc.get('fit_score')}")
            st.write(f"matched_skills: {sc.get('matched_skills')}")
            st.write(f"missing_skills: {sc.get('missing_skills')}")
            st.write(f"fit_reason: {sc.get('short_reason')}")
        if st.button("Save Job", use_container_width=True):
            try:
                saved = upsert_job(latest_job, db_path, scoring=st.session_state.latest_score)
                st.success(
                    f"Saved id={saved.get('id')} status={saved.get('status')} url={saved.get('url')}"
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"Save failed: {exc}")
    else:
        st.info("No extracted job yet.")

    st.divider()
    st.subheader("C. Job Pipeline")
    status_filter_options = ["All", *ALLOWED_STATUSES]
    selected_filter = st.selectbox("Filter by status", status_filter_options, index=0)
    status_filter = None if selected_filter == "All" else selected_filter
    st.caption(
        "Filter applies to the table below. Use 'All' to see every saved job."
    )
    try:
        jobs = list_jobs(db_path, status=status_filter)
    except Exception as exc:  # noqa: BLE001
        jobs = []
        st.error(f"Load jobs failed: {exc}")

    if jobs:
        display_rows = [
            {
                "status": j.get("status"),
                "company": j.get("company"),
                "title": j.get("title"),
                "location": j.get("location"),
                "fit_score": j.get("fit_score"),
                "url": j.get("url"),
                "updated_at": j.get("updated_at"),
            }
            for j in jobs
        ]
        st.dataframe(display_rows, use_container_width=True, hide_index=True)
    else:
        st.info("No jobs found for current filter.")

    if jobs:
        url_options = [str(j.get("url")) for j in jobs if str(j.get("url", "")).strip()]
        selected_url = st.selectbox("Select job URL to update status", url_options)
        selected_job = next((j for j in jobs if str(j.get("url")) == selected_url), None)
        new_status = st.selectbox("New status", list(ALLOWED_STATUSES), index=0)
        if st.button("Update Status", use_container_width=True):
            try:
                update_job_status(selected_url, new_status, db_path)
                st.success(f"Updated {selected_url} -> {new_status}")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Status update failed: {exc}")

        if st.button("Tailor Resume", use_container_width=True):
            if not selected_job:
                st.warning("Select a saved job first.")
            else:
                description = str(selected_job.get("description") or "").strip()
                if not description:
                    st.error("Job description is missing. Cannot tailor without a description.")
                else:
                    try:
                        client = ResumeTailorClient(
                            base_url=resume_tailor_api_base_url,
                            profile_id=resume_tailor_profile_id,
                        )
                        out = client.tailor_job(
                            job_id=str(selected_job.get("id")),
                            title=str(selected_job.get("title") or ""),
                            company=str(selected_job.get("company") or ""),
                            description=description,
                            url=str(selected_job.get("url") or ""),
                        )
                        app_id = str(
                            out.get("application_id")
                            or out.get("id")
                            or out.get("application", {}).get("application_id")
                            or ""
                        ).strip() or None
                        fit_score_raw = out.get("fit_score")
                        fit_score = (
                            int(fit_score_raw) if isinstance(fit_score_raw, (int, float)) else None
                        )
                        next_step = str(out.get("recommended_next_step") or "tailored")
                        top_gaps = out.get("top_gaps") or out.get("gap_summary") or []
                        if isinstance(top_gaps, list):
                            gap_summary = (
                                "; ".join(str(x) for x in top_gaps[:3] if str(x).strip()) or None
                            )
                        else:
                            gap_summary = str(top_gaps).strip() or None
                        from datetime import datetime, timezone

                        update_job_resume_tailor_result(
                            int(selected_job.get("id")),
                            db_path,
                            application_id=app_id,
                            fit_score=fit_score,
                            status=next_step,
                            gap_summary=gap_summary,
                            last_tailored_at=(
                                str(out.get("tailored_at") or "").strip()
                                or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                            ),
                        )
                        st.session_state.tailor_preview = {
                            "application_id": app_id,
                            "fit_score": fit_score,
                            "recommended_next_step": next_step,
                            "top_gaps": top_gaps,
                            "raw": out,
                        }
                        st.success("Tailored job sent to Resume Tailor and linkage saved.")
                    except ResumeTailorApiUnavailableError:
                        st.error(
                            "Resume Tailor API is not available. Start resume-tailor backend on port 8000."
                        )
                    except ResumeTailorApiError as exc:
                        st.error(str(exc))
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Tailor Resume failed: {exc}")

        if st.session_state.tailor_preview:
            tp = st.session_state.tailor_preview
            st.markdown("**Resume Tailor Result**")
            st.write(f"application_id: {tp.get('application_id')}")
            st.write(f"fit_score: {tp.get('fit_score')}")
            st.write(f"recommended_next_step: {tp.get('recommended_next_step')}")
            st.write(f"top_gaps: {tp.get('top_gaps')}")

    st.divider()
    st.subheader("Review Queue")
    try:
        review_jobs = list_review_ready_jobs(db_path, limit=20)
    except Exception as exc:  # noqa: BLE001
        review_jobs = []
        st.error(f"Loading review queue failed: {exc}")

    if review_jobs:
        rt_client = ResumeTailorClient(
            base_url=resume_tailor_api_base_url,
            profile_id=resume_tailor_profile_id,
        )
        review_runner = JobPipelineRunner(
            repository=repository,
            resume_tailor_client=rt_client,
            db_path=db_path,
        )
        for row in review_jobs:
            jid = str(row.get("job_id"))
            title = str(row.get("title") or "")
            company = str(row.get("company") or "")
            fit = row.get("resume_tailor_fit_score")
            app_id = row.get("resume_tailor_application_id")
            gaps = row.get("resume_tailor_gap_summary")
            last_tailored = row.get("last_tailored_at")
            url = row.get("url")
            st.markdown(f"**{company} — {title}**")
            st.write(f"job_id: {jid}")
            st.write(f"fit_score: {fit}")
            st.write(f"application_id: {app_id}")
            st.write(f"top_gaps: {gaps}")
            st.write(f"last_tailored_at: {last_tailored}")
            if url:
                st.markdown(f"[Open Job URL]({url})")

            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("Mark Applied", key=f"rq_apply_{jid}"):
                    result = review_runner.update_status(jid, "APPLIED", note="Marked applied via review queue UI.")
                    if result.ok:
                        st.success(f"Job {jid} marked APPLIED.")
                        st.rerun()
                    else:
                        st.error(result.message)
            with c2:
                if st.button("Reject", key=f"rq_reject_{jid}"):
                    result = review_runner.update_status(jid, "REJECTED", note="Marked rejected via review queue UI.")
                    if result.ok:
                        st.success(f"Job {jid} marked REJECTED.")
                        st.rerun()
                    else:
                        st.error(result.message)
            with c3:
                if st.button("Archive", key=f"rq_archive_{jid}"):
                    result = review_runner.update_status(jid, "ARCHIVED", note="Archived via review queue UI.")
                    if result.ok:
                        st.success(f"Job {jid} archived.")
                        st.rerun()
                    else:
                        st.error(result.message)
            st.markdown("---")
    else:
        st.info("No jobs currently in REVIEW_READY.")

    st.divider()
    st.subheader("Batch Actions")
    batch_state_filter = st.text_input("Batch state filter", value="SCORED")
    batch_min_fit_score = st.number_input(
        "Batch minimum fit score",
        value=70.0,
        min_value=0.0,
        max_value=100.0,
        step=1.0,
    )
    batch_limit = st.number_input("Batch limit", value=10, min_value=1, step=1)
    batch_dry_run = st.checkbox("Dry run batch (no Resume Tailor calls)", value=True)
    if st.button("Run Batch Tailor", use_container_width=True):
        try:
            client = ResumeTailorClient(
                base_url=resume_tailor_api_base_url,
                profile_id=resume_tailor_profile_id,
            )
            job_runner = JobPipelineRunner(
                repository=repository,
                resume_tailor_client=client,
                db_path=db_path,
            )
            batch_runner = BatchPipelineRunner(
                repository=repository,
                job_pipeline_runner=job_runner,
                db_path=db_path,
            )
            batch_summary = batch_runner.run_batch_to_tailored(
                state_filter=(batch_state_filter or "").strip() or None,
                min_fit_score=float(batch_min_fit_score),
                limit=int(batch_limit),
                dry_run=batch_dry_run,
            )
            st.success(
                f"Batch {batch_summary.get('batch_run_id')} completed. "
                f"succeeded={batch_summary.get('succeeded')} failed={batch_summary.get('failed')}"
            )
            st.write(f"total_candidates: {batch_summary.get('total_candidates')}")
            st.write(f"processed: {batch_summary.get('processed')}")
            st.dataframe(batch_summary.get("results") or [], use_container_width=True, hide_index=True)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Batch tailor failed: {exc}")

    st.divider()
    st.subheader("D. Export")
    export_filter = st.selectbox("Export status filter", status_filter_options, index=0)
    export_status = None if export_filter == "All" else export_filter
    if st.button("Export CSV", use_container_width=True):
        try:
            count = export_jobs_to_csv(db_path, export_path, status=export_status)
            st.session_state.last_export_path = export_path
            st.session_state.last_export_count = count
            st.success(f"Exported {count} rows to {export_path}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Export failed: {exc}")

    if st.session_state.last_export_path:
        abs_path = str(Path(st.session_state.last_export_path).resolve())
        st.write(f"Last export path: {abs_path}")
        st.write(f"Last export row count: {st.session_state.last_export_count}")


if __name__ == "__main__":
    main()
