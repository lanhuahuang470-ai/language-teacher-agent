"""Model factories: importing modules never initializes API clients."""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from language_tutor import config


@lru_cache(maxsize=1)
def get_tutor_llm():
    return _client(0.7)


@lru_cache(maxsize=1)
def get_assessor_llm():
    return _client(0)


def _client(temperature: float) -> ChatOpenAI:
    if not config.DEEPSEEK_API_KEY:
        raise ValueError("缺少 DEEPSEEK_API_KEY，请检查环境配置")
    return ChatOpenAI(
        model=config.LLM_MODEL,
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        temperature=temperature,
        timeout=config.LLM_TIMEOUT_SECONDS,
        max_tokens=config.LLM_MAX_OUTPUT_TOKENS,
    )
