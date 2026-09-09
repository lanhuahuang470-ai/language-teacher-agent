import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError

from language_tutor.agents import tools
from language_tutor.domain.learning_policy import advance
from language_tutor.graph.builder import build_graph, route_by_pending
from language_tutor.graph.nodes import assessor, init_session, placement, tutor
from language_tutor.graph.state import Exercise, GradeResult
from language_tutor.llm.json_utils import extract_json
from language_tutor.llm.outputs import (
    AssessmentOutput,
    PlanningOutput,
    TeachingOutput,
    invoke_validated,
)


def exercise():
    return Exercise(exercise_id="q1", knowledge_point="be动词", question="He __ happy.")


def grade(correct=True):
    return GradeResult(
        exercise_id="q1",
        is_correct=correct,
        score=1.0 if correct else 0.0,
        error_types=[],
        feedback_hint="留意主谓一致",
        correct_answer="He is happy.",
    )


def state(**changes):
    return {
        "student_id": "alice",
        "messages": [HumanMessage("is")],
        "session_plan": ["be动词", "一般现在时"],
        "current_kp": "be动词",
        "cefr_level": "A1",
        "pending_exercise": exercise(),
        "input_event": "answer",
        **changes,
    }


def agent_response(**data):
    return {"messages": [AIMessage(json.dumps(data, ensure_ascii=False))]}


class ConstantEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0]


def test_tool_schema_hides_identity_and_config(monkeypatch):
    for tool in tools.ALL_TOOLS:
        properties = tool.tool_call_schema.model_json_schema().get("properties", {})
        assert "student_id" not in properties
        assert "config" not in properties
    search = MagicMock(return_value=[])
    monkeypatch.setattr(tools, "search_similar_errors", search)
    tools.get_similar_errors.invoke(
        {"student_sentence": "bad", "student_id": "bob"},
        config={"configurable": {"student_id": "alice"}},
    )
    search.assert_called_once_with("bad", student_id="alice", k=3)


def test_missing_identity_fails_closed():
    with pytest.raises(ValueError, match="身份"):
        tools.get_similar_errors.invoke({"student_sentence": "bad"})


@pytest.mark.parametrize("event", ["start", "hint", "explain", "skip"])
def test_non_answer_does_not_route_to_assessor(event):
    assert route_by_pending(state(input_event=event)) == "tutor"


def test_answer_routes_to_assessor():
    assert route_by_pending(state()) == "assessor"
    assert route_by_pending(state(pending_exercise=None)) == "tutor"


def test_start_reuses_exercise_without_model_call(monkeypatch):
    fake = MagicMock(side_effect=AssertionError("must not call model"))
    replace_agent(monkeypatch, tutor, "get_tutor_llm", fake)
    result = tutor.run(state(input_event="start"))
    assert "He __ happy." in result["messages"][0][1]
    assert "pending_exercise" not in result
    assert "grade_result" not in result


@pytest.mark.parametrize("event", ["hint", "explain"])
def test_help_preserves_exercise_and_grade(monkeypatch, event):
    replace_agent(monkeypatch, tutor, "get_tutor_llm", lambda *a, **k: AIMessage("看主语。"))
    result = tutor.run(state(input_event=event))
    assert set(result) == {"messages"}


def test_course_progression():
    plan = ["be动词", "一般现在时"]
    assert advance(plan, "be动词", 0, grade()) == ("be动词", 1, False)
    assert advance(plan, "be动词", 1, grade(False)) == ("be动词", 0, False)
    assert advance(plan, "be动词", 1, grade()) == ("一般现在时", 0, False)
    assert advance(plan, "一般现在时", 1, grade()) == ("一般现在时", 0, True)


def test_teaching_passes_bounded_context_and_clears_grade(monkeypatch):
    fake = MagicMock(return_value=agent_response(reply="答对了，继续。", exercise="She __ nice."))
    replace_agent(monkeypatch, tutor, "get_tutor_agent", fake)
    result = tutor.run(state(pending_exercise=None, grade_result=grade(), correct_streak=1))
    assert result["current_kp"] == "一般现在时"
    assert result["grade_result"] is None
    assert result["pending_exercise"].knowledge_point == "一般现在时"
    sent = fake.call_args.args[0]["messages"]
    assert any("is" == content for _, content in sent)
    assert fake.call_args.kwargs["config"]["configurable"]["student_id"] == "alice"


def test_skip_does_not_advance_and_resets_streak(monkeypatch):
    replace_agent(
        monkeypatch,
        tutor,
        "get_tutor_agent",
        lambda *a, **k: agent_response(reply="换一题。", exercise="They __ nice."),
    )
    result = tutor.run(state(input_event="skip", correct_streak=1))
    assert result["current_kp"] == "be动词"
    assert result["correct_streak"] == 0
    assert result["pending_exercise"].exercise_id != "q1"


def test_course_completion_clears_pending():
    result = tutor.run(
        state(
            pending_exercise=None, grade_result=grade(), current_kp="一般现在时", correct_streak=1
        )
    )
    assert result["session_complete"] is True
    assert result["pending_exercise"] is None
    assert result["grade_result"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"score": 2},
        {"score": -0.1},
        {"score": float("nan")},
        {"score": "1"},
        {"is_correct": "true"},
        {"correct_answer": ""},
        {"is_correct": True, "score": 0.5},
        {"is_correct": True, "error_types": ["时态"]},
    ],
)
def test_invalid_assessment_is_rejected(changes):
    data = {
        "is_correct": True,
        "score": 1.0,
        "error_types": [],
        "feedback_hint": "正确",
        "correct_answer": "is",
        **changes,
    }
    with pytest.raises(ValidationError):
        AssessmentOutput.model_validate(data)


@pytest.mark.parametrize(
    "raw",
    [
        '{"reply":"brace } and { inside","exercise":"x"}',
        '前言 {"reply":"brace } and { inside","exercise":"x"} 后记',
        '```json\n{"reply":"brace } and { inside","exercise":"x"}\n```',
    ],
)
def test_json_braces_inside_strings(raw):
    assert extract_json(raw)["exercise"] == "x"


def test_invalid_output_retries_once():
    fake = MagicMock()
    fake.invoke.return_value = agent_response(reply="")
    with pytest.raises(ValueError, match="校验"):
        invoke_validated(fake, [("user", "teach")], TeachingOutput, "alice")
    assert fake.invoke.call_count == 2


def test_invalid_assessment_never_writes(monkeypatch):
    replace_agent(
        monkeypatch,
        assessor,
        "get_assessor_agent",
        lambda *a, **k: agent_response(is_correct=True, score=9),
    )
    session = MagicMock()
    monkeypatch.setattr(assessor, "record_assessment", session)
    with pytest.raises(ValueError):
        assessor.run(state())
    session.assert_not_called()


def test_assessment_passes_correct_answer_to_transaction(monkeypatch):
    replace_agent(
        monkeypatch,
        assessor,
        "get_assessor_agent",
        lambda *a, **k: agent_response(
            is_correct=False,
            score=0.0,
            error_types=["语法"],
            feedback_hint="注意主谓一致",
            correct_answer="He is happy.",
        ),
    )
    save = MagicMock(side_effect=lambda *args: args[-1])
    monkeypatch.setattr(assessor, "record_assessment", save)
    result = assessor.run(state())
    assert save.call_args.args[3].correct_answer == "He is happy."
    assert save.call_args.args[3].feedback_hint == "注意主谓一致"
    assert result["pending_exercise"] is None


def test_placement_does_not_write_mastery(monkeypatch):
    replace_agent(
        monkeypatch,
        assessor,
        "get_assessor_agent",
        lambda *a, **k: agent_response(
            is_correct=True, score=1.0, error_types=[], feedback_hint="正确", correct_answer="is"
        ),
    )
    session = MagicMock()
    monkeypatch.setattr(assessor, "record_assessment", session)
    result = assessor.run(state(placement_mode=True, placement_scores=[0.0]))
    assert result["placement_scores"] == [0.0, 1.0]
    session.assert_not_called()


def test_placement_finishes_and_clears_scores(monkeypatch):
    monkeypatch.setattr(placement, "SessionLocal", MagicMock())
    update_level = MagicMock()
    monkeypatch.setattr(placement, "update_student_level", update_level)
    result = placement.handle_placement(state(placement_scores=[1, 1, 1, 1, 0]))
    assert result["cefr_level"] == "B1"
    assert result["placement_mode"] is False
    assert result["placement_scores"] == []


def test_planning_rejects_unknown_course(monkeypatch):
    monkeypatch.setattr(init_session, "SessionLocal", MagicMock())
    monkeypatch.setattr(
        init_session, "get_or_create_student", lambda *a: (SimpleNamespace(cefr_level="A1"), False)
    )
    replace_agent(
        monkeypatch,
        init_session,
        "get_planning_agent",
        lambda *a, **k: agent_response(plan=["不存在的课程"], reason="bad"),
    )
    result = init_session.run({"student_id": "alice"})
    assert result["session_plan"] == init_session.CURRICULUM["A1"]


def test_graph_start_and_hint_keep_checkpoint_exercise(monkeypatch):
    monkeypatch.setattr(
        init_session,
        "run",
        lambda s: {} if s.get("session_plan") else {"session_plan": ["be动词"], "cefr_level": "A1"},
    )
    replace_agent(
        monkeypatch,
        tutor,
        "get_tutor_agent",
        lambda *a, **k: agent_response(reply="开始。", exercise="He __ happy."),
    )
    replace_agent(monkeypatch, tutor, "get_tutor_llm", lambda *a, **k: AIMessage("看主语。"))
    assessment = MagicMock(side_effect=AssertionError("must not assess"))
    monkeypatch.setattr(assessor, "run", assessment)
    graph = build_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "alice"}}
    first = graph.invoke(
        {"student_id": "alice", "messages": [HumanMessage("开始")], "input_event": "start"}, config
    )
    qid = first["pending_exercise"].exercise_id
    for event in ["start", "hint", "explain"]:
        result = graph.invoke({"messages": [HumanMessage(event)], "input_event": event}, config)
        assert result["pending_exercise"].exercise_id == qid
    assessment.assert_not_called()


def test_output_can_recover_once():
    fake = MagicMock()
    fake.invoke.side_effect = [
        agent_response(reply=""),
        agent_response(reply="好了", exercise="He __ nice."),
    ]
    result = invoke_validated(fake, [("user", "teach")], TeachingOutput, "alice")
    assert result.exercise == "He __ nice."
    assert fake.invoke.call_count == 2


@pytest.mark.parametrize("plan", [[], "be动词", None])
def test_invalid_plan_shape(plan):
    with pytest.raises(ValidationError):
        PlanningOutput.model_validate({"plan": plan})


def test_restarting_completed_course_resets_progress(monkeypatch):
    monkeypatch.setattr(init_session, "SessionLocal", MagicMock())
    monkeypatch.setattr(
        init_session, "get_or_create_student", lambda *a: (SimpleNamespace(cefr_level="A1"), False)
    )
    replace_agent(
        monkeypatch,
        init_session,
        "get_planning_agent",
        lambda *a, **k: agent_response(plan=["一般现在时"], reason="next"),
    )
    result = init_session.run(state(session_complete=True, input_event="start"))
    assert result["session_complete"] is False
    assert result["correct_streak"] == 0
    assert result["current_kp"] == "一般现在时"


def test_ui_blank_answer_and_changed_identity_are_rejected(monkeypatch):
    from language_tutor.ui import gradio_app as main

    invoke = MagicMock()
    monkeypatch.setattr(main, "_invoke", invoke)
    with pytest.raises(Exception):
        main.respond("", "alice", "alice", "回答")
    with pytest.raises(Exception):
        main.respond("is", "bob", "alice", "回答")
    invoke.assert_not_called()


def test_ui_command_is_an_event(monkeypatch):
    from language_tutor.ui import gradio_app as main

    invoke = MagicMock(return_value=([], ""))
    monkeypatch.setattr(main, "_invoke", invoke)
    main.respond("给个提示", "alice", "alice", "回答")
    invoke.assert_called_once_with("给个提示", "alice", "hint", None, "default")


def test_toolnode_injects_identity_for_model_tool_calls(monkeypatch):
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode

    search = MagicMock(return_value=[])
    monkeypatch.setattr(tools, "search_similar_errors", search)
    builder = StateGraph(MessagesState)
    builder.add_node("tools", ToolNode([tools.get_similar_errors]))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    node = builder.compile()
    result = node.invoke(
        {
            "messages": [
                AIMessage(
                    "",
                    tool_calls=[
                        {
                            "name": "get_similar_errors",
                            "args": {"student_sentence": "bad", "student_id": "bob"},
                            "id": "call1",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        },
        config={"configurable": {"student_id": "alice"}},
    )
    assert result["messages"][-1].content == "暂无相似错题记录"
    search.assert_called_once_with("bad", student_id="alice", k=3)


def test_full_graph_completes_course_and_does_not_grade_help(monkeypatch):
    monkeypatch.setattr(
        init_session,
        "run",
        lambda s: (
            {}
            if s.get("session_plan")
            else {"session_plan": ["be动词", "一般现在时"], "cefr_level": "A1"}
        ),
    )
    replace_agent(
        monkeypatch,
        tutor,
        "get_tutor_agent",
        lambda *a, **k: agent_response(reply="继续。", exercise="He __ happy."),
    )
    replace_agent(monkeypatch, tutor, "get_tutor_llm", lambda *a, **k: AIMessage("看主语。"))
    replace_agent(
        monkeypatch,
        assessor,
        "get_assessor_agent",
        lambda *a, **k: agent_response(
            is_correct=True,
            score=1.0,
            error_types=[],
            feedback_hint="回答正确",
            correct_answer="is",
        ),
    )
    mastery = MagicMock(side_effect=lambda *args: args[-1])
    monkeypatch.setattr(assessor, "record_assessment", mastery)
    graph = build_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "course-alice"}}
    result = graph.invoke(
        {"student_id": "alice", "input_event": "start", "messages": [HumanMessage("开始")]},
        config,
    )
    for _ in range(4):
        graph.invoke({"input_event": "hint", "messages": [HumanMessage("提示")]}, config)
        result = graph.invoke(
            {"input_event": "answer", "messages": [HumanMessage("is")]},
            config,
        )
    assert mastery.call_count == 4
    assert result["session_complete"] is True
    assert result["pending_exercise"] is None
    assert result["grade_result"] is None


def test_gradio_ui_can_be_constructed():
    from language_tutor.ui import gradio_app as main

    demo = main.create_demo()
    assert demo is not None


@pytest.mark.parametrize("raw", ["[]", "null", "42"])
def test_json_requires_object(raw):
    with pytest.raises(ValueError, match="对象"):
        extract_json(raw)


def replace_agent(monkeypatch, module, name, call):
    monkeypatch.setattr(module, name, lambda: SimpleNamespace(invoke=call))


@pytest.fixture(autouse=True)
def fake_persistence(monkeypatch):
    monkeypatch.setattr(assessor, "get_recorded_grade", lambda *args: None)
    monkeypatch.setattr(assessor, "record_assessment", lambda *args: args[-1])


def test_assessor_reuses_committed_grade_without_calling_model(monkeypatch):
    monkeypatch.setattr(assessor, "get_recorded_grade", lambda *args: grade())
    fail = MagicMock(side_effect=AssertionError("must not regrade"))
    replace_agent(monkeypatch, assessor, "get_assessor_agent", fail)
    result = assessor.run(state())
    assert result["grade_result"] == grade()
    fail.assert_not_called()


def test_stale_answer_is_not_graded():
    current = state(expected_exercise_id="older-question")
    assert route_by_pending(current) == "tutor"
    result = tutor.run(current)
    assert "pending_exercise" not in result
    assert "He __ happy." in result["messages"][0][1]


def test_gradio_api_schema_can_be_generated():
    from language_tutor.ui.gradio_app import create_demo

    demo = create_demo()
    assert isinstance(demo.get_api_info(), dict)
