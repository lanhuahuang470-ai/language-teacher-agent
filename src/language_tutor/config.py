# 集中读取 .env。所有模块从这里取配置，不直接读环境变量 —— 便于统一校验和替换
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(os.getenv("LANGUAGE_TUTOR_ENV_FILE", str(Path(__file__).resolve().parents[1] / ".env")))

APP_ENVIRONMENT = os.getenv("APP_ENVIRONMENT", "development")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
LLM_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "2000"))

DATABASE_URL = os.getenv("DATABASE_URL", "")

# 阿里云 DashScope Embedding API（错题库向量检索用）
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")


def validate_runtime() -> None:
    """Raise ``ValueError`` when a required key is missing or a limit is non-positive."""
    required = {
        "DEEPSEEK_API_KEY": DEEPSEEK_API_KEY,
        "DATABASE_URL": DATABASE_URL,
        "DASHSCOPE_API_KEY": DASHSCOPE_API_KEY,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError("缺少配置：" + ", ".join(missing))
    if LLM_TIMEOUT_SECONDS <= 0 or LLM_MAX_OUTPUT_TOKENS <= 0:
        raise ValueError("超时和输出 token 上限必须为正数")


TUTOR_HOST = os.getenv("TUTOR_HOST", "127.0.0.1")
TUTOR_PORT = int(os.getenv("TUTOR_PORT", "7860"))

# —— 存储与内存控制 ——
# state.messages 上限：超过后只保留最近 N 条（防 checkpoint blob 膨胀）
# 40 条 ≈ 5 堂课，足够 LLM 看近期上下文（LLM 实际只读最近 8 条）
MAX_MESSAGES = int(os.getenv("MAX_MESSAGES", "40"))
# checkpoint 保留数量：每 thread 只保留最新 N 个（防 checkpoints 表膨胀）
# 5 个 ≈ 1-2 轮对话的节点快照，满足正常恢复和基本回滚调试
CHECKPOINT_KEEP = int(os.getenv("CHECKPOINT_KEEP", "5"))

# 后台索引线程每次处理的待嵌入任务数
# 5 条一次 API 调用，比逐条调用省 4 次网络往返
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "5"))

# —— MCP 工具服务 ——
# 是否通过 MCP Server 加载工具（true=走 MCP，false=直接用本地 LangChain 工具）
# 测试环境关闭，因为 MCP 子进程拿不到测试用的 SQLite 内存数据库
USE_MCP_TOOLS = os.getenv("USE_MCP_TOOLS", "true").lower() in ("1", "true", "yes")
