# v2.1 Checkpoint: Real Resume Tailor Integration

## What changed (stub -> real bridge)

- `app/integrations/resume_tailor_bridge.py` now calls the live Resume Tailor callable instead of returning stubbed preview text.
- The bridge still keeps a thin adapter contract for Job Agent UI:
  - input: selected job + base resume path
  - output: normalized preview payload
- Streamlit Tailor action now surfaces controlled warnings when Resume Tailor is unavailable, without crashing the page.

## Required Resume Tailor callable

- Required entry point: `backend/app/services/tailor_pipeline.py::tailor_resume`
- The bridge resolves this from local filesystem (default sibling repo path), with optional override via env:
  - `RESUME_TAILOR_PIPELINE_PATH`

## Data passed into Resume Tailor

- `resume_docx_path`: path to base resume file (from UI input, default `config/base_resume.docx`)
- `job_description`: selected job `description`
- `context`: `Target role: {title} at {company}`

## Preview output returned to Job Agent

Bridge normalizes Resume Tailor response into:

- `tailored_summary`
- `updated_experience`
- `notes`

Normalization strategy:

- Prefers summary from `tailored_resume_sections.summary`
- Falls back to first line of `tailored_resume_text` if needed
- Prefers experience lines from `tailored_resume_sections.experience`
- Falls back to `prioritized_bullet_changes[*].after` if needed
- Adds notes with bridge mode and optional alignment/gap highlights

## Failure handling behavior

- Missing resume file -> raises `FileNotFoundError` -> UI warning
- Missing/unloadable Resume Tailor callable -> raises `ResumeTailorUnavailableError` -> UI warning
- Runtime errors during callable execution -> controlled bridge exception -> UI error
- Tailor action failure does not break other Job Agent workflows

## What remains separate

- No database merge between Job Agent and Resume Tailor
- No Resume Tailor code copied into Job Agent
- No AI Job Agent storage schema changes for this integration
- Job Agent remains the orchestration UI; Resume Tailor remains the tailoring engine

## Known limitations

- No DOCX export from Job Agent integration path yet (preview-only)
- Resume Tailor dependency path must be available locally
- Tailored outputs are not persisted in Job Agent storage

## Next candidates

- Add DOCX export handoff from Job Agent to Resume Tailor export flow
- Add explicit integration config for Resume Tailor path (beyond env override)
- Add generated preview refinement for cleaner, more readable snippets
