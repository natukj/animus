from pydantic import BaseModel, ValidationError
from typing import Union, Any, Optional, Dict, Tuple, List, NewType
import json
import asyncio
import base64
from fastapi import UploadFile
import fitz
import re
import uuid
from collections import Counter, defaultdict
from thefuzz import process  
import llm, prompts, utils
from parsers.pdf_parser import BaseParser

def encode_page_as_base64(page: fitz.Page):
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    return base64.b64encode(pix.tobytes()).decode('utf-8')


pages = list(range(0, 59))
# grouped_pages = pages[2::2]
# if pages[-1] != grouped_pages[-1]:
#     grouped_pages.append(pages[-1])
# last_page = grouped_pages[-1]
grouped_pages = [pages[i:i+2] for i in range(0, len(pages), 2)]
# if len(grouped_pages[-1]) < 2:
#     grouped_pages[-1].append(grouped_pages[0])

# for group in grouped_pages:
#     print(group)

# print(grouped_pages[0])
# print(grouped_pages[0][0])
# exit()
doc = fitz.open("/Users/jamesqxd/Documents/norgai-docs/ACTS/ukCOMPANIESACT2006.pdf")
# base_parser = BaseParser()
# toc_md_section_joined_lines = base_parser.to_markdown(doc, pages)
# with open("ztest_toc.md", "w") as f:
#     f.write(toc_md_section_joined_lines)

async def main_run():
    base_parser = BaseParser()
    async def process_page(page_nums: List[int], prior_schema: str = None, guide_flag: bool = False):
        nonlocal unique_schema_str
        nonlocal unique_schema
        if not prior_schema:
            toc_md_toc_section_str = base_parser.to_markdown(doc, page_nums)
            if guide_flag:
                USER_PROMPT = prompts.TOC_HIERARCHY_USER_PROMPT_V1SION_PRE.format(toc_md_string=toc_md_toc_section_str)
            else:
                USER_PROMPT = prompts.TOC_HIERARCHY_USER_PROMPT_V1SION.format(TOC_HIERARCHY_SCHEMA_TEMPLATE=prompts.TOC_HIERARCHY_SCHEMA_TEMPLATE, toc_md_string=toc_md_toc_section_str)
        else:
            unique_schema_dump = json.dumps(unique_schema, indent=2)
            toc_md_toc_section_str = base_parser.to_markdown(doc, page_nums)
            USER_PROMPT = prompts.TOC_HIERARCHY_USER_PROMPT_VISION.format(unique_schema_str=unique_schema_str, TOC_HIERARCHY_SCHEMA_TEMPLATE=unique_schema_dump, toc_md_string=toc_md_toc_section_str)
        page = doc[page_nums[0]]
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": USER_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{encode_page_as_base64(page)}",
                        },
                    }
                ]
            }
        ]
        if len(page_nums) > 1:
            for next_page_num in page_nums[1:]:
                next_page = doc[next_page_num]
                messages[0]["content"].append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{encode_page_as_base64(next_page)}",
                        },
                    }
                )
        while True:
            response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
            try:
                message_content = response.choices[0].message.content
                toc_hierarchy_schema = json.loads(message_content)
                if not prior_schema:
                    ordered_items = sorted(toc_hierarchy_schema.items(), key=lambda x: x[1].count('#'))
                    ordered_dict = dict(ordered_items)
                    utils.print_coloured(f"{json.dumps(ordered_dict, indent=2)}", "yellow")
                else:
                    highest_level_toc=max(toc_hierarchy_schema.values(), key=lambda x: x.count('#'))
                    highest_level_toc_count = highest_level_toc.count('#')
                    highest_level_temp=max(prior_schema.values(), key=lambda x: x.count('#'))
                    highest_level_temp_count = highest_level_temp.count('#')
                    if highest_level_toc_count > highest_level_temp_count:
                        for key, value in toc_hierarchy_schema.items():
                            level_count = value.count('#')
                            if level_count > highest_level_temp_count:
                                toc_hierarchy_schema[key] = value[:highest_level_temp_count]
                                utils.print_coloured(f"changed {key} to {value[:highest_level_temp_count]}", "red")
                        # utils.print_coloured(f"Schema {page_num}: {json.dumps(toc_hierarchy_schema, indent=2)}", "yellow")
                        # additional_messages = [
                        #     {"role": "assistant", "content": message_content},
                        #     {"role": "user", "content": f"Please correct the schema. There should not be levels higher than {highest_level_temp} x '#'."}
                        # ]
                        # messages = messages + additional_messages   
                        # continue
                return toc_hierarchy_schema
            except json.JSONDecodeError as e:
                print(f"JSONDecodeError: {e}")
                print(f"Message content: {message_content}")
                print("Retrying...")
                continue
            except Exception as e:
                print(f"Error: {e}")
                print("Retrying...")
                continue
    #pages = [17]
    schema_guide = await process_page(grouped_pages[0], guide_flag=True)
    guide_list = [f"There are {len(schema_guide)} levels in the Table of Contents. The levels are as follows:\n"]
    for key, value in prior_schema.items():
        guide_list.append(
            f"{key}:\n"
            f"  Level: {value['level']}\n"
            f"  Description: {value['description']}\n"
            f"  Example(s):\n{value['example']}\n"
        )
    guide_str = "\n".join(guide_list)
    prior_schema = await process_page(grouped_pages[0])
    #unique_schema = await create_unique_hierarchy(prior_schema)
    unique_schema = prior_schema
    # prior_schema_items = sorted(prior_schema.items(), key=lambda x: x[1].count('#'))
    # unique_schema = dict(prior_schema_items)
    toc_md_section_joined_lines = base_parser.to_markdown(doc, pages=grouped_pages[0])
    lines = toc_md_section_joined_lines.split("\n")
    unique_schema_str = ""
    for key, value in unique_schema.items():
        match = process.extractOne(key, [line for line in lines])[0]
        unique_schema_str += f"{match} -> {key}: {value}\n"
    print(unique_schema_str)
    for i in range(0, 11):
        print(f"{10 - i} seconds left...")
        await asyncio.sleep(1)
    # toc_hierarchy_schemas = await asyncio.gather(*[process_page(page_num, prior_schema=prior_schema) for page_num in pages[2:]])
    toc_hierarchy_schemas = await asyncio.gather(
        *[
            process_page(page_nums, prior_schema=prior_schema)
            for page_nums in grouped_pages[1:]
        ]
    )
    #toc_hierarchy_schemas.append(prior_schema)
    combined_toc_hierarchy_schema = prior_schema
    for toc_hierarchy_schema in toc_hierarchy_schemas:
        for key, value in toc_hierarchy_schema.items():
            capitalised_key = re.sub(r'\s*\d+$', '', key.capitalize())
            if capitalised_key in combined_toc_hierarchy_schema:
                if combined_toc_hierarchy_schema[capitalised_key] != value:
                    print(f"Conflict: {capitalised_key}: {combined_toc_hierarchy_schema[capitalised_key]} vs {value}")
            else:
                combined_toc_hierarchy_schema[capitalised_key] = value

    ordered_items = sorted(combined_toc_hierarchy_schema.items(), key=lambda x: x[1].count('#'))
    ordered_dict = dict(ordered_items)
    utils.print_coloured(f"{json.dumps(ordered_dict, indent=4)}", "green")
    with open("toc_hierarchy_schema.json", "w") as f:
        json.dump(ordered_dict, f, indent=2)



asyncio.run(main_run())