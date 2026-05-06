# AI Job Agent v1 Checkpoint

## What v1 does

- Discovers likely job links from a careers page URL (static HTML only).
- Extracts one job URL into a validated `JobPostingDraft`.
- Applies blocking validation (required URL/description, minimum description length).
- Saves validated jobs to local SQLite with URL-based upsert.
- Lists jobs, filters by status, updates status, and exports CSV.
- Provides one-page Streamlit UI for discover/extract/save/pipeline/export actions.

## What v1 intentionally does not do

- No LLM calls or AI-generated scoring.
- No browser automation or JavaScript execution.
- No authenticated scraping flows.
- No LinkedIn/Indeed scraping support.
- No multi-page UI or advanced dashboard workflows.

## Current architecture

- `app/extract`: HTTP page load + careers/job link discovery heuristics.
- `app/parse`: HTML-to-structured field parsing + text cleaning.
- `app/validation`: blocking validation gate for parsed drafts.
- `app/storage`: SQLite schema, repository, status pipeline, CSV export.
- `app/agent`: thin orchestration (`discover_jobs_from_careers_page`, `extract_job_from_url`).
- `main.py`: CLI entry for discovery, extraction, save, list, status updates, export.
- `ui/app.py`: thin one-page Streamlit shell over existing backend functions.

## Known limitations

- Many careers boards are client-rendered; static HTML discovery can return zero links.
- Heuristic link parsing may miss job URLs or include false positives on some sites.
- Job detail extraction quality depends on available SSR/SEO/JSON-LD content.
- Validation can block pages with thin visible text if no rich fallback content exists.
- SQLite is local-only and single-user by design in v1.

## Tested flows

- CLI discovery from careers URL (`--careers-url`, optional `--debug`).
- CLI single-job extraction (`--job-url`, optional `--debug`).
- Save validated draft to SQLite (`--save` with `--job-url`).
- List jobs and status filter (`--list-jobs`, optional `--status`).
- Update job status (`--update-status`, `--new-status`).
- CSV export (`--export-csv`, optional `--status`).
- Real-world smoke harness (`scripts/smoke_test_urls.py`) with non-fatal pass/warn/fail summary.
- Unit test coverage across parser, link finder, validator, repository, exporter, and CLI paths.

## Next feature candidates

- Fit scoring.
- Browser automation for client-rendered boards.
- Resume Tailor integration.
- Better job board adapters (site/API-specific extractors).
