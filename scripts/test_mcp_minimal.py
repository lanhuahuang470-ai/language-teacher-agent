"""最小化 MCP 连接测试 v4：打印 Server stderr 方便调试。"""

import asyncio
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "language_tutor.mcp_server"],
    )

    print("正在连接 MCP Server...", flush=True)

    try:
        async with stdio_client(server_params) as streams:
            read_stream, write_stream = streams
            print(
                f"已连接，类型: read={type(read_stream).__name__}, write={type(write_stream).__name__}",
                flush=True,
            )

            async with ClientSession(read_stream, write_stream) as session:
                print("Session 创建，初始化中...", flush=True)
                init_result = await asyncio.wait_for(session.initialize(), timeout=30)
                print(f"✅ 初始化成功，Server：{init_result.serverInfo.name}", flush=True)

                tools_result = await session.list_tools()
                print(f"\n📋 可用工具（{len(tools_result.tools)} 个）：", flush=True)
                for t in tools_result.tools:
                    print(f"  - {t.name}", flush=True)

                print("\n🧪 测试调用 get_curriculum...", flush=True)
                call_result = await session.call_tool("get_curriculum", {"cefr_level": "A1"})
                for content in call_result.content:
                    if hasattr(content, "text"):
                        print(f"   结果：{content.text}", flush=True)

                print("\n🎉 全部测试通过！", flush=True)
    except Exception as e:
        print(f"\n❌ 出错了: {type(e).__name__}: {e}", flush=True)
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
