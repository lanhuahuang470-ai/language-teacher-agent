# 会话初始化节点：从 PG 加载学生档案，用规划 Agent 生成 session_plan
#
# 升级：从固定课程清单 → 规划 Agent 个性化排序
#   老学生：规划 Agent 查掌握度 → 按薄弱度排序知识点 → 个性化计划
#   新学生：直接进入定级测试（不需要规划）
from language_tutor.agents.planning_agent import get_planning_agent
from language_tutor.db.crud import get_or_create_student
from language_tutor.db.engine import SessionLocal
from language_tutor.domain.curriculum import CURRICULUM
from language_tutor.graph.state import TutorState
from language_tutor.llm.outputs import PlanningOutput, invoke_validated
from language_tutor.telemetry import traced


@traced("init_session")
def run(state: TutorState) -> dict:
    student_id = state["student_id"]

    # 幂等检查：checkpointer 续接的老会话已有 plan，直接放行
    restarting = state.get("session_complete") and state.get("input_event") == "start"
    if not restarting and (state.get("session_plan") or state.get("placement_mode")):
        return {}

    # 从 PG 加载学生档案
    with SessionLocal() as session:
        student, is_new = get_or_create_student(session, student_id)
        cefr_level = student.cefr_level

    # 新学生先做入学定级测试，不做计划
    if is_new:
        return {"placement_mode": True, "placement_scores": []}

    # 老学生：用规划 Agent 生成个性化计划
    user_msg = (
        f"学生 ID：{student_id}，等级：{cefr_level}。"
        f"请分析该学生的掌握度数据，生成本次会话的教学计划。"
        f"先调用 get_weak_points 查薄弱知识点，再调用 get_curriculum 查课程清单。"
    )

    try:
        data = invoke_validated(
            get_planning_agent(), [("user", user_msg)], PlanningOutput, student_id
        )
        allowed = CURRICULUM.get(cefr_level, CURRICULUM["A1"])
        if any(kp not in allowed for kp in data.plan):
            raise ValueError("规划包含当前等级课程以外的知识点")
        plan = list(dict.fromkeys(data.plan))
    except ValueError:
        # Agent 输出解析失败时，用固定课程兜底
        plan = CURRICULUM.get(cefr_level, CURRICULUM["A1"])

    return {
        "cefr_level": cefr_level,
        "session_plan": plan,
        "correct_streak": 0,
        "session_complete": False,
        "current_kp": plan[0],
        "grade_result": None,
        "pending_exercise": None,
    }
