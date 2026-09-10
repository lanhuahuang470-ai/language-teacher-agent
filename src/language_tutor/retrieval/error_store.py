"""Persistent embeddings; SQL student filtering precedes Python cosine top-k.

This deliberately uses JSON vectors for a small corpus, avoiding a required PostgreSQL
extension. Large corpora should migrate the same interface to pgvector.
"""

from __future__ import annotations

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
    """返回单例的 DashScope 向量嵌入客户端。

    借助 lru_cache(maxsize=1) 复用唯一实例，避免在每次索引或检索时
    重复构造嵌入客户端带来的开销；index_error 与 search_similar_errors
    均通过本函数获取实例完成文本向量化。
    """
    return DashScopeEmbeddings()


def index_error(error_id: int) -> bool:
    """为指定错题生成向量嵌入并持久化，失败时记录原因并安排退避重试。

    返回 True 表示向量已就绪（命中缓存或本次写入成功），False 表示本次失败、
    需等待 retry_pending 在退避时间到达后重试。
    """
    with SessionLocal() as session:
        error = session.get(Error, error_id)
        job = session.get(ErrorEmbedding, error_id)
        if error is None or job is None:
            raise ValueError("缺少错题或索引任务")
        # 命中缓存：向量已存在且模型未变更，直接跳过重复嵌入
        if job.vector is not None and job.model == config.EMBEDDING_MODEL:
            return True
        sentence = error.error_sentence
    try:
        vector = get_embeddings().embed_query(sentence)
        # 校验向量非空且无 NaN/Inf，避免脏数据落入库中
        if not vector or not all(math.isfinite(value) for value in vector):
            raise ValueError("Invalid embedding")
    except Exception as exc:
        with SessionLocal() as session, session.begin():
            job = session.get(ErrorEmbedding, error_id)
            job.attempts += 1
            job.last_error = type(exc).__name__
            # 指数退避：2^attempts 秒，上限 300 秒，避免频繁重试压垮嵌入服务
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
    """批量处理待索引任务：一次 API 调用嵌入多条错句，减少网络往返开销。

    流程：
      1. 查出 limit 条待处理任务（vector 为空或模型版本过期且退避时间已到）
      2. 一次调 embed_documents 批量嵌入全部错句
      3. 成功的逐条写入向量；失败的逐条记退避重试
    """
    with SessionLocal() as session:
        rows = session.execute(
            select(ErrorEmbedding.error_id, Error.error_sentence)
            .join(Error, ErrorEmbedding.error_id == Error.id)
            .where(
                or_(ErrorEmbedding.vector.is_(None), ErrorEmbedding.model != config.EMBEDDING_MODEL)
            )
            .where(ErrorEmbedding.retry_after <= datetime.now(timezone.utc))
            .order_by(ErrorEmbedding.error_id)
            .limit(limit)
        ).all()
    if not rows:
        return 0
    sentences = [row[1] for row in rows]
    error_ids = [row[0] for row in rows]
    # 批量嵌入：一次 API 调用处理多条，省的是网络往返的固定开销
    try:
        vectors = get_embeddings().embed_documents(sentences)
        if len(vectors) != len(sentences):
            raise ValueError(f"返回向量数 {len(vectors)} 与输入数 {len(sentences)} 不匹配")
        bad = [
            i for i, vec in enumerate(vectors) if not vec or not all(math.isfinite(v) for v in vec)
        ]
        if bad:
            raise ValueError(f"无效向量索引: {bad}")
    except Exception as exc:
        # 批量调用失败：逐条记退避，下次 retry_pending 会逐条重试
        logger.warning(
            "batch_embedding_failed count=%d error_type=%s", len(error_ids), type(exc).__name__
        )
        now = datetime.now(timezone.utc)
        for eid in error_ids:
            with SessionLocal() as session, session.begin():
                job = session.get(ErrorEmbedding, eid)
                if job is not None:
                    job.attempts += 1
                    job.last_error = type(exc).__name__
                    job.retry_after = now + timedelta(seconds=min(300, 2 ** min(job.attempts, 8)))
        return 0
    # 成功：逐条写入向量
    success = 0
    for eid, vec in zip(error_ids, vectors):
        with SessionLocal() as session, session.begin():
            job = session.get(ErrorEmbedding, eid)
            if job is not None:
                job.vector = vec
                job.model = config.EMBEDDING_MODEL
                job.last_error = None
                success += 1
    return success


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return -1.0
    norm = math.sqrt(sum(x * x for x in left) * sum(x * x for x in right))
    return sum(x * y for x, y in zip(left, right)) / norm if norm else 0.0


def search_similar_errors(query_sentence: str, *, student_id: str, k: int = 3) -> list[dict]:
    """Return the top-k most similar historical errors for the student by cosine distance."""
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
