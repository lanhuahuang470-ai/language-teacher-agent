"""MCP Client 封装：连接 MCP Server，把工具转成 LangChain 能用的格式。

使用 mcp SDK 原生 Client（stdio 传输），手动转换为 LangChain StructuredTool。
不依赖 langchain-mcp-adapters，避免版本兼容问题。

核心设计：
- MCP 工具本身有 student_id 参数
- 但模型不能看到/修改 student_id
- 所以包装一层，从 RunnableConfig 里取 student_id 自动注入
"""

from __future__ import annotations

import asyncio
import sys
from functools import lru_cache
from typing import Any, List

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from pydantic import BaseModel, Field

# ── MCP Server 连接配置 ──────────────────────────────────────
# stdio 模式：启动一个子进程跑 MCP Server，通过标准输入输出通信
# 用 sys.executable 保证和当前进程用同一个 Python 环境
_SERVER_PARAMS = StdioServerParameters(
    command=sys.executable,
    args=["-m", "language_tutor.mcp_server"],
)


# ── 加载工具元数据 ──────────────────────────────────────────


async def _load_tool_schemas_async() -> List[dict]:
    """异步连接 MCP Server，加载所有工具的元数据（name/description/inputSchema）。"""
    async with stdio_client(_SERVER_PARAMS) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            return [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema,
                }
                for t in result.tools
            ]


@lru_cache(maxsize=1)
def _get_tool_schemas() -> List[dict]:
    """同步获取所有 MCP 工具的元数据（缓存一次）。

    首次调用会阻塞（要等 MCP Server 子进程启动并列出工具）。
    """
    return asyncio.run(_load_tool_schemas_async())


# ── 调用工具（每次调用建立新连接） ─────────────────────────────


async def _call_tool_async(tool_name: str, arguments: dict) -> str:
    """异步调用 MCP 工具，返回文本结果。

    每次调用创建新的 stdio 连接（简单可靠，适合低频工具调用）。
    """
    async with stdio_client(_SERVER_PARAMS) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            # 从 content 数组中提取文本
            parts: List[str] = []
            for content in result.content:
                if hasattr(content, "text"):
                    parts.append(content.text)
                elif isinstance(content, dict) and "text" in content:
                    parts.append(content["text"])
            return "\n".join(parts) if parts else str(result.content)


def _call_tool(tool_name: str, arguments: dict) -> str:
    """同步调用 MCP 工具。"""
    return asyncio.run(_call_tool_async(tool_name, arguments))


# ── 工具包装：隐藏 student_id + 转 LangChain 工具 ─────────────


def _schema_to_pydantic(name: str, input_schema: dict) -> type[BaseModel]:
    """把 MCP 的 inputSchema（JSON Schema）转成 Pydantic 模型。"""
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    annotations: dict[str, Any] = {}
    fields: dict[str, Any] = {}

    type_map = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }

    for prop_name, prop_schema in properties.items():
        if prop_name == "student_id":
            continue  # 去掉学生身份字段，模型看不到
        prop_type = prop_schema.get("type", "string")
        python_type = type_map.get(prop_type, str)
        annotations[prop_name] = python_type
        if prop_name in required:
            fields[prop_name] = Field(..., description=prop_schema.get("description", ""))
        else:
            default = prop_schema.get("default", None)
            fields[prop_name] = Field(
                default=default, description=prop_schema.get("description", "")
            )

    PydanticModel = type(
        f"{name.capitalize()}Input",
        (BaseModel,),
        {"__annotations__": annotations, **fields},
    )
    return PydanticModel


def _wrap_tool(tool_meta: dict) -> BaseTool:
    """把 MCP 工具元数据包装成 LangChain StructuredTool：
    1. 从输入 schema 中移除 student_id 字段（模型看不到）
    2. 调用时从 RunnableConfig 取出 student_id，自动注入
    """
    name = tool_meta["name"]
    description = tool_meta["description"]
    input_schema = tool_meta["input_schema"]

    WrappedInput = _schema_to_pydantic(name, input_schema)

    def _wrapped(config: RunnableConfig, **kwargs) -> str:
        student_id = config.get("configurable", {}).get("student_id")
        if not isinstance(student_id, str) or not student_id.strip():
            raise ValueError("工具调用缺少学生身份")
        kwargs["student_id"] = student_id
        return _call_tool(name, kwargs)

    return StructuredTool(
        name=name,
        description=description,
        func=_wrapped,
        args_schema=WrappedInput,
        handle_tool_error=True,
    )


# ── 对外接口：按名称取工具 ────────────────────────────────────


def get_tools(names: List[str]) -> List[BaseTool]:
    """按名称获取包装好的工具列表。

    Args:
        names: 工具名列表，如 ["get_mastery", "get_curriculum"]
    """
    tool_schemas = _get_tool_schemas()
    name_map = {t["name"]: t for t in tool_schemas}

    result = []
    for name in names:
        if name not in name_map:
            available = ", ".join(sorted(name_map.keys()))
            raise ValueError(f"工具 '{name}' 不存在。可用工具：{available}")
        result.append(_wrap_tool(name_map[name]))
    return result


# ── 三个 Agent 的工具子集 ────────────────────────────────────

# 规划 Agent 用的工具
PLANNING_TOOL_NAMES = [
    "get_weak_points",
    "get_curriculum",
    "get_error_summary",
    "get_kp_dependencies",
]

# 教学 Agent 用的工具
TEACHING_TOOL_NAMES = [
    "get_mastery",
    "get_weak_points",
    "get_curriculum",
    "get_error_history",
    "get_similar_errors",
]

# 评估 Agent 用的工具
ASSESSMENT_TOOL_NAMES = [
    "get_error_history",
    "get_similar_errors",
]


def get_planning_tools() -> List[BaseTool]:
    """获取规划 Agent 的工具集（从 MCP Server 加载）。"""
    return get_tools(PLANNING_TOOL_NAMES)


def get_teaching_tools() -> List[BaseTool]:
    """获取教学 Agent 的工具集（从 MCP Server 加载）。"""
    return get_tools(TEACHING_TOOL_NAMES)


def get_assessment_tools() -> List[BaseTool]:
    """获取评估 Agent 的工具集（从 MCP Server 加载）。"""
    return get_tools(ASSESSMENT_TOOL_NAMES)
