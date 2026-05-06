"""Normalizes noisy raw text before parsing."""

from __future__ import annotations

import re


def clean_text(raw_text: str) -> str:
    """
    Normalizes whitespace, collapses excessive blank lines, keeps readable breaks.

    Returns empty string for empty/whitespace-only input.
    """
    if raw_text is None or not str(raw_text).strip():
        return ""

    text = str(raw_text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in text.split("\n")]
    collapsed: list[str] = []
    blank_run = 0
    for ln in lines:
        if not ln:
            blank_run += 1
            if blank_run <= 1:
                collapsed.append("")
            continue
        blank_run = 0
        collapsed.append(ln)

    joined = "\n".join(collapsed).strip()
    joined = re.sub(r"[ \t]+", " ", joined)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip()
