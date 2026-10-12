"""Local Gradio demo. Student names are demo identities, not authentication."""

from __future__ import annotations

import json
import logging
from functools import lru_cache

import gradio as gr

from language_tutor import config
from language_tutor.bootstrap import get_runtime
from language_tutor.llm.outputs import ModelOutputError
from language_tutor.telemetry import request_trace

logger = logging.getLogger(__name__)

EVENTS = {"回答": "answer", "提示": "hint", "解释": "explain", "跳过": "skip"}
COMMANDS = {
    "开始": "start",
    "开始上课": "start",
    "给个提示": "hint",
    "提示": "hint",
    "我没理解": "explain",
    "解释一下": "explain",
    "跳过": "skip",
}


@lru_cache(maxsize=1)
def get_graph():
    return get_runtime().graph


def _invoke(
    message: str, student_id: str, event: str, expected_exercise_id=None, session_id="default"
) -> tuple[list[dict], str]:
    """Invoke the graph with validated inputs and return (chat_history, exercise_id)."""
    student_id = student_id.strip()
    if not student_id or len(student_id) > 100:
        raise gr.Error("请输入 1～100 字符的学生 ID。")
    if event == "answer" and not message.strip():
        raise gr.Error("请先输入答案。")
    if len(message) > 8000:
        raise gr.Error("输入过长，请限制在 8000 字符以内。")
    session_id = session_id.strip()
    if not session_id or len(session_id) > 100:
        raise gr.Error("请输入 1～100 字符的会话 ID。")
    thread_id = (
        student_id
        if session_id == "default"
        else json.dumps([student_id, session_id], ensure_ascii=False)
    )
    with request_trace() as tid:
        try:
            result = get_graph().invoke(
                {
                    "messages": [("user", message)],
                    "student_id": student_id,
                    "input_event": event,
                    "expected_exercise_id": expected_exercise_id,
                    "session_id": session_id,
                },
                {"configurable": {"thread_id": thread_id}},
            )
        except ModelOutputError as exc:
            raise gr.Error(str(exc)) from None
        except TimeoutError:
            raise gr.Error(
                f"AI 响应超时，请稍后重试。如果持续超时，请检查网络连接。（追踪号 {tid[:8]}）"
            ) from None
        except ConnectionError:
            raise gr.Error("无法连接数据库或 AI 服务，请检查服务是否正常运行后重试。") from None
        except Exception:
            logger.exception("graph_invoke_failed trace_id=%s", tid)
            raise gr.Error(
                f"系统内部错误，本轮未能完成。请重试，如持续报错请记录追踪号 {tid[:8]} 联系排查。"
            ) from None
    history = [
        {"role": "user" if msg.type == "human" else "assistant", "content": msg.content}
        for msg in result["messages"]
        if msg.type in {"human", "ai"}
    ]

    pending = result.get("pending_exercise")
    return history, pending.exercise_id if pending else ""


def start(student_id: str, session_id: str = "default"):
    """Trigger the first graph turn for a new or resuming student session."""
    history, question_id = _invoke("开始上课", student_id, "start", session_id=session_id)
    return history, student_id.strip(), question_id, session_id.strip()


def respond(
    message: str,
    student_id: str,
    active_student: str,
    action: str,
    expected_exercise_id=None,
    session_id="default",
    active_session="default",
):
    """Handle a student's message: resolve the event, invoke the graph, and clear the input."""
    if (
        not active_student
        or student_id.strip() != active_student
        or session_id.strip() != active_session
    ):
        raise gr.Error("请先点击“开始上课”加载该学生的会话。")
    event = EVENTS[action]
    if event == "answer":
        event = COMMANDS.get(message.strip(), "answer")
    if event == "answer" and not message.strip():
        raise gr.Error("请先输入答案。")
    history, question_id = _invoke(
        message.strip() or action, active_student, event, expected_exercise_id, session_id
    )
    return "", history, question_id


def create_demo():
    with gr.Blocks(title="英语教学助手") as demo:
        gr.Markdown("# 英语教学助手")
        active_student = gr.State("")
        active_session = gr.State("default")
        expected_exercise = gr.Textbox(visible=False)
        session_id = gr.Textbox(label="会话 ID（default 续接原会话）", value="default")
        student_id = gr.Textbox(label="学生 ID（本地演示，无登录鉴权）", value="alice")
        chatbot = gr.Chatbot(type="messages")
        action = gr.Radio(list(EVENTS), value="回答", label="本轮操作")
        with gr.Row():
            msg = gr.Textbox(placeholder="输入你的回答或问题...", scale=4)
            send_btn = gr.Button("发送", scale=1)
        start_btn = gr.Button("开始上课")
        start_btn.click(
            start,
            [student_id, session_id],
            [chatbot, active_student, expected_exercise, active_session],
        )
        inputs = [
            msg,
            student_id,
            active_student,
            action,
            expected_exercise,
            session_id,
            active_session,
        ]
        # All graph turns are serialized in this single-process demo.
        send_btn.click(
            respond,
            inputs,
            [msg, chatbot, expected_exercise],
        )
        msg.submit(
            respond,
            inputs,
            [msg, chatbot, expected_exercise],
        )
    demo.queue()
    return demo


def main():
    """Configure logging and launch the Gradio demo."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    create_demo().launch(server_name=config.TUTOR_HOST)


if __name__ == "__main__":
    main()
