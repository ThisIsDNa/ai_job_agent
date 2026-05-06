# System Flow

- Input (careers URL or job URL) -> Extract (HTTP HTML) -> Parse (structured fields) -> **Validate (blocking)** -> Return `JobPostingDraft`
- Agent layer orchestrates calls only; extract/parse/validate own their logic.
- Export/review/storage are out of scope for the current MVP slice.
- `load_page_text` reuses `load_page_html` then strips tags to plain text.
