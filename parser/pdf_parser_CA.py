from typing import Union, Any, Optional, Dict, Tuple, List, NewType
import json
import asyncio
import copy
import re
import uuid
from collections import Counter, defaultdict
from thefuzz import process  
import llm, prompts, schemas, utils
from parser.base_parser import BaseParser
from parser.pdf_parser_ToC import PDFToCParser

class PDFCAParser(BaseParser):
    def __init__(self, toc_parser: PDFToCParser, rate_limit: int = 50) -> None:
        """
        Initialise the PDFCAParser with a reference to the PDFToCParser instance.
        
        :param toc_parser: An instance of PDFToCParser containing the parsed data. 
        """
        super().__init__(rate_limit)
        #self.toc_parser = toc_parser
        self.document = toc_parser.document
        self.doc_title = toc_parser.doc_title
        self.toc_pages = toc_parser.toc_pages
        self.toc_pages_md = toc_parser.toc_pages_md
        self.toc_md_lines = toc_parser.toc_md_lines
        self.content_md_lines = toc_parser.content_md_lines
        self.toc_hierarchy_schema = toc_parser.toc_hierarchy_schema
        self.master_toc = toc_parser.master_toc
        self.grouped_pages_text: Dict[Tuple[int], List[str]] = None
        self.grouped_appendix_pages_text: Dict[Tuple[int], str] = None

    async def group_pages(self) -> None:
        grouped_pages = [self.toc_pages[:2]] + [self.toc_pages[i:i+4] for i in range(2, len(self.toc_pages), 4)]
        individual_page_texts = {page: self.toc_pages_md[self.toc_pages.index(page)].get("text", "") for page in self.toc_pages}
        grouped_pages_text = {tuple(group): [individual_page_texts[page] for page in group] for group in grouped_pages}
        end_pages = []
        end_pages_text = ""
        appendix_break = False
        for group in list(reversed(grouped_pages)):
            remaining_group_pages = []
            for page in group:
                page_text = individual_page_texts[page]
                if any(keyword in page_text.lower() for keyword in ['schedule', 'appendix', 'appendices']) and not appendix_break:
                    end_pages.append(page)
                    end_pages_text += page_text
                else:
                    appendix_break = True
                    remaining_group_pages.append(page)
            remaining_group_text = "".join(individual_page_texts[page] for page in remaining_group_pages)
            if remaining_group_pages:
                grouped_pages_text[tuple(remaining_group_pages)] = remaining_group_text
                if tuple(remaining_group_pages) != tuple(group):
                    del grouped_pages_text[tuple(group)]
            else:
                del grouped_pages_text[tuple(group)]
        self.grouped_pages_text = grouped_pages_text
        self.grouped_appendix_pages_text = {tuple(end_pages): end_pages_text} if end_pages else {}

    async def gen_toc_hierarchy_schema(self) -> List[Tuple[str, int]]:
        """
        Generate a hierarchy schema for the ToC hierarchy, eg
        {
            'Chapter': 1,
            'Part': 2,
            'Division': 3,
            'Subdivision': 4,
        }
        """
        async def process_pages(page_nums_and_text: tuple, initial_schema: dict = None, example: str = None) -> Dict[str, str]:
            page_nums, toc_md_toc_section_str = page_nums_and_text
            if not initial_schema:
                USER_PROMPT = prompts.TOC_HIERARCHY_USER_VISION.format(toc_md_string=toc_md_toc_section_str)
                pages_imgs = [utils.encode_page_as_base64(self.document[page_num]) for page_num in page_nums]
                messages = utils.message_template_vision(USER_PROMPT, *pages_imgs)
            else:
                messages = [
                    {"role": "system", "content": prompts.TOC_HIERARCHY_SYS_PROMPT},
                    {"role": "user", "content": prompts.TOC_HIERARCHY_USER_PLUS.format(prior_schema_template=json.dumps(prior_schema, indent=2), example=example, num_levels=len(prior_schema), toc_md_string=toc_md_toc_section_str)}
                ]
            response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
            try:
                message_content = response.choices[0].message.content
                toc_hierarchy_schema = json.loads(message_content)
                return toc_hierarchy_schema
            except json.JSONDecodeError:
                utils.print_coloured(f"gen_toc_hierarchy_schema JSONDecodeError: {message_content}", "red")
                raise
        
        prior_schema, appendix_schema = await asyncio.gather(
            self.rate_limited_process(process_pages, (next(iter(self.grouped_pages_text.items())),)),
            self.rate_limited_process(process_pages, (next(iter(self.grouped_appendix_pages_text.items())),))
        )
        prior_schema_descriptions = []
        for key, value in prior_schema.items():
            if "description" in value:
                prior_schema_descriptions.append(f"(array of strings, ALL verbatim {key} section lines from the text identified as the {value['description']})")
                del value["description"]
        prior_schema_template = copy.deepcopy(prior_schema) 
        utils.print_coloured(json.dumps(prior_schema, indent=2), "yellow")
        for key, description in zip(list(prior_schema_template.keys()), prior_schema_descriptions):
            prior_schema_template[key]["lines"] = description
        utils.print_coloured(json.dumps(prior_schema_template, indent=2), "yellow")
        user_input = input("Is this correct? (Y/n): ")
        if user_input.lower() != 'y':
            utils.print_coloured("fml", "red")
            exit()
        # create an example for llm
        prior_schema_example = copy.deepcopy(prior_schema) 
        _, text = next(iter(self.grouped_pages_text.items()))
        initial_toc_md_lines = text.split("\n")
        found_flags = {key: False for key in prior_schema.keys()}
        levels = {details["level"]: key for key, details in prior_schema.items()}
        found_lines = {level: [] for level in levels}
        first_idx = None
        last_idx = None
        for idx, line in enumerate(initial_toc_md_lines):
            for section, details in prior_schema_example.items():
                if line in details["lines"]:
                    found_flags[section] = True
                    found_lines[details["level"]].append((line, idx))

                    if first_idx is None or idx < first_idx:
                        first_idx = idx
                    if last_idx is None or idx > last_idx:
                        last_idx = idx
                    if all(found_flags.values()):
                        break
            if all(found_flags.values()):
                break
        example_substring = '\n'.join(initial_toc_md_lines[first_idx:last_idx + 1])
        example_substring_lines = set(example_substring.split('\n'))
        example = f"<example_text>\n{example_substring}\n</example_text>\n\n"
        for key, details in prior_schema_example.items():
            details["lines"] = [line for line in details["lines"] if line in example_substring_lines]
        example += f"<example_output>{json.dumps(prior_schema_example, indent=2)}</example_output>"
        utils.print_coloured(json.dumps(prior_schema_example, indent=2), "blue")

        toc_hierarchy_schemas = await asyncio.gather(
            *[
                self.rate_limited_process(
                    process_pages, 
                    page_nums, 
                    prior_schema=prior_schema_template,
                    example=example
                )
                for page_nums in list(self.grouped_pages_text.items())[1:]
            ]
        )
        combined_toc_hierarchy_schema = {}
        for schema in [prior_schema, appendix_schema] + toc_hierarchy_schemas:
            for details in schema.values():
                for line in details["lines"]:
                    if line not in combined_toc_hierarchy_schema:
                        combined_toc_hierarchy_schema[line] = details["level"]

        ordered_items = sorted(combined_toc_hierarchy_schema.items(), key=lambda x: x[1].count('#'))
        ordered_dict = dict(ordered_items)
        utils.print_coloured(f"{json.dumps(ordered_dict, indent=4)}", "green")
        with open(f"{self.doc_title}_toc_hierarchy_schema.json", "w") as f:
            json.dump(ordered_dict, f, indent=4)
        toc_hierarchy_schema = [(heading, level.count('#')) for heading, level in ordered_items]
        return toc_hierarchy_schema
    
    async def create_master_toc(self) -> None:
        if not self.toc_hierarchy_schema:
            self.toc_hierarchy_schema = await self.gen_toc_hierarchy_schema()
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
                current_part = {
                    "section": formatted_line.get('section', ""),
                    "number": formatted_line.get('number', ""),
                    "title": formatted_line.get('title', "")
                }
                utils.print_coloured(current_part, "cyan")
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
        
        max_line_length = max(len(line.strip()) for line in self.toc_md_lines)
        skip_next_line = False
        for line in self.toc_md_lines:
            stripped_line = line.strip()
            level = None
            match_found = False
            for heading, level_num in self.toc_hierarchy_schema:
                if len(heading) > max_line_length:
                    trimmed_heading = heading[:len(stripped_line)]
                else:
                    trimmed_heading = heading
                if trimmed_heading == stripped_line:
                    utils.print_coloured(f"Matched: {heading} in {stripped_line}", "green")
                    level = level_num
                    break
                if not match_found and ' ' in trimmed_heading and len(trimmed_heading) >= max_line_length*0.8:
                    if "The Companies (Northern Ireland) Order 1986" in trimmed_heading:
                        trimmed_heading = "Part 2 — The Companies (Northern Ireland) Order 1986 (S.I. 1986/1032"
                    else:
                        trimmed_heading = ' '.join(trimmed_heading.split(' ')[:-1])
                    if trimmed_heading in stripped_line:
                        utils.print_coloured(f"Matched after trim: {heading} in {stripped_line}", "yellow")
                        match_found = skip_next_line = True
                        level = level_num
                        break
            if level is not None:
                if item_buffer:
                    placeholder = str(uuid.uuid4())
                    item_futures.append((self.rate_limited_process(process_items, '\n'.join(item_buffer)), placeholder))
                    if stack:
                        current = stack[-1][1]
                        current["contents"] = placeholder
                    item_buffer = []

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
                if skip_next_line:
                    utils.print_coloured(f"Skipping line: {stripped_line}", "yellow")
                    skip_next_line = False
                    continue
                else:
                    if stripped_line:
                        item_buffer.append(stripped_line)

        if item_buffer:
            placeholder = str(uuid.uuid4())
            item_futures.append((self.rate_limited_process(process_items, '\n'.join(item_buffer)), placeholder))
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
        with open(f"{self.file_name}_parts.json", "w") as f:
            json.dump(parts, f, indent=2)
        utils.print_coloured("Parts created", "green")
        master_toc = schemas.parse_toc_dict(parts)
        self.master_toc = [toc.model_dump() for toc in master_toc]
        with open(f"{self.file_name}_master_toc.json", "w") as f:
            json.dump(self.master_toc, f, indent=2, default=lambda x: x.dict())
        utils.print_coloured("Master TOC created", "green")