from __future__ import annotations
from pydantic import BaseModel, ValidationError
from typing import Union, Any, Optional, Dict, Tuple, List, NewType
import json
import asyncio
import re
from fastapi import UploadFile
import fitz
from collections import Counter, defaultdict
from thefuzz import process  
import llm, prompts
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
    level: JSONstr
    sublevel: JSONstr | str
    subsublevel: JSONstr | str
    toc: List[TableOfContents]


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
    """Parses Legal (Australian Legislation) PDFs into Table of Contents (ToC)
    and creates dict for each item in the ToC with the section, number, title and content."""
    
    def __init__(self, rate_limit: int = 30):
        super().__init__(rate_limit)
        self.document = None
        self.toc_md_string = None
        self.content_md_string = None
        #self.toc_hierarchy_schema = {'Chapter': '##', 'Part': '###', 'Division': '####', 'Subdivision': '#####', 'Guide': '#####', 'Operative provisions': '#####'}
        #self.adjusted_toc_hierarchy_schema = {'Chapter': '#', 'Part': '##', 'Division': '###', 'Subdivision': '####', 'Guide': '####', 'Operative provisions': '####'}
        self.toc_hierarchy_schema = None
        self.adjusted_toc_hierarchy_schema = None
        self.toc_schema = None
        self.master_toc = None

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
        self.toc_md_string, self.content_md_string = self.generate_md_string()
        self.toc_hierarchy_schema = await self.generate_toc_hierarchy_schema()
        #self.toc_schema = await self.generate_toc_schema()
        #print(json.dumps(self.toc_schema, indent=4))
    
    def find_first_toc_page_no(self) -> int:
        """
        Find the first ToC page number in the document.
        """
        consecutive_toc_like_pages = 0
        for page_number in range(self.document.page_count):
            page = self.document[page_number]
            blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]
            if self.is_toc_like_page(blocks):
                consecutive_toc_like_pages += 1
                if consecutive_toc_like_pages >= 2:  # At least two consecutive TOC-like pages
                    return page_number - 1
            else:
                consecutive_toc_like_pages = 0
        print("Table of Contents not found.")
        return 0

    def is_toc_like_page(self, blocks: List[dict]) -> bool:
        """
        Determine if a page is ToC-like based on the text blocks.
        """
        toc_indicators = sum(1 for block in blocks for line in block['lines'] if self.is_toc_entry(line['spans']))
        return toc_indicators >= len(blocks) / 2

    def is_toc_entry(self, spans: List[dict]) -> bool:
        """
        Assess if the spans in a line are characteristic of ToC entries: small font, consistent, number-heavy.
        """
        text = " ".join(span['text'] for span in spans)
        font_sizes = [span['size'] for span in spans]
        return all(span['size'] < 12 for span in spans) and '...' not in text and any(char.isdigit() for char in text)

    def find_last_toc_page_no(self, start_page: int) -> int:
        """
        Find the last ToC page number in the document, starting from a given page.
        """
        current_fonts = {}
        previous_fonts = {}
        toc_end_page = start_page
        
        for page_number in range(start_page, self.document.page_count):
            page = self.document[page_number]
            blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]
            current_fonts = {}

            for block in blocks:
                for line in block['lines']:
                    for span in line['spans']:
                        font_size = round(span['size'])
                        if font_size not in current_fonts:
                            current_fonts[font_size] = len(span['text'].strip())
                        else:
                            current_fonts[font_size] += len(span['text'].strip())

            # compare font sizes distributions between current and previous page
            if previous_fonts:
                # check if there's a significant increase in larger fonts usage
                larger_font_transition = self.check_larger_font_transition(previous_fonts, current_fonts)
                if larger_font_transition:
                    toc_end_page = page_number - 1
                    break
            
            previous_fonts = current_fonts.copy()

        return toc_end_page + 1

    def check_larger_font_transition(self, previous_fonts: Dict[int, int], current_fonts: Dict[int, int]) -> bool:
        """
        Check if there is a significant transition to larger fonts, indicating the end of the TOC.
        """
        prev_max_font = max(previous_fonts, key=previous_fonts.get, default=0)
        current_max_font = max(current_fonts, key=current_fonts.get, default=0)
        return current_max_font > prev_max_font and current_fonts.get(current_max_font, 0) > previous_fonts.get(current_max_font, 0)
    
    def generate_md_string(self) -> Tuple[str, str]:
        """
        Generate Markdown strings for toc and content.
        """
        first_toc_page = self.find_first_toc_page_no()
        last_toc_page = self.find_last_toc_page_no(first_toc_page)
        toc_pages = list(range(first_toc_page, last_toc_page))
        content_pages = list(range(last_toc_page, self.document.page_count))
        toc_md_string = self.to_markdown(self.document, toc_pages)
        content_md_string = self.to_markdown(self.document, content_pages)
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
        async def process_function():
            toc_md_lines = self.toc_md_string.split("\n")
            toc_md_section_lines = [line for line in toc_md_lines if line.startswith('#')]
            toc_md_section_joined_lines = '\n'.join(toc_md_section_lines)
            messages = [
                {"role": "system", "content": prompts.TOC_HIERARCHY_SYS_PROMPT},
                {"role": "user", "content": prompts.TOC_HIERARCHY_USER_PROMPT.format(TOC_HIERARCHY_SCHEMA_TEMPLATE=prompts.TOC_HIERARCHY_SCHEMA_TEMPLATE, toc_md_string=toc_md_section_joined_lines)}
            ]
            while True:
                response = await llm.openai_client_chat_completion_request(messages, model="gpt-4-turbo")
                try:
                    if not response.choices or not response.choices[0].message:
                        print("Unexpected response structure:", response)
                        raise Exception("Unexpected response structure")
                    
                    message_content = response.choices[0].message.content
                    toc_hierarchy_schema = json.loads(message_content)
                    print(f"Schema: {json.dumps(toc_hierarchy_schema, indent=4)}")
                    updated_toc_hierarchy_schema = await self.map_toc_to_hierarchy(toc_md_section_lines, toc_hierarchy_schema)
                    if updated_toc_hierarchy_schema == toc_hierarchy_schema:
                        print("No changes to ToC Hierarchy Schema")
                    else:
                        print(updated_toc_hierarchy_schema)
                    return updated_toc_hierarchy_schema
                except json.JSONDecodeError:
                    print("Error decoding JSON for ToC Hierarchy Schema")
                    raise

        # usually gets it right but ~1/5 times it doesn't
        schemas = await asyncio.gather(*[self.rate_limited_process(process_function) for _ in range(3)])
        schema_counter = Counter(tuple(sorted(schema.items())) for schema in schemas)
        most_common_schema = dict(schema_counter.most_common(1)[0][0])
        print(f"Most Common Schema: {json.dumps(most_common_schema, indent=4)}")
        return most_common_schema
    
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
        # need to dynamically adjust the schema based on whats present in the content
        for heading, level in toc_hierarchy_schema.items():
            formatted_heading = f"{level} {heading}"
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
                print(f"Adjusted ToC Hierarchy Schema: {json.dumps(levels, indent=4)}")
                #print(f"Adjusted ToC Hierarchy Schema")
            else:    
                levels = await self.filter_schema(self.toc_hierarchy_schema, content)
                print(f"UNadjusted ToC Hierarchy Schema: {json.dumps(levels, indent=4)}")

        if max_depth is None:
            max_depth = max(marker.count('#') for marker in levels.values())

        if depth >= max_depth:
            return [], levels

        current_depth_levels = [name for name, marker in levels.items() if marker.count('#') == depth + 1]
        children, _ = await self.generate_toc_schema(levels, content, depth + 1, max_depth)

        toc_schema = [
            {
                "section": f"string (type of the section, e.g., {level_name})",
                "number": "string (numeric or textual identifier of the section)",
                "title": "string (title of the section)",
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
        Split the ToC parts into sub-parts based on the sub-part type
        """
        parts = {}
        stack = []
        i = 0
        while i < len(lines):
            line = lines[i]
            level = None
            for j, level_type in enumerate(level_types):
                if line.startswith(level_type):
                    level = j
                    break
            if level is not None:
                heading = line.strip()
                # concatenate multi-line headings
                j = 1
                while i + j < len(lines) and lines[i + j].startswith(level_types[level].split(" ")[0]):
                    next_line = lines[i + j].strip().lstrip('#').strip()
                    heading += ' ' + next_line
                    j += 1

                heading = await self.rate_limited_process(self.process_heading, heading)
                # pop stack until we reach the correct level
                while stack and stack[-1][0] >= level:
                    stack.pop()
                if stack:
                    parent = stack[-1][1]
                    if "children" not in parent:
                        parent["children"] = {}
                    parent["children"][json.dumps(heading)] = {}
                    stack.append((level, parent["children"][json.dumps(heading)]))
                else:
                    parts[json.dumps(heading)] = {}
                    stack.append((level, parts[json.dumps(heading)]))
                i += j
            else:
                if stack:
                    if line.strip():
                        if "content" not in stack[-1][1]:
                            stack[-1][1]["content"] = ""
                        stack[-1][1]["content"] += line.strip() + '\n'
                i += 1

        return parts
    
    async def split_toc_into_parts(self) -> Dict[str, Union[str, Dict[str, str]]]:
        """
        Split the ToC into parts based on the hierarchy schema and token count
        """
        lines = self.toc_md_string.split('\n')
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

        sorted_headings = sorted(most_common_headings.items(), key=lambda x: len(x[0]))
        level_types = [f"{level[0]} {level[1]}" for level in sorted_headings][:3] # only take the first 3 levels

        return await self.split_toc_parts_into_parts(lines, level_types)
    
    async def generate_formatted_toc(self, level_title: JSONstr, sublevel_title: Union[JSONstr, None], subsublevel_title: Union[JSONstr, None], content: str) -> Tuple[JSONstr, JSONstr, JSONstr, Dict[str, Any]]:

        async def process_function():
            nonlocal sublevel_title
            nonlocal subsublevel_title
            custom_schema, custom_levels = await self.generate_toc_schema(content=content)
            TOC_SCHEMA = {"contents": [json.dumps(custom_schema, indent=4)]}
            print(f"Custom Schema: {json.dumps(custom_schema, indent=4)}")
            # TOC_SCHEMA = {"contents": [json.dumps(self.toc_schema, indent=4)]}
            
            if not sublevel_title:
                messages = [
                    {"role": "system", "content": prompts.TOC_SCHEMA_SYS_PROMPT.format(section_types=", ".join(self.toc_hierarchy_schema.keys()), TOC_SCHEMA=TOC_SCHEMA)},
                    {"role": "user", "content": content}
                ]
                sublevel_title = "Complete"
                subsublevel_title = "Complete"
            else:
                section_types = ", ".join(custom_levels.keys())
                level_title_dict = json.loads(level_title)
                level_title_str = f"{level_title_dict['section']} {level_title_dict['number']} {level_title_dict['title']}"
                sublevel_title_dict = json.loads(sublevel_title)
                sublevel_title_str = f"{sublevel_title_dict['section']} {sublevel_title_dict['number']} {sublevel_title_dict['title']}"
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
                try:
                    message_content = response.choices[0].message.content
                    toc_schema = json.loads(message_content)
                    print(f"Completed JSON for {level_title_str} / {sublevel_title_str} / {subsublevel_title_str}")
                    return (level_title, sublevel_title, subsublevel_title, toc_schema)
                except json.JSONDecodeError:
                    print(f"Error decoding JSON for {level_title} - {sublevel_title}")
                    raise

        return await self.rate_limited_process(process_function)
    
    async def extract_toc(self) -> TableOfContentsDict:
        """
        Main method to extract and format the ToC.
        """
        levels = await self.split_toc_into_parts()
        tasks = []
        all_level_schemas = {"contents": []}
        with open("levels.json", "w") as f:
            json.dump(levels, f, indent=4)

        async def process_level(level_title, level_content, sublevel_title=None, subsublevel_title=None):
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

        for level_title, level_content in levels.items():
            await process_level(level_title, level_content)

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
        def parse_level(level_json: JSONstr):
            level_dict = json.loads(level_json)
            return level_dict['section'], level_dict['number'], level_dict['title']
        
        level_section, level_number, level_title = parse_level(content.level)
        if content.sublevel == "Complete" or content.toc[0].section == level_section:
            return TableOfContents(
                section=level_section,
                number=level_number,
                title=level_title,
                children=content.toc[0].children
            )
        sublevel_section, sublevel_number, sublevel_title = parse_level(content.sublevel)
        if content.subsublevel == "Complete":
            return TableOfContents(
                section=level_section,
                number=level_number,
                title=level_title,
                children=[
                    TableOfContents(
                        section=sublevel_section,
                        number=sublevel_number,
                        title=sublevel_title,
                        children=content.toc[0].children
                    )
                ]
            )
        subsublevel_section, subsublevel_number, subsublevel_title = parse_level(content.subsublevel)
        subsublevel_toc = content.toc[0].find_child(subsublevel_section, subsublevel_number)
        if subsublevel_toc:
            return TableOfContents(
                section=level_section,
                number=level_number,
                title=level_title,
                children=[
                    TableOfContents(
                        section=sublevel_section,
                        number=sublevel_number,
                        title=sublevel_title,
                        children=[subsublevel_toc]
                    )
                ]
            )
        else:
            return TableOfContents(
                section=level_section,
                number=level_number,
                title=level_title,
                children=[
                    TableOfContents(
                        section=sublevel_section,
                        number=sublevel_number,
                        title=sublevel_title,
                        children=[
                            TableOfContents(
                                section=subsublevel_section,
                                number=subsublevel_number,
                                title=subsublevel_title,
                                children=content.toc[0].children
                            )
                        ]
                    )
                ]
            )
        
    async def merge_toc(self, master_toc: List[TableOfContents], toc: List[TableOfContents], ) -> List[TableOfContents]:
        """
        Merge a new ToC sections.
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
        Build the master ToC from the split ToC parts.
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
    
    async def load_and_build_toc(self, file: Union[UploadFile, str]) -> List[TableOfContents]:
        """
        temp for testing
        Load a toc.json and build master toc.
        """
        if isinstance(file, UploadFile):
            raise ValueError("file must be a file path.")
        elif isinstance(file, str):
            with open(file, "r") as f:
                json_data = json.load(f)
                data = TableOfContentsDict(**json_data)
                master_toc = await self.build_master_toc(data)
                save_file_name = f"master_{file}"
                self.save_toc_to_file(master_toc, save_file_name)
        else:
            raise ValueError("file must be an instance of UploadFile or str.")
        
    async def generate_levels_list(self) -> List[Tuple[Optional[str], str, str]]:
        """
        Find and return a list of all levels in the ToC with their section, number, and title.
        """
        levels_list = []

        def convert_to_model(data: Dict[str, Any]) -> Union[TableOfContents, TableOfContentsChild]:
            if 'children' in data:
                data['children'] = [convert_to_model(child) for child in data['children']]
                return TableOfContents(**data)
            else:
                return TableOfContentsChild(**data)

        def traverse_sections(sections: List[Union[TableOfContents, TableOfContentsChild]]):
            for section in sections:
                if isinstance(section, TableOfContents):
                    levels_list.append((section.section, section.number, section.title))
                    if section.children:
                        traverse_sections(section.children)
                # elif isinstance(section, TableOfContentsChild):
                #     levels_list.append((None, section.number, section.title))

        toc_models = [convert_to_model(item) for item in self.master_toc]
        traverse_sections(toc_models)

        return levels_list
    
    async def generate_levels_list_from_json(self, master_toc: List[Dict[str, Any]]) -> List[Tuple[Optional[str], str, str]]:
        """
        temp for testing
        Find and return a list of all levels in the ToC with their section, number, and title.
        """
        levels_list = []

        def convert_to_model(data: Dict[str, Any]) -> Union[TableOfContents, TableOfContentsChild]:
            if 'children' in data:
                data['children'] = [convert_to_model(child) for child in data['children']]
                return TableOfContents(**data)
            else:
                return TableOfContentsChild(**data)

        def traverse_sections(sections: List[Union[TableOfContents, TableOfContentsChild]]):
            for section in sections:
                if isinstance(section, TableOfContents):
                    levels_list.append((section.section, section.number, section.title))
                    if section.children:
                        traverse_sections(section.children)
                # elif isinstance(section, TableOfContentsChild):
                #     levels_list.append((None, section.number, section.title))

        toc_models = [convert_to_model(item) for item in master_toc]
        traverse_sections(toc_models)

        return levels_list
    
    async def run_find_levels_from_json_path(self, file_path: str) -> List[Tuple[str, str, str]]:
        """
        temp for testing
        Run the find_levels method from a JSON file path.
        """
        with open(file_path, "r") as f:
            toc = json.load(f)
            levels = await self.generate_levels_list_from_json(toc)
            return levels
    
    async def generate_chunked_content(self) -> Dict[str, Dict[Any]]:
        """
        Split the content into a chunk dict based on the levels
        """
        level_info_list = await self.generate_levels_list()
        content_md_lines = self.content_md_string.split("\n")
        content_md_section_lines = [(line, idx) for idx, line in enumerate(content_md_lines) if line.startswith('#')]

        md_levels = self.adjusted_toc_hierarchy_schema if self.adjusted_toc_hierarchy_schema else self.toc_hierarchy_schema

        formatted_section_names = []
        for level_info in level_info_list:
            section_type, number, title = level_info
            if not section_type:
                section_match = None
            else:
                section_match = process.extractOne(section_type, md_levels.keys(), score_cutoff=95)
            if section_match:
                matched_section = section_match[0]
                md_level = md_levels[matched_section]
            else:
                max_level = max(md_levels.values(), key=len)
                md_level = max_level

            if section_type and number and title:
                if section_type in title and number in title:
                    section_name = title
                elif section_type in title:
                    section_name = f'{title} {number}'
                else:
                    section_name = f'{section_type} {number} {title}'
            elif not number:
                if section_type in title:
                    section_name = title
                else:
                    section_name = f'{section_type} {title}'
            else:
                section_name = section_type
            
            formatted_section_names.append(f"{md_level} {section_name}")

        doc_dict = {}
        current_hierarchy = []
        start_lines = []
        remaining_content_md_section_lines = content_md_section_lines[:]
        for i, formatted_section_name in enumerate(formatted_section_names):
            matches = process.extractBests(formatted_section_name, [line for line, _ in remaining_content_md_section_lines], score_cutoff=80, limit=10)
            if matches:
                highest_score = max(matches, key=lambda x: x[1])[1]
                highest_score_matches = [match for match in matches if match[1] == highest_score]
                # select the highest score with the lowest index
                matched_line = min(highest_score_matches, key=lambda x: next(idx for line, idx in remaining_content_md_section_lines if line == x[0]))[0]
                start_line_idx = next(idx for line, idx in remaining_content_md_section_lines if line == matched_line)
                
                remaining_content_md_section_lines = [item for item in remaining_content_md_section_lines if item[1] > start_line_idx]
                md_l, md_section_name = formatted_section_name.split(" ", 1)
                start_lines.append((md_l.strip(), md_section_name.strip(), start_line_idx))
            else:
                print(f"Could not match {formatted_section_name}")
                print(f"Remaining: {len(remaining_content_md_section_lines)}")
        
        for i, (md_l, section_name, start_line) in enumerate(start_lines):
            if i < len(start_lines) - 1:
                end_line = start_lines[i + 1][2] - 1
            else:
                end_line = len(content_md_lines) - 1

            section_text = "\n".join(content_md_lines[start_line:end_line + 1])
            num_tokens = self.count_tokens(section_text)
            
            current_node = {
                "section": section_name,
                "content": section_text,
                "tokens": num_tokens,
                "subsections": []
            }

            while current_hierarchy and current_hierarchy[-1][1] >= md_l:
                current_hierarchy.pop()

            if not current_hierarchy:
                doc_dict[section_name] = current_node
            else:
                parent_node = current_hierarchy[-1][0]
                parent_node["subsections"].append(current_node)

            current_hierarchy.append((current_node, md_l))

        return doc_dict
    
    async def parse(self, file: Union[UploadFile, str]) -> Dict[str, Dict[Any]]:
        """
        Main method to parse the PDF content.
        """
        await self.load_document(file)
        toc = await self.extract_toc()
        with open("toc.json", "w") as f:
            json.dump(toc, f, indent=4)
        data = TableOfContentsDict(**toc)
        await self.build_master_toc(data)
        content_dict = await self.generate_chunked_content()
        return content_dict
    
    async def parse_from_json(self, file_path: str) -> Dict[str, Dict[Any]]:
        """
        temp for testing
        Main method to parse the PDF content from a JSON file.
        """
        with open(file_path, "r") as f:
            toc = json.load(f)
            data = TableOfContentsDict(**toc)
            await self.build_master_toc(data)   
        content_dict = await self.generate_chunked_content()
        return content_dict