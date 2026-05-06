"""CLI entry for careers discovery and single-job extraction."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.agent.batch_logger import BatchLogger
from app.agent.batch_pipeline_runner import BatchPipelineRunner
from app.agent.job_pipeline_runner import JobPipelineRunner
from app.agent.agent_runner import discover_jobs_from_careers_page, extract_job_from_url
from app.integrations.resume_tailor_client import (
    ResumeTailorClient,
)
from app.score.fit_scorer import score_job_fit
from app.storage.exporter import export_jobs_to_csv
import app.storage.repository as repository
from app.storage.repository import (
    list_review_ready_jobs,
    list_jobs,
    update_job_status,
    update_job_pipeline_state,
    upsert_job,
)
from app.utils.logger import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Job Agent — MVP extract/parse/validate slice")
    parser.add_argument(
        "--careers-url",
        metavar="URL",
        help="Discover job links from a careers listing page",
    )
    parser.add_argument(
        "--job-url",
        metavar="URL",
        help="Extract and validate a single job posting page",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Verbose logging (stderr) and extra CLI diagnostics",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save validated --job-url output to local sqlite storage",
    )
    parser.add_argument(
        "--db-path",
        default="data/processed/jobs.sqlite",
        help="SQLite path for local job storage",
    )
    parser.add_argument(
        "--list-jobs",
        action="store_true",
        help="List saved jobs from local storage",
    )
    parser.add_argument(
        "--status",
        help="Optional status filter for --list-jobs",
    )
    parser.add_argument(
        "--update-status",
        metavar="URL",
        help="Job URL to update status for",
    )
    parser.add_argument(
        "--new-status",
        metavar="STATUS",
        help="New status value for --update-status",
    )
    parser.add_argument(
        "--export-csv",
        metavar="PATH",
        help="Export saved jobs to CSV path",
    )
    parser.add_argument(
        "--score",
        action="store_true",
        help="Compute deterministic fit score for --job-url using --profile-file",
    )
    parser.add_argument(
        "--profile-file",
        default="config/profile.json",
        help="Path to profile JSON for --score",
    )
    parser.add_argument(
        "--tailor-job",
        metavar="JOB_ID",
        help="Tailor a saved job using Resume Tailor agent API and persist linkage fields",
    )
    parser.add_argument(
        "--pipeline-status",
        metavar="JOB_ID",
        help="Show pipeline orchestration status for a saved job id",
    )
    parser.add_argument(
        "--update-pipeline-status",
        metavar="JOB_ID",
        help="Update pipeline state for a saved job id",
    )
    parser.add_argument(
        "--new-state",
        metavar="STATE",
        help="Target state for --update-pipeline-status",
    )
    parser.add_argument(
        "--note",
        metavar="TEXT",
        help="Optional note for pipeline state history entry",
    )
    parser.add_argument(
        "--pipeline-logs",
        metavar="JOB_ID",
        help="Show recent pipeline execution logs for a saved job id",
    )
    parser.add_argument(
        "--batch-tailor",
        action="store_true",
        help="Run batch tailoring across filtered saved jobs",
    )
    parser.add_argument(
        "--state-filter",
        default="SCORED",
        help="Pipeline state filter for --batch-tailor",
    )
    parser.add_argument(
        "--min-fit-score",
        type=float,
        default=None,
        help="Minimum fit score filter for --batch-tailor",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max jobs to process for --batch-tailor",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List batch candidates without calling Resume Tailor",
    )
    parser.add_argument(
        "--batch-logs",
        metavar="BATCH_RUN_ID",
        help="Show recent logs for a batch run id",
    )
    parser.add_argument(
        "--review-queue",
        action="store_true",
        help="List jobs in REVIEW_READY for human decision",
    )
    parser.add_argument(
        "--mark-applied",
        metavar="JOB_ID",
        help="Mark a review-ready job as APPLIED",
    )
    parser.add_argument(
        "--reject-job",
        metavar="JOB_ID",
        help="Mark a review-ready job as REJECTED",
    )
    parser.add_argument(
        "--archive-job",
        metavar="JOB_ID",
        help="Archive a job from any state",
    )
    args = parser.parse_args()

    configure_logging(debug=args.debug)

    if args.update_status:
        if not args.new_status:
            raise ValueError("--new-status is required when --update-status is provided")
        update_job_status(args.update_status, args.new_status, args.db_path)
        print(f"status_updated url={args.update_status!r} new_status={args.new_status!r}")
        return

    runner = JobPipelineRunner(
        repository=repository,
        resume_tailor_client=ResumeTailorClient(
            base_url=os.getenv("RESUME_TAILOR_API_BASE_URL", "http://localhost:8000"),
            profile_id=os.getenv("RESUME_TAILOR_PROFILE_ID", "profile_example"),
        ),
        db_path=args.db_path,
    )
    batch_runner = BatchPipelineRunner(
        repository=repository,
        job_pipeline_runner=runner,
        db_path=args.db_path,
    )

    if args.pipeline_status:
        status = runner.get_pipeline_status(args.pipeline_status)
        print(f"pipeline_state={status.get('pipeline_state')}")
        print(f"pipeline_run_id={status.get('pipeline_run_id')}")
        print(f"last_successful_step={status.get('last_successful_step')}")
        print(f"retry_count={status.get('retry_count')}")
        print(f"last_pipeline_started_at={status.get('last_pipeline_started_at')}")
        print(f"last_pipeline_completed_at={status.get('last_pipeline_completed_at')}")
        print(f"state_history={status.get('state_history')}")
        print(f"resume_tailor_application_id={status.get('resume_tailor_application_id')}")
        print(f"resume_tailor_fit_score={status.get('resume_tailor_fit_score')}")
        print(f"resume_tailor_status={status.get('resume_tailor_status')}")
        print(f"last_tailored_at={status.get('last_tailored_at')}")
        print(f"last_pipeline_error={status.get('last_pipeline_error')}")
        print(f"recent_logs={status.get('recent_logs')}")
        return

    if args.pipeline_logs:
        status = runner.get_pipeline_status(args.pipeline_logs)
        recent_logs = status.get("recent_logs") or []
        print(f"pipeline_logs_count={len(recent_logs)}")
        for row in recent_logs:
            ts = row.get("timestamp")
            step = row.get("step_name")
            st = row.get("status")
            err = row.get("error_code") or ""
            msg = row.get("message") or ""
            print(f"{ts} | {step} | {st} | {err} | {msg}")
        return

    if args.batch_logs:
        rows = BatchLogger().recent(args.batch_logs, limit=100)
        print(f"batch_logs_count={len(rows)}")
        for row in rows:
            ts = row.get("timestamp")
            event = row.get("event")
            st = row.get("status")
            details = row.get("details")
            print(f"{ts} | {event} | {st} | {details}")
        return

    if args.batch_tailor:
        summary = batch_runner.run_batch_to_tailored(
            state_filter=args.state_filter,
            min_fit_score=args.min_fit_score,
            limit=args.limit,
            dry_run=args.dry_run,
        )
        print(f"batch_run_id={summary.get('batch_run_id')}")
        print(f"total_candidates={summary.get('total_candidates')}")
        print(f"processed={summary.get('processed')}")
        print(f"succeeded={summary.get('succeeded')}")
        print(f"failed={summary.get('failed')}")
        for row in summary.get("results") or []:
            print(
                "job_id={job_id} ok={ok} state={state} app_id={app_id} fit_score={fit_score} "
                "error_code={error_code} message={message}".format(
                    job_id=row.get("job_id"),
                    ok=row.get("ok"),
                    state=row.get("pipeline_state"),
                    app_id=row.get("resume_tailor_application_id"),
                    fit_score=row.get("fit_score"),
                    error_code=row.get("error_code"),
                    message=row.get("message"),
                )
            )
        return

    if args.review_queue:
        rows = list_review_ready_jobs(args.db_path, limit=args.limit or 20)
        print(f"review_ready_count={len(rows)}")
        for row in rows:
            print(
                "job_id={job_id} fit_score={fit_score} company={company!r} title={title!r} "
                "app_id={app_id} top_gaps={gaps}".format(
                    job_id=row.get("job_id"),
                    fit_score=row.get("resume_tailor_fit_score"),
                    company=row.get("company"),
                    title=row.get("title"),
                    app_id=row.get("resume_tailor_application_id"),
                    gaps=row.get("resume_tailor_gap_summary"),
                )
            )
        return

    if args.mark_applied:
        result = runner.update_status(args.mark_applied, "APPLIED", note="Manually marked applied from review queue.")
        if not result.ok:
            raise RuntimeError(result.message)
        print(f"job_id={args.mark_applied} pipeline_state={result.state} message={result.message}")
        return

    if args.reject_job:
        result = runner.update_status(args.reject_job, "REJECTED", note="Manually rejected from review queue.")
        if not result.ok:
            raise RuntimeError(result.message)
        print(f"job_id={args.reject_job} pipeline_state={result.state} message={result.message}")
        return

    if args.archive_job:
        result = runner.update_status(args.archive_job, "ARCHIVED", note="Manually archived from review queue.")
        if not result.ok:
            raise RuntimeError(result.message)
        print(f"job_id={args.archive_job} pipeline_state={result.state} message={result.message}")
        return

    if args.update_pipeline_status:
        if not args.new_state:
            raise ValueError("--new-state is required with --update-pipeline-status")
        result = runner.update_status(args.update_pipeline_status, args.new_state, note=args.note)
        if not result.ok:
            raise RuntimeError(result.message)
        print(f"pipeline_state={result.state}")
        print(f"message={result.message}")
        return

    if args.tailor_job:
        result = runner.run_to_tailored(args.tailor_job)
        if not result.ok:
            raise RuntimeError(result.message)
        print(f"application_id={result.data.get('application_id')}")
        print(f"fit_score={result.data.get('fit_score')}")
        print(f"recommended_next_step={result.data.get('recommended_next_step')}")
        print(f"top_gaps={result.data.get('top_gaps')}")
        return

    if args.export_csv:
        n = export_jobs_to_csv(args.db_path, args.export_csv, status=args.status)
        print(f"exported_jobs_count={n} csv_path={args.export_csv!r}")
        return

    if args.list_jobs:
        rows = list_jobs(args.db_path, status=args.status)
        print(f"saved_jobs_count={len(rows)}")
        for row in rows:
            print(
                f"{row.get('status')} | {row.get('company')!r} | "
                f"{row.get('title')!r} | {row.get('url')}"
            )
        return

    if args.careers_url:
        trace: dict | None = {} if args.debug else None
        links = discover_jobs_from_careers_page(args.careers_url, debug=args.debug, trace=trace)
        if args.debug and trace:
            ls = trace.get("link_stats") or {}
            print(f"url_checked={trace.get('requested_url')!r}")
            print(f"html_char_len={trace.get('html_char_len')}")
            print(f"anchor_tags_total={ls.get('anchor_tags_total')}")
            print(f"anchors_resolved_http={ls.get('anchors_resolved_http')}")
            print(f"embedded_urls_found={ls.get('embedded_urls_found')}")
            print(f"candidates_before_filter={ls.get('consider_attempts')}")
            print(f"removed_noise={ls.get('removed_noise')}")
            print(f"removed_inclusion={ls.get('removed_inclusion')}")
            print(f"candidates_after_filter={ls.get('candidates_after_filter')}")
        print(f"discovered_job_link_count={len(links)}")
        limit = 10 if args.debug else 5
        for item in links[:limit]:
            print(item.get("url", ""))
        return

    if args.job_url:
        trace = {} if args.debug else None
        draft = extract_job_from_url(args.job_url, debug=args.debug, trace=trace)
        scored: dict | None = None
        if args.debug and trace:
            print(f"url_checked={trace.get('requested_url')!r}")
            print(f"html_char_len={trace.get('html_char_len')}")
            print(f"parsed_title={trace.get('parsed_title')!r}")
            print(f"parsed_company={trace.get('parsed_company')!r}")
            print(f"parsed_location={trace.get('parsed_location')!r}")
            print(f"description_len_before_validation={trace.get('description_len_before_validation')}")
            print(f"validation_warnings={trace.get('validation_warnings')}")
        print(f"title={draft.title!r}")
        print(f"company={draft.company!r}")
        print(f"location={draft.location!r}")
        print(f"url={draft.url!r}")
        print(f"description_char_count={len(draft.description)}")
        if not args.debug:
            print(f"validation_warnings={draft.validation_warnings}")
        if args.score:
            profile_path = Path(args.profile_file)
            if not profile_path.exists():
                print(f"score_warning=profile file not found: {args.profile_file!r}")
            else:
                try:
                    profile = json.loads(profile_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    print(f"score_warning=invalid profile JSON: {exc}")
                    profile = None
                if isinstance(profile, dict):
                    scored = score_job_fit(draft, profile)
                    print(f"fit_score={scored.get('fit_score')}")
                    print(f"matched_skills={scored.get('matched_skills')}")
                    print(f"missing_skills={scored.get('missing_skills')}")
                    print(f"fit_reason={scored.get('short_reason')}")
                else:
                    print("score_warning=profile JSON must be an object")
        if args.save:
            saved = upsert_job(draft, args.db_path, scoring=scored)
            update_job_pipeline_state(
                int(saved["id"]),
                args.db_path,
                pipeline_state="EXTRACTED",
                note="Job extracted and saved from CLI.",
            )
            print(f"saved_id={saved.get('id')} status={saved.get('status')} db_path={args.db_path!r}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
