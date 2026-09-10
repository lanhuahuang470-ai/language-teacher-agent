# 教学 Agent 的工具集：每个工具是一个 SQL 查询或向量检索的封装
#
# Agent 自主决定调哪个工具、什么时机调——这就是"agent"和"固定流程"的区别
# 工具返回的是字符串（不是对象），因为 LLM 需要读懂返回值来决策
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from language_tutor.agents.error_rag import search_similar_errors
from language_tutor.db.crud import get_error_summary as _get_error_summary
from language_tutor.db.crud import get_errors_by_kp, get_mastery_map
from language_tutor.db.engine import SessionLocal
from language_tutor.domain.curriculum import CURRICULUM, KP_DEPENDENCIES


def _student_id(config: RunnableConfig) -> str:
    student_id = config.get("configurable", {}).get("student_id")
    if not isinstance(student_id, str) or not student_id.strip():
        raise ValueError("工具调用缺少学生身份")
    return student_id


# 知识掌握度
@tool
def get_mastery(knowledge_point: str, config: RunnableConfig) -> str:
    """查询学生对某个知识点的掌握度（0~1）。
    返回示例：'be动词 的掌握度：0.85' 或 'be动词：暂无记录'。
    用于决定是否需要复习还是可以推进新知识点。"""
    with SessionLocal() as session:
        mastery = get_mastery_map(session, _student_id(config))
    score = mastery.get(knowledge_point)
    if score is None:
        return f"{knowledge_point}：暂无记录，可能是新知识点"
    return f"{knowledge_point} 的掌握度：{score:.2f}"


# 知识薄弱点
@tool
def get_weak_points(config: RunnableConfig) -> str:
    """查询学生最薄弱的知识点（掌握度最低的 3 个）。
    返回示例：'最薄弱的知识点：一般过去时(0.20), be动词(0.45), 主谓一致(0.60)'。
    用于决定复习重点。如果没有任何记录，返回提示。"""
    with SessionLocal() as session:
        mastery = get_mastery_map(session, _student_id(config))
    if not mastery:
        return "暂无学习记录，建议从课程第一个知识点开始"
    # 按掌握度升序，取最薄弱的 3 个
    sorted_items = sorted(mastery.items(), key=lambda x: x[1])
    weak = [f"{kp}({score:.2f})" for kp, score in sorted_items[:3]]
    return f"最薄弱的知识点：{', '.join(weak)}"


# 课程等级的知识点清单
@tool
def get_curriculum(cefr_level: str) -> str:
    """查询某个等级的课程知识点清单。
    返回示例：'A1 课程：be动词, 一般现在时, there be句型, 人称代词'。
    用于了解当前等级要学的所有知识点。"""
    plan = CURRICULUM.get(cefr_level, CURRICULUM["A1"])
    return f"{cefr_level} 课程：{', '.join(plan)}"


# 最近五条错题
@tool
def get_error_history(knowledge_point: str, config: RunnableConfig) -> str:
    """查询学生在某个知识点上的历史错题（SQL 精确查询）。
    返回最近的 5 条错题，包括错句和正确形式。
    用于了解学生的典型错误模式，针对性出题。"""
    with SessionLocal() as session:
        errors = get_errors_by_kp(session, _student_id(config), knowledge_point)
    if not errors:
        return f"学生在「{knowledge_point}」上暂无错题记录"
    lines = [f"「{knowledge_point}」最近 {len(errors)} 条错题："]
    for e in errors[:5]:
        lines.append(
            f"  - 错句：{e.error_sentence} → 正确：{e.correct_form}（错误类型：{e.error_types}）"
        )
    return "\n".join(lines)


# 相近错题
@tool
def get_similar_errors(student_sentence: str, config: RunnableConfig) -> str:
    """通过语义相似度检索历史错题（RAG 向量检索）。
    输入学生当前写的句子，返回语义最相似的 3 条历史错句。
    用于发现"用词不同但错误模式相同"的重复犯错。
    例如学生写 'He don't like it'，能匹配到历史错句 'She doesn't likes it'。"""
    results = search_similar_errors(student_sentence, student_id=_student_id(config), k=3)
    if not results:
        return "暂无相似错题记录"
    lines = ["语义相似的历史错题："]
    for r in results:
        lines.append(
            f"  - 错句：{r['sentence']} → 正确：{r['correct']} "
            f"（知识点：{r['knowledge_point']}，错误类型：{r['error_types']}，相似度：{r['score']:.2f}）"
        )
    return "\n".join(lines)


# 错题类型聚合统计（规划 Agent 专用）
@tool
def get_error_summary(config: RunnableConfig) -> str:
    """聚合统计学生在每个知识点上的错题数量和错误类型（含已解决/未解决分类）。
    返回示例：'一般过去时: 3条(未解决2/已解决1), 类型: 时态混淆/主谓一致; be动词: 1条(未解决1), 类型: 拼写'
    用于规划 Agent 分析学生的典型错误模式，已解决的知识点可以跳过或快速过。"""
    with SessionLocal() as session:
        summary = _get_error_summary(session, _student_id(config))
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


# 知识点前置依赖（规划 Agent 专用）
@tool
def get_kp_dependencies(knowledge_point: str) -> str:
    """查询学习某知识点前应先掌握的前置知识点。
    返回示例：'一般过去时的前置知识点：一般现在时' 或 '人称代词无前置依赖'。
    用于规划 Agent 判断是否需要先复习前置知识点。"""
    deps = KP_DEPENDENCIES.get(knowledge_point, [])
    if not deps:
        return f"{knowledge_point}无前置依赖，可以直接学习"
    return f"{knowledge_point}的前置知识点：{', '.join(deps)}"


ALL_TOOLS = [get_mastery, get_weak_points, get_curriculum, get_error_history, get_similar_errors]
