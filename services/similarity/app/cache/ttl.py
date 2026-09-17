import re

from app.config import settings

TTL_SKIP = 0
TTL_SHORT_SECONDS = 3600
TTL_LONG_SECONDS = 7 * 24 * 3600

_SKIP_PATTERNS = tuple(
    re.compile(p)
    for p in (
        r"\bright now\b",
        r"\bas of\b",
        r"\bbreaking\b",
        r"\bcurrently\b",
        r"\bcurrent price\b",
        r"\blive\b",
        r"\blatest news\b",
        r"\breal[- ]?time\b",
        r"\bstock price\b",
        r"\btoday\b",
        r"\btonight\b",
        r"\bweather\b",
        r"\bnow\b",
    )
)

_SHORT_PATTERNS = tuple(
    re.compile(p)
    for p in (
        r"\bforecast\b",
        r"\bheadline\b",
        r"\bheadlines\b",
        r"\blatest\b",
        r"\bnews\b",
        r"\brecent\b",
        r"\bthis (?:afternoon|evening|morning|week|month|year)\b",
        r"\btomorrow\b",
        r"\byesterday\b",
    )
)

_LONG_PATTERNS = tuple(
    re.compile(p)
    for p in (
        r"\bcapital of\b",
        r"\bdefine\b",
        r"\bdefinition of\b",
        r"\bhistory of\b",
        r"\bhow does\b",
        r"\bmeaning of\b",
        r"\bwhat is\b",
        r"\bwhen was\b",
        r"\bwho (?:is|was|invented)\b",
    )
)


def _matches(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def ttl_for_prompt(user_prompt: str) -> int:
    """Seconds to cache this prompt. 0 means do not store."""
    text = user_prompt.lower()
    if _matches(text, _SKIP_PATTERNS):
        return TTL_SKIP
    if _matches(text, _SHORT_PATTERNS):
        return TTL_SHORT_SECONDS
    if _matches(text, _LONG_PATTERNS):
        return TTL_LONG_SECONDS
    return settings.default_ttl_seconds
