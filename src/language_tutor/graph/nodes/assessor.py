# 评估节点：用评估 Agent 判分 —— 判分前先查历史错题
#
# 升级：从固定 LLM 调用 → 评估 Agent 自主调用错题工具
#   Agent 判分后如果答错，自主调 get_error_history + get_similar_errors
#   能识别"反复犯同类错误"，反馈更精准
from language_tutor.agents.assessor_agent import get_assessor_agent
from language_tutor.graph.state import GradeResult, TutorState
from language_tutor.llm.outputs import AssessmentOutput, invoke_validated
from language_tutor.services.assessment import get_recorded_grade, record_assessment
from language_tutor.telemetry import traced


@traced("assessor")
def run(state: TutorState) -> dict:
    exercise = state["pending_exercise"]
    student_answer = state["messages"][-1].content

    if not state.get("placement_mode"):
        previous = get_recorded_grade(state["student_id"], exercise.exercise_id)
        if previous is not None:
            return {"pending_exercise": None, "grade_result": previous}

    # 构造评估 prompt：题目 + 知识点 + 学生答案
    user_msg = (
        f"知识点：{exercise.knowledge_point}\n"
        f"题目：{exercise.question}\n"
        f"学生答案：{student_answer}\n"
        f"学生 ID：{state['student_id']}\n"
        f"请先判分。如果学生答错，调用 get_error_history 和 get_similar_errors "
        f"查历史错题，判断是否反复犯同类错误。"
    )

    data = invoke_validated(
        get_assessor_agent(), [("user", user_msg)], AssessmentOutput, state["student_id"]
    )
    grade = GradeResult(
        exercise_id=exercise.exercise_id,
        **data.model_dump(),
    )

    if not state.get("placement_mode"):
        grade = record_assessment(state["student_id"], exercise, student_answer, grade)

    result = {"pending_exercise": None}
    if state.get("placement_mode"):
        result["placement_scores"] = [*state.get("placement_scores", []), grade.score]
    else:
        result["grade_result"] = grade
    return result
