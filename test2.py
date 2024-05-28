import json
import asyncio
from typing import Any, Dict, List, Tuple, Union
import llm, prompts, utils

all_level_schemas = {"contents": []}
with open("levels.json", "r") as f:
    levels= json.load(f)

async def generate_toc_schema(levels: Dict[str, str], content: str = None, depth: int = 0, max_depth: int = None) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Generate a custom schema for the ToC based on the hierarchy schema.
    """
    if not levels:
        raise ValueError("Levels dictionary cannot be empty.")

    if max_depth is None:
        max_depth = max(marker.count('#') for marker in levels.values())

    if depth >= max_depth:
        return [], levels

    current_depth_levels = [name for name, marker in levels.items() if marker.count('#') == depth + 1]

    children = []
    if depth + 1 < max_depth:
        children, _ = await generate_toc_schema(levels, content, depth + 1, max_depth)

    toc_schema = [
        {
            "section": level_name,
            "number": "string (optional, numeric or textual identifier of the section)",
            "title": "string (optional, title of the section)",
            "children": children
        } for level_name in current_depth_levels
    ]

    return toc_schema, levels

async def generate_formatted_toc(content:str, levels: Dict[str, str]) -> str:
    """
    Generate a formatted Table of Contents (ToC) based on the provided content and levels.
    """
    custom_schema, _ = await generate_toc_schema(levels)
    TOC_SCHEMA = {"contents": [json.dumps(custom_schema, indent=4)]}
    section_types = ', '.join([f"'{section}'" for section in levels.keys()])
    level_title_str = "Chapter 3 Specialist liability rules"
    sublevel_title_str = "Part 3-5 Corporate taxpayers and corporate distributions"
    subsublevel_title_str = "Division 165 Income tax consequences of changing ownership or control of a company"
    messages = [
        {"role": "system", "content": prompts.TOC_SCHEMA_SYS_PROMPT_PLUS},
        {"role": "user", "content": prompts.TOC_SCHEMA_USER_PROMPT_PLUS.format(level_title=level_title_str, sublevel_title=sublevel_title_str, subsublevel_title=subsublevel_title_str, section_types=section_types, TOC_SCHEMA=TOC_SCHEMA, content=content)}
    ]
    # response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
    # if response.choices[0].finish_reason == "length":
    #     utils.print_coloured(f"RESPONSE TOO LONG: {level_title_str} / {sublevel_title_str} / {subsublevel_title_str}", "red")
    #     inital_message_content = response.choices[0].message.content
    if True:
        with open("inital_message_content.json", "r") as f:
            inital_message_content = f.read()
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
        max_retries = 3
        while retries < max_retries:
            response2 = await llm.openai_client_chat_completion_request(combined_messages, model="gpt-4-turbo", response_format="text")
            try:
                message_content2 = response2.choices[0].message.content
                print(message_content2)
                if message_content2.startswith("},") == False:
                    message_content2 = "}," + message_content2
                total_message_content = inital_message_content + message_content2
                toc_schema = json.loads(total_message_content)
                utils.print_coloured(f"{level_title_str} / {sublevel_title_str} / {subsublevel_title_str}", "green")
                return toc_schema
            except json.JSONDecodeError:
                retries += 1
                utils.print_coloured(f"Error decoding TOO LONG JSON ... / {subsublevel_title_str}, attempt {retries}", "red")
                if retries >= max_retries:
                    raise Exception("Max retries reached, unable to complete JSON")

    return

async def extract_toc(levels, schema, depth=0, path=[]):
    """
    Traverse and print the structure of the ToC based on levels.
    """
    toc_schema = None
    for level, content in levels.items():
        new_path = path + [level]
        if 'content' in content:
            level_path = ' > '.join(new_path)
            # print(f"Level path: {' > '.join(new_path)}, Content: {content['content'][:100]}")
            if level_path == """{"section": "Chapter", "number": "3", "title": "Specialist liability rules"} > {"section": "Part", "number": "3-5", "title": "Corporate taxpayers and corporate distributions"} > {"section": "Division", "number": "165", "title": "Income tax consequences of changing ownership or control of a company"}""":
                print(f"Level path: {level_path}")
                toc_schema = await generate_formatted_toc(content['content'], schema)
        if 'children' in content:
            await extract_toc(content['children'], schema, depth + 1, new_path)
    return toc_schema
    
    
async def main():
    TOC_SCHEMA = {
        "Chapter": "#",
        "Part": "##",
        "Division": "###",
        "Subdivision": "####",
        "Guide to Division": "####",
        "Guide to Subdivision": "####",
        "Operative provisions": "####"
    }
    pls = await extract_toc(levels, TOC_SCHEMA)
    print(json.dumps(pls, indent=4))
    #print(json.dumps(schema, indent=4))

asyncio.run(main())
"""RESPONSE TOO LONG: Chapter 3 Specialist liability rules / Part 3-5 Corporate taxpayers and corporate distributions / Division 165 Income tax consequences of changing ownership or control of a company"""
"""Level path: {"section": "Chapter", "number": "3", "title": "Specialist liability rules"} > {"section": "Part", "number": "3-5", "title": "Corporate taxpayers and corporate distributions"} > {"section": "Division", "number": "165", "title": "Income tax consequences of changing ownership or control of a company"}"""