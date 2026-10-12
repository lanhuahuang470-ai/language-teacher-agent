"""测试 MCP Server + Client 连接是否正常。"""

from language_tutor.mcp_client import get_teaching_tools


def main():
    print("正在连接 MCP Server，加载工具...")
    tools = get_teaching_tools()

    print(f"\n加载到 {len(tools)} 个工具：")
    for t in tools:
        print(f"  - {t.name}")

    # 测试调用一个不需要数据库的工具
    print("\n测试 get_curriculum 调用...")
    result = tools[2].invoke(
        {"cefr_level": "A1"}, config={"configurable": {"student_id": "test_stu"}}
    )
    print(f"结果: {result}")

    print("\n✅ MCP 连接测试通过！")


if __name__ == "__main__":
    main()
