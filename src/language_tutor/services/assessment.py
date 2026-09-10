"""One transaction per exercise; retries return the first committed result."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from language_tutor.db.crud import save_error, upsert_mastery
from language_tutor.db.engine import SessionLocal
from language_tutor.db.models import Assessment, ErrorEmbedding, Student
from language_tutor.graph.state import GradeResult


def get_recorded_grade(student_id: str, exercise_id: str) -> GradeResult | None:
    with SessionLocal() as session:
        row = session.get(Assessment, (student_id, exercise_id))
        return GradeResult.model_validate(row.grade) if row else None


def record_assessment(student_id, exercise, answer: str, grade: GradeResult) -> GradeResult:
    """Persist mastery, error, and assessment in one transaction; idempotent on replay."""
    try:
        with SessionLocal() as session, session.begin():
            # Serializes mastery updates for one student on PostgreSQL.
            session.execute(
                select(Student).where(Student.id == student_id).with_for_update()
            ).scalar_one()
            existing = session.get(Assessment, (student_id, exercise.exercise_id))
            if existing:
                return GradeResult.model_validate(existing.grade)
            upsert_mastery(session, student_id, exercise.knowledge_point, grade.score, commit=False)
            error_id = None
            # 语法错误时保存错题；纯拼写错误不保存（不是知识点不会）
            if not grade.grammar_correct:
                error = save_error(
                    session,
                    student_id,
                    exercise.knowledge_point,
                    answer,
                    grade.correct_answer,
                    grade.error_types,
                    commit=False,
                )
                error_id = error.id
                session.add(ErrorEmbedding(error_id=error_id))
            session.add(
                Assessment(
                    student_id=student_id,
                    exercise_id=exercise.exercise_id,
                    question=exercise.question,
                    student_answer=answer,
                    grade=grade.model_dump(),
                    error_id=error_id,
                )
            )
        return grade
    except IntegrityError:
        # Unique key handles concurrent replay; other constraint failures still propagate.
        existing = get_recorded_grade(student_id, exercise.exercise_id)
        if existing is not None:
            return existing
        raise
