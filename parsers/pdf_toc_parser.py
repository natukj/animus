from typing import Union, Any, Callable, Dict, Awaitable, List
import json
import asyncio
from fastapi import UploadFile
import fitz
import pathlib
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
        self.file_name: str = file.filename if isinstance(file, UploadFile) else pathlib.Path(file).stem
        #self.toc_pages: List[int] = list(range(1, 45))
        # with open("toc.md", "r") as f:
        #     self.toc_md_str = f.read()
        # self.toc_md_lines = self.toc_md_str.split("\n")
        # with open("content.md", "r") as f:
        #     self.content_md_str = f.read()
        # self.content_md_lines = self.content_md_str.split("\n")
        self.doc_title: str = None
        self.toc_pages: List[int] = None
        self.toc_pages_md: List[Dict[str, Any]] = None
        self.toc_md_str: str = None
        self.toc_md_lines: List[str] = None
        self.toc_md_apx_lines: List[str] = None
        self.content_md_str: str = None
        self.content_md_lines: List[str] = None
        self.toc_hierarchy_schema: Dict[str, str] = None
        self.master_toc: List[Dict[str, Any]] = None
        self.master_apx_toc: List[Dict[str, Any]] = None

    def to_markdown(self, doc: fitz.Document, pages: List[int] = None, page_chunks: bool = False) -> str | List[str]:
        """
        Convert the given text to Markdown format.
        """
        return utils.to_markdownOG(doc, pages=pages, page_chunks=page_chunks)
    
    async def find_toc_pages(self) -> List[int]:
        """
        Find the pages that contain the Table of Contents.
        """
        async def verify_toc_pages(page: int, start: bool = True) -> tuple:
            page_image = utils.encode_page_as_base64(self.document[page])
            if start:
                adjacent_page_image = utils.encode_page_as_base64(self.document[page - 1]) if page > 0 else None
            else:
                adjacent_page_image = utils.encode_page_as_base64(self.document[page + 1]) if page < len(self.document) - 1 else None
            if adjacent_page_image:
                messages = utils.message_template_vision(prompts.VERIFY_TOC_PAGES_PROMPT, page_image, adjacent_page_image)
            else:
                messages = utils.message_template_vision(prompts.VERIFY_TOC_PAGE_PROMPT, page_image)

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
        max_gap = 5 
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
            if percentage > 0.4: # somewhat arbitrary threshold
                if not toc_pages or i - toc_pages[-1] <= max_gap:
                    toc_pages.append(i)
                elif toc_pages:
                    break
            i += 1
            if i == 15 and check_right: # logic if there are not toc page nums
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
                start_tp, start_bp = await self.rate_limited_process(
                    verify_toc_pages, toc_pages[start_index] - start_count
                )
                if start_tp and not start_bp:
                    start_found = True
                elif start_tp and start_bp:
                    start_count += 1
                else:
                    start_index += 1
            if not end_found:
                end_tp, end_bp = await self.rate_limited_process(
                    verify_toc_pages, toc_pages[end_index] + end_count, start=False
                )
                if end_tp and not end_bp:
                    end_found = True
                elif end_tp and end_bp:
                    end_count += 1
                else:
                    end_index -= 1
        verified_toc_pages = list(range(max(0, toc_pages[start_index] - start_count), toc_pages[end_index] + end_count + 1)) 
        utils.print_coloured(f"Verified ToC pages: {verified_toc_pages}", "green")
        utils.is_correct()
        return verified_toc_pages
    
    async def extract_toc(self) -> None:
        """
        Extract the Table of Contents from the document.
        """
        if not self.toc_pages:
            self.toc_pages = await self.find_toc_pages()

        # ensure no overlap in pages (this might have been due to threading)
        content_pages = list(range(self.toc_pages[-1] + 1, len(self.document)))
        if set(self.toc_pages) & set(content_pages):
            raise ValueError("ToC pages overlap with content pages")

        self.toc_pages_md = self.to_markdown(self.document, self.toc_pages, True)
        self.content_md_str = self.to_markdown(self.document, content_pages, False)

        with open(f"{self.file_name}_toc_pages.json", "w") as f:
            json.dump(self.toc_pages_md, f, indent=4)
        pathlib.Path(f"{self.file_name}_content.md").write_bytes(self.content_md_str.encode())

        # with open(f"{self.file_name}_toc_pages.json", "r") as f:
        #     self.toc_pages_md = json.load(f)
        # with open(f"{self.file_name}_content.md", "r") as f:
        #     self.content_md_str = f.read()

        meta_doc_title = self.toc_pages_md[0]['metadata'].get('title')
        self.doc_title = meta_doc_title if meta_doc_title else self.file_name
        toc_md_str = ""
        for page in self.toc_pages_md:
            toc_md_str += page.get("text", "")
        self.toc_md_str = toc_md_str
        pathlib.Path(f"{self.doc_title}_toc.md").write_bytes(self.toc_md_str.encode())
        self.toc_md_lines = [line for line in self.toc_md_str.split("\n") if line.strip()]
        pathlib.Path(f"{self.doc_title}_content.md").write_bytes(self.content_md_str.encode())
        self.content_md_lines = [line for line in self.content_md_str.split("\n") if line.strip()]
    
    async def determine_toc_structure(self):
        if not self.toc_md_lines and not self.content_md_lines:
            await self.extract_toc()
        toc_md_section_lines = [line for line in self.toc_md_lines if line.startswith("#")]
        utils.print_coloured(f"{len(toc_md_section_lines)} / {len(self.toc_md_lines)} -> {len(toc_md_section_lines) / len(self.toc_md_lines)}", "yellow")
        if len(toc_md_section_lines) / len(self.toc_md_lines) > 0.05:
            if len(self.toc_pages) >= 3:
                return "VarTextSize"
            else:
                return "VarTextSizeSmall"
        else:
            if len(self.toc_pages) >= 3:
                return "SameTextSize"
            else:
                return "SameTextSizeSmall"
            
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
        semaphore = asyncio.Semaphore(50)
        async with semaphore:
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
