"""Deterministic, non-LLM fit scoring for validated job drafts."""

from __future__ import annotations

import re

from app.schemas.job_schema import JobPostingDraft

# Canonical skill groups: profile variants collapse here so one JD hit matches the whole group.
# Both projects use plain names; keep keys stable for matched_groups / missing_groups output.
SKILL_GROUPS: dict[str, list[str]] = {
    "sql": ["sql", "sql querying", "data analysis with sql"],
    "requirements": [
        "requirements analysis",
        "business requirements",
        "functional requirements",
        "acceptance criteria",
    ],
    "stakeholder": [
        "stakeholder management",
        "stakeholder alignment",
        "stakeholder communication",
        "cross-functional collaboration",
    ],
    "uat": [
        "uat",
        "user acceptance testing",
        "uat planning",
        "test case design",
        "test execution",
        "defect tracking",
    ],
    "bi": [
        "power bi",
        "power bi dashboards",
        "dashboard development",
        "reporting",
    ],
    "process": [
        "process improvement",
        "workflow optimization",
        "operational efficiency",
    ],
    "excel": ["excel"],
}


def _norm_tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9+#\.]+", (text or "").lower())
    return {w for w in words if len(w) >= 2}


def _extract_years(text: str) -> int | None:
    m = re.search(r"(\d{1,2})\+?\s+years?", (text or "").lower())
    return int(m.group(1)) if m else None


def _map_profile_skill_to_group(skill: str) -> str:
    """Return canonical group id, or standalone:<normalized> if no group matches."""
    sl = skill.strip().lower()
    if not sl:
        return "standalone:"
    for gid, variants in SKILL_GROUPS.items():
        for v in variants:
            vl = v.lower()
            if vl == sl or vl in sl or sl in vl:
                return gid
    return f"standalone:{sl}"


def _variants_for_group(gid: str) -> list[str]:
    if gid in SKILL_GROUPS:
        return SKILL_GROUPS[gid]
    if gid.startswith("standalone:"):
        rest = gid.split(":", 1)[1]
        return [rest] if rest else []
    return []


def _term_matches_job(term: str, job_blob_l: str, job_tokens: set[str]) -> bool:
    tl = (term or "").lower().strip()
    if not tl:
        return False
    if tl in job_blob_l:
        return True
    return _norm_tokens(tl).issubset(job_tokens)


def score_job_fit(job: JobPostingDraft, profile: dict) -> dict:
    """
    Directional fit score: role hint + grouped skill overlap vs job text + years hint.

    Skill overlap uses SKILL_GROUPS so profile variants do not inflate missing counts.
    Returns: fit_score, matched_groups, missing_groups, matched_skills, missing_skills,
    short_reason (plus legacy-friendly fields).
    """
    target_roles = [str(x).strip() for x in (profile.get("target_roles") or []) if str(x).strip()]
    core_skills = [str(x).strip() for x in (profile.get("core_skills") or []) if str(x).strip()]
    years_profile = profile.get("years_experience")

    job_blob = " ".join(
        [
            job.title or "",
            job.company or "",
            job.location or "",
            job.description or "",
        ]
    )
    job_blob_l = job_blob.lower()
    job_tokens = _norm_tokens(job_blob)

    # Unique groups in profile order (first profile line is representative label).
    group_order: list[str] = []
    group_rep: dict[str, str] = {}
    for sk in core_skills:
        gid = _map_profile_skill_to_group(sk)
        if gid not in group_rep:
            group_rep[gid] = sk
            group_order.append(gid)

    matched_groups: list[str] = []
    missing_groups: list[str] = []
    matched_skills: list[str] = []
    missing_skills: list[str] = []

    for gid in group_order:
        variants = _variants_for_group(gid)
        if not variants:
            continue
        hit = any(_term_matches_job(v, job_blob_l, job_tokens) for v in variants)
        rep = group_rep[gid]
        if hit:
            matched_groups.append(gid)
            matched_skills.append(rep)
        else:
            missing_groups.append(gid)
            missing_skills.append(rep)

    total_groups = len(group_order)
    matched_group_count = len(matched_groups)

    matched_roles = [r for r in target_roles if r.lower() in job_blob_l]
    role_score = 25 if matched_roles else 0
    if total_groups > 0:
        skill_ratio = matched_group_count / total_groups
    else:
        skill_ratio = 0.0
    skill_score = int(round(skill_ratio * 60))

    years_score = 0
    job_years = _extract_years(job.description or "")
    if isinstance(years_profile, int):
        if job_years is None or years_profile >= job_years:
            years_score = 15
        elif years_profile >= max(0, job_years - 2):
            years_score = 8
    elif isinstance(years_profile, str):
        m = re.match(r"\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$", years_profile)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if job_years is None or lo <= job_years <= hi:
                years_score = 15
            elif job_years is not None and abs(job_years - hi) <= 2:
                years_score = 8

    fit_score = max(0, min(100, role_score + skill_score + years_score))
    short_reason = (
        f"Matched {matched_group_count}/{total_groups} skill groups; "
        f"role_match={'yes' if bool(matched_roles) else 'no'}; "
        f"years_hint={'aligned' if years_score >= 15 else ('partial' if years_score > 0 else 'unknown')}"
    )

    return {
        "fit_score": fit_score,
        "matched_groups": matched_groups,
        "missing_groups": missing_groups,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "short_reason": short_reason,
    }
