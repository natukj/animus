from typing import Union, Any, Callable, List, Dict, Tuple, Awaitable
from abc import ABC, abstractmethod
from fastapi import UploadFile
import asyncio
import fitz  
import tiktoken
import utils


class BaseParser:
    def __init__(self, rate_limit: int = 50):
        if fitz.pymupdf_version_tuple < (1, 24, 0):
            raise NotImplementedError("PyMuPDF version 1.24.0 or later is needed.")
        self.semaphore = asyncio.Semaphore(rate_limit)

    def count_tokens(self, text: str, encoding_name: str = "cl100k_base") -> int:
        """
        count the number of tokens in the given text using the specified encoding.
        """
        encoding = tiktoken.get_encoding(encoding_name)
        num_tokens = len(encoding.encode(text))
        return num_tokens
    
    def to_markdown(self, doc: fitz.Document, pages: List[int] = None) -> str:
        """
        Convert the given text to Markdown format.
        """
        return utils.to_markdown(doc, pages)
    
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
                    attempts += 1
                    if attempts >= max_attempts:
                        print(f"Failed after {max_attempts} attempts")
                        return None

    
