# Architecture Notes

## System Roles

- `ai_job_agent`: discovers, extracts, scores, and orchestrates job lifecycle progression.
- `resume-tailor`: external service that performs resume intelligence/tailoring and owns application artifacts.

## Orchestration Layer

- `app/agent/pipeline_states.py`
  - Canonical state constants and transition guard (`is_valid_transition`).
- `app/agent/task_result.py`
  - Structured result contract (`ok`, `state`, `message`, `data`, `error_code`, `retryable`, `suggested_action`).
- `app/agent/job_pipeline_runner.py`
  - Deterministic orchestration spine for:
    - `run_to_tailored(job_id)`
    - `update_status(job_id, new_state, note=None)`
    - `get_pipeline_status(job_id)`
- `app/agent/pipeline_logger.py`
  - Append-only structured execution logs (`data/pipeline_logs/job_<id>.jsonl`).
- `app/agent/batch_pipeline_runner.py`
  - Batch orchestration for multiple saved jobs:
    - state/fit/limit filtering
    - dry-run candidate preview
    - continue-on-failure processing
- `app/agent/batch_logger.py`
  - Append-only batch logs (`data/pipeline_logs/batches/batch_<id>.jsonl`).

## Integration Layer

- `app/integrations/resume_tailor_client.py`
  - External API client (no logic duplication from resume-tailor).
  - Endpoints:
    - `POST /agent/resolve-resume`
    - `POST /agent/tailor-job`
    - `GET /agent/profile/{profile_id}/strategy`
    - `GET /agent/application/{application_id}`
  - Environment:
    - `RESUME_TAILOR_API_BASE_URL`
    - `RESUME_TAILOR_PROFILE_ID`

## Persistence and State Tracking

- `app/storage/repository.py`
  - Migration-safe optional columns and update helpers.
  - `list_review_ready_jobs(...)` — compact projection for jobs in `REVIEW_READY` (review queue).
  - Pipeline metadata fields include:
    - `pipeline_state`
    - `state_history`
    - `pipeline_run_id`
    - `last_successful_step`
    - `retry_count`
    - `last_pipeline_started_at`
    - `last_pipeline_completed_at`
    - `last_pipeline_error`
  - Resume Tailor linkage fields include:
    - `resume_tailor_application_id`
    - `resume_tailor_fit_score`
    - `resume_tailor_status`
    - `resume_tailor_gap_summary`
    - `last_tailored_at`

## Deterministic Pipeline

Primary progression:

`DISCOVERED -> EXTRACTED -> SCORED -> TAILORED -> REVIEW_READY -> APPLIED -> INTERVIEW / REJECTED / OFFER`

Operational states:

- `FAILED`
- `ARCHIVED`

## Operational Observability

- Every tailor run gets a `pipeline_run_id`.
- Runner emits step-level traces (`STARTED`, `LOAD_JOB`, `VALIDATE_JOB`, `CALL_RESUME_TAILOR`, `SAVE_RESULTS`, `UPDATE_STATE`, `COMPLETED`).
- Failures are structured and inspectable via:
  - `last_pipeline_error` in storage
  - JSONL step/error entries in `data/pipeline_logs/`
  - CLI commands:
    - `--pipeline-status JOB_ID`
    - `--pipeline-logs JOB_ID`

## Batch Orchestration

- CLI:
  - `--batch-tailor --state-filter SCORED --min-fit-score 70 --limit 10`
  - `--batch-tailor --dry-run`
  - `--batch-logs BATCH_RUN_ID`
- Batch summary includes candidates, processed count, success/failure totals, and per-job outcomes.
- Human review remains required before apply stage; batch orchestration does not autonomously submit applications.

## Review Queue

After a successful tailor run (single job via `JobPipelineRunner.run_to_tailored` or eligible jobs in a batch), pipeline state becomes **`REVIEW_READY`**. Jobs wait in the review queue until an operator records a **manual** decision.

**Decision flow**

- Tailor completes → `REVIEW_READY` (artifacts and linkage live in `resume-tailor`; local DB stores `resume_tailor_*` fields and timestamps).
- Operator reviews fit score, gap summary, and application id in CLI or UI.
- Operator transitions state explicitly — no automatic “apply” to external job boards.

**Manual transitions (via `JobPipelineRunner.update_status`)**

- `REVIEW_READY` → `APPLIED` — operator recorded that they applied (does **not** submit an application; tracking only).
- `REVIEW_READY` → `REJECTED` — operator declined the opportunity.
- **any** → `ARCHIVED` — remove from active review (always allowed by transition rules).

**CLI**

- `--review-queue` — list `REVIEW_READY` jobs (optional `--limit`).
- `--mark-applied JOB_ID`, `--reject-job JOB_ID`, `--archive-job JOB_ID` — manual decisions.

**Streamlit**

- `ui/streamlit_app.py` includes a **Review Queue** section: lists `REVIEW_READY` jobs with key fields and buttons for Mark Applied / Reject / Archive plus an optional job URL link.
