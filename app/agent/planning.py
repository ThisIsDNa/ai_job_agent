"""Planning utilities for agent step orchestration."""


def build_plan() -> list[str]:
    """Returns a minimal ordered plan for pipeline execution."""
    # TODO: replace static steps with dynamic planning logic.
    return ["extract", "parse", "score", "validate", "store"]

