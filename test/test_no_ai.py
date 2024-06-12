from pydantic import BaseModel, ValidationError
from typing import Union, Any, Optional, Dict, Tuple, List, NewType
import json
import asyncio
import base64
from fastapi import UploadFile
import random
import fitz
import re
import uuid
import pathlib
from collections import Counter, defaultdict
from thefuzz import process  
import llm, prompts, schemas, utils
from parser.base_parser import BaseParser

"""COMPLEX TYPICAL"""
pages = list(range(2, 32))
grouped_pages = [pages[i:i+2] for i in range(0, len(pages), 2)]
vol_num=9
# doc = fitz.open(f"/Users/jamesqxd/Documents/norgai-docs/TAX/C2024C00046VOL0{vol_num}.pdf")
# base_parser = BaseParser()
# toc_md_str = base_parser.to_markdown(doc=doc, pages=pages, page_chunks=False)
# pathlib.Path(f"vol{vol_num}.md").write_bytes(toc_md_str.encode())
async def main_run():
    
    toc_file_path = f"vol{vol_num}.md"
    with open(toc_file_path, "r") as f:
        toc_md_str = f.read()

    toc_md_lines = toc_md_str.split("\n")
    parts = {}
    stack = []
    heading_futures = []
    item_futures = []
    item_buffer = []

    async def process_heading(heading: str) -> Dict[str, str]:
        messages = [
                {"role": "system", "content": prompts.TOC_HIERARCHY_SYS_PROMPT},
                {"role": "user", "content": prompts.TOC_SECTION_USER_PROMPT.format(TOC_SECTION_TEMPLATE=prompts.TOC_SECTION_TEMPLATE, toc_line=heading)}
            ]
        response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
        try:
            if not response.choices or not response.choices[0].message:
                print("Unexpected response structure:", response)
                raise Exception("Unexpected response structure")
            
            message_content = response.choices[0].message.content
            formatted_line = json.loads(message_content)
            #print(formatted_line)
            current_part = {
                "section": formatted_line['section'],
                "number": formatted_line['number'],
                "title": formatted_line['title']
            }
            return current_part
        except Exception as e:
            utils.print_coloured(f"process_heading error loading json: {e}", "red")

    async def process_items(content: str) -> Dict[str, str]:
        messages = [
                {"role": "system", "content": prompts.TOC_HIERARCHY_SYS_PROMPT},
                {"role": "user", "content": prompts.TOC_ITEMS_USER.format(content=content)}
            ]
        response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
        try:
            if not response.choices or not response.choices[0].message:
                print("Unexpected response structure:", response)
                raise Exception("Unexpected response structure")
            
            message_content = response.choices[0].message.content
            items_dict = json.loads(message_content)
            items = items_dict['items']
            utils.print_coloured(items, "cyan")
            return items
        except Exception as e:
            utils.print_coloured(f"process_heading error loading json: {e}", "red")

    async def process_queue(futures):
        return await asyncio.gather(*[future for future, _ in futures])

    for line in toc_md_lines:
        stripped_line = line.strip()
        if stripped_line.startswith("#"):
            if item_buffer:
                placeholder = str(uuid.uuid4())
                item_futures.append((process_items('\n'.join(item_buffer)), placeholder))
                if stack:
                    current = stack[-1][1]
                    current["contents"] = placeholder
                item_buffer = []

            level = stripped_line.count("#")
            heading = stripped_line.lstrip('#').strip()
            placeholder = str(uuid.uuid4()) 
            
            while stack and stack[-1][0] >= level:
                stack.pop()
            
            if stack:
                parent = stack[-1][1]
                if "children" not in parent:
                    parent["children"] = {}
                parent["children"][placeholder] = {}
                stack.append((level, parent["children"][placeholder]))
            else:
                parts[placeholder] = {}
                stack.append((level, parts[placeholder]))
            heading_futures.append((process_heading(heading), placeholder))
        else:
            if stripped_line:
                item_buffer.append(stripped_line)

    if item_buffer:
        placeholder = str(uuid.uuid4())
        item_futures.append((process_items('\n'.join(item_buffer)), placeholder))
        if stack:
            current = stack[-1][1]
            current["contents"] = placeholder

    processed_headings, processed_items = await asyncio.gather(
        process_queue(heading_futures),
        process_queue(item_futures)
    )
    duplicate_headings = {}
    def replace_placeholders(data, futures, processed):
        for original_placeholder, processed_data in zip([placeholder for _, placeholder in futures], processed):
            def replace(data):
                if isinstance(data, dict):
                    for key in list(data.keys()):
                        # items logic
                        if key == "contents":
                            if data[key] == original_placeholder:
                                data[key] = processed_data
                        # headings logic
                        if key == original_placeholder:
                            new_key = json.dumps(processed_data)
                            if new_key in data:
                                if new_key not in duplicate_headings:
                                    duplicate_headings[new_key] = 1
                                else:
                                    duplicate_headings[new_key] += 1
                                unique_key = f"{new_key}-{duplicate_headings[new_key]}"
                                data[unique_key] = data.pop(key)
                            else:
                                data[new_key] = data.pop(key)
                        else:
                            replace(data[key])
                # elif isinstance(data, list):
                #     for index, item in enumerate(data):
                #         if item == original_placeholder:
                #             data[index] = processed_data
            replace(data)

    replace_placeholders(parts, heading_futures, processed_headings)
    replace_placeholders(parts, item_futures, processed_items)
    
    with open("vol9tocnew.json", "w") as f:
        json.dump(parts, f, indent=4)

asyncio.run(main_run())
exit()
async def main_process():
    with open("vol9toc3.json", "r") as f:
        levels_dict = json.load(f)
    tasks = []
    all_level_schemas = {"contents": []}
    global_max_depth = 0
    async def process_level(levels: Dict[str, Any], path: List[str] = []) -> List[Tuple[List[str], str]]:
        for key, value in levels.items():
            current_path = path + [key]
            if 'content' in value:
                task = asyncio.create_task(generate_formatted_toc(current_path, value['content']))
                tasks.append(task)
            elif 'children' in value:
                await process_level(value['children'], current_path)

    async def generate_toc_schema(levels: Dict[str, str], depth: int = 0, max_depth: int = None, limit: int = None) -> List[Dict[str, Any]]:
        nonlocal global_max_depth
        """{'#': '{"section": "Chapter", "number": "4", "title": "International aspects of income tax"}', '##': '{"section": "Division", "number": "880", "title": "Sovereign entities and activities"}', '###': '{"section": "", "number": "", "title": "Operative provisions"}'}"""
        if max_depth is None:
            max_depth = max(len(key) for key in levels.keys())
        global_max_depth = max(global_max_depth, max_depth)

        if depth >= max_depth:
            return []
        current_depth_marker = '#' * (depth + 1)
        current_depth_levels = {
            key: value for key, value in levels.items() if key == current_depth_marker
        }
        if limit is not None and depth + 1 == max_depth:
            current_depth_levels = dict(list(current_depth_levels.items())[:limit])

        children = await generate_toc_schema(levels, depth + 1, max_depth, limit)
        return [
            {
                "section": f"string (type of the section, e.g., {json.loads(levels[level_name]).get('section')})" if json.loads(levels[level_name]).get('section') else "",
                "number": f"string (numeric or textual identifier of the section, e.g., {json.loads(levels[level_name]).get('number')})" if json.loads(levels[level_name]).get('number') else "",
                "title": f"string (title of the section, e.g., {json.loads(levels[level_name]).get('title')})" if json.loads(levels[level_name]).get('title') else "",
                "children": children if children else [
                    {
                        "number": "string (numeric or textual identifier of the item)",
                        "title": "string (title of the item)"
                    },
                    {
                        "number": "string (numeric or textual identifier of the item)",
                        "title": "string (title of the item)"
                    }
                ]
            } for level_name in current_depth_levels
        ]
    
    async def generate_formatted_toc(path: List[str], content: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        formatted_levels = {}
        dynamic_levels = ""

        for i, level in enumerate(path):
            level_split = level.rsplit('}', 1)
            if len(level_split) == 2:
                level = level_split[0]+"}"
            try:
                level_dict = json.loads(level)
                level_title_str = f"{level_dict.get('section')} {level_dict.get('number')} {level_dict.get('title')}"
            except json.JSONDecodeError:
                utils.print_coloured(f"JSONDecodeError: {level}", "red")
                level_title_str = level
            formatted_levels['#' * (i+1)] = level
            indent = " " * (i * 4)
            dynamic_levels += f"{indent}- {level_title_str}\n"

        custom_schema = await generate_toc_schema(formatted_levels)
        TOC_SCHEMA = {"contents": [json.dumps(custom_schema, indent=4)]}
        #utils.print_coloured(json.dumps(custom_schema, indent=4), "cyan")
        messages = [
            {"role": "system", "content": prompts.TOC_SCHEMA_SYS},
            {"role": "user", "content": prompts.TOC_SCHEMA_USER.format(dynamic_levels=dynamic_levels, TOC_SCHEMA=TOC_SCHEMA, content=content)}
        ]
        response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
        if not response.choices or not response.choices[0].message:
            print("Unexpected response structure:", response)
            raise Exception("Unexpected response structure")
        try:
            message_content = response.choices[0].message.content
            toc_schema = json.loads(message_content)
            utils.print_coloured(dynamic_levels, "green")
            return (formatted_levels, toc_schema)
        except json.JSONDecodeError as e:
            print(f"JSONDecodeError: {e}")
            print(f"Message content: {message_content}")
            raise
    # if the top level of data has only one key (ToC header), skip it and start from its children
    if len(levels_dict) == 1 and 'children' in next(iter(levels_dict.values())):
        levels_dict = next(iter(levels_dict.values()))['children']
    await process_level(levels_dict)
    subtocs = await asyncio.gather(*tasks)
    for formatted_levels, subtoc in subtocs:
        if subtoc and subtoc.get("contents"):
            entry = {"toc": subtoc["contents"]}
            for i in range(1, global_max_depth + 1):
                if i == 1:
                    level_key = "level"
                else:
                    level_key = "sub" * (i - 1) + "level"
                level_marker = '#' * i
                if level_marker in formatted_levels:
                    entry[level_key] = formatted_levels[level_marker]
            all_level_schemas["contents"].append(entry)
    utils.print_coloured(f"Global max depth: {global_max_depth}", "yellow")
    with open("vol9toc3_schema.json", "w") as f:
        json.dump(all_level_schemas, f, indent=4)
            
#asyncio.run(main_process())

async def main_merge():
    async def find_existing_section(toc: List[schemas.TableOfContents], section: str, number: str, title: str) -> Optional[schemas.TableOfContents]:
        """Find an existing section by section and number."""
        for item in toc:
            if item.section == section and item.number == number and item.title == title:
                return item
        return None

    async def nest_toc(content: Any) -> schemas.TableOfContents:
        """Builds a nested table of contents based on content levels."""
        def parse_level(level_json: str):
            level_dict = json.loads(level_json)
            return level_dict['section'], level_dict['number'], level_dict['title']

        levels = [value for key, value in content.__dict__.items() if 'level' in key and value is not None]
        if not levels:
            raise ValueError("No levels provided")
        
        root_toc = None
        current_toc = None

        for i, level_json in enumerate(levels):
            section, number, title = parse_level(level_json)
            new_toc = schemas.TableOfContents(section=section, number=number, title=title, children=[])

            if root_toc is None:
                root_toc = new_toc
                current_toc = root_toc
            else:
                current_toc.children.append(new_toc)
                current_toc = new_toc

        if current_toc:
            print("###")
            print(current_toc)
            print("***")
            print(content.toc)
            print("===")
            print(root_toc)
            print("\n")

        return content.toc

    async def merge_toc(master_toc: List[schemas.TableOfContents], toc: schemas.TableOfContents) -> List[schemas.TableOfContents]:
        """Merge ToC sections."""
        existing_level = await find_existing_section(master_toc, toc.section, toc.number, toc.title)
        if existing_level:
            existing_level.children = schemas.merge_children(existing_level.children, toc.children or [])
        else:
            master_toc.append(toc)
        return master_toc

    with open("vol9toc3_schema.json", "r") as f:
        toc_schema = json.load(f)

    master_toc: List[schemas.TableOfContents] = []
    Contents = schemas.generate_contents_class(4)
    for content in toc_schema.get("contents", []):
        # convert levels to the dynamically generated Contents class
        levels = {key: content[key] for key in content if 'level' in key}
        toc = content["toc"]
        entry = Contents(**levels, toc=toc)
        nested_toc = await nest_toc(entry)
        master_toc = await merge_toc(master_toc, nested_toc)

    with open("vol9toc3_merged.json", "w") as f:
        json.dump([toc.model_dump() for toc in master_toc], f, indent=4)

asyncio.run(main_merge())