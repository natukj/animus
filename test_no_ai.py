from pydantic import BaseModel, ValidationError
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
from parser.base_parser import BaseParser

"""COMPLEX TYPICAL"""
pages = list(range(2, 32))
grouped_pages = [pages[i:i+2] for i in range(0, len(pages), 2)]
vol_num=9
# doc = fitz.open(f"/Users/jamesqxd/Documents/norgai-docs/TAX/C2024C00046VOL0{vol_num}.pdf")
# base_parser = BaseParser()
# toc_md_str = base_parser.to_markdownOG(doc=doc, pages=pages, page_chunks=False)
# pathlib.Path(f"vol{vol_num}(OG)2.md").write_bytes(toc_md_str.encode())
async def main_run():
    
    toc_file_path = f"vol{vol_num}(OG)2.md"
    with open(toc_file_path, "r") as f:
        toc_md_str = f.read()

    toc_md_lines = toc_md_str.split("\n")
    parts = {}
    stack = []

    for line in toc_md_lines:
        stripped_line = line.strip()
        if stripped_line.startswith("#"):
            level = stripped_line.count("#")
            heading = stripped_line.lstrip('#').strip()
            #heading = re.sub(r'\s\d+$', '', heading)
            placeholder = str(uuid.uuid4()) 
            
            while stack and stack[-1][0] >= level:
                stack.pop()
            
            if stack:
                parent = stack[-1][1]
                if "children" not in parent:
                    parent["children"] = {}
                parent["children"][heading] = {}
                stack.append((level, parent["children"][heading]))
            else:
                parts[heading] = {}
                stack.append((level, parts[heading]))
        else:
            if stack:
                if stripped_line:
                    current = stack[-1][1]
                    if "content" not in current:
                        current["content"] = ""
                    current["content"] += stripped_line + "\n"
    
    with open("vol9OGtoc2.json", "w") as f:
        json.dump(parts, f, indent=4)

asyncio.run(main_run())
