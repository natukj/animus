from __future__ import annotations
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

JSONstr = NewType('JSONstr', str)

class TableOfContentsChild(BaseModel):
    number: str
    title: str

class TableOfContents(BaseModel):
    section: Optional[str]
    number: str
    title: str
    children: Optional[List[Union[TableOfContents, TableOfContentsChild]]]

    def find_child(self, section: Optional[str], number: str) -> Optional[Union[TableOfContents, TableOfContentsChild]]:
        """find an existing child by section and number."""
        if not self.children:
            return None
        for child in self.children:
            if isinstance(child, TableOfContents) and child.section == section and child.number == number:
                return child
            if isinstance(child, TableOfContentsChild) and child.number == number:
                return child
        return None

    def add_child(self, child: Union[TableOfContents, TableOfContentsChild]):
        """add a new child or merge with an existing one."""
        if not self.children:
            self.children = []

        if isinstance(child, TableOfContents):
            existing_child = self.find_child(child.section, child.number)
            if existing_child and isinstance(existing_child, TableOfContents):
                existing_child.children = merge_children(existing_child.children, child.children or [])
            else:
                self.children.append(child)
        else:
            if not any(isinstance(existing, TableOfContentsChild) and existing.number == child.number for existing in self.children):
                self.children.append(child)


class Contents(BaseModel):
    level: JSONstr | None
    sublevel: JSONstr | str | None
    subsublevel: JSONstr | str | None
    toc: List[Union[TableOfContents, TableOfContentsChild]]


class TableOfContentsDict(BaseModel):
    contents: List[Contents]

def merge_children(existing_children: Optional[List[Union[TableOfContents, TableOfContentsChild]]], new_children: List[Union[TableOfContents, TableOfContentsChild]]) -> List[Union[TableOfContents, TableOfContentsChild]]:
    """merge a list of new children into existing children."""
    if existing_children is None:
        existing_children = []

    existing_dict = {child.number: child for child in existing_children if isinstance(child, TableOfContents)}

    for new_child in new_children:
        if isinstance(new_child, TableOfContents):
            if new_child.number in existing_dict:
                existing_child = existing_dict[new_child.number]
                existing_child.children = merge_children(existing_child.children, new_child.children or [])
            else:
                existing_children.append(new_child)
        else:
            if not any(isinstance(child, TableOfContentsChild) and child.number == new_child.number for child in existing_children):
                existing_children.append(new_child)

    return existing_children

class PDFParser(BaseParser):
    """
    Parses a PDF that contains a Table of Contents (ToC) and extracts structured content to a dict.
    Absolutely hinders on the ToC and Markdown formatting of the toc.
    """
    
    def __init__(self, rate_limit: int = 50):
        super().__init__(rate_limit)
        self.document = None
        self.toc_pages = None
        self.toc_md_string = None
        self.content_md_string = None
        self.toc_hierarchy_schema = None
        self.adjusted_toc_hierarchy_schema = None
        self.master_toc = None
        self.no_md_flag = False

    async def load_document(self, file: Union[UploadFile, str]) -> None:
        """
        Load a PDF document from an uploaded file or a file path.
        """
        if isinstance(file, UploadFile):
            file_content = await file.read()
            self.document = fitz.open(stream=file_content, filetype="pdf")
        elif isinstance(file, str):
            self.document = fitz.open(file)
        else:
            raise ValueError("file must be an instance of UploadFile or str.")
        self.toc_md_string, self.content_md_string = await self.generate_md_string()
        self.toc_md_string_lines = self.toc_md_string.split("\n").lower()
        self.content_md_string_lines = self.content_md_string.split("\n").lower()
        self.toc_hierarchy_schema = await self.generate_toc_hierarchy_schema()
        with open("zztoc_md_string.md", "w") as f:
            f.write(self.toc_md_string) 
        with open("zzcontent_md_string.md", "w") as f:
            f.write(self.content_md_string)
        # self.no_md_flag = True
        # with open ("toc_hierarchy_schema.json", "r") as f:
        #     self.toc_hierarchy_schema = json.load(f)
        # with open("zztoc_md_string.md", "r") as f:
        #     self.toc_md_string = f.read()
        # with open("zzcontent_md_string.md", "r") as f:
        #     self.content_md_string = f.read()

    def encode_page_as_base64(self, page: fitz.Page):
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        return base64.b64encode(pix.tobytes()).decode('utf-8')
    
    async def find_toc_pages(self) -> List[int]:
        """
        Find the ToC pages in the document.
        """
        # vol9
        #return [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31]
        # uk companies act
        #return [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58]
        
        async def verify_toc_page(page: fitz.Page) -> bool:
            nonlocal checked_pages
            if page.number in checked_pages:
                utils.print_coloured(checked_pages[page.number], "cyan")
                return checked_pages[page.number]
            while True:
                messages=[
                    {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Is this page a Table of Contents? If there are no page numbers it is most likely not. Respond with ONLY 'yes' or 'no'"},
                        {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{self.encode_page_as_base64(page)}",
                        },
                        },
                    ],
                    }
                ]
                response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o", response_format="text")
                message_content = response.choices[0].message.content
                if message_content.lower() == "yes" or "yes" in message_content.lower():
                    utils.print_coloured(message_content, "green")
                    checked_pages[page.number] = True
                    return True
                elif message_content.lower() == "no" or "no" in message_content.lower():
                    utils.print_coloured(message_content, "red")
                    checked_pages[page.number] = False
                    return False
                
        toc_pages = []
        i = 0
        check_right = True 
        #for i in range(self.document.page_count):
        while i < self.document.page_count - 1:
            page = self.document[i]
            page_rect = page.rect
            if check_right:
                rect = fitz.Rect(page_rect.width * 0.7, 0, page_rect.width, page_rect.height)
            else:
                rect = fitz.Rect(0, 0, page_rect.width * 0.3, page_rect.height)
            words = page.get_text("words", clip=rect)
            words = [w for w in words if fitz.Rect(w[:4]) in rect]
            page_num_count = sum(1 for w in words if w[4].isdigit())
            percentage = page_num_count / len(words) if len(words) > 0 else 0
            i += 1
            if percentage > 0.4:
                toc_pages.append(i)
            # logic if there are not toc page nums
            if i == 30 and check_right:
                if not toc_pages:
                    check_right = False
                    i = 0
        if not toc_pages:
            raise ValueError("No Table of Contents found - can not proceed.")
        utils.print_coloured(f"Potential ToC pages: {toc_pages}", "yellow")
        # verify the first and last pages
        start_index = 0
        end_index = len(toc_pages) - 1
        start_count = end_count = 0
        start_found = end_found = False
        checked_pages: Dict[int, bool] = {} 
        while start_index <= end_index:
            if start_found and end_found:
                break
            tasks = []
            if not start_found:
                utils.print_coloured(f"Is {toc_pages[start_index] - start_count} a Toc page?", "yellow")
                tasks.append(self.rate_limited_process(verify_toc_page, self.document[toc_pages[start_index] - start_count]))
            if not end_found:
                utils.print_coloured(f"Is {toc_pages[end_index] + end_count} a ToC page?", "yellow")
                tasks.append(self.rate_limited_process(verify_toc_page, self.document[toc_pages[end_index] + end_count]))
            
            results = await asyncio.gather(*tasks)
            if not start_found:
                start_result = results[0]
                if start_result:
                    if toc_pages[start_index] == 0 or toc_pages[start_index] - start_count == 0:
                        start_found = True
                    else:
                        utils.print_coloured(f"Is {toc_pages[start_index] - start_count - 1} a ToC page?", "yellow")
                        prev_page_result = await self.rate_limited_process(verify_toc_page, self.document[toc_pages[start_index] - start_count - 1])
                    if prev_page_result:
                        start_count += 1
                    else:
                        start_found = True
                else:
                    start_index += 1

            if not end_found:
                end_result = results[-1]
                if end_result:
                    utils.print_coloured(f"Is {toc_pages[end_index] + end_count + 1} a ToC page?", "yellow")
                    next_page_result = await self.rate_limited_process(verify_toc_page, self.document[toc_pages[end_index] + end_count + 1])
                    if next_page_result:
                        end_count += 1
                    else:
                        end_found = True
                else:
                    end_index -= 1
                
                if start_index > end_index:
                    return []
            
        verified_toc_pages = list(range(max(0, toc_pages[start_index] - start_count), toc_pages[end_index] + end_count + 1))
        utils.print_coloured(f"Verified ToC pages: {verified_toc_pages}", "green")
        return verified_toc_pages
    
    async def generate_md_string(self) -> Tuple[str, str]:
        """
        Generate Markdown strings for toc and content.
        """
        self.toc_pages = await self.find_toc_pages()
        last_toc_page = self.toc_pages[-1] + 1
        content_pages = list(range(last_toc_page, self.document.page_count))
        toc_md_string = self.to_markdown(self.document, self.toc_pages)
        content_md_string = self.to_markdown(self.document, content_pages)
        # with open("zztoc_md_string.md", "r") as f:
        #     toc_md_string = f.read()
        # with open("zzcontent_md_string.md", "r") as f:
        #     content_md_string = f.read()
        return toc_md_string, content_md_string
    
    async def map_toc_to_hierarchy(self, toc_lines: List[str], toc_hierarchy_schema: Dict[str, str]) -> Dict[str, str]:
        """
        Map the ToC sections to the hierarchy schema without llm
            - done to fix llm issue in generate_toc_hierarchy_schema
            where it will sometimes give {'Chapter': '#',...} instead of {'Chapter': '##',...}
        """
        hierarchy_map = {}
        updated_toc_hierarchy_schema = toc_hierarchy_schema.copy()
        for line in toc_lines:
            if line.strip().startswith('#'):
                level = '#' * line.count('#')
                heading_text = line.strip('#').strip()
                key = heading_text.split('—')[0].split(maxsplit=1)[0]

                if key not in hierarchy_map or len(hierarchy_map[key]) > len(level):
                    hierarchy_map[key] = level

        for key, schema_level in toc_hierarchy_schema.items():
            if key in hierarchy_map:
                updated_toc_hierarchy_schema[key] = hierarchy_map[key]
                    
        return updated_toc_hierarchy_schema

    async def generate_toc_hierarchy_schema(self) -> Dict[str, str]:
        """
        Generate a hierarchy schema for the ToC hierarchy, eg
        {
            'Chapter': '#',
            'Part': '##',
            'Division': '###',
            'Subdivision': '####'
        }
        """
        combined_toc_hierarchy_schema = {}

        async def split_lines(lines: List[str], num_parts: int) -> List[List[str]]:
            length = len(lines)
            part_size = length // num_parts
            parts = []
            for i in range(num_parts):
                start = i * part_size
                end = (i + 1) * part_size if i < num_parts - 1 else length
                parts.append(lines[start:end])
            return parts
        
        async def process_function(toc_md_section_joined_lines: str) -> Dict[str, str]:
            if self.no_md_flag:
                USER_PROMPT = prompts.TOC_HIERARCHY_USER_PROMPT_NOMD.format(TOC_HIERARCHY_SCHEMA_TEMPLATE=prompts.TOC_HIERARCHY_SCHEMA_TEMPLATE, toc_md_string=toc_md_section_joined_lines)
            else:
                USER_PROMPT = prompts.TOC_HIERARCHY_USER_PROMPT.format(TOC_HIERARCHY_SCHEMA_TEMPLATE=prompts.TOC_HIERARCHY_SCHEMA_TEMPLATE, toc_md_string=toc_md_section_joined_lines)
            messages = [
                {"role": "system", "content": prompts.TOC_HIERARCHY_SYS_PROMPT},
                {"role": "user", "content": USER_PROMPT}
            ]
            while True:
                response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
                try:
                    if not response.choices or not response.choices[0].message:
                        print("Unexpected response structure:", response)
                        raise Exception("Unexpected response structure")
                    
                    message_content = response.choices[0].message.content
                    toc_hierarchy_schema = json.loads(message_content)
                    print(f"Schema: {json.dumps(toc_hierarchy_schema, indent=4)}")
                    if not self.no_md_flag:
                        updated_toc_hierarchy_schema = await self.map_toc_to_hierarchy(toc_md_section_lines, toc_hierarchy_schema)
                        if updated_toc_hierarchy_schema == toc_hierarchy_schema:
                            print("No changes to ToC Hierarchy Schema")
                        else:
                            print(updated_toc_hierarchy_schema)
                        return updated_toc_hierarchy_schema
                    else:
                        return toc_hierarchy_schema
                except json.JSONDecodeError:
                    print("Error decoding JSON for ToC Hierarchy Schema")
                    raise

        async def process_pages(page_nums: List[int], guide_schema: str = None) -> Dict[str, str]:
            toc_md_toc_section_str = self.to_markdown(self.document, page_nums)
            if not guide_schema:
                USER_PROMPT = prompts.TOC_HIERARCHY_USER_PROMPT_VISION.format(toc_md_string=toc_md_toc_section_str)
            else:
                USER_PROMPT = prompts.TOC_HIERARCHY_USER_PROMPT_VISION_PLUS.format(toc_md_string=toc_md_toc_section_str, guide_str=guide_schema)
            page = self.document[page_nums[0]]
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": USER_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{self.encode_page_as_base64(page)}",
                            },
                        }
                    ]
                }
            ]
            if len(page_nums) > 1:
                for next_page_num in page_nums[1:]:
                    next_page = self.document[next_page_num]
                    messages[0]["content"].append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{self.encode_page_as_base64(next_page)}",
                            },
                        }
                    )
            while True:
                response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
                try:
                    message_content = response.choices[0].message.content
                    toc_hierarchy_schema = json.loads(message_content)
                    # TODO: add logic to check if the lines are in the content
                    return toc_hierarchy_schema
                except json.JSONDecodeError as e:
                    print(f"JSONDecodeError: {e}")
                    print(f"Message content: {message_content}")
                    raise
                except Exception as e:
                    print(f"Error: {e}")

        
        # TODO: must be a better way to determine no md flag
        toc_md_lines = self.toc_md_string.split("\n")
        toc_md_section_lines = [line for line in toc_md_lines if line.startswith('#')]
        utils.print_coloured(f"Number of ToC lines: {len(toc_md_section_lines)} out of {len(toc_md_lines)} with a ratio of {len(toc_md_section_lines) / len(toc_md_lines)}", "yellow")
        if len(toc_md_section_lines) / len(toc_md_lines) > 0.05:
            toc_md_sections = ['\n'.join(section) for section in await split_lines(toc_md_section_lines, 5)]
        else:
            self.no_md_flag = True
            utils.print_coloured("No ToC Flag Set", "yellow")
            grouped_toc_pages = [self.toc_pages[i:i+2] for i in range(0, len(self.toc_pages), 2)]
            guide_schema_dict = await self.rate_limited_process(process_pages, grouped_toc_pages[0])
            guide_schema_list = [f"There are only {len(guide_schema_dict)} levels in the Table of Contents. The levels are as follows:\n"]
            for key, value in guide_schema_dict.items():
                guide_schema_list.append(
                    f"{key}:\n"
                    f"  Level: {value['level']}\n"
                    f"  Description: {value['description']}\n"
                    f"  Example(s): {value['lines']}\n"
                )
            guide_schema_str = "\n".join(guide_schema_list)
            utils.print_coloured(guide_schema_str, "green")
            for key, value in guide_schema_dict.items():
                for line in value["lines"]:
                    if line not in combined_toc_hierarchy_schema:
                        combined_toc_hierarchy_schema[line] = value["level"]

        if not self.no_md_flag:
            schemas = await asyncio.gather(*[self.rate_limited_process(process_function, section) for section in toc_md_sections])
            for schema in schemas:
                for key, value in schema.items():
                    capitalised_key = re.sub(r'\s*\d+$', '', key.capitalize())
                    if capitalised_key not in combined_toc_hierarchy_schema: 
                        combined_toc_hierarchy_schema[capitalised_key] = value
        else:
            schemas = await asyncio.gather(*[self.rate_limited_process(process_pages, page_nums, guide_schema=guide_schema_str) for page_nums in grouped_toc_pages[1:]])
            for schema in schemas:
                for level, content in schema.items():
                    for line in content["lines"]:
                        if line not in combined_toc_hierarchy_schema:
                            combined_toc_hierarchy_schema[line] = level
        ordered_items = sorted(combined_toc_hierarchy_schema.items(), key=lambda x: x[1].count('#'))
        ordered_dict = dict(ordered_items)
        utils.print_coloured(f"{json.dumps(ordered_dict, indent=4)}", "green")

        return combined_toc_hierarchy_schema

    
    async def filter_schema(self, toc_hierarchy_schema: Dict[str, str], content: str, num_sections: int = 5) -> Dict[str, str]:
        """
        Filter the schema to reduce size and complexity.
        """
        lines = self.toc_md_string.split('\n')
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
            formatted_heading = f"{level} {heading}" if not self.no_md_flag else heading
            if formatted_heading in content and heading not in result:
                result[heading] = level
        return result
    
    async def generate_toc_schema(self, levels: Dict[str, str] = None, content: str = None, depth: int = 0, max_depth: int = None) -> List[Dict[str, Any]]:
        """
        Generate a custom schema for the ToC based on the hierarchy schema.
        """
        if levels is None:
            top_level = min(self.toc_hierarchy_schema.values(), key=lambda x: x.count('#'))
            top_level_count = top_level.count('#')
            if top_level_count > 1:
                adjust_count = top_level_count - 1
                levels_unfiltered = {k: v[adjust_count:] for k, v in self.toc_hierarchy_schema.items()}
                self.adjusted_toc_hierarchy_schema = levels_unfiltered
                levels = await self.filter_schema(levels_unfiltered, content)
                #print(f"Adjusted ToC Hierarchy Schema: {json.dumps(levels, indent=4)}")
            else:    
                levels = await self.filter_schema(self.toc_hierarchy_schema, content)
                #print(f"UNadjusted ToC Hierarchy Schema: {json.dumps(levels, indent=4)}")

        if max_depth is None:
            max_depth = max(marker.count('#') for marker in levels.values())

        if depth >= max_depth:
            return [], levels

        current_depth_levels = [name for name, marker in levels.items() if marker.count('#') == depth + 1]
        children, _ = await self.generate_toc_schema(levels, content, depth + 1, max_depth)

        toc_schema = [
            {
                "section": f"string (type of the section, e.g., {level_name})",
                "number": "string (numeric or textual identifier of the section or empty string if not present)",
                "title": "string (title of the section or empty string if not present)",
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
        return toc_schema, levels
    
    async def generate_toc_schema_no_md(self, levels: Dict[str, Dict[str, str]], depth: int = 0, max_depth: int = None, limit: int = None) -> List[Dict[str, Any]]:
        """
        Generate a custom schema for the ToC based on the hierarchy schema (no md).
        """
        if max_depth is None:
            max_depth = max(marker['level'].count('#') for marker in levels.values())
            
        if depth >= max_depth:
            return []

        current_depth_levels = [name for name, marker in levels.items() if marker['level'].count('#') == depth + 1]

        if limit is not None and depth + 1 == max_depth:
            current_depth_levels = current_depth_levels[:limit]
        
        children = await self.generate_toc_schema_no_md(levels, depth + 1, max_depth, limit)

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

    async def process_heading(self, heading: str) -> Dict[str, str]:
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
            print(formatted_line)
            current_part = {
                "section": formatted_line['section'],
                "number": formatted_line['number'],
                "title": formatted_line['title']
            }
            return current_part
        except Exception as e:
            print(f"process_heading error loading json: {e}")

    async def split_toc_parts_into_parts(self, lines: List[str], level_types: List[str]) -> Dict[str, Union[str, Dict]]:
        """
        Split the ToC parts into sub-parts based on the sub-part type, 
        processing headings concurrently while maintaining the original structure.
        """
        parts = {}
        stack = []
        i = 0
        heading_futures = []

        async def process_heading_queue():
            return await asyncio.gather(*[future for future, _ in heading_futures])

        while i < len(lines):
            line = lines[i]
            level = None
            for j, level_type in enumerate(level_types):
                if line.startswith(level_type):
                    level = j
                    break
            if level is not None:
                heading = line.strip()
                j = 1
                while i + j < len(lines) and lines[i + j].startswith(level_types[level].split(" ")[0] + ' '):
                    next_line = lines[i + j].strip().lstrip('#').strip()
                    heading += ' ' + next_line
                    j += 1
                # strip last number from heading (pagenumber)
                heading = re.sub(r'\s\d+$', '', heading)
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
                i += j
            else:
                if stack:
                    if line.strip():
                        if "content" not in stack[-1][1]:
                            stack[-1][1]["content"] = ""
                        stack[-1][1]["content"] += re.sub(r'\s\d+$', '', line.strip()) + '\n'
                i += 1

        processed_headings = await process_heading_queue() 
        for processed_heading, original_heading in zip(processed_headings, [heading for _, heading in heading_futures]):
            def replace_heading(data):
                if isinstance(data, dict):
                    for key in list(data.keys()): 
                        if key == original_heading:
                            data[json.dumps(processed_heading)] = data.pop(original_heading)
                        else:
                            replace_heading(data[key])
            replace_heading(parts)
        return parts
    
    async def split_no_md_toc_parts_into_parts(self, lines: List[str], level_types: List[str, str]) -> Dict[str, Union[str, Dict]]:
        parts = {}
        stack = []
        i = 0
        heading_futures = []

        async def process_heading_queue():
            return await asyncio.gather(*[future for future, _ in heading_futures])
        
        while i < len(lines):
            line = lines[i].strip()
            level = None
            for level_type, level_num in level_types:
                if level_type in line:
                    level = level_num
                    break
            if level is not None:
                heading = line.strip()
                placeholder = str(uuid.uuid4())
                heading_futures.append((self.rate_limited_process(self.process_heading, heading), placeholder))
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
                i += 1
            else:
                if stack:
                    if line.strip():
                        if "content" not in stack[-1][1]:
                            stack[-1][1]["content"] = ""
                        stack[-1][1]["content"] += line.strip() + '\n'
                i += 1

        processed_headings = await process_heading_queue()
        for processed_heading, original_heading in zip(processed_headings, [heading for _, heading in heading_futures]):
            def replace_heading(data):
                if isinstance(data, dict):
                    for key in list(data.keys()): 
                        if key == original_heading:
                            data[json.dumps(processed_heading)] = data.pop(original_heading)
                        else:
                            replace_heading(data[key])
            replace_heading(parts)
        return parts
    
    async def split_toc_into_parts(self) -> Dict[str, Union[str, Dict[str, str]]]:
        """
        Split the ToC into parts based on the hierarchy schema and token count
        """
        lines_dirty = self.toc_md_string.split('\n')
        lines = [line for line in lines_dirty if line.strip()]
        grouped_schema = defaultdict(list)
        for key, value in self.toc_hierarchy_schema.items():
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
        
        if self.no_md_flag:
            sorted_headings = sorted(self.toc_hierarchy_schema.items(), key=lambda x: x[1].count('#'))
            # level_types = [(heading, level.count('#')) for heading, level in sorted_headings[:3]]
            level_types = [(heading, level.count('#')) for heading, level in sorted_headings]
            #level_types = [('SCHEDULES', 1), ('APPENDICES', 1), ('PART', 1)] #RAMSAY NURSES ALWAYS WRONG
            return await self.split_no_md_toc_parts_into_parts(lines, level_types)
        else:
            sorted_headings = sorted(most_common_headings.items(), key=lambda x: len(x[0]))
            level_types = [f"{level[0]} {level[1]}" for level in sorted_headings][:3] # only take the top 3 levels
            return await self.split_toc_parts_into_parts(lines, level_types)
    
    async def generate_formatted_toc(self, level_title: JSONstr, sublevel_title: Union[JSONstr, None], subsublevel_title: Union[JSONstr, None], content: str) -> Tuple[JSONstr, JSONstr, JSONstr, Dict[str, Any]]:

        async def process_function():
            nonlocal sublevel_title
            nonlocal subsublevel_title
            custom_schema, custom_levels = await self.generate_toc_schema(content=content)
            TOC_SCHEMA = {"contents": [json.dumps(custom_schema, indent=4)]}
            
            if self.no_md_flag:
                section_types = ", ".join(custom_levels.keys())
                level_title_dict = json.loads(level_title)
                level_title_str = f"{level_title_dict['section']} {level_title_dict.get('number', '')} {level_title_dict['title']}"
                sublevel_title_str = ""
                subsublevel_title_str = ""
                messages = [
                    {"role": "system", "content": prompts.TOC_SCHEMA_SYS_PROMPT_PLUS},
                    {"role": "user", "content": prompts.TOC_SCHEMA_USER_PROMPT.format(level_title=level_title_str, section_types=section_types, TOC_SCHEMA=TOC_SCHEMA, content=content)}
                ]
                messages_str = json.dumps(messages, indent=4)
                utils.print_coloured(f"{level_title_str} ({self.count_tokens(messages_str)} tokens)", "red")
                sublevel_title = "Complete"
                subsublevel_title = "Complete"
            else:
                section_types = ", ".join(custom_levels.keys())
                level_title_dict = json.loads(level_title)
                level_title_str = f"{level_title_dict['section']} {level_title_dict['number']} {level_title_dict['title']}"
                if sublevel_title:
                    sublevel_title_dict = json.loads(sublevel_title)
                    sublevel_title_str = f"{sublevel_title_dict['section']} {sublevel_title_dict['number']} {sublevel_title_dict['title']}"
                else:
                    sublevel_title_str = ""
                    sublevel_title = "Complete"
                if subsublevel_title:
                    subsublevel_title_dict = json.loads(subsublevel_title)
                    subsublevel_title_str = f"{subsublevel_title_dict['section']} {subsublevel_title_dict['number']} {subsublevel_title_dict['title']}"
                else:
                    subsublevel_title_str = ""
                    subsublevel_title = "Complete"
                messages = [
                    {"role": "system", "content": prompts.TOC_SCHEMA_SYS_PROMPT_PLUS},
                    {"role": "user", "content": prompts.TOC_SCHEMA_USER_PROMPT_PLUS.format(level_title=level_title_str, sublevel_title=sublevel_title_str, subsublevel_title=subsublevel_title_str, section_types=section_types, TOC_SCHEMA=TOC_SCHEMA, content=content)}
                ]
            response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
            if not response.choices or not response.choices[0].message:
                print("Unexpected response structure:", response)
                raise Exception("Unexpected response structure")
            if response.choices[0].finish_reason == "length":
                utils.print_coloured(f"TOO LONG: {level_title_str} / {sublevel_title_str} / {subsublevel_title_str}", "red")
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
                    {"role": "user", "content": prompts.CONTINUE_JSON_PROMPT},
                    {"role": "assistant", "content": remaining_content}]
                combined_messages = messages + additional_messages
                retries = 0
                max_retries = 5
                while retries < max_retries:
                    response2 = await llm.openai_client_chat_completion_request(combined_messages, model="gpt-4o", response_format="text")
                    try:
                        message_content2 = response2.choices[0].message.content
                        utils.print_coloured(message_content2, "yellow")
                        # if message_content2.startswith("},") == False:
                        #     message_content2 = "}," + message_content2
                        if message_content2.startswith(remaining_content) == False:
                            message_content2 = remaining_content + message_content2
                        total_message_content = inital_message_content + message_content2
                        toc_schema = json.loads(total_message_content)
                        utils.print_coloured(f"{level_title_str} / {sublevel_title_str} / {subsublevel_title_str}", "green")
                        return (level_title, sublevel_title, subsublevel_title, toc_schema)
                    except json.JSONDecodeError:
                        retries += 1
                        utils.print_coloured(f"Error decoding TOO LONG JSON ... / {subsublevel_title_str}, attempt {retries}", "red")
                        if retries >= max_retries:
                            raise Exception("Max retries reached, unable to complete JSON")
            try:
                message_content = response.choices[0].message.content
                toc_schema = json.loads(message_content)
                # try:
                #     TableOfContentsDict(**toc_schema)
                # except ValidationError as e:
                #     utils.print_coloured(f"Validation error for {level_title_str} / {sublevel_title_str} / {subsublevel_title_str}: {e}", "red")
                    #raise
                utils.print_coloured(f"{level_title_str} / {sublevel_title_str} / {subsublevel_title_str}", "green")
                return (level_title, sublevel_title, subsublevel_title, toc_schema)
            except json.JSONDecodeError:
                print(f"Error decoding JSON for {level_title} - {sublevel_title}")
                raise

        return await self.rate_limited_process(process_function)
    
    async def generate_formatted_toc_no_md(self, level_title_str: str, level_content: Dict[str, Any], sublevels: Dict[str, Dict[str, str]]) -> Tuple[Tuple[None, None, None], Dict[str, Any]]:
        async def format_toc_no_md():
            custom_schema = await self.generate_toc_schema_no_md(sublevels, limit=3)
            TOC_SCHEMA = {"contents": [json.dumps(custom_schema, indent=4)]}
            section_types = ", ".join(sublevels.keys())
            messages = [
                {"role": "system", "content": prompts.TOC_SCHEMA_SYS_PROMPT_PLUS},
                {"role": "user", "content": prompts.TOC_SCHEMA_USER_PROMPT_PLUS_NOMD.format(level_title_str=level_title_str, section_types=section_types, TOC_SCHEMA=TOC_SCHEMA, level_content=json.dumps(level_content, indent=4))}
            ]
            response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
            if not response.choices or not response.choices[0].message:
                print("Unexpected response structure:", response)
                raise Exception("Unexpected response structure")
            if response.choices[0].finish_reason == "length":
                utils.print_coloured(f"{level_title_str} too long...", "red")
                inital_message_content = response.choices[0].message.content
                split_content = inital_message_content.rsplit('},', 1)
                if len(split_content) == 2:
                    inital_message_content, remaining_content = split_content
                    remaining_content = '},' + remaining_content.strip()
                else:
                    remaining_content = ''
                additional_messages = [
                    {"role": "assistant", "content": inital_message_content},
                    {"role": "user", "content": prompts.CONTINUE_JSON_PROMPT},
                    {"role": "assistant", "content": remaining_content}]
                combined_messages = messages + additional_messages
                retries = 0
                max_retries = 5
                while retries < max_retries:
                    response2 = await llm.openai_client_chat_completion_request(combined_messages, model="gpt-4o", response_format="text")
                    try:
                        message_content2 = response2.choices[0].message.content
                        if message_content2.startswith(remaining_content) == False:
                            message_content2 = remaining_content + message_content2
                        total_message_content = inital_message_content + message_content2
                        toc_schema = json.loads(total_message_content)
                        utils.print_coloured(f"{level_title_str}", "green")
                        return (None, None, None, toc_schema)
                    except json.JSONDecodeError:
                        retries += 1
                        utils.print_coloured(f"Error decoding JSON for {level_title_str}, attempt {retries}", "red")
                        if retries >= max_retries:
                            raise Exception("Max retries reached, unable to complete JSON")
            try:
                message_content = response.choices[0].message.content
                toc_schema = json.loads(message_content)
                utils.print_coloured(f"{level_title_str}", "green")
                return (None, None, None, toc_schema)
            except json.JSONDecodeError:
                print(f"Error decoding JSON for {level_title_str}")
                raise
        return await self.rate_limited_process(format_toc_no_md)
    
    async def extract_toc(self) -> TableOfContentsDict:
        """
        Extract and format the ToC.
        """
        #levels = await self.split_toc_into_parts()
        with open("levels.json", "r") as f:
            levels = json.load(f)
        tasks = []
        all_level_schemas = {"contents": []}
        # with open("levels.json", "w") as f:
        #     json.dump(levels, f, indent=4)

        async def process_level(level_title: JSONstr, level_content: Dict[str, Any], sublevel_title=None, subsublevel_title=None) -> None:
            if "content" in level_content:
                # if there is content, generate the formatted ToC request
                task = asyncio.create_task(self.generate_formatted_toc(level_title, sublevel_title, subsublevel_title, level_content["content"]))
                tasks.append(task)

            if "children" in level_content:
                # process each child level recursively
                for child_title, child_content in level_content["children"].items():
                    if "children" in child_content:
                        # process further children, process them as subsublevels
                        for subchild_title, subchild_content in child_content["children"].items():
                            await process_level(level_title, subchild_content, child_title, subchild_title)
                    else:
                        await process_level(level_title, child_content, child_title)
        
        async def process_level_no_md(level_json_str: str, level_content: Dict[str, Any], depth: int = 1) -> None:
            sublevels = {}
            level_json = json.loads(level_json_str)
            level_section, level_number, level_title = level_json["section"], level_json["number"], level_json["title"]
            level_title_str = f"{level_section} {level_number} " + (level_title if level_title else "")
            if level_content.get("content", "") and not level_title:
                level_title_str += "(the title of this section should be available in the content)"
            sublevels[level_section] = {'level': '#' * depth, 'added_from': 'section'}
            async def process_children(children: Dict[str, Any], current_depth: int) -> None:
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
                    if child_level not in sublevels:
                        sublevels[child_level] = {'level': '#' * (current_depth + 1), 'added_from': added_from}
                    if "children" in child_content:
                        await process_children(child_content["children"], current_depth + 1)
            if "children" in level_content:
                await process_children(level_content["children"], depth)
            task = asyncio.create_task(self.generate_formatted_toc_no_md(level_title_str, level_content, sublevels))
            tasks.append(task) 
            # utils.print_coloured(f"Level: {json.dumps(sublevels, indent=2)}", "cyan")  
            # custom_schema = await self.generate_toc_schema_no_md(sublevels, limit=3)
            # utils.print_coloured(f"Schema: {json.dumps(custom_schema, indent=2)}", "magenta")      

        if not self.no_md_flag:
            for level_title, level_content in levels.items():
                await process_level(level_title, level_content)
        else:
            for level_title, level_content in levels.items():
                await process_level_no_md(level_title, level_content)

        try:
            results = await asyncio.gather(*tasks)
            for level_title, sublevel_title, subsublevel_title, result in results:
                if result and result.get('contents'):
                    all_level_schemas["contents"].append({
                        "level": level_title,
                        "sublevel": sublevel_title,
                        "subsublevel": subsublevel_title,
                        "toc": result['contents']
                    })
        except Exception as e:
            print(f"Error extracting ToC: {e}")

        return all_level_schemas
    
    async def find_existing_section(self, toc: List[TableOfContents], section: str, number: str) -> Optional[TableOfContents]:
        """find an existing section by section and number."""
        for item in toc:
            if item.section == section and item.number == number:
                return item
        return None
    
    async def nest_toc(self, content: Contents) -> TableOfContents:
        """builds a nested table of contents based on content levels"""
        if not content.level:
            if not content.toc:
                raise ValueError("TOC is empty")
            
            def create_table_of_contents(item: Union[TableOfContents, TableOfContentsChild]) -> TableOfContents:
                if isinstance(item, TableOfContents):
                    return TableOfContents(
                        section=item.section,
                        number=item.number,
                        title=item.title,
                        children=[create_table_of_contents(child) for child in item.children] if item.children else None
                    )
                elif isinstance(item, TableOfContentsChild):
                    return TableOfContentsChild(
                        number=item.number,
                        title=item.title,
                    )
                else:
                    raise ValueError(f"Invalid TOC item type: {type(item)}")
            return create_table_of_contents(content.toc[0])
        
        def parse_level(level_json: JSONstr):
            level_dict = json.loads(level_json)
            return level_dict['section'], level_dict['number'], level_dict['title']
        
        def find_nested_toc(tocs: List[Union[TableOfContents, TableOfContentsChild]], section: str, number: str) -> Optional[TableOfContents]:
            """recursively search for a TableOfContents by section and number in nested children"""
            for toc in tocs:
                if isinstance(toc, TableOfContents):
                    if toc.section == section and toc.number == number:
                        return toc
                    found = find_nested_toc(toc.children or [], section, number)
                    if found:
                        return found
            return None
        
        level_section, level_number, level_title = parse_level(content.level)
        result_toc = TableOfContents(section=level_section, number=level_number, title=level_title, children=[])
        if content.sublevel == "Complete":
            level_toc = find_nested_toc(content.toc, level_section, level_number)
            if level_toc:
                result_toc.children = level_toc.children
            else:
                result_toc.children = content.toc 
        else:
            sublevel_section, sublevel_number, sublevel_title = parse_level(content.sublevel)
            sublevel_toc = TableOfContents(section=sublevel_section, number=sublevel_number, title=sublevel_title, children=[])
            result_toc.children = [sublevel_toc]

            if content.subsublevel == "Complete":
                found_sublevel_toc = find_nested_toc(content.toc, sublevel_section, sublevel_number)
                if found_sublevel_toc:
                    utils.print_coloured(f"sublevel_toc: {found_sublevel_toc}", "cyan")
                    sublevel_toc.children = [found_sublevel_toc]
                else:
                    sublevel_toc.children = content.toc
            else:
                subsublevel_section, subsublevel_number, subsublevel_title = parse_level(content.subsublevel)
                subsublevel_toc = TableOfContents(section=subsublevel_section, number=subsublevel_number, title=subsublevel_title, children=[])
                sublevel_toc.children = [subsublevel_toc]

                found_subsublevel_toc = find_nested_toc(content.toc, subsublevel_section, subsublevel_number)
                if found_subsublevel_toc:
                    utils.print_coloured(f"subsublevel_toc: {found_subsublevel_toc}", "green")
                    subsublevel_toc.children = [found_subsublevel_toc]
                else:
                    subsublevel_toc.children = content.toc

        return result_toc
        
    async def merge_toc(self, master_toc: List[TableOfContents], toc: List[TableOfContents], ) -> List[TableOfContents]:
        """
        merge ToC sections
        """
        sorted_schema = sorted(self.toc_hierarchy_schema.items(), key=lambda item: len(item[1]))
        top_level_type = sorted_schema[0][0]
        existing_level = await self.find_existing_section(master_toc, top_level_type, toc.number)
        if existing_level:
            existing_level.children = merge_children(existing_level.children, toc.children or [])
        else:
            master_toc.append(toc)

    async def build_master_toc(self, data: TableOfContentsDict) -> List[TableOfContents]:
        """
        build the master ToC from the split ToC parts
        """
        master_toc: List[TableOfContents] = []
        for content in data.contents:
            toc = await self.nest_toc(content)
            await self.merge_toc(master_toc, toc)
        self.master_toc = [toc.model_dump() for toc in master_toc]
        self.save_toc_to_file(master_toc, "master_toc.json")
        return master_toc
    
    def save_toc_to_file(self, toc: List[TableOfContents], file_name: str):
        """temp for testing"""
        with open(file_name, "w") as file:
            json.dump(toc, file, indent=2, default=lambda x: x.dict())
    
    async def generate_master_toc_content(self) -> Dict[str, Dict[Any]]:
        """
        add the document content to the master ToC.
        """
        # content_md_lines = self.content_md_string.split("\n")
        # content_md_section_lines = [(line, idx) for idx, line in enumerate(content_md_lines) if line.startswith('#')]
        def format_md_lines():
            content_md_lines = self.content_md_string.split("\n")
            content_md_section_lines = []
            processed_lines = []
            for i in range(len(content_md_lines)):
                line = content_md_lines[i]
                if line.startswith('#') and i not in processed_lines:
                    current_part = line.strip()
                    j = 1
                    while i + j < len(content_md_lines) and content_md_lines[i + j].startswith('#'):
                        next_line = content_md_lines[i + j].strip().lstrip('#').strip()
                        current_part += ' ' + next_line
                        processed_lines.append(i + j)
                        j += 1
                    content_md_section_lines.append((current_part, i))
            return content_md_lines, content_md_section_lines
        
        content_md_lines, content_md_section_lines = format_md_lines()
        if self.no_md_flag:
            content_md_section_lines = [(line, idx) for idx, line in enumerate(content_md_lines)]
        with open("zzcontent_md_section_lines.md", "w") as f:
            f.write("\n".join([f"{line} [{idx}]" for line, idx in content_md_section_lines]))

        md_levels = self.adjusted_toc_hierarchy_schema if self.adjusted_toc_hierarchy_schema else self.toc_hierarchy_schema

        def format_section_name(section: str, number: str, title: str) -> str:
            if not self.no_md_flag:
                section_match = process.extractOne(section, md_levels.keys(), score_cutoff=98) if section else None
                md_level = md_levels.get(section_match[0], max(md_levels.values(), key=len) + "#") if section_match else max(md_levels.values(), key=len) + "#"

                formatted_parts = []
                if section and not section in title:
                    formatted_parts.append(section)
                if number and not number in title:
                    formatted_parts.append(number)
                if title:
                    formatted_parts.append(title)

                return f'{md_level} {" ".join(formatted_parts)}'
            else:
                full_section_name = f"{section} {number} {title}".strip()
                section_match = process.extractOne(full_section_name, md_levels.keys(), score_cutoff=98)
                if section_match:
                    utils.print_coloured(f"{full_section_name} -> {section_match[0]} [{section_match[1]}]", "green")
                    return section_match[0]
                variations = [
                    f"{section} {number}".strip(),
                    f"{section} {title}".strip(),
                    f"{number} {title}".strip(),
                    section.strip(),
                    title.strip()
                ]
                for variation in variations:
                    if variation:
                        section_match = process.extractOne(variation, md_levels.keys(), score_cutoff=98)
                        if section_match:
                            utils.print_coloured(f"{variation} -> {section_match[0]} [{section_match[1]}]", "green")
                            return section_match[0]
                utils.print_coloured(f"Could not match: {full_section_name}", "red")
                return full_section_name

            
        def traverse_and_update_toc(master_toc: List[Dict[str, Any]]):
            levels_dict = {"contents": []}

            def convert_to_model(data: Dict[str, Any]) -> Union[TableOfContents, TableOfContentsChild]:
                if 'children' in data:
                    data['children'] = [convert_to_model(child) for child in data['children']]
                    return TableOfContents(**data)
                else:
                    return TableOfContentsChild(**data)

            def flatten_toc(toc_models: List[Union[TableOfContents, TableOfContentsChild]]) -> List[Union[TableOfContents, TableOfContentsChild]]:
                flattened = []
                for model in toc_models:
                    if isinstance(model, TableOfContents):
                        flattened.append(model)
                        if model.children:
                            flattened.extend(flatten_toc(model.children))
                    elif isinstance(model, TableOfContentsChild):
                        flattened.append(model)
                return flattened
            
            remaining_content_md_section_lines = content_md_section_lines.copy()
            def get_section_content(next_section: Tuple[str, str, str], section: Tuple[str, str, str] = None) -> Tuple[str, int]:
                nonlocal remaining_content_md_section_lines
                if section:
                    formatted_section_name = format_section_name(*section)
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
                    next_formatted_section_name = format_section_name(*next_section)
                    next_number = next_section[1] if next_section[1] else ""
                    if next_number:
                        filtered_remaining_content_md_section_lines = [(line, idx) for line, idx in remaining_content_md_section_lines if next_number in line]
                        matches = process.extractBests(next_formatted_section_name, [line for line, _ in filtered_remaining_content_md_section_lines], score_cutoff=80, limit=10)
                    else:
                        matches = process.extractBests(next_formatted_section_name, [line for line, _ in remaining_content_md_section_lines], score_cutoff=80, limit=10)
                    if matches:
                        highest_score = max(matches, key=lambda x: x[1])[1]
                        unique_scores = sorted(set([match[1] for match in matches]))
                        if len(unique_scores) > 1:
                            second_highest_score = sorted(set([match[1] for match in matches]))[-2]
                            if highest_score - second_highest_score <= 5 and second_highest_score >= 95:
                                #Match: 160 Appointment of directors of public company to be voted on individually: 160 (appointment of directors of public company to be voted on individually). [4746]
                                # from: [('160 (appointment of directors of public company to be voted on individually).', 99), ('**160****Appointment of directors of public company to be voted on individually**', 98), ('**1160 Meaning of “subsidiary” etc: power to amend**', 86)]
                                highest_score_matches = [match for match in matches if match[1] == highest_score]
                                second_highest_score_matches = [match for match in matches if match[1] == second_highest_score]
                                formatted_highest_matches = [match for match in highest_score_matches if match[0].lstrip().startswith(('#', '*', '_'))]
                                formatted_second_highest_matches = [match for match in second_highest_score_matches if match[0].lstrip().startswith(('#', '*', '_'))]
                                if formatted_second_highest_matches and not formatted_highest_matches:
                                    highest_score = second_highest_score
                        highest_score_matches = [match for match in matches if match[1] == highest_score]
                        matched_line = min(highest_score_matches, key=lambda x: next(idx for line, idx in remaining_content_md_section_lines if line == x[0]))[0]
                        line_idx = next(idx for line, idx in remaining_content_md_section_lines if line == matched_line)
                        utils.print_coloured(f"Match: {next_formatted_section_name}: {matched_line} [{line_idx}]", "yellow")
                        if "172 Duty to promote the success of the company" in next_formatted_section_name:
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
                    line_idx = len(content_md_lines)

                section_content = "\n".join(content_md_lines[start_line_idx:line_idx-1])
                num_tokens = self.count_tokens(section_content)
                remaining_content_md_section_lines = [item for item in remaining_content_md_section_lines if item[1] >= line_idx]
                return section_content, num_tokens
                    

            def traverse_sections(sections: List[Union[TableOfContents, TableOfContentsChild]], parent_dict: Dict[str, Any], flattened_toc: List[Union[TableOfContents, TableOfContentsChild]]):
                for section in sections:
                    if isinstance(section, TableOfContents):
                        #formatted_section_name = format_section_name(section.section, section.number, section.title)
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
                            section_content, section_tokens = get_section_content(next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, TableOfContents) else ("", next_item.number, next_item.title))
                            # if len(section_content) > len(formatted_section_name)*1.3:
                            #     section_dict["content"] = section_content
                            #     section_dict["tokens"] = section_tokens


                        if section.children:
                            traverse_sections(section.children, section_dict, flattened_toc)
                    
                    elif isinstance(section, TableOfContentsChild):
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
                            section_content, section_tokens = get_section_content(next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, TableOfContents) else ("", next_item.number, next_item.title))
                            child_dict["content"] = section_content
                            child_dict["tokens"] = section_tokens
                        else:
                            section_content, section_tokens = get_section_content(next_section="")
                            child_dict["content"] = section_content
                            child_dict["tokens"] = section_tokens
            
            toc_models = [convert_to_model(item) for item in master_toc]
            flattened_toc = flatten_toc(toc_models)
            
            for item in toc_models:
                formatted_section_name = format_section_name(item.section, item.number, item.title)
                section_dict = {
                    "section": item.section,
                    "number": item.number,
                    "title": item.title,
                    "content": "",
                    "tokens": 0,
                    "children": []
                }
                levels_dict["contents"].append(section_dict)
                
                current_index = flattened_toc.index(item)
                if current_index + 1 < len(flattened_toc):
                    next_item = flattened_toc[current_index + 1]
                    section_content, section_tokens = get_section_content(section=(item.section, item.number, item.title), next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, TableOfContents) else ("", next_item.number, next_item.title))
                    if len(section_content) > len(formatted_section_name)*1.3:
                        section_dict["content"] = section_content
                        section_dict["tokens"] = section_tokens
                
                traverse_sections(item.children, section_dict, flattened_toc)
            
            return levels_dict
        
        return traverse_and_update_toc(self.master_toc)

        
    
    async def parse(self, file: Union[UploadFile, str]) -> Dict[str, Dict[Any]]:
        """
        Main method to parse the PDF content.
        """
        await self.load_document(file)
        # toc = await self.extract_toc()
        # with open("toc.json", "w") as f:
        #     json.dump(toc, f, indent=4)
        # data = TableOfContentsDict(**toc)
        # await self.build_master_toc(data)
        with open("master_toc.json", "r") as f:
            self.master_toc = json.load(f)
        content_dict = await self.generate_master_toc_content()
        return content_dict