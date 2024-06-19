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
        self.document = toc_parser.document
        self.doc_title = toc_parser.doc_title
        self.toc_pages = toc_parser.toc_pages
        self.toc_pages_md = toc_parser.toc_pages_md
        self.toc_md_lines = toc_parser.toc_md_lines
        self.toc_md_apx_lines = toc_parser.toc_md_apx_lines
        self.content_md_lines = toc_parser.content_md_lines
        self.toc_hierarchy_schema = toc_parser.toc_hierarchy_schema
        self.master_toc = toc_parser.master_toc
        self.master_apx_toc = toc_parser.master_apx_toc
        self.appendix_toc_hierarchy_schema: Dict[str, str] = {}
        self.appendix_md_lines: List[str] = []
        self.grouped_pages_text: Dict[Tuple[int], List[str]] = None
        self.grouped_appendix_pages_text: Dict[Tuple[int], str] = None
        self.remaining_sections: List[str] = None
        # self.init_remaining_content_section_lines(self.content_md_lines, md_levels=False)
        self.init_child_format_section_name(self.format_section_name)

    def group_pages(self) -> None:
        grouped_pages = [self.toc_pages[:2]] + [self.toc_pages[i:i+4] for i in range(2, len(self.toc_pages), 4)]
        individual_page_texts = {page: self.toc_pages_md[self.toc_pages.index(page)].get("text", "") for page in self.toc_pages}
        grouped_pages_text = {tuple(group): "".join(individual_page_texts[page] for page in group) for group in grouped_pages}
        end_pages = []
        end_pages_text = ""
        for group in list(reversed(grouped_pages)):
            group_text = grouped_pages_text[tuple(group)]
            if any(keyword in group_text.lower() for keyword in ['schedule', 'appendix', 'appendices']):
                split_index = group_text.lower().find(next(keyword for keyword in ['schedule', 'appendix', 'appendices'] if keyword in group_text.lower()))
                if split_index != -1:
                    appendix_text = group_text[split_index:]
                    non_appendix_text = group_text[:split_index]
                    end_pages.extend(group)
                    end_pages_text = appendix_text + end_pages_text
                    grouped_pages_text[tuple(group)] = non_appendix_text
                    break

        self.grouped_pages_text = {group: text for group, text in grouped_pages_text.items() if text.strip()}
        self.grouped_appendix_pages_text = {tuple(end_pages): end_pages_text} if end_pages else None
        if self.grouped_appendix_pages_text:
            self.toc_md_lines = [line for group_text in grouped_pages_text.values() for line in group_text.split("\n") if line.strip()]
            self.toc_md_apx_lines = [line for line in end_pages_text.split("\n") if line.strip()]

        # for i, (group, text) in enumerate(self.grouped_appendix_pages_text.items()):
        #     print(f"Pages({i}) {group}: {text}")
        # for i, (group, text) in enumerate(self.grouped_pages_text.items()):
        #     print(f"Pages({i}) {group}: {len(text)}")
        #     # if i == 11:
        #     #     print(text)
        # utils.is_correct()
    #def split_apx_text(self) -> None:

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
        async def process_pages(
                page_nums_and_text: tuple,
                is_apx: bool = False, 
                prior_schema: dict = None, 
                example: str = None) -> None:
            page_nums, toc_md_toc_section_str = page_nums_and_text
            if not prior_schema and not is_apx:
                USER_PROMPT = prompts.TOC_HIERARCHY_USER_VISION.format(toc_md_string=toc_md_toc_section_str)
                pages_imgs = [utils.encode_page_as_base64(self.document[page_num]) for page_num in page_nums]
                messages = utils.message_template_vision(USER_PROMPT, *pages_imgs)
            elif is_apx:
                USER_PROMPT = prompts.TOC_HIERARCHY_USER_VISION_APPENDIX.format(toc_md_string=toc_md_toc_section_str)
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
        if not self.grouped_pages_text:
            self.group_pages()
        prior_schema, appendix_schema = await asyncio.gather(
            self.rate_limited_process(process_pages, (next(iter(self.grouped_pages_text.items())))),
            self.rate_limited_process(process_pages, (next(iter(self.grouped_appendix_pages_text.items()))), is_apx=True)
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
        utils.print_coloured(json.dumps(appendix_schema, indent=2), "yellow")
        utils.print_coloured(json.dumps(prior_schema_template, indent=2), "yellow")
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
        utils.print_coloured(json.dumps(prior_schema_example, indent=2), "green")
        utils.is_correct()
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
        # combined_toc_hierarchy_schema = {}
        # for schema in [prior_schema, appendix_schema] + toc_hierarchy_schemas:
        #     for details in schema.values():
        #         for line in details["lines"]:
        #             if line not in combined_toc_hierarchy_schema:
        #                 combined_toc_hierarchy_schema[line] = details["level"]
        # split content/appendix
        if appendix_schema:
            for details in appendix_schema.values():
                level = details["level"]
                for line in details["lines"]:
                    if level not in self.appendix_toc_hierarchy_schema:
                        self.appendix_toc_hierarchy_schema[level] = []
                    self.appendix_toc_hierarchy_schema[level].append(line)
            apx_idxs = []
            for idx, line in enumerate(reversed(self.content_md_lines)):
                for heading in self.appendix_toc_hierarchy_schema['#']:
                    if heading in line:
                        utils.print_coloured(f"Found {heading} in {line}", "yellow")
                        apx_idxs.append(len(self.content_md_lines) - idx)
                        break
            if apx_idxs:
                split_idx = min(apx_idxs)
                utils.print_coloured(f"Length of content_md_lines: {len(self.content_md_lines)}", "yellow")
                self.appendix_md_lines = self.content_md_lines[split_idx:]
                main_content = self.content_md_lines[:split_idx]
                self.content_md_lines = main_content
                utils.print_coloured(f"Splitting at {split_idx}", "yellow")
                utils.print_coloured(f"Length of content_md_lines after split: {len(self.content_md_lines)}", "yellow")
                with open(f"z{self.doc_title}_content.md", "w") as f:
                    f.write('\n'.join(main_content))
                with open(f"zz{self.doc_title}_apx.md", "w") as f:
                    f.write('\n'.join(self.appendix_md_lines))
                utils.is_correct(prompt="Splitting content and appendix")
                # toc_split_idx = Nones
                # for index, line in enumerate(self.toc_md_lines):
                #     if any(line.lower().startswith(keyword) for keyword in ['schedule', 'appendix', 'appendices']):
                #         toc_split_idx = index
                #         utils.print_coloured(f"Splitting TOC at {toc_split_idx}: {line}", "yellow")
                #         break
                # if toc_split_idx:
                #     toc_apx_content = self.toc_md_lines[toc_split_idx:]
                #     toc_main_content = self.toc_md_lines[:toc_split_idx]
                #     self.toc_md_lines = toc_main_content
                #     self.toc_md_apx_lines = toc_apx_content 
                # utils.is_correct()
            else:
                utils.print_coloured("NO APX SPLIT FOUND", "red")
                            
        combined_toc_hierarchy_schema = {}
        for schema in [prior_schema] + toc_hierarchy_schemas:
            for details in schema.values():
                level = details["level"]
                for line in details["lines"]:
                    if level not in combined_toc_hierarchy_schema:
                        combined_toc_hierarchy_schema[level] = []
                    combined_toc_hierarchy_schema[level].append(line)

        #toc_hierarchy_schema_items = sorted(combined_toc_hierarchy_schema.items(), key=lambda x: x[1].count('#'))
        toc_hierarchy_schema_items = sorted(combined_toc_hierarchy_schema.items(), key=lambda x: x[0].count('#'))
        self.toc_hierarchy_schema = dict(toc_hierarchy_schema_items)
        self.remaining_sections = [heading for headings in self.toc_hierarchy_schema.values() for heading in headings]
        utils.print_coloured(f"{json.dumps(self.appendix_toc_hierarchy_schema, indent=4)}", "green")
        utils.print_coloured(f"{json.dumps(self.toc_hierarchy_schema, indent=4)}", "green")
        with open(f"{self.doc_title}_toc_hierarchy_schema.json", "w") as f:
            json.dump(self.toc_hierarchy_schema, f, indent=4)
        with open(f"{self.doc_title}_appendix_toc_hierarchy_schema.json", "w") as f:
            json.dump(self.appendix_toc_hierarchy_schema, f, indent=4)
        #toc_hierarchy_schema = [(heading, level.count('#')) for heading, level in ordered_items]
        # remaining_sections = [heading for headings in toc_hierarchy_schema.values() for heading in headings]
        # unique_headings = set(remaining_sections)
        # for unique_heading in unique_headings:
        #     heading_content_count = sum(unique_heading in line for line in self.content_md_lines)
        #     heading_count = remaining_sections.count(unique_heading)
        #     difference = heading_content_count - heading_count
        #     if difference > 0:
        #         remaining_sections.extend([unique_heading] * difference)
        # utils.is_correct()
        # self.remaining_sections = remaining_sections
        # return toc_hierarchy_schema
    
    async def create_master_toc(self, toc_hierarchy_schema_levels: Dict[str, int], is_apx: bool = False) -> None:
        if is_apx:
            toc_lines = self.toc_md_apx_lines
            parts_file = f"{self.doc_title}_apx_parts.json"
            master_toc_file = f"{self.doc_title}_apx_master_toc.json"
        else:
            parts_file = f"{self.doc_title}_parts.json"
            master_toc_file = f"{self.doc_title}_master_toc.json"
            toc_lines = self.toc_md_lines
        parts = {}
        stack = []
        heading_futures = []
        item_futures = []
        item_buffer = []
        max_line_length = max(len(line.strip()) for line in toc_lines)
        skip_next_line = False
        for line in toc_lines:
            stripped_line = line.strip()
            level = None
            match_found = False
            for heading, level_num in toc_hierarchy_schema_levels:
                if len(heading) > max_line_length:
                    trimmed_heading = heading[:len(stripped_line)]
                else:
                    trimmed_heading = heading
                if trimmed_heading == stripped_line:
                    utils.print_coloured(f"Matched: {heading} in {stripped_line}", "green")
                    level = level_num
                    if len(heading) > len(stripped_line):
                        skip_next_line = True
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
                    item_futures.append((self.rate_limited_process(self.process_items, '\n'.join(item_buffer)), placeholder))
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
                heading_futures.append((self.rate_limited_process(self.process_heading, heading), placeholder))
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
            item_futures.append((self.rate_limited_process(self.process_items, '\n'.join(item_buffer)), placeholder))
            if stack:
                current = stack[-1][1]
                current["contents"] = placeholder
        utils.is_correct()
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
        with open(parts_file, "w") as f:
            json.dump(parts, f, indent=2)
        utils.print_coloured(f"{parts_file} created", "green")
        master_toc = schemas.parse_toc_dict(parts, pre_process=False)
        if is_apx:
            self.master_apx_toc = [toc.model_dump() for toc in master_toc]
            with open(master_toc_file, "w") as f:
                json.dump(self.master_apx_toc, f, indent=2, default=lambda x: x.dict())
            utils.print_coloured(f"{master_toc_file} created", "green")
        else:
            self.master_toc = [toc.model_dump() for toc in master_toc]
            with open(master_toc_file, "w") as f:
                json.dump(self.master_toc, f, indent=2, default=lambda x: x.dict())
            utils.print_coloured(f"{master_toc_file} created", "green")

    async def call_create_master_toc(self) -> None:
        if not self.toc_hierarchy_schema:
            await self.gen_toc_hierarchy_schema()
        #toc_hierarchy_schema_levels = [(heading, level.count('#')) for heading, level in self.toc_hierarchy_schema.items()]
        tasks = []
        toc_hierarchy_schema_levels = [
            (heading, level.count('#'))
            for level, headings in self.toc_hierarchy_schema.items()
            for heading in headings
        ]
        tasks.append(self.create_master_toc(toc_hierarchy_schema_levels))
        if self.appendix_toc_hierarchy_schema:
            toc_hierarchy_schema_apx_levels = [
                (heading, level.count('#'))
                for level, headings in self.appendix_toc_hierarchy_schema.items()
                for heading in headings
            ]
            tasks.append(self.create_master_toc(toc_hierarchy_schema_apx_levels, is_apx=True))
        await asyncio.gather(*tasks)
        
    def format_section_name_keys(self, section: str, number: str, title: str) -> str:
        full_section_name = f"{section} {number} {title}".strip()
        section_match = process.extractOne(full_section_name, self.toc_hierarchy_schema.keys(), score_cutoff=98)
        if section_match:
            utils.print_coloured(f"{full_section_name} -> {section_match[0]} ({section_match[1]})", "cyan")
            return section_match[0]
        variations = [
            f"{section} {number}".strip(),
            f"{section} {title}".strip(),
            f"{number} {title}".strip(),
            title.strip()
        ]
        for variation in variations:
            if variation:
                section_match = process.extractOne(variation, self.toc_hierarchy_schema.keys(), score_cutoff=98)
                if section_match:
                    utils.print_coloured(f"{variation} -> {section_match[0]} ({section_match[1]})", "yellow")
                    return section_match[0]
        if section != "":
            utils.print_coloured(f"Could not match: {full_section_name}", "red")
        return full_section_name
    
    def format_section_name_apx(self, section: str, number: str, title: str) -> str:
        # this is not generalisable - maybe get LLM to dynamically generate the schema
        return f'{section} {number}'
    
    def format_section_name(self, section: str, number: str, title: str) -> str:
        full_section_name = f"{section} {number} {title}".strip()
        section_match = process.extractOne(full_section_name, self.remaining_sections, score_cutoff=98)
        if section_match:
            matched_heading = section_match[0]
            utils.print_coloured(f"{full_section_name} -> {matched_heading} ({section_match[1]})", "cyan")
            #self.remaining_sections.remove(matched_heading)
            return matched_heading

        variations = [
            f"{section} {number}".strip(),
            f"{section} {title}".strip(),
            f"{number} {title}".strip(),
            title.strip()
        ]
        for variation in variations:
            if variation:
                section_match = process.extractOne(variation, self.remaining_sections, score_cutoff=98)
                if section_match:
                    matched_heading = section_match[0]
                    utils.print_coloured(f"{variation} -> {matched_heading} ({section_match[1]})", "yellow")
                    #self.remaining_sections.remove(matched_heading)
                    return matched_heading

        if section != "":
            utils.print_coloured(f"Could not match: {full_section_name}", "red")
        return full_section_name
    
    def add_content_to_master_toc(self, master_toc: schemas.TableOfContents) -> Dict[str, Dict[str, Any]]:
        return self.call_add_content_to_master_toc(master_toc)
    
    async def fake_create_master_toc(self) -> None:
        with open(f"{self.doc_title}_toc_hierarchy_schema.json", "r") as f:
            self.toc_hierarchy_schema = json.load(f)
        with open(f"{self.doc_title}_appendix_toc_hierarchy_schema.json", "r") as f:
            self.appendix_toc_hierarchy_schema = json.load(f)
        with open(f"{self.doc_title}_master_toc.json", "r") as f:
            self.master_toc = json.load(f)
        with open(f"{self.doc_title}_apx_master_toc.json", "r") as f:
            self.master_apx_toc = json.load(f)
        self.remaining_sections = [heading for headings in self.toc_hierarchy_schema.values() for heading in headings]
        apx_idxs = []
        for idx, line in enumerate(reversed(self.content_md_lines)):
            for heading in self.appendix_toc_hierarchy_schema['#']:
                if heading in line:
                    utils.print_coloured(f"Found {heading} in {line}", "yellow")
                    apx_idxs.append(len(self.content_md_lines) - idx)
                    break

        if apx_idxs:
            split_idx = min(apx_idxs)
            utils.print_coloured(f"Length of content_md_lines: {len(self.content_md_lines)}", "yellow")
            self.appendix_md_lines = self.content_md_lines[split_idx:]
            main_content = self.content_md_lines[:split_idx]
            self.content_md_lines = main_content
            utils.print_coloured(f"Splitting at {split_idx}", "yellow")
            utils.print_coloured(f"Length of content_md_lines after split: {len(self.content_md_lines)}", "yellow")
            with open(f"z{self.doc_title}_content.md", "w") as f:
                f.write('\n'.join(main_content))
            with open(f"zz{self.doc_title}_apx.md", "w") as f:
                f.write('\n'.join(self.appendix_md_lines))
    
    async def parse(self) -> Dict[str, Dict[str, Any]]:
        await self.fake_create_master_toc()
        #await self.call_create_master_toc()
        utils.is_correct(prompt="check master tocs")
        self.init_remaining_content_section_lines(self.content_md_lines, md_levels=False)
        master_toc_dict = self.add_content_to_master_toc(self.master_toc)
        if self.master_apx_toc:
            self.init_remaining_content_section_lines(self.appendix_md_lines, md_levels=False)
            self.init_child_format_section_name(self.format_section_name_apx)
            apx_master_toc_dict = self.add_content_to_master_toc(self.master_apx_toc)
            master_toc_dict["contents"].extend(apx_master_toc_dict["contents"])
        return master_toc_dict