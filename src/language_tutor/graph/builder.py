# 图的组装：拓扑即流程，LLM 只管内容
#
# 拓扑：START → init_session → (路由) → tutor → END
#                                  ↙ assessor → tutor
from langgraph.graph import END, START, StateGraph

from language_tutor.domain.learning_policy import stale_answer
from language_tutor.graph.nodes import assessor, init_session, tutor
from language_tutor.graph.state import TutorState


def route_by_pending(state: TutorState) -> str:
    """只有答题事件进入评估；开始、提示、解释和跳过由教学节点处理。"""
    if (
        state.get("pending_exercise")
        and state.get("input_event", "answer") == "answer"
        and not stale_answer(state)
    ):
        return "assessor"
    return "tutor"


def build_graph(*, checkpointer):
    """Compile the state graph with an explicit checkpointer."""
    g = StateGraph(TutorState)
    g.add_node("init_session", init_session.run)
    g.add_node("tutor", tutor.run)
    g.add_node("assessor", assessor.run)

    g.add_edge(START, "init_session")
    g.add_conditional_edges(
        "init_session",
        route_by_pending,
        {"tutor": "tutor", "assessor": "assessor"},
    )
    g.add_edge("assessor", "tutor")
    g.add_edge("tutor", END)

    return g.compile(checkpointer=checkpointer)
