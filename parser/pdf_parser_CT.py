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
    def __init__(self, toc_parser: PDFToCParser, rate_limit: int = 50) -> None:
        """
        Initialise the PDFCTParser with a reference to the PDFToCParser instance.
        
        :param toc_parser: An instance of PDFToCParser containing the parsed data.
        """
        super().__init__(rate_limit)
        #self.toc_parser = toc_parser
        self.doc_title = toc_parser.doc_title
        self.toc_md_lines = toc_parser.toc_md_lines
        self.content_md_lines = toc_parser.content_md_lines
        self.master_toc = toc_parser.master_toc

    async def create_master_toc(self) -> None:
        parts = {}
        stack = []
        heading_futures = []
        item_futures = []
        item_buffer = []
        for line in self.toc_md_lines:
            stripped_line = line.strip()
            if stripped_line.startswith("#"):
                if item_buffer:
                    placeholder = str(uuid.uuid4())
                    item_futures.append((self.rate_limited_process(self.process_items, '\n'.join(item_buffer)), placeholder))
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
                heading_futures.append((self.rate_limited_process(self.process_heading, heading), placeholder))
            else:
                if stripped_line:
                    item_buffer.append(stripped_line)

        if item_buffer:
            placeholder = str(uuid.uuid4())
            item_futures.append((self.rate_limited_process(self.process_items, '\n'.join(item_buffer)), placeholder))
            if stack:
                current = stack[-1][1]
                current["contents"] = placeholder

        processed_headings, processed_items = await asyncio.gather(
            self.process_queue(heading_futures),
            self.process_queue(item_futures)
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
        with open(f"{self.file_name}_parts.json", "w") as f:
            json.dump(parts, f, indent=2)
        utils.print_coloured("Parts created", "green")
        master_toc = schemas.parse_toc_dict(parts)
        self.master_toc = [toc.model_dump() for toc in master_toc]
        with open(f"{self.file_name}_master_toc.json", "w") as f:
            json.dump(self.master_toc, f, indent=2, default=lambda x: x.dict())
        utils.print_coloured("Master TOC created", "green")
    
    def format_section_name(self, section: str, number: str, title: str) -> str:
        formatted_parts = []
        if section and not section in title:
            formatted_parts.append(section)
        if number and not number in title:
            formatted_parts.append(number)
        if title:
            formatted_parts.append(title)

        return f'{" ".join(formatted_parts)}'
    
    def add_content_to_master_toc(self) -> Dict[str, Dict[str, Any]]:
        remaining_content_md_section_lines = [(line, idx) for idx, line in enumerate(self.content_md_lines) if line.startswith('#')]
        master_toc_dict = {"contents": []}
        def get_section_content(next_section: Tuple[str, str, str], section: Tuple[str, str, str] = None) -> Tuple[str, int]:
            nonlocal remaining_content_md_section_lines
            if section:
                formatted_section_name = self.format_section_name(*section)
                start_matches = process.extractBests(formatted_section_name, [line for line, _ in remaining_content_md_section_lines], score_cutoff=80, limit=10)
                if start_matches:
                    start_highest_score = max(start_matches, key=lambda x: x[1])[1]
                    start_highest_score_matches = [match for match in start_matches if match[1] == start_highest_score]
                    start_matched_line = min(start_highest_score_matches, key=lambda x: next(idx for line, idx in remaining_content_md_section_lines if line == x[0]))[0]
                    start_line_idx = next(idx for line, idx in remaining_content_md_section_lines if line == start_matched_line)
                    utils.print_coloured(f"Start Match: {formatted_section_name}: {start_matched_line} [{start_line_idx}]", "cyan")
                else:
                    print(f"Could not match start: {formatted_section_name}")
                    start_line_idx = remaining_content_md_section_lines[0][1]
            else:
                start_line_idx = remaining_content_md_section_lines[0][1]

            if next_section:
                next_formatted_section_name = self.format_section_name(*next_section)
                next_number = next_section[1] if next_section[1] else ""
                if next_number:
                    filtered_remaining_content_md_section_lines = [(line, idx) for line, idx in remaining_content_md_section_lines if next_number in line]
                    matches = process.extractBests(next_formatted_section_name, [line for line, _ in filtered_remaining_content_md_section_lines], score_cutoff=80, limit=10)
                else:
                    matches = process.extractBests(next_formatted_section_name, [line for line, _ in remaining_content_md_section_lines], score_cutoff=80, limit=10)
                if matches:
                    highest_score = max(matches, key=lambda x: x[1])[1]
                    highest_score_matches = [match for match in matches if match[1] == highest_score]
                    matched_line = min(highest_score_matches, key=lambda x: next(idx for line, idx in remaining_content_md_section_lines if line == x[0]))[0]
                    line_idx = next(idx for line, idx in remaining_content_md_section_lines if line == matched_line)
                    utils.print_coloured(f"{next_formatted_section_name} -> {matched_line} [{line_idx}]", "green")
                    if "<add problematic line here>" in next_formatted_section_name:
                        print(f"Match: {next_formatted_section_name}: {matched_line} [{line_idx}]")
                        print("from:", matches)
                else:
                    i = 0
                    for line, idx in remaining_content_md_section_lines:
                        print(f"Line: {line} [{idx}]")
                        i += 1
                        if i > 10:
                            break
                    raise ValueError(f"Could not match end: {next_formatted_section_name}")
            else:
                line_idx = len(self.content_md_lines)

            section_content = "\n".join(self.content_md_lines[start_line_idx:line_idx-1])
            num_tokens = utils.count_tokens(section_content)
            remaining_content_md_section_lines = [item for item in remaining_content_md_section_lines if item[1] >= line_idx]
            return section_content, num_tokens
        
        def traverse_sections(sections: List[Union[schemas.TableOfContents, schemas.TableOfContentsChild]], parent_dict: Dict[str, Any], flattened_toc: List[Union[schemas.TableOfContents, schemas.TableOfContentsChild]]):
            for section in sections:
                if isinstance(section, schemas.TableOfContents):
                    section_dict = {
                        "section": section.section,
                        "number": section.number,
                        "title": section.title,
                        "content": "",
                        "tokens": 0,
                        "children": []
                    }
                    parent_dict["children"].append(section_dict)

                    current_index = flattened_toc.index(section)
                    if current_index + 1 < len(flattened_toc):
                        next_item = flattened_toc[current_index + 1]
                        section_content, section_tokens = get_section_content(next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, schemas.TableOfContents) else ("", next_item.number, next_item.title))

                    if section.children:
                        traverse_sections(section.children, section_dict, flattened_toc)
                
                elif isinstance(section, schemas.TableOfContentsChild):
                    child_dict = {
                        "number": section.number,
                        "title": section.title,
                        "content": "",
                        "tokens": 0
                    }
                    parent_dict["children"].append(child_dict)

                    current_index = flattened_toc.index(section)
                    if current_index + 1 < len(flattened_toc):
                        next_item = flattened_toc[current_index + 1]
                        section_content, section_tokens = get_section_content(next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, schemas.TableOfContents) else ("", next_item.number, next_item.title))
                        child_dict["content"] = section_content
                        child_dict["tokens"] = section_tokens
                    else:
                        section_content, section_tokens = get_section_content(next_section="")
                        child_dict["content"] = section_content
                        child_dict["tokens"] = section_tokens

        toc_models = [schemas.convert_to_model(item) for item in self.master_toc]
        flattened_toc = schemas.flatten_toc(toc_models)
        
        for item in toc_models:
            section_dict = {
                "section": item.section,
                "number": item.number,
                "title": item.title,
                "content": "",
                "tokens": 0,
                "children": []
            }
            master_toc_dict["contents"].append(section_dict)
            
            current_index = flattened_toc.index(item)
            if current_index + 1 < len(flattened_toc):
                next_item = flattened_toc[current_index + 1]
                section_content, section_tokens = get_section_content(section=(item.section, item.number, item.title), next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, schemas.TableOfContents) else ("", next_item.number, next_item.title))
            
            traverse_sections(item.children, section_dict, flattened_toc)

        return master_toc_dict
    
    async def fake_create_master_toc(self) -> None:
        with open("master_toc.json", "r") as f:
            self.master_toc = json.load(f)
    
    async def parse(self) -> Dict[str, Dict[str, Any]]:
        #await self.create_master_toc()
        await self.fake_create_master_toc()
        master_toc_dict = self.add_content_to_master_toc()
        return master_toc_dict
    
    