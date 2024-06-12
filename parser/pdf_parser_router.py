from typing import Union, Any, Optional, Dict, Tuple, List, NewType
import json
import asyncio
import base64
from fastapi import UploadFile
import fitz
import re
import uuid
from collections import Counter, defaultdict
from thefuzz import process  
import llm, prompts, utils
from parser.pdf_parser_CT import PDFCTParser
from parser.pdf_parser_CA import PDFCAParser
from parser.pdf_parser_ToC import PDFToCParser

class PDFParserRouter:
    def __init__(self):
        self.toc_parser = None
        self.parser_type = None
        self.parsers = {
            "CT": PDFCTParser
        }
    async def parse(self, file: Union[UploadFile, str]) -> Dict[str, Any]:
        if not self.parser_type:
            await self.get_parser_type(file)
        if self.parser_type not in self.parsers:
            raise ValueError(f"Invalid parser type: {self.parser_type}")
        specific_parser_class = self.parsers[self.parser_type]
        specific_parser = specific_parser_class(self.toc_parser)
        print(f"Using parser: {specific_parser_class.__name__}")  # Debug print
        
        return await specific_parser.parse()
    
    async def get_parser_type(self, file: Union[UploadFile, str]) -> str:
        self.toc_parser = PDFToCParser(file)
        self.parser_type = await self.toc_parser.determine_toc_structure()