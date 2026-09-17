from app.cache.ttl import TTL_LONG_SECONDS, TTL_SHORT_SECONDS, TTL_SKIP, ttl_for_prompt
from app.config import settings


def test_skip_live_and_time_sensitive_prompts():
    assert ttl_for_prompt("What is the weather in Boston right now?") == TTL_SKIP
    assert ttl_for_prompt("What is today's stock price for AAPL?") == TTL_SKIP
    assert ttl_for_prompt("Give me the latest news on the election") == TTL_SKIP


def test_short_ttl_for_recent_prompts():
    assert ttl_for_prompt("Summarize recent papers on transformers") == TTL_SHORT_SECONDS
    assert ttl_for_prompt("What happened this week in Congress?") == TTL_SHORT_SECONDS


def test_long_ttl_for_stable_facts():
    assert ttl_for_prompt("What is the capital of France?") == TTL_LONG_SECONDS
    assert ttl_for_prompt("Define photosynthesis") == TTL_LONG_SECONDS


def test_default_ttl_when_no_rule_matches():
    assert ttl_for_prompt("Write a polite email declining a meeting") == settings.default_ttl_seconds
