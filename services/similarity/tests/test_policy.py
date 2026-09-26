import pytest
from datetime import UTC, datetime, timedelta

from app.cache.policy import isHit, neighbor_miss
from app.cache.ttl import threshold_for_prompt
from app.config import settings

FUTURE = (datetime.now(UTC) + timedelta(hours=1)).timestamp()
PAST = (datetime.now(UTC) - timedelta(hours=1)).timestamp()


def test_threshold_follows_ttl_buckets():
    assert threshold_for_prompt("What is the capital of France?") == float(settings.threshold_loose)
    assert threshold_for_prompt("What happened this week in Congress?") == float(settings.threshold_strict)
    assert threshold_for_prompt("Write a polite email declining a meeting") == float(
        settings.similarity_threshold
    )
    assert threshold_for_prompt("What is the weather in Boston right now?") == float(
        settings.similarity_threshold
    )


def test_isHit_uses_loose_cutoff_for_stable_facts():
    prompt = "What is the capital of France?"
    assert isHit(0.93, FUTURE, prompt)
    assert not isHit(0.89, FUTURE, prompt)


def test_isHit_uses_strict_cutoff_for_short_ttl_prompts():
    prompt = "What happened this week in Congress?"
    assert isHit(0.99, FUTURE, prompt)
    assert not isHit(0.93, FUTURE, prompt)


def test_isHit_rejects_expired_entries():
    assert not isHit(0.99, PAST, "What is the capital of France?")


def test_neighbor_miss_reports_gap_under_the_cutoff():
    prompt = "What is the capital of France?"
    threshold = float(settings.threshold_loose)
    cutoff, gap = neighbor_miss(threshold - 0.03, prompt)
    assert cutoff == threshold
    assert gap == pytest.approx(0.03)
