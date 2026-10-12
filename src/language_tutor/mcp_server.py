"""教学工具 MCP Server。

使用 mcp SDK 自带的 FastMCP（mcp.server.fastmcp）实现，
不依赖第三方 fastmcp 包，避免版本兼容问题。

将原来 agents/tools.py 中的 7 个 LangChain 工具封装为 MCP 服务，
实现 Agent 编排层与业务工具层解耦。

工具按权限分为三组：
- 规划工具：get_weak_points / get_curriculum / get_error_summary / get_kp_dependencies
- 教学工具：get_mastery / get_weak_points / get_curriculum / get_error_history / get_similar_errors
- 评估工具：get_error_history / get_similar_errors

学生身份通过 student_id 参数显式传递。
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from language_tutor.db.crud import get_error_summary as _get_error_summary
from language_tutor.db.crud import get_errors_by_kp, get_mastery_map
from language_tutor.db.engine import SessionLocal
from language_tutor.domain.curriculum import CURRICULUM, KP_DEPENDENCIES
from language_tutor.retrieval.error_store import search_similar_errors

mcp = FastMCP("language-tutor-tools")


# ── 掌握度工具 ──────────────────────────────────────────────


@mcp.tool()
def get_mastery(knowledge_point: str, student_id: str) -> str:
    """查询学生对某个知识点的掌握度（0~1）。

    返回示例：'be动词 的掌握度：0.85' 或 'be动词：暂无记录'。
    用于决定是否需要复习还是可以推进新知识点。
    """
    with SessionLocal() as session:
        mastery = get_mastery_map(session, student_id)
    score = mastery.get(knowledge_point)
    if score is None:
        return f"{knowledge_point}：暂无记录，可能是新知识点"
    return f"{knowledge_point} 的掌握度：{score:.2f}"


@mcp.tool()
def get_weak_points(student_id: str) -> str:
    """查询学生最薄弱的知识点（掌握度最低的 3 个）。

    返回示例：'最薄弱的知识点：一般过去时(0.20), be动词(0.45), 主谓一致(0.60)'。
    用于决定复习重点。如果没有任何记录，返回提示。
    """
    with SessionLocal() as session:
        mastery = get_mastery_map(session, student_id)
    if not mastery:
        return "暂无学习记录，建议从课程第一个知识点开始"
    sorted_items = sorted(mastery.items(), key=lambda x: x[1])
    weak = [f"{kp}({score:.2f})" for kp, score in sorted_items[:3]]
    return f"最薄弱的知识点：{', '.join(weak)}"


# ── 课程工具 ────────────────────────────────────────────────


@mcp.tool()
def get_curriculum(cefr_level: str) -> str:
    """查询某个等级的课程知识点清单。

    返回示例：'A1 课程：be动词, 一般现在时, there be句型, 人称代词'。
    用于了解当前等级要学的所有知识点。
    """
    plan = CURRICULUM.get(cefr_level, CURRICULUM["A1"])
    return f"{cefr_level} 课程：{', '.join(plan)}"


@mcp.tool()
def get_kp_dependencies(knowledge_point: str) -> str:
    """查询学习某知识点前应先掌握的前置知识点。

    返回示例：'一般过去时的前置知识点：一般现在时' 或 '人称代词无前置依赖'。
    用于规划 Agent 判断是否需要先复习前置知识点。
    """
    deps = KP_DEPENDENCIES.get(knowledge_point, [])
    if not deps:
        return f"{knowledge_point}无前置依赖，可以直接学习"
    return f"{knowledge_point}的前置知识点：{', '.join(deps)}"


# ── 错题工具 ────────────────────────────────────────────────


@mcp.tool()
def get_error_history(knowledge_point: str, student_id: str) -> str:
    """查询学生在某个知识点上的历史错题（SQL 精确查询）。

    返回最近的 5 条错题，包括错句和正确形式。
    用于了解学生的典型错误模式，针对性出题。
    """
    with SessionLocal() as session:
        errors = get_errors_by_kp(session, student_id, knowledge_point)
    if not errors:
        return f"学生在「{knowledge_point}」上暂无错题记录"
    lines = [f"「{knowledge_point}」最近 {len(errors)} 条错题："]
    for e in errors[:5]:
        lines.append(
            f"  - 错句：{e.error_sentence} → 正确：{e.correct_form}（错误类型：{e.error_types}）"
        )
    return "\n".join(lines)


@mcp.tool()
def get_similar_errors(student_sentence: str, student_id: str) -> str:
    """通过语义相似度检索历史错题（RAG 向量检索）。

    输入学生当前写的句子，返回语义最相似的 3 条历史错句。
    用于发现"用词不同但错误模式相同"的重复犯错。
    例如学生写 'He don't like it'，能匹配到历史错句 'She doesn't likes it'。
    """
    results = search_similar_errors(student_sentence, student_id=student_id, k=3)
    if not results:
        return "暂无相似错题记录"
    lines = ["语义相似的历史错题："]
    for r in results:
        lines.append(
            f"  - 错句：{r['sentence']} → 正确：{r['correct']} "
            f"（知识点：{r['knowledge_point']}，错误类型：{r['error_types']}，"
            f"相似度：{r['score']:.2f}）"
        )
    return "\n".join(lines)


@mcp.tool()
def get_error_summary(student_id: str) -> str:
    """聚合统计学生在每个知识点上的错题数量和错误类型。

    含已解决/未解决分类。
    返回示例：'一般过去时: 3条(未解决2/已解决1), 类型: 时态混淆/主谓一致; be动词: 1条(未解决1), 类型: 拼写'
    用于规划 Agent 分析学生的典型错误模式。
    """
    with SessionLocal() as session:
        summary = _get_error_summary(session, student_id)
    if not summary:
        return "暂无错题记录"
    parts = []
    for item in summary:
        types = "/".join(item["error_types"]) if item["error_types"] else "无"
        parts.append(
            f"{item['knowledge_point']}: {item['count']}条"
            f"(未解决{item['unresolved']}/已解决{item['resolved']}), 类型: {types}"
        )
    return "; ".join(parts)


def main() -> None:
    """启动 MCP Server（stdio 传输）。"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
