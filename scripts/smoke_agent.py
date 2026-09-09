"""Live API smoke test. Run explicitly; not part of the offline pytest suite."""

from language_tutor.agents.tutor_agent import get_tutor_agent


def main():
    request = {
        "messages": [("user", "请讲解 A1 等级的 be动词，并出一道练习题。先查当前学生的掌握度。")]
    }
    config = {"configurable": {"student_id": "test_agent_user"}, "recursion_limit": 12}
    final = None
    seen = set()
    tool_calls = []
    # values gives the complete current state; reuse the final state instead of invoking twice.
    for event in get_tutor_agent().stream(request, config=config, stream_mode="values"):
        final = event
        for message in event.get("messages", []):
            key = message.id or id(message)
            if key in seen:
                continue
            seen.add(key)
            for call in getattr(message, "tool_calls", []):
                tool_calls.append(call["name"])
                print(f"工具调用：{call['name']}")
    if final is None:
        raise RuntimeError("Agent 未返回结果")
    print(final["messages"][-1].content)
    print(f"调用过的工具：{tool_calls}")


if __name__ == "__main__":
    main()
