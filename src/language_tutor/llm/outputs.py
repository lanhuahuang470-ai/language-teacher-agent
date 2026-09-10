"""Validate model responses before they reach graph state or persistence."""

from __future__ import annotations

import json
import logging
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, computed_field, model_validator

from language_tutor.llm.json_utils import extract_json
from language_tutor.telemetry import emit

logger = logging.getLogger(__name__)
Output = TypeVar("Output", bound=BaseModel)


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TeachingOutput(ResponseModel):
    """Schema for tutor agent responses: reply text and exercise text."""

    model_config = ConfigDict(
        extra="ignore", str_strip_whitespace=True
    )  # Ignore harmless extra metadata; required fields remain validated.
    reply: str = Field(min_length=1)
    exercise: str = Field(
        min_length=1, description="完整题目文本字符串，含选项（如有）；不能是对象、数组或 null"
    )


class PlanningOutput(ResponseModel):
    plan: list[str] = Field(min_length=1, max_length=4)
    focus: str = Field(default="mixed", description="review/mixed/new，表示本次重点")
    reason: str = ""


class AssessmentOutput(ResponseModel):
    """Schema for assessment agent responses: grammar, spelling, score, and feedback.

    评分分两层：
    - grammar_correct：语法结构是否正确（决定课程推进和错题保存）
    - spelling_correct：拼写是否正确（只影响反馈，不影响推进）
    - is_correct（计算属性）：语法且拼写都正确，向后兼容
    """

    grammar_correct: bool = Field(strict=True)
    spelling_correct: bool = Field(default=True, strict=True)
    score: float = Field(ge=0, le=1, allow_inf_nan=False, strict=True)
    error_types: list[str] = Field(default_factory=list)
    feedback_hint: str = Field(min_length=1)
    correct_answer: str = Field(min_length=1)

    @computed_field  # type: ignore[misc]
    @property
    def is_correct(self) -> bool:
        """语法和拼写都正确才算完全正确。"""
        return self.grammar_correct and self.spelling_correct

    @model_validator(mode="after")
    def consistent_grade(self):
        # 完全正确（语法+拼写）时 score 必须为 1
        if self.is_correct != (self.score == 1):
            raise ValueError("完全正确时 score 必须为 1，否则必须小于 1")
        if self.is_correct and self.error_types:
            raise ValueError("完全正确时 error_types 必须为空")
        # 语法错误时 error_types 不能为空（拼写错误可以单独出现）
        if not self.grammar_correct and not self.error_types:
            raise ValueError("语法错误时 error_types 不能为空")
        return self


class ModelOutputError(ValueError):
    """A bounded repair failed; safe details can be displayed without response content."""


def _issues(exc, schema):
    if isinstance(exc, ValidationError):
        return [
            {
                "field": str(error["loc"][0])
                if error["loc"] and error["loc"][0] in schema.model_fields
                else "$",
                "type": error["type"],
            }
            for error in exc.errors(include_input=False, include_context=False, include_url=False)
        ][:8]
    return [{"field": "$", "type": "invalid_json_or_message"}]


def _response_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            block["text"]
            for block in content
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ]
        if texts:
            return "".join(texts)
    raise ValueError("模型回复不包含文本")


def invoke_validated(agent, messages: list, schema: type[Output], student_id: str) -> Output:
    """Retry malformed output once; never manufacture a grade after failure."""
    config = {"configurable": {"student_id": student_id}, "recursion_limit": 12}
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    request_messages = list(messages)
    request_messages.append(
        (
            "user",
            "最终回复必须是符合以下 JSON Schema 的单个对象。"
            "字符串中的换行用反斜杠 n 转义，不要改变字段类型。\n" + schema_json,
        )
    )
    for attempt in range(2):
        result = agent.invoke({"messages": request_messages}, config=config)
        usages = [getattr(msg, "usage_metadata", None) or {} for msg in result.get("messages", [])]
        emit(
            "agent_completed",
            schema=schema.__name__,
            attempt=attempt + 1,
            input_tokens=sum(usage.get("input_tokens", 0) for usage in usages)
            if any(usages)
            else None,
            output_tokens=sum(usage.get("output_tokens", 0) for usage in usages)
            if any(usages)
            else None,
            tool_calls=sum(
                len(getattr(msg, "tool_calls", []) or []) for msg in result.get("messages", [])
            ),
        )
        raw = ""
        try:
            raw = _response_text(result["messages"][-1].content)
            return schema.model_validate(extract_json(raw))
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            issues = _issues(exc, schema)
            logger.warning(
                "model_output_invalid schema=%s attempt=%s issues=%s",
                schema.__name__,
                attempt + 1,
                json.dumps(issues),
            )
            if attempt:
                # 翻译技术字段名为用户可读的中文说明
                field_map = {
                    "reply": "回复内容",
                    "exercise": "题目",
                    "grammar_correct": "语法判定",
                    "spelling_correct": "拼写判定",
                    "score": "评分",
                    "is_correct": "判定结果",
                    "correct_answer": "正确答案",
                    "feedback_hint": "反馈要点",
                    "error_types": "错误类型",
                    "plan": "学习计划",
                    "focus": "学习重点",
                    "$": "整体格式",
                }
                type_map = {
                    "missing": "缺失",
                    "string_too_short": "内容为空",
                    "string_too_long": "内容过长",
                    "string_type": "类型错误",
                    "value_error": "值不合法",
                    "bool_parsing": "应为布尔值",
                    "float_parsing": "应为数值",
                    "list_type": "应为列表",
                    "extra_forbidden": "包含多余字段",
                    "invalid_json_or_message": "无法解析为 JSON",
                }
                parts = []
                for item in issues:
                    f = field_map.get(item["field"], item["field"])
                    t = type_map.get(item["type"], item["type"])
                    parts.append(f"{f}：{t}")
                raise ModelOutputError(
                    "AI 回复格式有误（" + "，".join(parts) + "），本轮未能完成。"
                    "请直接重新发送上一次的答案或点击「开始上课」重试。"
                ) from None
            # Show the actual invalid response and precise errors, not just the original task again.
            if raw:
                request_messages.append(("assistant", raw))
            request_messages.append(
                (
                    "user",
                    "上一条回复未通过校验，错误如下："
                    + json.dumps(issues, ensure_ascii=False)
                    + "。请修复上一条回复，保留教学内容；不要调用工具，不要添加解释。"
                    + (
                        "exercise 必须是完整题目字符串（含选项），不能是对象、数组或 null。"
                        if schema is TeachingOutput
                        else ""
                    )
                    + "不要猜测或省略必填字段。只输出符合以下 Schema 的 JSON：\n"
                    + schema_json,
                )
            )
    raise AssertionError("unreachable")
