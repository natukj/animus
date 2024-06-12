from typing import Union, Any, Optional, Dict, Tuple, List, NewType
import json
import asyncio
import base64
from fastapi import UploadFile
import fitz
import re
import uuid
import pathlib
from collections import Counter, defaultdict
from thefuzz import process  
import llm, prompts, utils

class PDFToCParser:
    def __init__(self, file: Union[UploadFile, str]) -> None:
        if isinstance(file, UploadFile):
            file_content = file.read()
            self.document = fitz.open(stream=file_content, filetype="pdf")
        elif isinstance(file, str):
            self.document = fitz.open(file)
        else:
            raise ValueError("file must be an instance of UploadFile or str.")
        self.toc_pages: List[int] = list(range(2, 32))
        with open("toc.md", "r") as f:
            self.toc_md_str = f.read()
        self.toc_md_lines = self.toc_md_str.split("\n")
        with open("content.md", "r") as f:
            self.content_md_str = f.read()
        self.content_md_lines = self.content_md_str.split("\n")
        #self.toc_md_str: str = None
        # self.toc_md_lines: List[str] = None
        # self.content_md_str: str = None
        # self.content_md_lines: List[str] = None
        self.toc_hierarchy_schema: Dict[str, str] = None
        self.adjusted_toc_hierarchy_schema: Dict[str, str] = None
        self.master_toc: List[Dict[str, Any]] = None

    def to_markdown(self, doc: fitz.Document, pages: List[int] = None, page_chunks: bool = False) -> str | List[str]:
        """
        Convert the given text to Markdown format.
        """
        return utils.to_markdownOG(doc, pages=pages, page_chunks=page_chunks)
    
    def encode_page_as_base64(self, page: fitz.Page) -> str:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        return base64.b64encode(pix.tobytes()).decode('utf-8')
    
    def message_template_vision(self, user_prompt: str, *images: str) -> Dict[str, Any]:
        message_template = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt}
                    ] + [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}}
                        for image in images[:30]  # limit to the first 30 images think gpt4o will only take 39
                    ]
                }
            ]
        return message_template
    
    async def find_toc_pages(self) -> List[int]:
        """
        Find the pages that contain the Table of Contents.
        """
        async def verify_toc_pages(page: int, start: bool = True) -> tuple:
            page_image = self.encode_page_as_base64(self.document[page])
            if start:
                adjacent_page_image = self.encode_page_as_base64(self.document[page - 1]) if page > 0 else None
            else:
                adjacent_page_image = self.encode_page_as_base64(self.document[page + 1]) if page < len(self.document) - 1 else None
            if adjacent_page_image:
                messages = self.message_template_vision(prompts.VERIFY_TOC_PAGES_PROMPT, page_image, adjacent_page_image)
            else:
                messages = self.message_template_vision(prompts.VERIFY_TOC_PAGE_PROMPT, page_image)

            response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
            message_content = response.choices[0].message.content
            try:
                toc_response = json.loads(message_content)
                if 'bottom_page' in toc_response:
                    top_page_is_toc = toc_response['top_page']
                    bottom_page_is_toc = toc_response['bottom_page']
                    if start:
                        utils.print_coloured(f"{page}:{page-1} - {top_page_is_toc}:{bottom_page_is_toc}", "yellow")
                    else:
                        utils.print_coloured(f"{page}:{page+1} - {top_page_is_toc}:{bottom_page_is_toc}", "yellow")
                    return (top_page_is_toc, bottom_page_is_toc)
                else:
                    return (toc_response['top_page'], False)
            except json.JSONDecodeError:
                utils.print_coloured(f"JSONDecodeError: {message_content}", "red")
                raise

        toc_pages = []
        i = 0
        check_right = True 
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
            if i == 30 and check_right: # logic if there are not toc page nums
                if not toc_pages:
                    check_right = False
                    i = 0
        if not toc_pages:
            raise ValueError("No Table of Contents found - can not proceed.")
        utils.print_coloured(f"Potential ToC pages: {toc_pages}", "yellow")
        start_index = 0
        end_index = len(toc_pages) - 1
        start_found, end_found = False, False
        start_count, end_count = 0, 0
        while start_index < end_index:
            if start_found and end_found:
                break
            if not start_found:
                start_tp, start_bp = await verify_toc_pages(toc_pages[start_index]-start_count)
                if start_tp and not start_bp:
                    start_found = True
                elif start_tp and start_bp:
                    start_count += 1
                else:
                    start_index += 1
            if not end_found:
                end_tp, end_bp = await verify_toc_pages(toc_pages[end_index]+end_count, start=False)
                if end_tp and not end_bp:
                    end_found = True
                elif end_tp and end_bp:
                    end_count += 1
                else:
                    end_index -= 1
        verified_toc_pages = list(range(max(0, toc_pages[start_index] - start_count), toc_pages[end_index] + end_count + 1)) 
        utils.print_coloured(f"Verified ToC pages: {verified_toc_pages}", "green")
        return verified_toc_pages
    
    async def extract_toc(self) -> None:
        """
        Extract the Table of Contents from the document.
        """
        if not self.toc_pages:
            self.toc_pages = await self.find_toc_pages()
        self.toc_md_str = self.to_markdown(doc=self.document, pages=self.toc_pages, page_chunks=False)
        pathlib.Path(f"toc.md").write_bytes(self.toc_md_str.encode())
        self.toc_md_lines = self.toc_md_str.split("\n")
        self.content_md_str = self.to_markdown(doc=self.document, pages=(list(range(self.toc_pages[-1] + 1, len(self.document)))), page_chunks=False)
        pathlib.Path(f"content.md").write_bytes(self.content_md_str.encode())
        self.content_md_lines = self.content_md_str.split("\n")
    
    async def determine_toc_structure(self):
        if not self.toc_md_lines and not self.content_md_lines:
            await self.extract_toc()
        toc_md_section_lines = [line for line in self.toc_md_lines if line.startswith("#")]
        utils.print_coloured(f"Number of ToC lines: {len(toc_md_section_lines)} out of {len(self.toc_md_lines)} with a ratio of {len(toc_md_section_lines) / len(self.toc_md_lines)}", "yellow")
        if len(toc_md_section_lines) / len(self.toc_md_lines) > 0.05:
            if len(self.toc_pages) >= 3:
                return "CT"
            else:
                return "ST"
        else:
            if len(self.toc_pages) >= 3:
                return "CA"
            else:
                return "SA"
