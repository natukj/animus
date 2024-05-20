import asyncio
import json 
import llm, prompts

# THIS DOESNT WORK

async def check_json_response(system_prompt: str, user_prompt: str, response_json: str) -> str:
    check_system_prompt = """You are reponsible for quality checks on the work of colleagues. You must pay very close attention to detail and ensure that the work is accurate and correct. If not, as the senior member of the team, you must correct their mistakes. You must always respond with a JSON Object or an empty JSON Object. """
    formatted_user_prompt = prompts.IS_THIS_JSON_CORRECT.format(SYSTEM_PROMPT=system_prompt, USER_PROMPT=user_prompt, RESPONSE_JSON=response_json)
    messages = [
        {"role": "system", "content": check_system_prompt},
        {"role": "user", "content": formatted_user_prompt}
    ]
    response = await llm.openai_chat_completion_request(messages, response_format="json")
    if response and 'choices' in response and len(response['choices']) > 0:
        try:
            return response['choices'][0]['message']['content']
        except json.JSONDecodeError:
            print("Error decoding JSON for JSON Response Check")
            raise

async def check_json_response_claude(system_prompt: str, user_prompt: str, response_json: str) -> str:
    check_system_prompt = """You are reponsible for quality checks on the work of colleagues. You must pay very close attention to detail and ensure that the work is accurate and correct. If not, as the senior member of the team, you must correct their mistakes. You must always respond with a JSON Object or an empty JSON Object. """
    formatted_user_prompt = prompts.IS_THIS_JSON_CORRECT.format(SYSTEM_PROMPT=system_prompt, USER_PROMPT=user_prompt, RESPONSE_JSON=response_json)
    end_of_user_prompt = """
    Before responding, please think about it step-by-step within <thinking></thinking> tags. Then, provide your final JSON Object answer within <answer></answer> tags."""
    total_user_prompt = check_system_prompt + formatted_user_prompt + end_of_user_prompt
    messages = [
        {"role": "user", "content": total_user_prompt}
    ]
    response = await llm.claude_chat_completion_request(messages)
    return response['content'][0]['text']

async def self_reflection(system_prompt: str, user_prompt: str, response_json: str) -> str:
    self_reflection_prompt = """Please reflect on your response. You must pay very close attention to detail and ensure that all criteria is met. If not, you must correct your mistakes. Reponse with the correct JSON Object."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
        {"role": "assistant", "content": response_json},
        {"role": "user", "content": self_reflection_prompt}
    ]
    response = await llm.openai_chat_completion_request(messages, response_format="json")
    if response and 'choices' in response and len(response['choices']) > 0:
        try:
            return response['choices'][0]['message']['content']
        except json.JSONDecodeError:
            print("Error decoding JSON for JSON Response Check")
            raise
    