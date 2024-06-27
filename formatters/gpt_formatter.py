import asyncio
import json
import llm, prompts, utils

async def format_content_plus_summary_gpt(content: str, path: str, doc_name: str = "Tax Income Assesment Act 1997"):
    messages = [
        {"role": "system", "content": "You are an AI assistant skilled in formatting legal documents as a JSON object."},
        {"role": "user", "content": prompts.FORMAT_CONTENT_SUMMARY_GPT.format(doc_name=doc_name, path=path, content=content)}]
    while True:
        result = await llm.openai_client_chat_completion_request(messages)
        if result.choices[0].finish_reason == "length":
            utils.print_coloured(f"Response too long: {path}...", "red")
            return content, ""
        result_str = result.choices[0].message.content
        try:
            formatted_result = json.loads(result_str)
            formatted_content = formatted_result["formatted_content"]
            summary = formatted_result["summary"]
            if formatted_content and summary:
                return formatted_content, summary
        except json.JSONDecodeError:
            utils.print_coloured(f"Error decoding JSON response: {result_str}", "red")
            raise