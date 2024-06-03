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


pages = list(range(2, 59))

doc = fitz.open("/Users/jamesqxd/Documents/norgai-docs/ACTS/ukCOMPANIESACT2006.pdf")
# base_parser = BaseParser()
# toc_md_section_joined_lines = base_parser.to_markdown(doc, pages)
# with open("ztest_toc.md", "w") as f:
#     f.write(toc_md_section_joined_lines)

prior_schema = {
    "Part": "#",
    "Chapter": "##",
    "General introductory provisions": "###",
    "Companies and Companies Acts": "####",
    "Companies": "#####",
    "The Companies Acts": "#####",
    "Types of company": "####",
    "Limited and unlimited companies": "#####",
    "Private and public companies": "#####",
    "Companies limited by guarantee and having share capital": "#####",
    "Community interest companies": "#####",
    "Company formation": "###",
    "General": "####",
    "Method of forming company": "#####",
    "Memorandum of association": "#####",
    "Requirements for registration": "####",
    "Registration documents": "#####",
    "Statement of capital and initial shareholdings": "#####",
    "Statement of guarantee": "#####",
    "Statement of proposed officers": "#####",
    "Statement of compliance": "#####",
    "Registration and its effect": "####",
    "Registration": "#####",
    "Issue of certificate of incorporation": "#####",
    "Effect of registration": "#####",
    "A company\u2019s constitution": "#####",
    "Introductory": "####",
    "Articles of association": "#####",
    "Power of Secretary of State to prescribe model articles": "#####",
    "Default application of model articles": "#####",
    "Alteration of articles": "####",
    "Amendment of articles": "#####",
    "Entrenched provisions of the articles": "#####",
    "Notice to registrar of existence of restriction on amendment of articles": "#####",
    "Statement of compliance where amendment of articles restricted": "#####",
    "Effect of alteration of articles on company\u2019s members": "#####",
    "Registrar to be sent copy of amended articles": "#####",
    "Registrar\u2019s notice to comply in case of failure with respect to amended articles": "#####",
    "Supplementary": "####",
    "Existing companies: provisions of memorandum treated as provisions of articles": "#####",
    "Resolutions and agreements affecting a company\u2019s constitution": "####",
    "Copies of resolutions or agreements to be forwarded to registrar": "####",
    "Miscellaneous and supplementary provisions": "###",
    "Statement of company\u2019s objects": "#####"
}
def create_unique_hierarchy(schema):
    result = {}
    levels = set()
    for key, value in schema.items():
        if value not in levels:
            result[key] = value
            levels.add(value)
    return result

unique_schema = create_unique_hierarchy(prior_schema)
print(json.dumps(unique_schema, indent=4))

base_parser = BaseParser()
toc_md_section_joined_lines = base_parser.to_markdown(doc, pages=[0, 1])
# with open("z12test_toc.md", "w") as f:
#     f.write(toc_md_section_joined_lines)

lines = toc_md_section_joined_lines.split("\n")
unique_schema_str = ""
for key, value in unique_schema.items():
    match = process.extractOne(key, [line for line in lines])[0]
    unique_schema_str += f"{match} -> {key}: {value}\n"
print(unique_schema_str)

async def main_run():
    base_parser = BaseParser()
    async def process_page(page_num: int, prior_schema: str = None):
        if not prior_schema:
            inital_prompt = "Here is an example of the JSON structure you need to follow:"
            next_page_num = page_num + 1
            next_page = doc[next_page_num]
            toc_md_toc_section_str = base_parser.to_markdown(doc, [page_num, next_page_num])
            USER_PROMPT = prompts.TOC_HIERARCHY_USER_PROMPT_VISION.format(PROIR_SCHEMA_OR_TEMPLATE_STRING=inital_prompt, TOC_HIERARCHY_SCHEMA_TEMPLATE=prompts.TOC_HIERARCHY_SCHEMA_TEMPLATE, toc_md_string=toc_md_toc_section_str)
        else:
            inital_prompt = "For context, here is the hierarchy mapping you must follow:\n\n{unique_schema_str}\n\nUse this as a template and guide for hierarchy levels and the number of '#' characters to apply to the different formatting in the ToC. You have been given page {page_num} from the ToC so do NOT assume the hierarchy based on the position in the Markdown. Follow the formatting given above extremely closely.\n\nHere is the JSON structure to follow:".format(unique_schema_str=unique_schema_str, page_num=page_num)
            toc_md_toc_section_str = base_parser.to_markdown(doc, [page_num])
            USER_PROMPT = prompts.TOC_HIERARCHY_USER_PROMPT_VISION.format(PROIR_SCHEMA_OR_TEMPLATE_STRING=inital_prompt, TOC_HIERARCHY_SCHEMA_TEMPLATE=unique_schema, toc_md_string=toc_md_toc_section_str)
        page = doc[page_num]
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
        if not prior_schema:
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
                #utils.print_coloured(f"Schema {page_num}: {json.dumps(toc_hierarchy_schema, indent=2)}", "yellow")
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
    #toc_hierarchy_schemas = await process_page(0)
    pages = [17]
    toc_hierarchy_schemas = await asyncio.gather(*[process_page(page_num, prior_schema=prior_schema) for page_num in pages])
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



asyncio.run(main_run())