"""Explicit application types allowed in current and historical checkpoints."""

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


def checkpoint_serializer():
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
