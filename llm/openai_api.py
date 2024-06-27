from tenacity import retry, wait_random_exponential, stop_after_attempt, retry_if_exception_type
import httpx
import os
import ssl
import openai
from openai import AsyncOpenAI
client = AsyncOpenAI()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

@retry(
    wait=wait_random_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type((Exception)),
    before_sleep=lambda retry_state: print(f"Retrying attempt {retry_state.attempt_number} for OAI completion request...")
)
async def openai_client_chat_completion_request(messages, model="gpt-4o", temperature=0.4, response_format="json_object"):
    # if i don't use this i get Exception: [SSL: SSLV3_ALERT_BAD_RECORD_MAC] sslv3 alert bad record mac (_ssl.c:2580) randomly
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={ "type": response_format },
            temperature=temperature
        )
        return response
    except openai.APIError as e:
        print(f"OpenAI API Error: {e}")
        raise

@retry(
    wait=wait_random_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type((Exception)),
    before_sleep=lambda retry_state: print(f"Retrying attempt {retry_state.attempt_number} for embedding request...")
)
async def openai_client_embedding_request(text, model="text-embedding-3-small"):
    text = text.replace("\n", " ")
    try:
        response = await client.embeddings.create(input = [text], model=model)
        return response.data[0].embedding
    except openai.APIError as e:
        print(f"OpenAI Embedding API Error: {e}")
        raise


@retry(wait=wait_random_exponential(multiplier=1, max=40), stop=stop_after_attempt(3),
    retry=retry_if_exception_type(ssl.SSLError))
async def openai_chat_completion_request(messages, model="gpt-4o", temperature=0.4, tools=None, tool_choice=None, response_format="text"):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }
    json_data = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }

    if response_format == "json":
        json_data["response_format"] = {"type": "json_object"}

    if tools is not None:
        json_data["tools"] = tools

    if tool_choice is not None:
        json_data["tool_choice"] = tool_choice

    async with httpx.AsyncClient(verify=False) as client:
        try:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=json_data,
                timeout=300,
            )
            response.raise_for_status()
            return response.json()
        except httpx.ReadTimeout as e:
            print("Request timed out")
            print(f"Exception: {e}")
            raise
        except httpx.HTTPStatusError as e:
            print(f"Request failed with status code: {e.response.status_code}")
            print(f"Exception: {e}")
            raise
        except ssl.SSLError as e:
            print("SSL Error occurred")
            print(f"Exception: {e}")
            raise 
        except Exception as e:
            print("Unable to generate ChatCompletion response")
            print(f"Exception: {e}")
            raise
