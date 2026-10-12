import logging

from evals.run import DEFAULT_DATA, load_cases, run
from language_tutor.telemetry import request_trace, traced


def test_seed_baseline_is_labeled_and_contains_partial_credit_cases():
    cases, meta = load_cases(DEFAULT_DATA)
    assert len(cases) >= 60
    assert meta.human_reviewed is True
    assert any(case.expected_score == 0.5 for case in cases)
    report = run("exact-match", cases, dataset_meta=meta)
    assert report["model"] is None
    assert "human reviewed" in report["dataset_status"]
    assert report["correctness_accuracy"] < 1
    assert report["score_mae_valid_only"] > 0


def test_trace_does_not_log_student_content(caplog):
    @traced("sample")
    def operation(secret_text):
        return secret_text

    with caplog.at_level(logging.INFO, logger="language_tutor.events"):
        with request_trace() as correlation:
            assert operation("private student answer") == "private student answer"
    assert correlation in caplog.text
    assert "private student answer" not in caplog.text
