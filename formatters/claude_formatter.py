import asyncio
import json
from typing import Any, Awaitable, Callable
import llm, prompts, utils

class RateLimiter:
    def __init__(self, semaphore_value: int = 50):
        self.semaphore = asyncio.Semaphore(semaphore_value)

    async def rate_limited_process(
        self, 
        process_function: Callable[..., Awaitable[Any]],
        *args: Any, 
        max_attempts: int = 5, 
        **kwargs: Any
    ) -> Any:
        attempts = 0
        async with self.semaphore:
            while attempts < max_attempts:
                try:
                    return await process_function(*args, **kwargs)
                except Exception as e:
                    function_name = process_function.__name__ if hasattr(process_function, '__name__') else 'Unknown function'
                    utils.print_coloured(f"Error during RLP {function_name}: {e}", "red")
                    utils.print_coloured(f"Retrying... Attempt {attempts + 1}", "red")
                    attempts += 1
                    if attempts >= max_attempts:
                        utils.print_coloured(f"Failed after {max_attempts} attempts", "red")
                        return None

async def process_chunk(chunk: str, path: str) -> dict:
    try:
        formatted_prompt = prompts.FORMAT_ITEM_USER_CLAUDE.format(path=path, content=chunk)
        messages = [{"role": "user", "content": formatted_prompt}]
        result = await llm.claude_client_chat_completion_request(messages, model="claude-3-sonnet-20240229")

        if result == formatted_prompt:
            utils.print_coloured(f"Content filtering blocked output for {path}. Using original content.", "yellow")
            return {
                "path": path,
                "formatted_content": chunk,
                "references": []
            }
    
        item_content = utils.extract_between_tags("formatted_content", result, strip=True)
        references_json = utils.extract_between_tags("references", result)
        
        output = {
            "path": path,
            "formatted_content": item_content,
            "references": []
        }
        try:
            references_dict = json.loads(references_json)
            output["references"] = references_dict
        except json.JSONDecodeError:
            utils.print_coloured(f"Warning: Could not parse references JSON for {path}", "yellow")

        print(f"Processed chunk for path: {path}")
        return output
    except Exception as e:
        utils.print_coloured(f"Error processing chunk for {path}: {str(e)}", "red")
        return {
            "path": path,
            "formatted_content": chunk,
            "references": []
        }

async def format_contents_claude(contents: dict):
    formatted_items = []
    items = utils.traverse_contents(contents)
    all_tasks = []
    rate_limiter = RateLimiter(200)
    
    for item in items:
        content = item.get('content', '')
        path = item.get('path', '')
        tokens = item.get('tokens', 0)
        if tokens > 20000:
            formatted_items.append({
                "path": path,
                "formatted_content": content,
                "references": []
            })
        elif tokens > 3500:
            init_chunk, chunks = utils.split_content(content)
            chunk_tasks = [rate_limiter.rate_limited_process(process_chunk, chunks[0], path)]
            for i, chunk in enumerate(chunks[1:], start=2):
                context = f"**This item has been split into {len(chunks)} chunks. For context, the beginning of this item content is:\n\n{init_chunk}\n\nPlease only output the formatted content from the following content (chunk {i} of {len(chunks)}):**\n\n{chunk}"
                chunk_tasks.append(rate_limiter.rate_limited_process(process_chunk, context, path))
            all_tasks.extend(chunk_tasks)
        else:
            all_tasks.append(rate_limiter.rate_limited_process(process_chunk, content, path))

    results = await asyncio.gather(*all_tasks)

    current_path = None
    current_item = None
    for result in results:
        if result is None:
            utils.print_coloured(f"Skipping None result", "red")
            continue

        path = result.get('path')
        utils.print_coloured(f"Processed: {path}", "yellow")
        if path != current_path:
            if current_item:
                formatted_items.append(current_item)
            current_path = path
            current_item = {
                "path": path,
                "formatted_content": "",
                "references": []
            }
        current_item["formatted_content"] += result["formatted_content"]
        current_item["references"].extend(result["references"])

    if current_item:
        formatted_items.append(current_item)

    # deduplicate references for each item
    for item in formatted_items:
        if isinstance(item["references"], list):
            try:
                item["references"] = [
                    dict(ref) if isinstance(ref, dict) else json.loads(ref) if isinstance(ref, str) else ref
                    for ref in item["references"]
                ]
                
                # remove duplicates while preserving order
                seen = set()
                item["references"] = [
                    d for d in item["references"]
                    if not (tuple(d.items()) in seen or seen.add(tuple(d.items())))
                ]
            except json.JSONDecodeError as e:
                utils.print_coloured(f"Error parsing references for {item['path']}: {e}", "yellow")
                utils.print_coloured(f"References: {item['references']}", "yellow")
                item["references"] = []
        else:
            utils.print_coloured(f"Unexpected references type for {item['path']}: {type(item['references'])}", "yellow")
            utils.print_coloured(f"References: {item['references']}", "yellow")
            item["references"] = []

    return formatted_items
