from app.cache.tuner import (
    DEFAULT_FIXTURE,
    DEFAULT_THRESHOLDS,
    cosine_score,
    format_reports,
    load_pairs,
    replay,
)


def test_cosine_score_identical_vectors():
    vector = [1.0, 0.0, 0.0]
    assert cosine_score(vector, vector) == 1.0


def test_cosine_score_orthogonal_vectors():
    assert cosine_score([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_replay_hit_rate_and_precision_across_thresholds():
    scored = [
        (0.99, True),
        (0.96, True),
        (0.93, False),
        (0.80, False),
    ]
    by_threshold = {report.threshold: report for report in replay(scored)}

    loose = by_threshold[0.90]
    assert loose.hits == 3
    assert loose.true_positives == 2
    assert loose.false_positives == 1
    assert loose.hit_rate == 0.75
    assert loose.precision == 2 / 3

    mid = by_threshold[0.95]
    assert mid.hits == 2
    assert mid.false_positives == 0
    assert mid.precision == 1.0

    tight = by_threshold[0.98]
    assert tight.hits == 1
    assert tight.true_positives == 1
    assert tight.hit_rate == 0.25


def test_replay_precision_is_zero_when_there_are_no_hits():
    reports = replay([(0.50, True)], thresholds=(0.95,))
    assert reports[0].hits == 0
    assert reports[0].precision == 0.0


def test_load_pairs_fixture_has_both_labels():
    pairs = load_pairs(DEFAULT_FIXTURE)
    assert len(pairs) >= 4
    assert any(pair.same_intent for pair in pairs)
    assert any(not pair.same_intent for pair in pairs)
    assert DEFAULT_FIXTURE.is_file()


def test_format_reports_includes_thresholds():
    text = format_reports(replay([(0.97, True)], DEFAULT_THRESHOLDS))
    assert "0.90" in text
    assert "0.95" in text
    assert "0.98" in text
