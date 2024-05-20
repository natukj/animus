from typing import Union, Any, Callable, Dict, Tuple, List
import json
import asyncio
from fastapi import UploadFile
import fitz  
import llm, prompts
from parser.base_parser import BaseParser

class ToCParser(BaseParser):
    """Table of Contents (ToC) parser class for Legal (Australian Legislation) PDFs."""
    
    def __init__(self, rate_limit: int = 50):
        super().__init__(rate_limit)
        self.document = None
        self.toc_md_string = None
        self.toc_hierarchy_schema = None
        self.toc_schema = None

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
        self.toc_md_string = self.generate_toc_md_string()
        self.toc_hierarchy_schema = await self.generate_toc_hierarchy_schema()
        self.toc_schema = await self.generate_toc_schema()
    
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
    
    def generate_toc_md_string(self) -> str:
        """
        Generate a ToC Markdown string.
        """
        first_toc_page = self.find_first_toc_page_no()
        last_toc_page = self.find_last_toc_page_no(first_toc_page)
        toc_pages = list(range(first_toc_page, last_toc_page))
        toc_md_string = self.to_markdown(self.document, toc_pages)
        return toc_md_string

    async def generate_toc_hierarchy_schema(self) -> Dict[str, str]:
        """
        Generate a schema for the ToC hierarchy, eg
        {
            'Chapter': '#',
            'Part': '##',
            'Division': '###',
            'Subdivision': '####'
        }
        """
        async def process_function():
            messages = [
                {"role": "system", "content": prompts.TOC_HIERARCHY_SYS_PROMPT},
                {"role": "user", "content": self.toc_md_string}
            ]
            while True:
                response = await llm.openai_chat_completion_request(messages, response_format="json")
                if response and 'choices' in response and len(response['choices']) > 0:
                    try:
                        toc_hierarchy_schema = json.loads(response['choices'][0]['message']['content'])
                        all_keys_present = all(self.toc_md_string.count(key) > 1 for key in toc_hierarchy_schema.keys())
                        if not all_keys_present:
                            print("Not all keys present multiple times in ToC")
                            raise Exception("Not all keys present multiple times in ToC")
                        print(toc_hierarchy_schema)
                        return toc_hierarchy_schema
                    except json.JSONDecodeError:
                        print("Error decoding JSON for ToC Hierarchy Schema")
                        raise

        return await self.rate_limited_process(process_function)
    
    async def generate_toc_schema(self, levels: Dict[str, str] = None, depth: int = 0, max_depth: int = None) -> List[Dict[str, Any]]:
        """
        Generate a custom schema for the ToC based on the hierarchy schema.
        """
        if levels is None:
            top_level = min(self.toc_hierarchy_schema.values(), key=lambda x: x.count('#'))
            top_level_count = top_level.count('#')
            if top_level_count > 1:
                adjust_count = top_level_count - 1
                levels = {k: v[adjust_count:] for k, v in self.toc_hierarchy_schema.items()}
            else:    
                levels = self.toc_hierarchy_schema

        if max_depth is None:
            max_depth = max(marker.count('#') for marker in levels.values())

        if depth >= max_depth:
            return []

        current_depth_levels = [name for name, marker in levels.items() if marker.count('#') == depth + 1]
        children = await self.generate_toc_schema(levels, depth + 1, max_depth)

        return [
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

    
    def _split_part(self, text: str) -> Tuple[str, str]:
        middle_index = len(text) // 2
        before = text.rfind("\n\n#### ", 0, middle_index)
        after = text.find("\n\n#### ", middle_index)

        if before == -1 and after == -1:
            return text[:middle_index], text[middle_index:]
        elif before == -1 or (after != -1 and (after - middle_index) < (middle_index - before)):
            split_index = after
        else:
            split_index = before

        return text[:split_index], text[split_index:]

    def _recursive_split(self, text: str) -> List[str]:
        if self.count_tokens(text) <= 2000:
            return [text]
        else:
            left_half, right_half = self._split_part(text)
            return self._recursive_split(left_half) + self._recursive_split(right_half)

    def split_toc_parts_into_parts(self, lines: List[str], second_level_type: str) -> Dict[str, str]:
        """
        Split the ToC parts into sub-parts based on the sub-part type
        """
        parts = {}
        current_part = None
        part_content = []
        for line in lines:
            if line.startswith(second_level_type):
                if current_part:
                    full_part_text = '\n'.join(part_content)
                    if self.count_tokens(full_part_text) > 2000:
                        sub_parts = self._recursive_split(full_part_text)
                        for i, part in enumerate(sub_parts, 1):
                            parts[f"{current_part} - Split {i}"] = part
                    else:
                        parts[current_part] = full_part_text
                    part_content = []
                current_part = line
            part_content.append(line)
        
        if current_part:
            full_part_text = '\n'.join(part_content)
            if self.count_tokens(full_part_text) > 2000:
                sub_parts = self._recursive_split(full_part_text)
                for i, part in enumerate(sub_parts, 1):
                    parts[f"{current_part} - Split {i}"] = part
            else:
                parts[current_part] = full_part_text

        return parts
    
    async def split_toc_into_parts(self) -> Dict[str, Union[str, Dict[str, str]]]:
        """
        Split the ToC into parts based on the hierarchy schema and token count
        """
        # self.toc_hierarchy_schema = await self.generate_toc_hierarchy_schema()
        sorted_schema = sorted(self.toc_hierarchy_schema.items(), key=lambda item: len(item[1]))
        top_level_type = f"{sorted_schema[0][1]} {sorted_schema[0][0]}"
        second_level_type = f"{sorted_schema[1][1]} {sorted_schema[1][0]}"

        lines = self.toc_md_string.split('\n')
        top_levels = {}
        top_level = None
        top_level_content = []

        for line in lines:
            if line.startswith(top_level_type):
                if top_level:
                    full_chapter_text = '\n'.join(top_level_content)
                    if self.count_tokens(full_chapter_text) > 2000:
                        top_levels[top_level] = self.split_toc_parts_into_parts(top_level_content, second_level_type)
                    else:
                        top_levels[top_level] = full_chapter_text
                    top_level_content = []
                top_level = line
            top_level_content.append(line)

        if top_level:
            full_chapter_text = '\n'.join(top_level_content)
            if self.count_tokens(full_chapter_text) > 2000:
                top_levels[top_level] = self.split_toc_parts_into_parts(top_level_content, second_level_type)
            else:
                top_levels[top_level] = full_chapter_text

        return top_levels
    
    async def generate_formatted_toc(self, level_title: str, sublevel_title: Union[str, None], content: str) -> Tuple[str, str, Dict[str, Any]]:
        async def process_function():
            nonlocal sublevel_title
            TOC_SCHEMA={"contents": [json.dumps(self.toc_schema, indent=4)]}

            if sublevel_title:
                messages = [
                    {"role": "system", "content": prompts.TOC_SCHEMA_SYS_PROMPT.format(section_types=", ".join(self.toc_hierarchy_schema.keys()), TOC_SCHEMA=TOC_SCHEMA)},
                    {"role": "user", "content": content}
                ]
            else:
                section_types = ", ".join(self.toc_hierarchy_schema.keys())
                messages = [
                    {"role": "system", "content": prompts.TOC_SCHEMA_SYS_PROMPT_PLUS.format(section_types=section_types, chapter_title=level_title, part_title=sublevel_title, TOC_SCHEMA=TOC_SCHEMA)},
                    {"role": "user", "content": content}
                ]
                sublevel_title = "Full Chapter"
            response = await llm.openai_chat_completion_request(messages, response_format="json")
            if response and 'choices' in response and len(response['choices']) > 0:
                if response["choices"][0]["finish_reason"] == "length":
                    print(f"Response too long for {level_title} - {sublevel_title}")
                    raise Exception("Response too long")
                try:
                    toc_schema = json.loads(response['choices'][0]['message']['content'])
                    print(f"Completed JSON for {level_title} - {sublevel_title}")
                    return (level_title, sublevel_title, toc_schema)
                except json.JSONDecodeError:
                    print(f"Error decoding JSON for {level_title} - {sublevel_title}")
                    raise

        return await self.rate_limited_process(process_function)
    
    async def extract_toc(self) -> Dict[str, Any]:
        """
        Main method to extract and format the ToC.
        """
        levels = await self.split_toc_into_parts()
        tasks = []
        for level_title, content in levels.items():
            if isinstance(content, dict):  # level has sublevels
                for sublevel_title, sublevel_content in content.items():
                    task = self.generate_formatted_toc(level_title, sublevel_title, sublevel_content)
                    tasks.append(task)
            else:
                task = self.generate_formatted_toc(level_title, None, content)
                tasks.append(task)

        results = await asyncio.gather(*tasks)
        print(f"the number of results is {len(results)}")
        all_level_schemas = {"contents": []}

        for level_title, sublevel_title, result in results:
            if result and result.get('contents'):
                all_level_schemas["contents"].append({
                    "chapter": level_title,
                    "part": sublevel_title,
                    "toc": result['contents']
                })

        return all_level_schemas
    
    async def split_toc(self) -> Dict[str, Union[str, Dict[str, str]]]:
        custom_schema = await self.generate_toc_schema()
        return {"contents": [custom_schema]}
