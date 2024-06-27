import asyncio
import os
from tenacity import retry, wait_random_exponential, stop_after_attempt
import httpx
from groq import AsyncGroq
client = AsyncGroq()
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')

async def groq_client_chat_completion_request(messages, model="llama3-8b-8192"):
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=10,
        )
        return response
    except Exception as e:
        print(f"Groq Request failed with exception: {e}")
        raise

@retry(wait=wait_random_exponential(multiplier=1, max=40), stop=stop_after_attempt(3))
async def groq_chat_completion_request(messages, tools=None, tool_choice=None, json_mode=False, model="mixtral-8x7b-32768"):
    """llama3-8b-8192, llama3-70b-8192, mixtral-8x7b-32768"""
    headers = {
        "Authorization": f"Bearer " + GROQ_API_KEY,
        "Content-Type": "application/json",
    }

    json_data = {
        "messages": messages,
        "model": model
    }
    if json_mode:
        json_data.update({"response_format": {"type": "json_object"}})
    if tools is not None:
        json_data.update({"tools": tools})
    if tool_choice is not None:
        json_data.update({"tool_choice": tool_choice})

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=json_data,
                timeout=60
            )
            response.raise_for_status()
            return response
        except httpx.ReadTimeout as e:
            print("Groq Request timed out.")
            print(f"Exception: {e}")
            raise
        except httpx.HTTPStatusError as e:
            print(f"Groq Request failed with status code: {e.response.status_code}")
            print(f"Exception: {e}")
            raise
        except Exception as e:
            print("Groq Unable to generate ChatCompletion response.")
            print(f"Exception: {e}")
            raise




async def example():
    client = AsyncGroq()

    chat_completion = await client.chat.completions.create(
        #
        # Required parameters
        #
        messages=[
            # Set an optional system message. This sets the behavior of the
            # assistant and can be used to provide specific instructions for
            # how it should behave throughout the conversation.
            {
                "role": "system",
                "content": "you are a helpful assistant."
            },
            # Set a user message for the assistant to respond to.
            {
                "role": "user",
                "content": "Explain the importance of fast language models",
            }
        ],

        # The language model which will generate the completion.
        model="llama3-8b-8192",

        #
        # Optional parameters
        #

        # Controls randomness: lowering results in less random completions.
        # As the temperature approaches zero, the model will become
        # deterministic and repetitive.
        temperature=0.5,

        # The maximum number of tokens to generate. Requests can use up to
        # 2048 tokens shared between prompt and completion.
        max_tokens=1024,

        # Controls diversity via nucleus sampling: 0.5 means half of all
        # likelihood-weighted options are considered.
        top_p=1,

        # A stop sequence is a predefined or user-specified text string that
        # signals an AI to stop generating content, ensuring its responses
        # remain focused and concise. Examples include punctuation marks and
        # markers like "[end]".
        stop=None,

        # If set, partial message deltas will be sent.
        stream=False,
    )

    # Print the completion returned by the LLM.
    print(chat_completion.choices[0].message.content)

