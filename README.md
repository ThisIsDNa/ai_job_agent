# AI Job Agent

`ai_job_agent` is a deterministic job workflow engine that discovers jobs, extracts structured job data, scores fit, and orchestrates job lifecycle progression. Resume intelligence and application 
artifacts are delegated to `resume-tailor` through an API client.

## Overview

- `ai_job_agent` discovers/extracts/scores jobs and persists local tracking metadata.
- `resume-tailor` owns resume intelligence, tailoring decisions, and application artifacts.
- `ai_job_agent` orchestrates lifecycle state transitions and execution tracing around those external calls.

## Core features

- **Discover / extract** — careers link discovery and single-job HTML extraction with validation.
- **Score** — deterministic fit scoring from a local profile (no LLM required).
- **Batch tailor** — process multiple saved jobs through `resume-tailor` with filters, dry-run, and continue-on-failure summaries.
- **Review queue** — list jobs in `REVIEW_READY` with Resume Tailor linkage and gap highlights; apply / reject / archive via explicit CLI or UI actions only.
- **Observability** — per-job pipeline runs, JSONL traces, batch logs, and structured status fields in SQLite.
- **Outcome tracking** — pipeline state history and optional workspace job `status` for list/export workflows (no auto-submit).

## Lifecycle

End-to-end story:

`Discover / Extract → Score → Batch Tailor → Review Queue → Manual Decision → Outcome Tracking`

After tailoring (single job or batch), eligible jobs land in **`REVIEW_READY`**. You decide **Applied**, **Rejected**, or **Archived** explicitly. The tool prepares artifacts and metadata for 
review; it does not submit applications on your behalf.

**The system prepares applications for review but does not submit applications automatically.**

## Architecture

Core orchestration and integration modules:

- `app/agent/pipeline_states.py` — deterministic state model and transition rules.
- `app/agent/task_result.py` — structured pipeline task result contract.
- `app/agent/job_pipeline_runner.py` — orchestration spine for run/update/status behaviors.
- `app/agent/pipeline_logger.py` — append-only JSONL execution tracing.
- `app/agent/batch_pipeline_runner.py` — batch-safe orchestration across multiple saved jobs.
- `app/agent/batch_logger.py` — append-only batch event logs.
- `app/integrations/resume_tailor_client.py` — external API client for Resume Tailor.
- `app/storage/repository.py` — SQLite persistence helpers and migration-safe state metadata updates.

Supporting modules:

- `app/extract` — source loading and link discovery.
- `app/parse` — parsing and cleanup.
- `app/score` — deterministic fit scoring.
- `app/validation` — blocking quality gate.
- `ui/streamlit_app.py` — operator-facing workflow actions.

## Pipeline States

Primary lifecycle:

`DISCOVERED -> EXTRACTED -> SCORED -> TAILORED -> REVIEW_READY -> APPLIED -> INTERVIEW / REJECTED / OFFER`

Operational states:

- `FAILED` — step failed and requires operator intervention or retry.
- `ARCHIVED` — terminal archived state.

State transitions are validated by `is_valid_transition(...)` in `app/agent/pipeline_states.py`.

## Resume Tailor Integration

Environment variables:

```bash
RESUME_TAILOR_API_BASE_URL=http://localhost:8000
RESUME_TAILOR_PROFILE_ID=profile_dustin
```

Endpoints used by `ResumeTailorClient`:

- `POST /agent/resolve-resume`
- `POST /agent/tailor-job`
- `GET /agent/profile/{profile_id}/strategy`
- `GET /agent/application/{application_id}`

Design boundary:

- `resume-tailor` is treated as an external service.
- `ai_job_agent` does not duplicate resume-tailor core logic.
- Idempotency is handled via the existing integration payload contract.

## Setup

```bash
cd ai_job_agent
pip install -r requirements.txt
```

Run UI:

```bash
python -m streamlit run ui/streamlit_app.py
```

## CLI Usage

Discovery and extraction:

```bash
python main.py --careers-url "https://example.com/careers"
python main.py --job-url "https://example.com/job/123"
python main.py --job-url "https://example.com/job/123" --save --db-path "data/processed/jobs.sqlite"
```

Tailor and orchestration:

```bash
python main.py --tailor-job 123 --db-path data/processed/jobs.sqlite
python main.py --pipeline-status 123 --db-path data/processed/jobs.sqlite
python main.py --pipeline-logs 123 --db-path data/processed/jobs.sqlite
python main.py --batch-tailor --state-filter SCORED --min-fit-score 70 --limit 10 --db-path data/processed/jobs.sqlite
python main.py --batch-tailor --dry-run --db-path data/processed/jobs.sqlite
python main.py --batch-logs batch_<id> --db-path data/processed/jobs.sqlite
```

Review queue (manual decisions only):

```bash
python main.py --review-queue --db-path data/processed/jobs.sqlite
python main.py --mark-applied 123 --db-path data/processed/jobs.sqlite
python main.py --reject-job 123 --db-path data/processed/jobs.sqlite
python main.py --archive-job 123 --db-path data/processed/jobs.sqlite
```

Optional: limit how many review-ready rows are listed (`--limit` defaults to `10`; use e.g. `--limit 20` with `--review-queue`).

Pipeline state management:

```bash
python main.py --update-pipeline-status 123 --new-state REVIEW_READY --note "manual promotion"
```

Scoring and export:

```bash
python main.py --job-url "https://example.com/job/123" --score --profile-file "config/profile.json"
python main.py --export-csv "data/processed/jobs_export.csv"
```

## Observability

Pipeline execution tracking includes:

- `pipeline_run_id`
- `retry_count`
- `last_successful_step`
- `last_pipeline_started_at`
- `last_pipeline_completed_at`
- `last_pipeline_error`

Execution traces are append-only JSONL logs under:

- `data/pipeline_logs/`

Each entry captures:

- timestamp
- job_id
- pipeline_run_id
- step_name
- status
- details (and structured error fields when present)

Use CLI for quick inspection:

```bash
python main.py --pipeline-status 123 --db-path data/processed/jobs.sqlite
python main.py --pipeline-logs 123 --db-path data/processed/jobs.sqlite
python main.py --batch-logs batch_<id> --db-path data/processed/jobs.sqlite
```

Batch observability:

- Batch runs emit append-only JSONL logs under `data/pipeline_logs/batches/`.
- Dry-run mode returns candidates without calling Resume Tailor.
- Batch processing continues on per-job failures and returns structured success/failure summaries.

## Design Philosophy

- Deterministic workflow first.
- AI is an enhancement layer, not an uncontrolled decision-maker.
- Resume Tailor remains an external service boundary.
- Human review is expected before apply-stage actions.
- **The system prepares applications for review but does not submit applications automatically** (CLI, batch, and UI included).

## Future Work

- Scheduled job processing.
- Batch tailoring orchestration.
- UI pipeline dashboard for run traces and state transitions.
- Automated retry queue for retryable failures.
- Outcome feedback loop to improve prioritization heuristics.

## Tests

```bash
pytest
```
