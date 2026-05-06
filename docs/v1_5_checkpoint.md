# AI Job Agent v1.5 Checkpoint

## Current capabilities

- Discover likely job links from careers URLs using static HTML heuristics.
- Extract a job URL into a validated `JobPostingDraft` (no LLM).
- Apply blocking validation (required URL/description, minimum description quality threshold).
- Compute deterministic fit scoring from local profile context.
- Persist jobs in SQLite with URL-based upsert (no duplicates by URL).
- Store optional scoring metadata with each saved job.
- List/filter jobs, update pipeline status, and export to CSV.
- Run one-page Streamlit UI for discover/extract/save/status/export.

## Architecture overview

- `app/extract`: page loading + link discovery (`requests`, `BeautifulSoup`, static regex).
- `app/parse`: text cleaning + job page parsing.
- `app/validation`: blocking validation gate (`JobPostingDraft` contract).
- `app/score`: deterministic heuristic scoring (`score_job_fit`).
- `app/storage`: SQLite init/migration, repository, CSV exporter.
- `app/agent`: thin orchestration (`discover_jobs_from_careers_page`, `extract_job_from_url`).
- `main.py`: CLI surface for all supported operations.
- `ui/app.py`: thin one-page Streamlit shell over existing backend functions.

## CLI commands

- Discover links:
  - `python main.py --careers-url "<careers_url>"`
  - Optional diagnostics: `--debug`
- Extract one job:
  - `python main.py --job-url "<job_url>"`
- Score extracted job:
  - `python main.py --job-url "<job_url>" --score`
  - Optional profile path: `--profile-file config/profile.json`
- Save validated job:
  - `python main.py --job-url "<job_url>" --save`
  - Score + save together:
  - `python main.py --job-url "<job_url>" --score --save`
- Storage operations:
  - `python main.py --list-jobs`
  - `python main.py --list-jobs --status Interested`
  - `python main.py --update-status "<url>" --new-status Interested`
  - `python main.py --export-csv "data/processed/jobs_export.csv"`
  - `python main.py --export-csv "data/processed/interested_jobs.csv" --status Interested`

## UI capabilities (one page)

- **Discover Jobs**: input careers URL, run discovery, view link table.
- **Extract Job**: input job URL, extract + validate, view key fields/warnings.
- **Score before saving**: optional profile path + checkbox to compute/display fit score.
- **Save Job**: persists validated draft (with optional scoring metadata).
- **Job Pipeline**: view saved jobs, filter by status, update status by selected URL.
- **Export**: export CSV with optional status filter.

## Storage schema summary

`jobs` table includes:

- Core identity/content:
  - `id`, `company`, `title`, `location`, `url` (unique), `description`, `source`
- Pipeline/validation:
  - `status` (default `Found`), `date_found`, `validation_warnings`
- Timestamps:
  - `created_at`, `updated_at`
- Optional scoring columns (v1.5):
  - `fit_score`
  - `matched_skills`
  - `missing_skills`
  - `fit_reason`

Migration is backward-compatible: missing optional columns are added at initialization.

## Scoring behavior and limitations

- Deterministic, non-LLM scoring based on:
  - role phrase overlap
  - core skill overlap
  - lightweight years-of-experience hint
- Returns:
  - `fit_score` (0–100), `matched_skills`, `missing_skills`, `short_reason`
- Directional only:
  - useful for prioritization, not hiring decisions
  - sensitive to keyword phrasing and extraction quality

## Known limitations

- Static HTML only; no JavaScript execution/browser automation.
- Client-rendered boards may produce zero discoverable links.
- Heuristic adapters can miss links or include edge-case noise.
- No authenticated scraping/session handling.
- No LinkedIn/Indeed scraping path.
- No LLM-based semantic interpretation yet.

## Recommended next feature candidates

- Better job board adapters (site/API-specific extractors).
- Resume Tailor integration (bridge job signals into tailoring workflow).
- Browser automation for client-rendered boards.
- LLM-assisted scoring later (with deterministic guardrails retained).
