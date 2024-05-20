from tenacity import retry, wait_random_exponential, stop_after_attempt
import httpx
import os

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')


@retry(wait=wait_random_exponential(multiplier=1, max=40), stop=stop_after_attempt(3))
async def claude_chat_completion_request(messages, tools=None, tool_choice=None, model="claude-3-opus-20240229"):
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    json_data = {"model": model, "messages": messages, "max_tokens": 1024}
    if tools is not None:
        json_data.update({"tools": tools})
    if tool_choice is not None:
        json_data.update({"tool_choice": tool_choice})

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=json_data,
                timeout=30, 
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