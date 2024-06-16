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

with open("UKparts_updated.json", "r", encoding="utf-8") as f:
    parts = json.load(f, object_pairs_hook=OrderedDict)

master_toc = schemas.parse_toc_dict(parts, pre_process=False)
master_toc_save = [toc.model_dump() for toc in master_toc]
with open(f"uk_master_toc.json", "w") as f:
    json.dump(master_toc_save, f, indent=2, default=lambda x: x.dict())