"""Diagnostic placement policy; scores are provisional, not mastery updates."""

from uuid import uuid4

from language_tutor.db.crud import update_student_level
from language_tutor.db.engine import SessionLocal
from language_tutor.domain.curriculum import CURRICULUM
from language_tutor.graph.state import Exercise, TutorState
from language_tutor.llm.client import get_tutor_llm

PLACEMENT_LEVELS = ["A1", "A1", "A2", "A2", "B1"]
PLACEMENT_GRADING = {0: "A1", 1: "A1", 2: "A2", 3: "A2", 4: "B1", 5: "B1"}


def handle_placement(state: TutorState) -> dict:
    scores = state.get("placement_scores", [])
    question_num = len(scores)
    if question_num >= len(PLACEMENT_LEVELS):
        level = PLACEMENT_GRADING[sum(score >= 0.5 for score in scores)]
        with SessionLocal() as session:
            update_student_level(session, state["student_id"], level)
        plan = list(CURRICULUM[level])
        return {
            "cefr_level": level,
            "session_plan": plan,
            "current_kp": plan[0],
            "placement_mode": False,
            "placement_scores": [],
            "correct_streak": 0,
            "session_complete": False,
            "grade_result": None,
            "pending_exercise": None,
        }
    difficulty = PLACEMENT_LEVELS[question_num]
    question = (
        get_tutor_llm()
        .invoke(
            [
                ("system", "你是英语出题器，只输出一道题目，不包含答案，不输出 JSON。"),
                ("user", f"请出一道 {difficulty} 难度的基础语法或词汇题。"),
            ]
        )
        .content
    )
    if not isinstance(question, str) or not question.strip():
        raise ValueError("未能生成有效定级题，请重试")
    greeting = "欢迎！我们先做一个简单的英语水平测试。" if question_num == 0 else ""
    return {
        "messages": [
            (
                "assistant",
                f"{greeting}第 {question_num + 1}/{len(PLACEMENT_LEVELS)} "
                f"题（{difficulty}）：\n\n{question}",
            )
        ],
        "pending_exercise": Exercise(
            exercise_id=uuid4().hex,
            knowledge_point=f"定级测试-{difficulty}",
            question=question,
        ),
    }
