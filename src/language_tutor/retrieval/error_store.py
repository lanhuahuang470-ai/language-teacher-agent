"""Persistent embeddings; SQL student filtering precedes Python cosine top-k.

This deliberately uses JSON vectors for a small corpus, avoiding a required PostgreSQL
extension. Large corpora should migrate the same interface to pgvector.
"""

import heapq
import logging
import math
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from sqlalchemy import or_, select

from language_tutor import config
from language_tutor.db.engine import SessionLocal
from language_tutor.db.models import Error, ErrorEmbedding
from language_tutor.retrieval.embeddings import DashScopeEmbeddings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_embeddings():
    return DashScopeEmbeddings()


def index_error(error_id: int) -> bool:
    with SessionLocal() as session:
        error = session.get(Error, error_id)
        job = session.get(ErrorEmbedding, error_id)
        if error is None or job is None:
            raise ValueError("缺少错题或索引任务")
        if job.vector is not None and job.model == config.EMBEDDING_MODEL:
            return True
        sentence = error.error_sentence
    try:
        vector = get_embeddings().embed_query(sentence)
        if not vector or not all(math.isfinite(value) for value in vector):
            raise ValueError("Invalid embedding")
    except Exception as exc:
        with SessionLocal() as session, session.begin():
            job = session.get(ErrorEmbedding, error_id)
            job.attempts += 1
            job.last_error = type(exc).__name__
            job.retry_after = datetime.now(timezone.utc) + timedelta(
                seconds=min(300, 2 ** min(job.attempts, 8))
            )
        logger.warning("embedding_failed error_id=%s error_type=%s", error_id, type(exc).__name__)
        return False
    with SessionLocal() as session, session.begin():
        job = session.get(ErrorEmbedding, error_id)
        job.vector = vector
        job.model = config.EMBEDDING_MODEL
        job.last_error = None
    return True


def ensure_index_jobs() -> int:
    """Backfill old errors without changing their historical answers."""
    with SessionLocal() as session, session.begin():
        missing = session.scalars(
            select(Error.id)
            .outerjoin(ErrorEmbedding, Error.id == ErrorEmbedding.error_id)
            .where(ErrorEmbedding.error_id.is_(None))
        ).all()
        for error_id in missing:
            session.add(ErrorEmbedding(error_id=error_id))
        return len(missing)


def retry_pending(limit: int = 50) -> int:
    with SessionLocal() as session:
        ids = session.scalars(
            select(ErrorEmbedding.error_id)
            .where(
                or_(ErrorEmbedding.vector.is_(None), ErrorEmbedding.model != config.EMBEDDING_MODEL)
            )
            .where(ErrorEmbedding.retry_after <= datetime.now(timezone.utc))
            .order_by(ErrorEmbedding.error_id)
            .limit(limit)
        ).all()
    return sum(index_error(error_id) for error_id in ids)


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return -1.0
    norm = math.sqrt(sum(x * x for x in left) * sum(x * x for x in right))
    return sum(x * y for x, y in zip(left, right)) / norm if norm else 0.0


def search_similar_errors(query_sentence: str, *, student_id: str, k: int = 3) -> list[dict]:
    if not student_id.strip():
        raise ValueError("检索必须提供学生身份")
    if not 1 <= k <= 20:
        raise ValueError("k 必须在 1～20 之间")
    with SessionLocal() as session:
        rows = session.execute(
            select(Error, ErrorEmbedding)
            .join(ErrorEmbedding, Error.id == ErrorEmbedding.error_id)
            .where(
                Error.student_id == student_id,
                ErrorEmbedding.vector.is_not(None),
                ErrorEmbedding.model == config.EMBEDDING_MODEL,
            )
        ).all()
        candidates = [
            {
                "sentence": error.error_sentence,
                "correct": error.correct_form,
                "knowledge_point": error.knowledge_point,
                "error_types": error.error_types,
                "vector": embedding.vector,
            }
            for error, embedding in rows
        ]
    if not candidates:
        return []
    try:
        query = get_embeddings().embed_query(query_sentence)
    except Exception as exc:
        logger.warning("embedding_query_failed error_type=%s", type(exc).__name__)
        return []  # SQL history tool remains available.
    scored = [
        {
            **{key: value for key, value in row.items() if key != "vector"},
            "score": _cosine(query, row["vector"]),
        }
        for row in candidates
    ]
    return heapq.nlargest(k, scored, key=lambda row: row["score"])
