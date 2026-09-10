from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select

from language_tutor.db.models import Assessment, Error, ErrorEmbedding, Mastery
from language_tutor.graph.state import Exercise, GradeResult
from language_tutor.retrieval import error_store
from language_tutor.services import assessment


def question():
    return Exercise(exercise_id="q1", knowledge_point="be动词", question="He __ happy.")


def wrong_grade():
    return GradeResult(
        exercise_id="q1",
        grammar_correct=False,
        spelling_correct=True,
        score=0.0,
        error_types=["主谓一致"],
        feedback_hint="注意主语",
        correct_answer="He is happy.",
    )


def test_replay_returns_original_grade_without_duplicate_writes(database):
    first = assessment.record_assessment("alice", question(), "are", wrong_grade())
    changed = wrong_grade().model_copy(update={"score": 0.5})
    replay = assessment.record_assessment("alice", question(), "was", changed)
    assert replay == first
    with database() as session:
        assert session.scalar(select(func.count()).select_from(Assessment)) == 1
        assert session.scalar(select(func.count()).select_from(Error)) == 1
        assert session.scalar(select(func.count()).select_from(ErrorEmbedding)) == 1
        assert session.get(Mastery, ("alice", "be动词")).score == 0
        assert session.scalar(select(Error.correct_form)) == "He is happy."


def test_failed_error_write_rolls_back_mastery(database, monkeypatch):
    with database() as session, session.begin():
        session.add(Mastery(student_id="alice", knowledge_point="be动词", score=0.5))
    monkeypatch.setattr(
        assessment, "save_error", MagicMock(side_effect=RuntimeError("write failure"))
    )
    with pytest.raises(RuntimeError):
        assessment.record_assessment("alice", question(), "are", wrong_grade())
    with database() as session:
        assert session.get(Mastery, ("alice", "be动词")).score == 0.5
        assert session.scalar(select(func.count()).select_from(Assessment)) == 0


def test_embedding_failure_is_retryable_without_rescoring(database, monkeypatch):
    assessment.record_assessment("alice", question(), "are", wrong_grade())
    with database() as session:
        error_id = session.scalar(select(Error.id))
    fake = SimpleNamespace(embed_query=MagicMock(side_effect=TimeoutError("offline failure")))
    monkeypatch.setattr(error_store, "get_embeddings", lambda: fake)
    assert error_store.index_error(error_id) is False
    with database() as session:
        job = session.get(ErrorEmbedding, error_id)
        assert job.vector is None
        assert job.attempts == 1
        assert session.scalar(select(func.count()).select_from(Assessment)) == 1
    fake.embed_query.side_effect = None
    fake.embed_query.return_value = [1.0, 0.0]
    assert error_store.index_error(error_id)
    assert error_store.index_error(error_id)
    assert fake.embed_query.call_count == 2


def test_persistent_rag_filters_before_top_k_and_survives_new_client(database, monkeypatch):
    for student in ["bob", "alice"]:
        assessment.record_assessment(student, question(), student + " wrong", wrong_grade())
    monkeypatch.setattr(
        error_store,
        "get_embeddings",
        lambda: SimpleNamespace(
            embed_query=lambda _: [1.0, 0.0],
            embed_documents=lambda texts: [[1.0, 0.0] for _ in texts],
        ),
    )
    assert error_store.retry_pending() == 2
    # A fresh adapter can search persisted vectors without regenerating document embeddings.
    queries = MagicMock(return_value=[1.0, 0.0])
    monkeypatch.setattr(error_store, "get_embeddings", lambda: SimpleNamespace(embed_query=queries))
    result = error_store.search_similar_errors("wrong", student_id="alice", k=1)
    assert len(result) == 1
    assert result[0]["sentence"] == "alice wrong"
    assert result[0]["correct"] == "He is happy."
    queries.assert_called_once_with("wrong")
    assert error_store.search_similar_errors("wrong", student_id="unknown") == []


def test_backfill_is_idempotent(database):
    with database() as session, session.begin():
        session.add(
            Error(
                student_id="alice",
                knowledge_point="be动词",
                error_sentence="bad",
                correct_form="good",
                error_types="语法",
            )
        )
    assert error_store.ensure_index_jobs() == 1
    assert error_store.ensure_index_jobs() == 0


def test_retry_job_respects_backoff(database, monkeypatch):
    assessment.record_assessment("alice", question(), "are", wrong_grade())
    with database() as session, session.begin():
        job = session.scalar(select(ErrorEmbedding))
        job.retry_after = datetime(2099, 1, 1, tzinfo=timezone.utc)
    call = MagicMock()
    monkeypatch.setattr(error_store, "index_error", call)
    assert error_store.retry_pending() == 0
    call.assert_not_called()


def test_additive_migration_is_repeatable(database, monkeypatch):
    from language_tutor.db import migrations
    from language_tutor.db.models import SchemaMigration, Student

    monkeypatch.setattr(migrations, "get_engine", lambda: database.kw["bind"])
    migrations.migrate()
    migrations.migrate()
    with database() as session:
        assert session.scalar(select(func.count()).select_from(SchemaMigration)) == 2
        assert session.get(Student, "alice") is not None


def test_legacy_checkpoint_type_can_be_restored(monkeypatch):
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    serializer = JsonPlusSerializer()
    with monkeypatch.context() as context:
        context.setattr(Exercise, "__module__", "graph.state")
        encoded = serializer.dumps_typed(question())
    restored = serializer.loads_typed(encoded)
    assert restored == question()


def test_resolve_errors_by_kp_marks_resolved_without_deleting(database):
    from language_tutor.db.crud import resolve_errors_by_kp

    assessment.record_assessment("alice", question(), "are", wrong_grade())
    with database() as session:
        assert session.scalar(select(func.count()).select_from(Error)) == 1
        assert session.scalar(select(func.count()).select_from(ErrorEmbedding)) == 1
        assert session.scalar(select(Error.resolved)) is False
    with database() as session:
        resolve_errors_by_kp(session, "alice", "be动词")
    with database() as session:
        # 错题和向量索引仍然保留，只是 resolved 标记为 True
        assert session.scalar(select(func.count()).select_from(Error)) == 1
        assert session.scalar(select(func.count()).select_from(ErrorEmbedding)) == 1
        assert session.scalar(select(Error.resolved)) is True


def test_error_summary_aggregates_by_knowledge_point(database):
    from language_tutor.db.crud import get_error_summary

    assessment.record_assessment("alice", question(), "are", wrong_grade())
    assessment.record_assessment(
        "alice",
        Exercise(exercise_id="q2", knowledge_point="一般过去时", question="He __ happy."),
        "are",
        GradeResult(
            exercise_id="q2",
            grammar_correct=False,
            spelling_correct=True,
            score=0.0,
            error_types=["时态混淆"],
            feedback_hint="注意时态",
            correct_answer="He was happy.",
        ),
    )
    with database() as session:
        summary = get_error_summary(session, "alice")
    assert len(summary) == 2
    kp_names = [item["knowledge_point"] for item in summary]
    assert "be动词" in kp_names
    assert "一般过去时" in kp_names
    for item in summary:
        assert item["count"] >= 1
        assert isinstance(item["error_types"], list)
