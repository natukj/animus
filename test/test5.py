import json
import asyncio
from typing import Any, Dict, List, Tuple, Union
from collections import defaultdict, Counter
import llm, prompts, utils
import tiktoken


def count_tokens(text: str, encoding_name: str = "o200k_base") -> int:
    """
    count the number of tokens in the given text using the specified encoding.
    """
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(text))
    return num_tokens

with open("toc_hierarchy_schema.json", "r") as f:
    toc_hierarchy_schema = json.load(f)

async def filter_schema(toc_hierarchy_schema: Dict[str, str], content: str, num_sections: int = 5) -> Dict[str, str]:
        """
        Filter the schema to reduce size and complexity.
        """
        with open("zztoc_md_string.md", "r") as f:
            toc_md_string = f.read()
        lines = toc_md_string.split('\n')
        grouped_schema = defaultdict(list)
        for key, value in toc_hierarchy_schema.items():
            grouped_schema[value].append(key)

        def find_most_common_heading(headings: List[str], lines: List[str]):
            counts = Counter()
            for line in lines:
                for heading in headings:
                    if heading in line:
                        counts[heading] += 1
            most_common_heading = counts.most_common(1)[0][0] if counts else None
            return most_common_heading
        
        most_common_headings = {}
        for level, headings in grouped_schema.items():
            if len(headings) > 1:
                most_common_heading = find_most_common_heading(headings, lines)
                most_common_headings[level] = most_common_heading
            else:
                most_common_headings[level] = headings[0]

        sorted_headings = sorted(most_common_headings.items(), key=lambda x: len(x[0]))
        result = {heading: level for level, heading in sorted_headings[:num_sections]}
        # dynamically adjust the schema based on whats present in the content
        for heading, level in toc_hierarchy_schema.items():
            formatted_heading = heading
            if formatted_heading in content and heading not in result:
                result[heading] = level
        return result

async def generate_toc_schema(levels: Dict[str, Dict[str, str]], depth: int = 0, max_depth: int = None, limit: int = None) -> List[Dict[str, Any]]:
    """
    Generate a custom schema for the ToC based on the hierarchy schema.
    """
    if max_depth is None:
        max_depth = max(marker['level'].count('#') for marker in levels.values())

    if depth >= max_depth:
        return []

    current_depth_levels = [name for name, marker in levels.items() if marker['level'].count('#') == depth + 1]
    if limit is not None and depth + 1 == max_depth:
        current_depth_levels = current_depth_levels[:limit]
    
    children = await generate_toc_schema(levels, depth + 1, max_depth, limit)

    return [
        {
            "section": f"string (type of the section, e.g., {level_name})" if levels[level_name]['added_from'] == 'section' else "string (type of the section)",
            "number": "string (numeric or textual identifier of the section)",
            "title": "string (title of the section)" if levels[level_name]['added_from'] == 'section' else f"string (title of the section, e.g., {level_name})", 
            "children": children if children else [
                {
                    "number": "string (numeric or textual identifier of the section)",
                    "title": "string (title of the section)"
                },
                {
                    "number": "string (numeric or textual identifier of the section)",
                    "title": "string (title of the section)"
                }
            ]
        } for level_name in current_depth_levels
    ]

async def process_level_new(level_json_str: str, level_content: Dict[str, Any], depth: int = 1) -> Dict[str, Dict[str, str]]:
    levels = {}
    level_json = json.loads(level_json_str)
    level_section, level_number, level_title = level_json["section"], level_json["number"], level_json["title"]
    level_title_str = f"{level_section} {level_number} " + (level_title if level_title else "")
    if level_content.get("content", "") and not level_title:
        level_title_str += "(the title of this section should be available in the content)"
    levels[level_section] = {'level': '#' * depth, 'added_from': 'section'}
    async def process_children(children: Dict[str, Any], current_depth: int):
        for child_json_str, child_content in children.items():
            child_json = json.loads(child_json_str)
            child_section, child_number, child_title = child_json["section"], child_json["number"], child_json["title"]

            if child_number:
                child_level = child_section
                added_from = 'section'
            else:
                child_level = child_title
                added_from = 'title'
            if child_level == "":
                child_level = child_section
                #added_from = 'section'

            if child_level not in levels:
                levels[child_level] = {'level': '#' * (current_depth + 1), 'added_from': added_from}
            if "children" in child_content:
                await process_children(child_content["children"], current_depth + 1)

    if "children" in level_content:
        await process_children(level_content["children"], depth)

    return level_title_str, levels
                

async def main():
    with open("levels.json", "r") as f:
        levels_json = json.load(f)
    for level_json_str, level_content in levels_json.items():
        if level_json_str != "{\"section\": \"PART\", \"number\": \"17\", \"title\": \"\"}":
            continue
        level_title_str, custom_levels = await process_level_new(level_json_str, level_content)
        custom_schema = await generate_toc_schema(custom_levels, limit=3)
        TOC_SCHEMA = {"contents": [json.dumps(custom_schema, indent=4)]}
        section_types = ", ".join(custom_levels.keys())
        messages = [
            {"role": "system", "content": prompts.TOC_SCHEMA_SYS_PROMPT_PLUS},
            {"role": "user", "content": prompts.TOC_SCHEMA_USER_PROMPT_PLUS_NOMD.format(level_title_str=level_title_str, section_types=section_types, TOC_SCHEMA=TOC_SCHEMA, level_content=json.dumps(level_content, indent=4))}
        ]
        utils.print_coloured(f"messages tokens: {count_tokens(json.dumps(messages))}", "red")
        utils.print_coloured(f"level_content: {count_tokens(json.dumps(level_content, indent=2))}", "yellow")
        utils.print_coloured(f"TOC_SCHEMA_SYS_PROMPT_PLUS: {count_tokens(prompts.TOC_SCHEMA_SYS_PROMPT_PLUS)}", "cyan")
        response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
        if response.choices[0].finish_reason == "length":
            inital_message_content = response.choices[0].message.content
            split_content = inital_message_content.rsplit('},', 1)
        if len(split_content) == 2:
            inital_message_content, remaining_content = split_content
            remaining_content = '},' + remaining_content.strip()
            utils.print_coloured(remaining_content, "yellow")
        else:
            remaining_content = ''
        additional_messages = [
            {"role": "assistant", "content": inital_message_content},
            {"role": "user", "content": "Please continue from EXACTLY where you left off so that the two responses can be concatenated and form a complete JSON object. Make sure to include the closing brackets, quotation marks and commas. Do NOT add any additional text, such as '```json' or '```'."},
            {"role": "assistant", "content": remaining_content}]
        combined_messages = messages + additional_messages
        retries = 0
        max_retries = 5
        while retries < max_retries:
            response2 = await llm.openai_client_chat_completion_request(combined_messages, model="gpt-4o", response_format="text")
            try:
                message_content2 = response2.choices[0].message.content
                utils.print_coloured(message_content2, "yellow")
                if message_content2.startswith(remaining_content) == False:
                    message_content2 = remaining_content + message_content2
                total_message_content = inital_message_content + message_content2
                toc_schema = json.loads(total_message_content)
                utils.print_coloured(f"yay", "green")
                with open("zz17.json", "w") as f:
                    json.dump(toc_schema, f, indent=2)
                return "DONE"
            except json.JSONDecodeError:
                retries += 1
                utils.print_coloured(f"Error decoding TOO LONG JSON", "red")
                if retries >= max_retries:
                    raise Exception("Max retries reached, unable to complete JSON")
        # toc_schema = json.loads(message_content)
        # print(json.dumps(toc_schema, indent=2))
        # with open("zzzzzzzz15.json", "w") as f:
        #     json.dump(toc_schema, f, indent=2)

asyncio.run(main())