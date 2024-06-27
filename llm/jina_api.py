from tenacity import retry, wait_random_exponential, stop_after_attempt, retry_if_exception_type
import httpx
import os
import json
JINA_API_KEY = os.getenv("JINA_API_KEY")

@retry(
    wait=wait_random_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type((Exception)),
    before_sleep=lambda retry_state: print(f"Retrying attempt {retry_state.attempt_number} for reranking request...")
)
async def rerank_documents(query: str, documents: list[str], top_n: int = 3):
    url = "https://api.jina.ai/v1/rerank"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {JINA_API_KEY}",
    }
    data = {
        "model": "jina-reranker-v2-base-multilingual",
        "query": query,
        "documents": documents,
        "top_n": top_n
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data, timeout=30)
            return response.json()
        except httpx.ReadTimeout as e:
            print(f"Jina HTTPX ReadTimeout: {e}")
            raise
        except httpx.HTTPStatusError as e:
            print(f"Jina HTTPX HTTPStatusError: {e}")
            raise
        except httpx.RequestError as e:
            print(f"Jina HTTPX RequestError: {e}")
            raise
        except httpx.HTTPError as e:
            print(f"Jina HTTPX HTTPError: {e}")
            raise
        except Exception as e:
            print(f"Jina HTTPX Exception: {e}")
            raise