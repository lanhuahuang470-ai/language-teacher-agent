"""Explicit application types allowed in current and historical checkpoints."""

from __future__ import annotations

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


def checkpoint_serializer():
    """Return a ``JsonPlusSerializer`` that allows Exercise and GradeResult in checkpoints."""
    return JsonPlusSerializer(
        allowed_msgpack_modules=[
            (module, name)
            for module in (
                "language_tutor.domain.schemas",
                "language_tutor.graph.state",
                "graph.state",
            )
            for name in ("Exercise", "GradeResult")
        ]
    )
