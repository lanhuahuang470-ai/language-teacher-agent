import json
import logging
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from language_tutor.domain.schemas import Exercise, GradeResult
from language_tutor.graph.serialization import checkpoint_serializer
from language_tutor.llm.json_utils import extract_json
from language_tutor.llm.outputs import ModelOutputError, TeachingOutput, invoke_validated


def test_literal_newlines_in_json_strings_are_preserved():
    raw = '{"reply":"第一行\n第二行", "exercise":"Fill in:\nHe __ happy."}'
    result = TeachingOutput.model_validate(extract_json(raw))
    assert result.exercise == "Fill in:\nHe __ happy."


def test_repair_includes_invalid_reply_and_specific_field(monkeypatch):
    invalid = json.dumps({"reply": "讲解", "exercise": {"question": "He __ happy."}})
    fake = MagicMock()
    requests = []

    def invoke(inputs, config):
        requests.append(list(inputs["messages"]))
        if len(requests) == 1:
            return {"messages": [AIMessage(invalid)]}
        assert requests[-1][-2] == ("assistant", invalid)
        assert '"field": "exercise"' in requests[-1][-1][1]
        assert "string_type" in requests[-1][-1][1]
        return {"messages": [AIMessage('{"reply":"讲解", "exercise":"He __ happy."}')]}

    fake.invoke.side_effect = invoke
    assert invoke_validated(fake, [("user", "teach")], TeachingOutput, "alice").exercise
    assert len(requests) == 2


def test_failure_reports_fields_without_logging_response(caplog):
    fake = MagicMock()
    fake.invoke.return_value = {
        "messages": [AIMessage('{"reply":"private answer", "exercise":null}')]
    }
    with caplog.at_level(logging.WARNING), pytest.raises(ModelOutputError, match="exercise"):
        invoke_validated(fake, [("user", "teach")], TeachingOutput, "alice")
    assert "string_type" in caplog.text
    assert "private answer" not in caplog.text


def test_content_blocks_and_extra_metadata_are_supported():
    fake = MagicMock()
    fake.invoke.return_value = {
        "messages": [
            AIMessage(
                content=[
                    {
                        "type": "text",
                        "text": '{"reply":"解释", "exercise":"He __ happy.", "metadata":{}}',
                    }
                ]
            )
        ]
    }
    assert invoke_validated(fake, [], TeachingOutput, "alice").exercise == "He __ happy."


@pytest.mark.parametrize(
    "module", ["graph.state", "language_tutor.graph.state", "language_tutor.domain.schemas"]
)
@pytest.mark.parametrize("kind", [Exercise, GradeResult])
def test_explicit_checkpoint_types_without_warning(monkeypatch, caplog, module, kind):
    instance = (
        Exercise(exercise_id="q", knowledge_point="be", question="He __ happy.")
        if kind is Exercise
        else GradeResult(
            exercise_id="q", is_correct=True, score=1, error_types=[], feedback_hint="正确"
        )
    )
    serde = checkpoint_serializer()
    with monkeypatch.context() as context:
        context.setattr(kind, "__module__", module)
        encoded = serde.dumps_typed(instance)
    with caplog.at_level(logging.WARNING):
        assert serde.loads_typed(encoded) == instance
    assert "unregistered" not in caplog.text


def test_checkpoint_still_supports_framework_messages():
    serde = checkpoint_serializer()
    message = HumanMessage("hello")
    assert serde.loads_typed(serde.dumps_typed(message)) == message


def test_ui_surfaces_validation_error(monkeypatch):
    import gradio as gr

    from language_tutor.ui import gradio_app

    graph = MagicMock()
    graph.invoke.side_effect = ModelOutputError("exercise: string_type")
    monkeypatch.setattr(gradio_app, "get_graph", lambda: graph)
    with pytest.raises(gr.Error, match="exercise"):
        gradio_app._invoke("开始上课", "alice", "start")
