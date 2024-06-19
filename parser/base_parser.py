from typing import Union, Any, Callable, List, Dict, Tuple, Awaitable
from abc import ABC, abstractmethod
import re
from thefuzz import process  
import asyncio
import json
import llm, prompts, schemas, utils


class BaseParser(ABC):
    def __init__(self, rate_limit: int = 50):
        self.semaphore = asyncio.Semaphore(rate_limit)
        self.remaining_section_lines: List[Tuple[str, int]] = []
        self.child_format_section_name: Callable = None

    @abstractmethod
    def format_section_name(self, section: str, number: str, title: str) -> str:
        """
        Format the section name. To be implemented by subclasses.
        """
        pass
    
    @abstractmethod
    async def create_master_toc(self) -> None:
        """
        Split the Table of Contents into its constituent parts and create a master Table of Contents. 
        """
        pass

    @abstractmethod
    def add_content_to_master_toc(self) -> Dict[str, Dict[str, Any]]:
        """
        Add content to the master Table of Contents.
        """
        pass

    @abstractmethod
    def parse(self) -> Dict[str, Dict[str, Any]]:
        """
        Parse the PDF document.
        """
        pass

    async def process_heading(self, heading: str) -> Dict[str, str]:
        """
        Format a heading using the OpenAI API
        -> {"section": "Chapter", "number": "1", "title": "Introduction"}
        """
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

    async def process_items(self, content: str) -> List[Dict[str, str]]:
        """
        Format a list of items using the OpenAI API
        -> [{"number": "1", "title": "title1"}, {"number": "2", "title": "title2"}]
        """
        messages = [
                {"role": "system", "content": prompts.TOC_HIERARCHY_SYS_PROMPT},
                {"role": "user", "content": prompts.TOC_ITEMS_USER.format(content=content)}
            ]
        response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
        try:
            if not response.choices or not response.choices[0].message:
                utils.print_coloured(f"Unexpected response structure: {response}", "red")
                raise Exception("Unexpected response structure")
            
            message_content = response.choices[0].message.content
            items_dict = json.loads(message_content)
            items = items_dict['items']
            utils.print_coloured(items, "cyan")
            return items
        except Exception as e:
            utils.print_coloured(f"process_items error loading json: {e}", "red")

    async def process_queue(self, futures):
        return await asyncio.gather(*[future for future, _ in futures])
    
    def init_remaining_content_section_lines(self, content_md_lines: List[str], md_levels: bool = True):
        """
        Initialise the `remaining_content_section_lines` list.
        If `md_levels` is True, only lines starting with '#' are considered.
        """
        if md_levels:
            self.remaining_content_section_lines = [
                (line, idx) for idx, line in enumerate(content_md_lines) if line.startswith('#')
            ]
        else:
            self.remaining_content_section_lines = [
                (line, idx) for idx, line in enumerate(content_md_lines)
            ]
        self.content_md_lines = content_md_lines
    
    def init_child_format_section_name(self, child_format_section_name: Callable):
        self.child_format_section_name = child_format_section_name
    
    def get_section_content(
        self,
        next_section: Tuple[str, str, str],
        section: Tuple[str, str, str] = None
    ) -> Tuple[str, int]:
        if section:
            utils.print_coloured(f"Current Section: {section}", "cyan")
        utils.print_coloured(f"Next Section: {next_section}", "cyan")
        if section:
            formatted_section_name = self.child_format_section_name(*section)
            section_name = section[0] if section[0] else None
            section_number = section[1] if section[1] else None
            if section_number and section_name:
                filtered_remaining_content_section_lines = [
                    (line, idx) for line, idx in self.remaining_content_section_lines 
                    if f'{section_name.lower()} {section_number}' in line.lower()
                ]
                start_matches = process.extractBests(
                    formatted_section_name, 
                    [line for line, _ in filtered_remaining_content_section_lines], 
                    score_cutoff=80, 
                    limit=10
                )
            elif section_number:
                filtered_remaining_content_section_lines = [
                    (line, idx) for line, idx in self.remaining_content_section_lines 
                    if section_number in line
                ]
                start_matches = process.extractBests(
                    formatted_section_name, 
                    [line for line, _ in filtered_remaining_content_section_lines], 
                    score_cutoff=80, 
                    limit=10
                )
            else:
                start_matches = process.extractBests(
                    formatted_section_name, 
                    [line for line, _ in self.remaining_content_section_lines], 
                    score_cutoff=80, 
                    limit=10
                )
            if start_matches:
                start_highest_score = max(start_matches, key=lambda x: x[1])[1]
                start_highest_score_matches = [match for match in start_matches if match[1] == start_highest_score]
                start_matched_line = min(
                    start_highest_score_matches, 
                    key=lambda x: next(idx for line, idx in self.remaining_content_section_lines if line == x[0])
                )[0]
                start_line_idx = next(idx for line, idx in self.remaining_content_section_lines if line == start_matched_line)
                utils.print_coloured(f"START: {formatted_section_name} -> {start_matched_line} [{start_line_idx}]", "green")
                utils.print_coloured(f"from: {start_matches}", "yellow")
                self.remaining_content_section_lines = [item for item in self.remaining_content_section_lines if item[1] > start_line_idx]
            else:
                utils.print_coloured(f"Could not match start: {formatted_section_name}", "red")
                start_line_idx = self.remaining_content_section_lines[0][1]
        else:
            start_line_idx = self.remaining_content_section_lines[0][1]

        if next_section:
            next_formatted_section_name = self.child_format_section_name(*next_section)
            next_section_name = next_section[0] if next_section[0] else None
            next_number = next_section[1] if next_section[1] else None

            if next_number and next_section_name:
                utils.print_coloured(f"FILTER NUMBER + SECTION {next_formatted_section_name}", "cyan")
                filtered_remaining_content_section_lines = [
                    (line, idx) for line, idx in self.remaining_content_section_lines 
                    if f'{next_section_name.lower()} {next_number}' in line.lower()
                ]
                matches = process.extractBests(
                    next_formatted_section_name, 
                    [line for line, _ in filtered_remaining_content_section_lines], 
                    score_cutoff=80, 
                    limit=10
                )
            elif next_number:
                filtered_remaining_content_section_lines = [
                    (line, idx) for line, idx in self.remaining_content_section_lines 
                    if re.search(r'\b' + re.escape(next_number) + r'\b', line)
                ]
                matches = process.extractBests(
                    next_formatted_section_name, 
                    [line for line, _ in filtered_remaining_content_section_lines], 
                    score_cutoff=80, 
                    limit=10
                )
            else:
                matches = process.extractBests(
                    next_formatted_section_name, 
                    [line for line, _ in self.remaining_content_section_lines], 
                    score_cutoff=80, 
                    limit=10
                )
            if matches:
                highest_score = max(matches, key=lambda x: x[1])[1]
                # NOTE special case -> Match: 160 Appointment of directors of public company to be voted on individually: 160 (appointment of directors of public company to be voted on individually). [4746]
                # from: [('160 (appointment of directors of public company to be voted on individually).', 99), ('**160****Appointment of directors of public company to be voted on individually**', 98), ('**1160 Meaning of “subsidiary” etc: power to amend**', 86)]
                unique_scores = sorted(set([match[1] for match in matches]))
                if len(unique_scores) > 1:
                    closely_scored_matches = [
                        match for match in matches
                        if (highest_score - match[1] < 10) and match[1] >= 85
                    ]
                    formatted_closely_scored_matches = [
                        match for match in closely_scored_matches
                        if match[0].lstrip().startswith(('#', '*', '_'))
                    ]
                    if formatted_closely_scored_matches:
                        highest_score = max(formatted_closely_scored_matches, key=lambda x: x[1])[1]
                # end special case
                highest_score_matches = [match for match in matches if match[1] == highest_score]
                matched_line = min(
                    highest_score_matches, 
                    key=lambda x: next(idx for line, idx in self.remaining_content_section_lines if line == x[0])
                )[0]
                line_idx = next(idx for line, idx in self.remaining_content_section_lines if line == matched_line)
                utils.print_coloured(f"{next_formatted_section_name} -> {matched_line} [{line_idx}]", "green")
                utils.print_coloured(f"from: {matches}", "yellow")
                if "_Registrar’s power to strike off defunct company_" in next_formatted_section_name:
                    print(f"Match: {next_formatted_section_name}: {matched_line} [{line_idx}]")
                    print("from:", matches)
            else:
                i = 0
                for line, idx in self.remaining_content_section_lines:
                    print(f"Line: {line} [{idx}]")
                    i += 1
                    if i > 10:
                        break
                raise ValueError(f"Could not match end: {next_formatted_section_name}")
        else:
            line_idx = len(self.content_md_lines)

        section_content = "\n".join(self.content_md_lines[start_line_idx:line_idx-1])
        num_tokens = utils.count_tokens(section_content)
        utils.print_coloured(f"num tokens {num_tokens}", "magenta")
        self.remaining_content_section_lines = [item for item in self.remaining_content_section_lines if item[1] >= line_idx]
        return section_content, num_tokens
    
    def call_add_content_to_master_toc(self,
        master_toc: schemas.TableOfContents) -> Dict[str, Dict[str, Any]]:
        def traverse_sections(
            sections: List[Union[schemas.TableOfContents, schemas.TableOfContentsChild]],
            parent_dict: Dict[str, Any],
            flattened_toc: List[Union[schemas.TableOfContents, schemas.TableOfContentsChild]]
        ):
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
                        section_content, section_tokens = self.get_section_content(next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, schemas.TableOfContents) else ("", next_item.number, next_item.title))
                        section_dict["content"] = section_content
                        section_dict["tokens"] = section_tokens
                    else:
                        section_content, section_tokens = self.get_section_content(next_section=None)
                        section_dict["content"] = section_content
                        section_dict["tokens"] = section_tokens

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
                        section_content, section_tokens = self.get_section_content(next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, schemas.TableOfContents) else ("", next_item.number, next_item.title))
                        child_dict["content"] = section_content
                        child_dict["tokens"] = section_tokens
                    else:
                        section_content, section_tokens = self.get_section_content(next_section=None)
                        child_dict["content"] = section_content
                        child_dict["tokens"] = section_tokens

        master_toc_dict = {"contents": []}
        toc_models = [schemas.convert_to_model(item) for item in master_toc]
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
                section_content, section_tokens = self.get_section_content(section=(item.section, item.number, item.title), next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, schemas.TableOfContents) else ("", next_item.number, next_item.title))
                section_dict["content"] = section_content
                section_dict["tokens"] = section_tokens
            else:
                section_content, section_tokens = self.get_section_content(next_section=None)
                section_dict["content"] = section_content
                section_dict["tokens"] = section_tokens
            traverse_sections(item.children, section_dict, flattened_toc)

        return master_toc_dict
    
    async def rate_limited_process(
        self, 
        process_function: Callable[..., Awaitable[Any]],
        *args: Any, 
        max_attempts: int = 5, 
        **kwargs: Any
    ) -> Any:
        """
        rate-limited processing with retries.

        Args:
            process_function (Callable): The function to execute with rate limiting.
            *args: Arguments to pass to the process function.
            max_attempts (int): Maximum number of retry attempts.
            **kwargs: Keyword arguments to pass to the process function.

        Returns:
            Any: The result of the process function or None if it fails after max attempts.
        """
        attempts = 0
        async with self.semaphore:
            while attempts < max_attempts:
                try:
                    return await process_function(*args, **kwargs)
                except Exception as e:
                    function_name = process_function.__name__ if hasattr(process_function, '__name__') else 'Unknown function'
                    utils.print_coloured(f"Error during RLP {function_name}: {e}", "red")
                    # utils.print_coloured(f"Retrying... Attempt {attempts + 1}\nargs: {args} and kwargs: {kwargs}", "red")
                    utils.print_coloured(f"Retrying... Attempt {attempts + 1}", "red")
                    attempts += 1
                    if attempts >= max_attempts:
                        utils.print_coloured(f"Failed after {max_attempts} attempts", "red")
                        return None
        
    

# class PDFParserRouter:
#     """Routes PDFs to appropriate parsers based on complexity."""

#     def __init__(self):
#         self.simple_parser = SimplePDFParser()
#         self.complex_parser = ComplexPDFParser()

#     def parse(self, pdf_path: str) -> str: 
#         """Parses a PDF using the appropriate parser."""
#         if self._is_complex(pdf_path):
#             print("Using ComplexPDFParser")
#             return self.complex_parser.parse(pdf_path)  # Assuming you define a 'parse' method
#         else:
#             print("Using SimplePDFParser")
#             return self.simple_parser.parse(pdf_path)  # Assuming you define a 'parse' method

#     def _is_complex(self, pdf_path: str) -> bool:
#         """
#         Determine if a PDF is complex. 

#         This is a placeholder - replace with your actual complexity detection logic.
#         """
#         # Example (replace with your logic):
#         doc = fitz.open(pdf_path)
#         if doc.page_count > 50: 
#             return True
#         # Add more conditions based on your needs
#         return False
    
#     def to_markdown(self, doc: fitz.Document, pages: List[int] = None) -> str:
#         """
#         Convert the given text to Markdown format.
#         """
#         return utils.to_markdown(doc, pages)
    
#     def to_markdownOG(self, doc: fitz.Document, pages: List[int] = None, page_chunks: bool = False) -> str | List[str]:
#         """
#         Convert the given text to Markdown format.
#         """
#         return utils.to_markdownOG(doc, pages=pages, page_chunks=page_chunks)
    
#     def to_markdownOOG(self, doc: fitz.Document, pages: List[int] = None) -> str:
#         """
#         Convert the given text to Markdown format.
#         """
#         return utils.to_markdownOOG(doc, pages)
