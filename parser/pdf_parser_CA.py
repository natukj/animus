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
from parser.base_parser import BaseParser

class PDFCAParser(BaseParser):
    def __init__(self, rate_limit: int = 50):
        super().__init__(rate_limit)
        self.document = None
        self.toc_pages = None
        self.toc_md_string = None
        self.content_md_string = None
        self.toc_hierarchy_schema = None
        self.adjusted_toc_hierarchy_schema = None
        self.master_toc = None
        self.no_md_flag = False