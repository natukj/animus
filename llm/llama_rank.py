import asyncio
from typing import List, Dict, Any
import json
from llm import groq_client_chat_completion_request
import utils

#"llama-3.1-8b-instant" # 30 rpm // useless
#"llama3-8b-8192" # 300 rpm
SYS_PROMPT = "You are a tax expert. You must determine whether the following information is relevant to the user's query: '{query}'. If it is relevant, output 'True'. If it is not relevant, output 'False'."

async def llama_rank_docs(user_query: str, content_nodes: List[Dict[str, Any]], model: str = "llama-3.1-8b-instant", max_retries: int = 3):
    semaphore = asyncio.Semaphore(100)

    async def process_item(node: Dict[str, Any]):
        async with semaphore:
            doc_content = f"{node['id']}\n\nTitle: {node['title']}\n\nContent: {node['content']}\n\n"
            messages = [
                {"role": "system", "content": SYS_PROMPT.format(query=user_query)},
                {"role": "user", "content": doc_content}
            ]
            if utils.count_tokens(json.dumps(messages)) > 8000:
                utils.print_coloured(f"Token count exceeds 8000 for {node['id']}. Skipping...", "yellow")
                return node, "invalid"
            for attempt in range(max_retries):
                try:
                    response = await groq_client_chat_completion_request(messages, model=model, max_tokens=1)
                    result = response.choices[0].message.content.strip().lower()
                    if result in ["true", "false"]:
                        return node, result
                except Exception as e:
                    if attempt == max_retries - 1:
                        utils.print_coloured(f"Error processing {node['id']}: {str(e)}", "red")
                        return node, "error"
            
            return node, "invalid"

    async def llama_rank():
        tasks = [process_item(node) for node in content_nodes]
        results = await asyncio.gather(*tasks)
        
        relevant_docs = []
        for node, api_result in results:
            utils.print_coloured(f"{node['self_ref']}: {node['title']}", "blue")
            utils.print_coloured(f"ID: {node['id']}", "cyan")
            if api_result == "true":
                utils.print_coloured(api_result, "green")
                relevant_docs.append(node)
            elif api_result == "false":
                utils.print_coloured(api_result, "red")
            else:
                utils.print_coloured(api_result, "yellow")
            print("-" * 50)
        
        return relevant_docs

    return await llama_rank()