# 会话初始化节点：从 PG 加载学生档案，用规划 Agent 生成 session_plan
#
# 三种入口路径：
#   1. 新学生：建档 → 进入定级测试（placement_mode=True）
#   2. 老学生继续上课：checkpointer 续接已有 plan → 直接放行
#   3. 老学生重新开始：session_complete=True + input_event="start" → 重新规划
#
# 自动升级逻辑：
#   老学生重新开始上课时，检查当前等级全部知识点掌握度 ≥ 0.8
#   满足条件则升一级，写入 PG，用新等级的知识点生成计划
from language_tutor.agents.planning_agent import get_planning_agent
from language_tutor.db.crud import get_mastery_map, get_or_create_student, update_student_level
from language_tutor.db.engine import SessionLocal
from language_tutor.domain.curriculum import CURRICULUM
from language_tutor.graph.state import TutorState
from language_tutor.llm.outputs import PlanningOutput, invoke_validated
from language_tutor.telemetry import traced


@traced("init_session")
def run(state: TutorState) -> dict:
    """加载学生档案，决定是定级、续接还是重新规划。

    被图的 START 边调用，每次图执行时第一个运行。
    """
    student_id = state["student_id"]

    # 幂等检查：checkpointer 续接的老会话已有 plan，直接放行
    # 只有 session_complete + input_event="start" 才重新规划（老学生学完重来）
    restarting = state.get("session_complete") and state.get("input_event") == "start"
    if not restarting and (state.get("session_plan") or state.get("placement_mode")):
        return {}

    # 从 PG 加载学生档案；新学生自动建档（cefr_level 默认 A1）
    with SessionLocal() as session:
        student, is_new = get_or_create_student(session, student_id)
        cefr_level = student.cefr_level

    # 路径 1：新学生 → 进入定级测试
    if is_new:
        return {"placement_mode": True, "placement_scores": []}

    # 路径 3：老学生重新开始 → 检查是否满足升级条件
    # 升级规则：当前等级全部知识点掌握度 >= 0.8 → 升一级
    # 为什么 0.8：滚动平均后的分数，0.8 表示大多数题目答对
    with SessionLocal() as session:
        mastery_map = get_mastery_map(session, student_id)
        current_kps = CURRICULUM.get(cefr_level, [])
        if current_kps and all(mastery_map.get(kp, 0) >= 0.8 for kp in current_kps):
            # CURRICULUM 是有序字典，按 key 顺序找下一级
            levels = list(CURRICULUM)
            next_idx = levels.index(cefr_level) + 1
            if next_idx < len(levels):
                cefr_level = levels[next_idx]
                # 升级写入 PG，持久化新等级
                update_student_level(session, student_id, cefr_level)

    # 路径 2/3 汇合：用规划 Agent 生成个性化计划
    # 规划 Agent 自主决策：查薄弱点 → 查错题模式 → 查前置依赖 → 综合规划
    # 不强制调用顺序，让 Agent 自主决定调哪些工具、怎么综合信息
    user_msg = (
        f"学生 ID：{student_id}，等级：{cefr_level}。"
        f"请分析该学生的掌握度、错题模式和知识点依赖关系，"
        f"生成本次会话的教学计划。"
    )

    try:
        data = invoke_validated(
            get_planning_agent(), [("user", user_msg)], PlanningOutput, student_id
        )
        # 安全校验：规划 Agent 只能选当前等级内的知识点
        allowed = CURRICULUM.get(cefr_level, CURRICULUM["A1"])
        if any(kp not in allowed for kp in data.plan):
            raise ValueError("规划包含当前等级课程以外的知识点")
        # 去重保序：dict.fromkeys 保留首次出现的顺序
        plan = list(dict.fromkeys(data.plan))
    except ValueError:
        # Agent 输出解析失败或包含非法知识点 → 用固定课程兜底
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
