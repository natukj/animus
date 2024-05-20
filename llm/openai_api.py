from tenacity import retry, wait_random_exponential, stop_after_attempt
import httpx
import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

@retry(wait=wait_random_exponential(multiplier=1, max=40), stop=stop_after_attempt(3))
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

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=json_data,
                timeout=60,
            )
            response.raise_for_status()
            return response.json()
        except httpx.ReadTimeout as e:
            print("Request timed out")
            print(f"Exception: {e}")
            return None
        except httpx.HTTPStatusError as e:
            print(f"Request failed with status code: {e.response.status_code}")
            print(f"Exception: {e}")
            return None
        except Exception as e:
            print("Unable to generate ChatCompletion response")
            print(f"Exception: {e}")
            return None
