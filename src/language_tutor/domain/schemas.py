"""Pydantic schemas for exercises and grade results."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class Exercise(BaseModel):
    """待判分的练习。教学节点出题时写入，评估节点判分后清空。"""

    exercise_id: str
    knowledge_point: str  # 考查点，如 "一般过去时"
    question: str


class GradeResult(BaseModel):
    """判分结果。评估节点用结构化输出产生，教学节点读完后清空。

    评分分两层：
    - grammar_correct：语法结构是否正确（决定课程推进和错题保存）
    - spelling_correct：拼写是否正确（只影响反馈，不影响推进）
    - is_correct（计算属性）：语法且拼写都正确（向后兼容旧 checkpoint）
    """

    exercise_id: str
    grammar_correct: bool
    spelling_correct: bool = True
    score: float = Field(ge=0, le=1, allow_inf_nan=False)
    error_types: list[str]  # 如 ["时态", "主谓一致"]，后续喂给错题库
    feedback_hint: str  # 给教学节点的反馈要点（不是面向学生的最终话术）
    correct_answer: str = ""  # 默认值仅兼容旧 checkpoint；新判分要求非空。

    @computed_field  # type: ignore[misc]
    @property
    def is_correct(self) -> bool:
        """语法和拼写都正确才算完全正确，向后兼容旧代码读取。"""
        return self.grammar_correct and self.spelling_correct
