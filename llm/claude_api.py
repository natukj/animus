from tenacity import retry, wait_random_exponential, stop_after_attempt
import httpx
import os
from anthropic import AsyncAnthropic
client = AsyncAnthropic()
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

@retry(wait=wait_random_exponential(multiplier=1, max=40), stop=stop_after_attempt(3))
async def claude_client_chat_completion_request(messages, tools=None, tool_choice=None, model="claude-3-5-sonnet-20240620"):
    try:
        response = await client.messages.create(
            max_tokens=4096,
            messages=messages,
            model=model
        )
        return response.content[0].text
    except Exception as e:
        error_message = str(e)
        print(f"Anthropic API returned an error: {error_message}")
        
        if "Output blocked by content filtering policy" in error_message:
            print("Content filtering blocked the output. Returning original prompt.")
            return messages[0]["content"]
        # For other types of errors, we might want to re-raise the exception
        # or handle them differently depending on your requirements
        raise


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