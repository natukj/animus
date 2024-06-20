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
from collections import OrderedDict
from thefuzz import process  
import llm, prompts, schemas, utils
from parsers.pdf_parser import BaseParser
def find_empty_keys_with_following(data):
    empty_keys_with_following = []
    items = list(data.items()) 
    for i in range(len(items)):
        key, value = items[i]
        if value == {}:
            following_key = items[i + 1][0] if i + 1 < len(items) else None
            empty_keys_with_following.append((key, following_key))
            details = json.loads(key)
            if not details.get('title'):
                next_details = json.loads(following_key) if following_key else None
                if next_details:
                    print(f"{details.get('section')} {details.get('number')} {details.get('title')} {next_details.get('section')} {next_details.get('number')} {next_details.get('title')}")
            
        if isinstance(value, dict):
            empty_keys_with_following.extend(find_empty_keys_with_following(value))

    return empty_keys_with_following

async def main():
    with open("UKparts.json", "r", encoding="utf-8") as f:
        # load the data into an OrderedDict to maintain the order of keys
        parts = json.load(f, object_pairs_hook=OrderedDict)

    def merge_keys_and_delete_next(data):
        new_data = OrderedDict()
        items = list(data.items())
        i = 0
        while i < len(items):
            key, value = items[i]
            while value == {} and i + 1 < len(items):
                following_key, following_value = items[i + 1]
                details = json.loads(key)
                next_details = json.loads(following_key)
                if not details.get('title') and next_details.get('title'):
                    details['title'] = next_details['title']
                    key = json.dumps(details, ensure_ascii=False)
                    value = following_value
                    i += 1  # continue merging with next item
                else:
                    break  # break if no merge is needed
            if isinstance(value, dict):
                value = merge_keys_and_delete_next(value)
            new_data[key] = value
            i += 1
        return new_data

    updated_parts = merge_keys_and_delete_next(parts)

    with open("UKparts_updated.json", "w", encoding="utf-8") as f:
        # Dump the data as JSON, maintaining the order of keys
        json.dump(updated_parts, f, indent=4, ensure_ascii=False)
#asyncio.run(main())
# async def mains():
#     with open("UKparts.json") as f:
#         parts = json.load(f)
#     def merge_keys_and_delete_next(data):
#         items = list(data.items())
#         i = 0
#         while i < len(items):
#             key, value = items[i]
#             if value == {}:
#                 if i + 1 < len(items):
#                     following_key, following_value = items[i + 1]
#                     details = json.loads(key)
#                     next_details = json.loads(following_key)
#                     if not details.get('title') and next_details.get('title'):
#                         details['title'] = next_details['title']
#                         updated_key = json.dumps(details)
#                         data[updated_key] = following_value
#                         del data[key]
#                         del data[following_key]
#                         items = list(data.items())
#                         continue
#             if isinstance(value, dict):
#                 merge_keys_and_delete_next(value)
#             i += 1

#     merge_keys_and_delete_next(parts)

#     with open("UKparts_updateds.json", "w") as f:
#         json.dump(parts, f, indent=4)

# doc = fitz.open("/Users/jamesqxd/Documents/norgai-docs/BND/residential-sectional-doors-pg.pdf")
# async def okay():
#     images = []
#     for page in range(1, doc.page_count):
#         page = doc[page]
#         image = utils.encode_page_as_base64(page, xzoom=2, yzoom=2)
#         images.append(image)

#     messages = utils.message_template_vision("What are the installation requirements? Specifically the stormshield PFI... I need to know the Minimum Sideroom", *images)
#     response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o", response_format="text")
#     message_content = response.choices[0].message.content
#     utils.print_coloured(message_content, "green")

# asyncio.run(okay())
# with open("zzplit_apx.md", 'r') as f:
#     toc_md_apx_lines = f.readlines()
        
# formatted_section_name = "Schedule 2"
# filtered_remaining_content_section_lines = [
#             line for line in toc_md_apx_lines
#             if "2" in line and "Schedule" in line
#         ]
# matches = process.extractBests(
#                     formatted_section_name, 
#                     [line for line in toc_md_apx_lines], 
#                     score_cutoff=80, 
#                     limit=100
#                 )
# for match in matches:
#     print(match)


# with open("ukCOMPANIESACT2006_master_toc.json", "r") as f:
#     master_toc = json.load(f)
# toc_models = [schemas.convert_to_model(item) for item in master_toc]
# flattened_toc = schemas.flatten_toc(toc_models)
# for item in toc_models:
#     # print(item)
#     # print("\n")
#     current_index = flattened_toc.index(item)
#     if current_index + 1 < len(flattened_toc):
#         next_item = flattened_toc[current_index + 1]
#         print(f"{item.section} {item.number} {item.title} - {next_item.section} {next_item.number} {next_item.title}")
#         print(len(item.children))
with open("final_apx_content_uk.json", "r") as f:
    apx_content = json.load(f)
with open("final_content_uk.json", "r") as f:
    content = json.load(f)
content["contents"].extend(apx_content["contents"])
with open("final_combined_content_uk.json", "w") as f:
    json.dump(content, f, indent=4)
exit()
with open("UKparts_updated.json", "r", encoding="utf-8") as f:
    parts = json.load(f, object_pairs_hook=OrderedDict)

master_toc = schemas.parse_toc_dict(parts, pre_process=False)
master_toc_save = [toc.model_dump() for toc in master_toc]
with open(f"uk_master_toc.json", "w") as f:
    json.dump(master_toc_save, f, indent=2, default=lambda x: x.dict())