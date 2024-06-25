import asyncio
import json
import re
import os
import llm, prompts, utils

def extract_between_tags(tag: str, string: str, strip: bool = False) -> str:
    ext_list = re.findall(f"<{tag}>(.+?)</{tag}>", string, re.DOTALL)
    if ext_list:
        content = ext_list[0]
        return content.strip() if strip else content
    return ""

def traverse_contents(data, current_path=""):
    results = []
    for item in data:
        item_path = f"{item.get('section', '')} {item.get('number', '')} {item.get('title', '')}"
        full_path = f"{current_path} / {item_path}".strip(" /")
        if 'content' in item:
            results.append({
                'path': full_path,
                'content': item['content'],
                'tokens': item.get('tokens', 0)
            })
        if 'children' in item:
            results.extend(traverse_contents(item['children'], full_path))
    return results

def find_item_from_path(data, target_path, current_path=""):
    def normalise_path(path):
        return ' '.join(path.lower().split())
    target_path_normalized = normalise_path(target_path)
    for item in data:
        item_path = f"{item.get('section', '')} {item.get('number', '')} {item.get('title', '')}"
        full_path = f"{current_path} / {item_path}".strip(" /")
        full_path_normalized = normalise_path(full_path)
        if full_path_normalized == target_path_normalized:
            return {
                'path': full_path,
                'content': item.get('content', ''),
                'tokens': item.get('tokens', 0)
            }
        if 'children' in item:
            result = find_item_from_path(item['children'], target_path, full_path)
            if result:
                return result
    return None

def split_content(content: str, target_chunk_tokens: int = 2000) -> list:
    initial_chunk= ""
    chunks = []
    lines = content.split('\n')
    
    current_chunk = ""
    current_chunk_tokens = 0
    
    for line in lines:
        line_tokens = utils.count_tokens(line)
        if line.startswith('___') and current_chunk and current_chunk_tokens >= target_chunk_tokens:
            chunks.append(current_chunk.strip())
            current_chunk = line
            current_chunk_tokens = line_tokens
        elif line.startswith('___') and not initial_chunk and current_chunk:
            initial_chunk = current_chunk
        else:
            if current_chunk:
                current_chunk += "\n"
            current_chunk += line
            current_chunk_tokens += line_tokens
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return initial_chunk, chunks

async def process_chunk(chunk: str, path: str):
    formatted_prompt = prompts.FORMAT_ITEM_USER_CLAUDE.format(path=path, content=chunk)
    messages = [{"role": "user", "content": formatted_prompt}]
    result = await llm.claude_client_chat_completion_request(messages, model="claude-3-haiku-20240307")
    
    item_content = extract_between_tags("formatted_content", result, strip=True)
    references_json = extract_between_tags("references", result)
    
    output = {
        "formatted_content": item_content,
        "references": []
    }
    try:
        references_dict = json.loads(references_json)
        output["references"] = references_dict
    except json.JSONDecodeError:
        pass

    print(f"Processed chunk for path: {path}")
    return output


with open("/Users/jamesqxd/Documents/norgai-docs/TAX/parsed/final_aus_tax.json", "r") as f:
    tax_data = json.load(f)["contents"]

target_path = "Chapter 1 Introduction and core provisions / Part 1-4 Checklists of what is covered by concepts used in the core provisions / Division 10 Particular kinds of assessable income /  10-5 List of provisions about assessable income"
async def main_run():
    results = []
    result = find_item_from_path(tax_data, target_path)
    results.append(result)

    # if not result:
    #     print("Item not found")
    #     return
    all_results = []
    #results = traverse_contents(tax_data)
    for result in results:
        content = result['content']
        path = result['path']
        tokens = result['tokens']
        tasks = []
        if tokens > 3500 and tokens < 20000:
            init_chunk, chunks = split_content(content)
            tasks.append(process_chunk(chunks[0], path))
            for i, chunk in enumerate(chunks[1:], start=2):
                context = f"**This item has been split into {len(chunks)} chunks. For context, the beginning of this item content is:\n\n{init_chunk}\n\nPlease only output the formatted content from the following content (chunk {i} of {len(chunks)}):**\n\n{chunk}"
                tasks.append(process_chunk(context, path))

            chunk_results = await asyncio.gather(*tasks)
            combined_result = {
                "path": path,
                "formatted_content": "",
                "references": []
            }
            for chunk_result in chunk_results:
                combined_result["formatted_content"] += chunk_result["formatted_content"]
                if chunk_result["references"]:
                    combined_result["references"].extend(chunk_result["references"])
            combined_result["references"] = [dict(t) for t in {tuple(d.items()) for d in combined_result["references"]}]
            all_results.append(combined_result)
            break
    output_dir = "ztest_tax_output"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "formatted_items_haiku.json")
    
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2)
    
    print(f"Results saved to {output_file}")
asyncio.run(main_run())
