"""规划 Agent：分析学生掌握度、错题模式和知识点依赖，生成个性化学习计划。

与教学 Agent 的区别：
  教学 Agent 负责"怎么教"（讲解+出题+反馈）
  规划 Agent 负责"教什么"（知识点选择+顺序+复习 vs 新学）

工具来源：
- 默认从 MCP Server 加载（USE_MCP_TOOLS=true）
- 测试/离线环境 fallback 到本地 LangChain 工具

专属工具：get_weak_points / get_curriculum / get_error_summary / get_kp_dependencies
不直接看具体错句内容——规划只看聚合统计，不关心个别错句。
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.prebuilt import create_react_agent

from language_tutor import config
from language_tutor.agents.tools import (
    get_curriculum,
    get_error_summary,
    get_kp_dependencies,
    get_weak_points,
)
from language_tutor.llm.client import get_assessor_llm  # 规划用低温度，要稳定

PLANNING_PROMPT = """你是一个英语学习路径规划师，负责为学生制定个性化学习计划。

你的职责：
1. 分析学生的掌握度和错题模式，找出薄弱知识点和反复犯的错误类型
2. 检查知识点之间的依赖关系，确保前置知识点已掌握
3. 综合以上信息，决定本次会话教哪些知识点、什么顺序

你可以使用以下工具：
- get_weak_points：查最薄弱的知识点（掌握度最低的）
- get_curriculum：查当前等级的课程清单
- get_error_summary：查学生在每个知识点上的错题数量和错误类型聚合统计
- get_kp_dependencies：查某知识点的前置依赖知识点

规划策略（按优先级从高到低）：
1. 【前置依赖检查】如果要教的知识点有前置依赖，先查前置知识点的掌握度。
   如果前置知识点掌握度 < 0.6，必须先把前置知识点放进计划里复习。
2. 【错题模式分析】查看错题聚合统计，如果某知识点反复犯同类错误（3次以上），
   优先放入计划重点复习。
3. 【薄弱优先】掌握度 < 0.6 的知识点优先复习；掌握度 > 0.8 的可以跳过。
4. 【新旧搭配】一次会话 2-3 个知识点，建议 1-2 个复习 + 1 个新知识点。
5. 【顺序合理】复习的知识点放在新知识点前面，前置依赖放在后面之前。

你必须只输出一个 JSON 对象，格式如下：
{"plan": ["知识点1", "知识点2"], "focus": "review 或 mixed 或 new", "reason": "简要说明规划理由"}

focus 字段说明：
- "review"：全部是复习已有知识点
- "mixed"：复习 + 新知识点搭配
- "new"：全部是新知识点（学生当前等级已掌握较好的前提下）"""


def _get_local_planning_tools():
    """本地 LangChain 工具（测试 fallback）。"""
    return [get_weak_points, get_curriculum, get_error_summary, get_kp_dependencies]


# 兼容旧引用（测试用）：本地工具列表，工具 schema 不暴露 student_id
PLANNING_TOOLS = _get_local_planning_tools()


@lru_cache(maxsize=1)
def get_planning_agent():
    """Return a cached ReAct planning agent with analysis tools.

    工具来源：
    - USE_MCP_TOOLS=true 时从 MCP Server 加载
    - 否则使用本地 LangChain 工具（测试/离线环境）
    """
    if config.USE_MCP_TOOLS:
        from language_tutor.mcp_client import get_planning_tools

        tools = get_planning_tools()
    else:
        tools = _get_local_planning_tools()

    return create_react_agent(
        get_assessor_llm(),
        tools=tools,
        prompt=PLANNING_PROMPT,
    )
