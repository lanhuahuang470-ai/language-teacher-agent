"""Own persistent connections for the lifetime of a local application."""

from __future__ import annotations

import atexit
import logging
from contextlib import ExitStack
from functools import lru_cache
from threading import Event, Thread

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

from language_tutor import config
from language_tutor.db.engine import close_database
from language_tutor.db.migrations import migrate
from language_tutor.graph.builder import build_graph
from language_tutor.graph.serialization import checkpoint_serializer
from language_tutor.retrieval.error_store import ensure_index_jobs, retry_pending

logger = logging.getLogger(__name__)


class Runtime:
    """Manages PostgresSaver, SQLAlchemy engine, and a background embedding-retry worker."""

    def __init__(self):
        """Validate config, run migrations, open the checkpointer, and start the index worker."""
        config.validate_runtime()
        self.resources = ExitStack()
        self.stop = Event()
        self.worker = None
        try:
            migrate()
            ensure_index_jobs()
            url = make_url(config.DATABASE_URL).set(drivername="postgresql")
            connection = self.resources.enter_context(
                Connection.connect(
                    url.render_as_string(hide_password=False),
                    autocommit=True,
                    prepare_threshold=0,
                    row_factory=dict_row,
                )
            )
            saver = PostgresSaver(connection, serde=checkpoint_serializer())
            saver.setup()
            # 启动后清理旧 checkpoint（控制 checkpoints 表膨胀）
            # 为什么在 setup 后做：需要表已经存在
            self._cleanup_checkpoints(connection)
            self.graph = build_graph(checkpointer=saver)
            self.worker = Thread(target=self._index_loop, name="error-index", daemon=True)
            self.worker.start()
        except BaseException:
            self.resources.close()
            raise

    def _cleanup_checkpoints(self, conn: Connection) -> None:
        """清理每个 thread 超出 CHECKPOINT_KEEP 的旧 checkpoint。

        为什么启动时做而不是每次对话做：
          - 清理是重操作（全表排序 + 删除），不需要每轮都做
          - 启动时一次清理足够控制体积
          - 避免对话延迟增加

        删除顺序（外键约束）：
          1. checkpoint_writes（子表，引用 checkpoint）
          2. checkpoint_blobs（子表，按 channel 存的增量 blob）
          3. checkpoints（父表，主记录）
        """
        keep = max(1, config.CHECKPOINT_KEEP)  # 至少保留 1 个
        with conn.cursor() as cur:
            # 找出每个 (thread_id, checkpoint_ns) 需要保留的 checkpoint_id
            # 用 row_number 窗口函数按 checkpoint_id 倒序编号
            cur.execute(
                """
                WITH ranked AS (
                    SELECT
                        thread_id,
                        checkpoint_ns,
                        checkpoint_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY thread_id, checkpoint_ns
                            ORDER BY checkpoint_id DESC
                        ) AS rn
                    FROM checkpoints
                )
                SELECT thread_id, checkpoint_ns, checkpoint_id
                FROM ranked
                WHERE rn > %s
                """,
                (keep,),
            )
            rows = cur.fetchall()
            if not rows:
                return
            # 收集要删除的 checkpoint 主键列表
            to_delete = [(r["thread_id"], r["checkpoint_ns"], r["checkpoint_id"]) for r in rows]
            # 用 list 而非 tuple：psycopg 3 把 list 适配成 PostgreSQL array，
            # tuple 会被适配成 record，ANY() 会报 "Array value must start with '{'"
            ids_list = [r["checkpoint_id"] for r in rows]

            # 步骤 1：删 checkpoint_writes（子表）
            # checkpoint_writes 的主键是 (thread_id, checkpoint_ns, task_id, write_idx)
            # 但它引用 checkpoints 的 (thread_id, checkpoint_ns, checkpoint_id)
            cur.execute(
                "DELETE FROM checkpoint_writes WHERE checkpoint_id = ANY(%s)",
                (ids_list,),
            )

            # 步骤 2：删 checkpoints（父表）
            # 注意：checkpoint_blobs 是按 channel 存的，可能被多个 checkpoint 共享
            # 所以不直接删 blobs —— 它们会被后续的 checkpoint 复用
            cur.execute(
                "DELETE FROM checkpoints WHERE checkpoint_id = ANY(%s)",
                (ids_list,),
            )

            logger.info(
                "checkpoint_cleanup removed=%d keep_per_thread=%d",
                len(to_delete),
                keep,
            )

    def _index_loop(self) -> None:
        """Poll pending embedding tasks until ``stop`` is set."""
        batch = max(1, config.EMBEDDING_BATCH_SIZE)
        while not self.stop.is_set():
            try:
                retry_pending(limit=batch)
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "index_worker_failed error_type=%s", type(exc).__name__
                )
            self.stop.wait(5)

    def close(self) -> None:
        """Signal the worker to stop, join it, and release all held resources."""
        self.stop.set()
        if self.worker is not None:
            self.worker.join()
        self.resources.close()
        close_database()


@lru_cache(maxsize=1)
def get_runtime() -> Runtime:
    """Return a cached ``Runtime`` singleton and register ``atexit`` cleanup."""
    runtime = Runtime()
    atexit.register(runtime.close)
    return runtime
