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


def validate_runtime():
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
