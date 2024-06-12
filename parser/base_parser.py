from typing import Union, Any, Callable, List, Dict, Tuple, Awaitable
from abc import ABC, abstractmethod
from fastapi import UploadFile
import asyncio
import base64
import fitz  
import tiktoken
import utils


class BaseParser(ABC):
    def __init__(self, rate_limit: int = 50):
        self.semaphore = asyncio.Semaphore(rate_limit)

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
                    print(f"Error during rate_limited_process: {e}")
                    print(f"Retrying... Attempt {attempts + 1}\nargs: {args} and kwargs: {kwargs}")
                    attempts += 1
                    if attempts >= max_attempts:
                        print(f"Failed after {max_attempts} attempts")
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
