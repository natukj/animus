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
import llm, prompts, schemas, utils
from parser.base_parser import BaseParser
from parser.pdf_parser_ToC import PDFToCParser

class PDFCTParser(BaseParser):
    def __init__(self, toc_parser: PDFToCParser) -> None:
        """
        Initialise the PDFCTParser with a reference to the PDFToCParser instance.
        
        :param toc_parser: An instance of PDFToCParser containing the parsed data.
        """
        super().__init__(toc_parser.rate_limit)
        self.toc_parser = toc_parser
        self.toc_md_lines = toc_parser.toc_md_lines
        self.content_md_lines = toc_parser.content_md_lines
        self.master_toc = None

    async def create_master_toc(self) -> None:
        """
        Split the Table of Contents into its constituent parts.
        """
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
                    "section": formatted_line.get('section', ""),
                    "number": formatted_line.get('number', ""),
                    "title": formatted_line.get('title', "")
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
                utils.print_coloured(f"process_items error loading json: {e}", "red")

        async def process_queue(futures):
            return await asyncio.gather(*[future for future, _ in futures])

        for line in self.toc_md_lines:
            stripped_line = line.strip()
            if stripped_line.startswith("#"):
                if item_buffer:
                    placeholder = str(uuid.uuid4())
                    item_futures.append((process_items('\n'.join(item_buffer)), placeholder))
                    item_futures.append((self.rate_limited_process(process_items, '\n'.join(item_buffer)), placeholder))
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
                heading_futures.append((self.rate_limited_process(process_heading, heading), placeholder))
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
                replace(data)

        replace_placeholders(parts, heading_futures, processed_headings)
        replace_placeholders(parts, item_futures, processed_items)
        with open("parts.json", "w") as f:
            json.dump(parts, f, indent=2)
        utils.print_coloured("Parts created", "green")
        master_toc = schemas.parse_toc_dict(parts)
        self.master_toc = [toc.model_dump() for toc in master_toc]
        with open("master_toc.json", "w") as f:
            json.dump(self.master_toc, f, indent=2, default=lambda x: x.dict())
        utils.print_coloured("Master TOC created", "green")
    
