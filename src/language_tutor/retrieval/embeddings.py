from langchain_core.embeddings import Embeddings

from language_tutor import config


class DashScopeEmbeddings(Embeddings):
    def __init__(self):
        from openai import OpenAI

        self.client = OpenAI(
            api_key=config.DASHSCOPE_API_KEY,
            base_url=config.DASHSCOPE_BASE_URL,
            timeout=15,
            max_retries=1,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            input=texts, model=config.EMBEDDING_MODEL, encoding_format="float"
        )
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string and return the first vector."""
        return self.embed_documents([text])[0]
