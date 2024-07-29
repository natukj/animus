from typing import Any, Dict
import json
import asyncio
import os
import uuid
import parsers, schemas, utils

class VarTextSizeAdapter(parsers.PDFParser):
    def __init__(self, toc_parser: parsers.PDFToCParser, output_dir: str, checkpoint: bool, verbose: bool, rate_limit: int = 50) -> None:
        """
        PDFParser adapter that uses the variable text size for hierarchy determination.
        
        :param toc_parser: An instance of PDFToCParser containing the parsed data.
        :param output_dir: Directory to save output files.
        :param checkpoint: Whether to use checkpoints during parsing.
        :param verbose: Whether to print verbose output.
        :param rate_limit: Rate limit for API calls.
        """
        super().__init__(output_dir, checkpoint, verbose, rate_limit)
        self.doc_title = toc_parser.file_name
        self.toc_md_lines = toc_parser.toc_md_lines
        self.content_md_lines = toc_parser.content_md_lines
        self.master_toc = toc_parser.master_toc
        self.init_child_format_section_name(self.format_section_name)

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

        toc_parts_file = os.path.join(self.output_dir, f"{self.doc_title}_parts.json")
        with open(toc_parts_file, "w") as f:
            json.dump(parts, f, indent=2)
        if self.verbose:
            utils.print_coloured(f"ToC parts saved to: {self.doc_title}_parts.json", "green")

        master_toc = schemas.parse_toc_dict(parts)
        self.master_toc = [toc.model_dump() for toc in master_toc]
        master_toc_file = os.path.join(self.output_dir, f"{self.doc_title}_master_toc.json")
        with open(master_toc_file, "w") as f:
            json.dump(self.master_toc, f, indent=2, default=lambda x: x.dict())
        if self.verbose:
            utils.print_coloured(f"Master ToC saved to: {self.doc_title}_master_toc.json", "green")
    
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
        return self.call_add_content_to_master_toc(self.master_toc)
    
    async def fake_create_master_toc(self) -> None:
        with open("add_dir_to_master_toc.json", "r") as f:
            self.master_toc = json.load(f)
    
    async def parse(self) -> Dict[str, Dict[str, Any]]:
        await self.create_master_toc()
        #await self.fake_create_master_toc()
        self.init_remaining_content_section_lines(self.content_md_lines)
        master_toc_dict = self.add_content_to_master_toc()
        return master_toc_dict