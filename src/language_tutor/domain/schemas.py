from pydantic import BaseModel, Field


class Exercise(BaseModel):
    """待判分的练习。教学节点出题时写入，评估节点判分后清空。"""

    exercise_id: str
    knowledge_point: str  # 考查点，如 "一般过去时"
    question: str


class GradeResult(BaseModel):
    """判分结果。评估节点用结构化输出产生，教学节点读完后清空。"""

    exercise_id: str
    is_correct: bool
    score: float = Field(ge=0, le=1, allow_inf_nan=False)
    error_types: list[str]  # 如 ["时态", "主谓一致"]，后续喂给错题库
    feedback_hint: str  # 给教学节点的反馈要点（不是面向学生的最终话术）
    correct_answer: str = ""  # 默认值仅兼容旧 checkpoint；新判分要求非空。
