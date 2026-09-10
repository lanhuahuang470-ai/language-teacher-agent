"""定级测试逻辑：新学生入学时出 9 道递增难度的题，根据答对数量确定 CEFR 等级。

定级流程：
  1. init_session 检测到新学生 → 设置 placement_mode=True
  2. tutor.run 调用 handle_placement → 出定级题
  3. 学生答题 → assessor.run 判分 → 返回 score 加入 placement_scores
  4. tutor.run 再次调用 handle_placement → 看是否还有题
  5. 9 题做完 → 根据答对数确定等级 → 写入 PG → 转入正式教学

注意：定级期间不写掌握度（placement_scores 只是临时分数），不写错题。
"""

from uuid import uuid4

from language_tutor.db.crud import update_student_level
from language_tutor.db.engine import SessionLocal
from language_tutor.domain.curriculum import CURRICULUM
from language_tutor.graph.state import Exercise, TutorState
from language_tutor.llm.client import get_tutor_llm

# 9 道定级题的难度序列：A1→A1→A2→A2→B1→B1→B2→B2→C1
# 每道题对应一个 CEFR 等级，LLM 据此出对应难度的题
PLACEMENT_LEVELS = ["A1", "A1", "A2", "A2", "B1", "B1", "B2", "B2", "C1"]

# 答对数量（score >= 0.5 算答对）→ 最终等级的映射
# 0~1 题答对 → A1，2~3 → A2，4~5 → B1，6~7 → B2，8~9 → C1
PLACEMENT_GRADING = {
    0: "A1",
    1: "A1",
    2: "A2",
    3: "A2",
    4: "B1",
    5: "B1",
    6: "B2",
    7: "B2",
    8: "C1",
    9: "C1",
}


def handle_placement(state: TutorState) -> dict:
    """出下一道定级题，或者 9 道做完后确定等级并转入正式教学。

    由 tutor.run 在 placement_mode=True 时调用。
    返回值有两种情况：
      - 还有题：返回 {messages: [定级题], pending_exercise: Exercise}
      - 题做完了：返回 {cefr_level, session_plan, placement_mode:False, ...}
    """
    scores = state.get("placement_scores", [])
    question_num = len(scores)  # 已答的题数 = 下一题的索引

    # 9 道题全部答完 → 计算最终等级
    if question_num >= len(PLACEMENT_LEVELS):
        # score >= 0.5 算答对，统计答对总数
        correct_count = sum(score >= 0.5 for score in scores)
        level = PLACEMENT_GRADING[correct_count]
        # 写入 PG，持久化学生等级
        with SessionLocal() as session:
            update_student_level(session, state["student_id"], level)
        # 取该等级的知识点列表作为学习计划
        plan = list(CURRICULUM[level])
        return {
            "cefr_level": level,
            "session_plan": plan,
            "current_kp": plan[0],
            "placement_mode": False,  # 退出定级模式
            "placement_scores": [],  # 清空临时分数
            "correct_streak": 0,
            "session_complete": False,
            "grade_result": None,
            "pending_exercise": None,
        }

    # 还没答完 → 出下一道定级题
    difficulty = PLACEMENT_LEVELS[question_num]
    # 用 tutor LLM 出题（temp=0.7，允许题目多样性）
    # 注意：这里直接调 LLM，不走 ReAct Agent，因为定级题不需要查工具
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

    # 第一道题加欢迎语，后续只出题号
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
