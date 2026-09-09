"""Own persistent connections for the lifetime of a local application."""

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


class Runtime:
    def __init__(self):
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
            self.graph = build_graph(checkpointer=saver)
            self.worker = Thread(target=self._index_loop, name="error-index", daemon=True)
            self.worker.start()
        except BaseException:
            self.resources.close()
            raise

    def _index_loop(self):
        while not self.stop.is_set():
            try:
                retry_pending(limit=1)
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "index_worker_failed error_type=%s", type(exc).__name__
                )
            self.stop.wait(5)

    def close(self):
        self.stop.set()
        if self.worker is not None:
            self.worker.join()
        self.resources.close()
        close_database()


@lru_cache(maxsize=1)
def get_runtime() -> Runtime:
    runtime = Runtime()
    atexit.register(runtime.close)
    return runtime
