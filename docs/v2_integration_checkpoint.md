# v2 Integration Checkpoint: Resume Tailor Bridge

## What the bridge does

- Adds a thin integration adapter at `app/integrations/resume_tailor_bridge.py`.
- Accepts selected Job Agent job context plus a base resume file path.
- Returns preview-only tailored output payload:
  - `tailored_summary`
  - `updated_experience`
  - `notes`
- Is wired into one-page Streamlit UI via **Tailor Resume** button in Job Pipeline.

## What it intentionally does not do

- Does not merge Job Agent and Resume Tailor databases.
- Does not write resume content into the jobs table.
- Does not invoke Resume Tailor core logic directly yet (stub/bridge mode).
- Does not generate DOCX output.
- Does not add browser automation or LLM behavior.

## Data passed from Job Agent to Resume Tailor bridge

- Job payload from selected saved job:
  - `title`
  - `company`
  - `description`
  - (plus existing saved job fields available in row dict)
- Base resume file path:
  - default UI path: `config/base_resume.docx`

## Base resume requirement

- A base resume file must exist at the configured path.
- Current default: `config/base_resume.docx` (placeholder provided).
- If missing, UI shows warning and does not crash.

## Current UI behavior

- In **Job Pipeline**, user selects a saved job URL.
- User clicks **Tailor Resume**.
- UI calls bridge and displays preview text only:
  - tailored summary
  - updated experience bullets (suggested)
  - integration notes
- Existing discover/extract/save/status/export flows remain unchanged.

## Known limitations

- Bridge output is stubbed and heuristic; not true Resume Tailor execution.
- No generated resume preview document; text-only preview.
- No DOCX export from integration path.
- No dedicated integration test coverage yet.
- No cross-service contract versioning yet.

## System boundary statement

- Job Agent and Resume Tailor remain separate systems.
- Integration is minimal, reversible, and adapter-based.
- Current bridge is an interface checkpoint, not a system merge.

## Next feature candidates

- Replace stub bridge with real Resume Tailor API/module call.
- Add generated resume preview.
- Add DOCX export later.
- Add integration tests.
