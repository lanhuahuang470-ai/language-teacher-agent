from functools import lru_cache

# 规划 Agent：分析学生掌握度数据，生成个性化学习计划
#
# 与教学 Agent 的区别：
#   教学 Agent 负责讲解和出题（"执行"层面）
#   规划 Agent 负责决定教什么、复习什么（"策略"层面）
#
# 专属工具：get_mastery / get_weak_points / get_curriculum
# 不需要错题工具——规划只看掌握度数据，不关心具体错句内容
from langgraph.prebuilt import create_react_agent

from language_tutor.agents.tools import get_curriculum, get_mastery, get_weak_points
from language_tutor.llm.client import get_assessor_llm  # 规划用低温度，要稳定

PLANNING_TOOLS = [get_mastery, get_weak_points, get_curriculum]

PLANNING_PROMPT = """你是一个英语学习路径规划师，负责为学生制定个性化学习计划。

你的职责：
1. 分析学生的掌握度数据，找出薄弱知识点
2. 根据学生等级和掌握度，决定本次会话的教学顺序
3. 如果学生有薄弱知识点，优先安排复习

你可以使用以下工具：
- get_mastery：查某个知识点的掌握度
- get_weak_points：查最薄弱的知识点（掌握度最低的）
- get_curriculum：查当前等级的课程清单

规划原则：
- 掌握度 < 0.6 的知识点优先复习
- 掌握度 > 0.8 的知识点可以跳过或快速过
- 新知识点放在复习之后
- 一次会话安排 2-3 个知识点

你必须只输出一个 JSON 对象，格式如下：
{"plan": ["知识点1", "知识点2"], "reason": "简要说明规划理由"}"""


# 规划 Agent：低温度 + 3 个分析工具
@lru_cache(maxsize=1)
def get_planning_agent():
    return create_react_agent(
        get_assessor_llm(),
        tools=PLANNING_TOOLS,
        prompt=PLANNING_PROMPT,
    )
