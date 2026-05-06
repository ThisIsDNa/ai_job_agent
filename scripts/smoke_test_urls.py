"""Run lightweight real-world smoke checks for careers and job URLs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Ensure project root imports (app.*, config) work when running this script directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.agent_runner import discover_jobs_from_careers_page, extract_job_from_url
from app.utils.logger import configure_logging

CONFIG_PATH = PROJECT_ROOT / "config" / "smoke_test_urls.json"


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Config must be a JSON object")
    return data


def run() -> int:
    """Executes smoke checks and prints concise pass/fail summary."""
    configure_logging(debug=True)
    cfg = _load_config(CONFIG_PATH)
    careers_urls = cfg.get("careers_urls") or []
    job_urls = cfg.get("job_urls") or []

    print("=== Careers URL Smoke Tests ===")
    careers_pass = 0
    careers_warn = 0

    for url in careers_urls:
        trace: dict[str, Any] = {}
        try:
            links = discover_jobs_from_careers_page(str(url), debug=True, trace=trace)
            stats = trace.get("link_stats") or {}
            final_count = int(stats.get("final_link_count", len(links)))
            status = "PASS" if final_count > 0 else "WARN"
            if status == "PASS":
                careers_pass += 1
            else:
                careers_warn += 1
            print(
                f"[{status}] url={url} html_len={trace.get('html_char_len', 0)} "
                f"anchors={stats.get('anchor_tags_total', 0)} "
                f"embedded={stats.get('embedded_urls_found', 0)} "
                f"final_links={final_count}"
            )
        except Exception as exc:  # noqa: BLE001 - smoke harness should continue
            careers_warn += 1
            print(f"[WARN] url={url} reason={exc}")

    print("\n=== Job URL Smoke Tests ===")
    job_pass = 0
    job_fail = 0

    for url in job_urls:
        trace = {}
        try:
            draft = extract_job_from_url(str(url), debug=True, trace=trace)
            job_pass += 1
            print(
                f"[PASS] url={url} title={draft.title!r} company={draft.company!r} "
                f"location={draft.location!r} desc_len={len(draft.description)} "
                f"warnings={draft.validation_warnings}"
            )
        except Exception as exc:  # noqa: BLE001 - smoke harness should continue
            job_fail += 1
            print(f"[FAIL] url={url} reason={exc}")

    print("\n=== Summary ===")
    print(f"careers: pass={careers_pass} warn={careers_warn} total={len(careers_urls)}")
    print(f"jobs: pass={job_pass} fail={job_fail} total={len(job_urls)}")

    # Non-fatal by design: this harness is for diagnostics, not CI gating.
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
