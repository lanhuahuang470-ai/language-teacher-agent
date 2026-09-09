# 图的共享 State：节点之间唯一的通信方式
#
# 分工原则：
#   - State 是工作内存（本次会话内流转），PG 是长期内存（跨会话存活，如掌握度）
#   - 路由依据是结构化事件、待答题和提交题号，不能埋在自然语言里
#   - 每个字段都能回答：谁写、谁读、何时清（见各字段注释）

from typing import Annotated, Literal

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from language_tutor.domain.schemas import Exercise, GradeResult


class TutorState(TypedDict, total=False):
    # —— 会话身份与上下文 ——
    messages: Annotated[list, add_messages]  # 追加式，由 reducer 管理
    student_id: str  # 会话初始化时写入，整会话不变
    expected_exercise_id: str | None  # 浏览器提交时看到的题号，拒绝过期答案。
    session_id: str
    input_event: Literal["start", "answer", "hint", "explain", "skip"]

    # —— 会话初始化时从 PG 加载的只读缓存 ——
    cefr_level: str  # A1 / A2 / B1，教学节点据此调整难度
    session_plan: list[str]  # 本次会话的知识点清单
    correct_streak: int  # 当前知识点连续完全答对次数；推进或答错时归零。
    session_complete: bool

    # —— 入学水平评估（新学生专用，定级后清除）——
    placement_mode: bool  # True = 正在做定级测试
    placement_scores: list[float]  # 显式覆盖，定级结束后可以清空。

    # —— 教学⇄判分循环的工作区（临时字段，用完必须清空）——
    current_kp: str  # 当前正在教的知识点，切换时覆盖
    pending_exercise: Exercise | None
    grade_result: GradeResult | None

    # 注意：可选字段用 get 读取；学生身份等由入口保证的必填字段可直接索引


__all__ = ["Exercise", "GradeResult", "TutorState"]
