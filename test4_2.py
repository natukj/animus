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
from parser.base_parser import BaseParser

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


async def main_run():
    base_parser = BaseParser()
    async def process_page(page_nums: List[int], prior_schema: str = None):
        toc_md_toc_section_str = base_parser.to_markdown(doc, page_nums)
        if not prior_schema:
            USER_PROMPT = prompts.TOC_HIERARCHY_USER_PROMPT_VISION.format(toc_md_string=toc_md_toc_section_str)
        else:
            USER_PROMPT = prompts.TOC_HIERARCHY_USER_PROMPT_VISION_PLUS.format(toc_md_string=toc_md_toc_section_str, guide_str=prior_schema)
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
                    utils.print_coloured(f"{json.dumps(toc_hierarchy_schema, indent=2)}", "yellow")
                else:
                    utils.print_coloured(f"{json.dumps(toc_hierarchy_schema, indent=2)}", "cyan")

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

    prior_schema = await process_page(grouped_pages[0])
    guide_list = [f"There are only {len(prior_schema)} levels in the Table of Contents. The levels are as follows:\n"]
    for key, value in prior_schema.items():
        guide_list.append(
            f"{key}:\n"
            f"  Level: {value['level']}\n"
            f"  Description: {value['description']}\n"
            f"  Example(s): {value['lines']}\n"
        )
    guide_str = "\n".join(guide_list)
    utils.print_coloured(guide_str, "green")

    toc_hierarchy_schemas = await asyncio.gather(
        *[
            process_page(page_nums, prior_schema=prior_schema)
            for page_nums in grouped_pages[1:]
        ]
    )
    combined_toc_hierarchy_schema = {}
    for key, value in prior_schema.items():
        for line in value["lines"]:
            if line not in combined_toc_hierarchy_schema:
                combined_toc_hierarchy_schema[line] = value["level"]
    for schema in toc_hierarchy_schemas:
        for level, content in schema.items():
            for line in content["lines"]:
                if line not in combined_toc_hierarchy_schema:
                    combined_toc_hierarchy_schema[line] = level

    ordered_items = sorted(combined_toc_hierarchy_schema.items(), key=lambda x: x[1].count('#'))
    ordered_dict = dict(ordered_items)
    utils.print_coloured(f"{json.dumps(ordered_dict, indent=4)}", "green")
    with open("toc_hierarchy_schema.json", "w") as f:
        json.dump(ordered_dict, f, indent=2)
        
    
asyncio.run(main_run())