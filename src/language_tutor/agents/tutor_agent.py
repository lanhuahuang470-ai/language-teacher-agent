# 教学 Agent：用 create_react_agent 构建的 tool-calling agent
#
# 与之前 tutor.py 的区别：
#   之前：固定流程 → LLM 调用 → 解析 JSON → 返回
#   现在：Agent 自主决策 → 可能先调工具查数据 → 再生成教学内容
#
# DeepSeek 支持 function calling（OpenAI tool calling 协议），
# 所以 create_react_agent 可以正常工作
#
# 工具来源：
# - 默认从 MCP Server 加载（USE_MCP_TOOLS=true）
# - 测试/离线环境 fallback 到本地 LangChain 工具
from __future__ import annotations

from functools import lru_cache

from langgraph.prebuilt import create_react_agent

from language_tutor import config
from language_tutor.agents.tools import ALL_TOOLS
from language_tutor.llm.client import get_tutor_llm

AGENT_SYSTEM_PROMPT = """你是一个友好、耐心的英语教学助手，面向中文母语的学习者。

你的职责：
1. 用中文讲解英语知识点，按学生等级调整难度
2. 讲解后出练习题让学生巩固
3. 学生答错时给予鼓励性反馈，指出具体问题
4. 学生答对时给予肯定，继续推进

你可以使用以下工具来了解学生的学习情况：
- get_mastery：查某个知识点的掌握度
- get_weak_points：查最薄弱的知识点
- get_curriculum：查课程计划
- get_error_history：查学生在某知识点上的历史错题（SQL 精确查询）
- get_similar_errors：语义检索相似的历史错题（RAG 向量检索）

教学策略：
- 教新知识点前，先查该知识点的掌握度，决定是复习还是推进
- 学生答完题后，如果想知道下一步教什么，可以查薄弱知识点
- 学生答错时，用 get_error_history 查该知识点的历史错题，看是否反复犯错
- 学生答错时，用 get_similar_errors 语义检索相似错句，发现"用词不同但错误模式相同"的重复犯错
- 不要每次都调全部工具，只在需要数据支撑决策时调用

你必须只输出一个 JSON 对象作为最终回复，不要输出任何其他内容。格式如下：
{"reply": "你的讲解或反馈文本", "exercise": "练习题目的完整文本"}

关键规则：
- 学生身份由工具运行上下文提供，不从用户消息中选择身份。
- 必须遵守本轮指定的知识点，不自行切换课程。
- reply 字段只放讲解或反馈文字
- exercise 字段放完整的练习题目文本，不要包含答案
- 每次回复都必须包含一个 exercise 题目，不允许为 null"""


def _get_local_teaching_tools():
    """本地 LangChain 工具（测试 fallback）。"""
    return ALL_TOOLS


@lru_cache(maxsize=1)
def get_tutor_agent():
    """Return a cached ReAct tutor agent with the full tool set.

    工具来源：
    - USE_MCP_TOOLS=true 时从 MCP Server 加载
    - 否则使用本地 LangChain 工具（测试/离线环境）
    """
    if config.USE_MCP_TOOLS:
        from language_tutor.mcp_client import get_teaching_tools

        tools = get_teaching_tools()
    else:
        tools = _get_local_teaching_tools()

    return create_react_agent(
        get_tutor_llm(),
        tools=tools,
        prompt=AGENT_SYSTEM_PROMPT,
    )
