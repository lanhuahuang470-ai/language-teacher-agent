"""Structured operational events without student text, answers or credentials."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from time import perf_counter
from uuid import uuid4

trace_id = ContextVar("trace_id", default="background")
logger = logging.getLogger("language_tutor.events")


def emit(event: str, **fields):
    logger.info(json.dumps({"event": event, "trace_id": trace_id.get(), **fields}))


@contextmanager
def request_trace():
    token = trace_id.set(uuid4().hex)
    try:
        yield trace_id.get()
    finally:
        trace_id.reset(token)


def traced(name: str):
    """Decorator that emits ``node_completed`` / ``node_failed`` events around a function call."""

    def decorate(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            start = perf_counter()
            try:
                result = function(*args, **kwargs)
            except Exception as exc:
                emit(
                    "node_failed",
                    node=name,
                    elapsed_ms=round((perf_counter() - start) * 1000, 2),
                    error_type=type(exc).__name__,
                )
                raise
            emit("node_completed", node=name, elapsed_ms=round((perf_counter() - start) * 1000, 2))
            return result

        return wrapper

    return decorate
