"""Generic helper functions shared across app modules."""


def safe_str(value: object) -> str:
    """Converts value to a stripped string."""
    # TODO: expand helper set as concrete use-cases appear.
    return str(value).strip()

