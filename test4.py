from pydantic import BaseModel, ValidationError
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

def encode_page_as_base64(page: fitz.Page):
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    return base64.b64encode(pix.tobytes()).decode('utf-8')


pages = list(range(0, 59))

doc = fitz.open("/Users/jamesqxd/Documents/norgai-docs/ACTS/ukCOMPANIESACT2006.pdf")

async def main_run():
    base_parser = BaseParser()
    toc_md_section_joined_lines = base_parser.to_markdown(doc, [0])
    page = doc[0]
    USER_PROMPT = prompts.TOC_HIERARCHY_USER_PROMPT_NOMD.format(TOC_HIERARCHY_SCHEMA_TEMPLATE=prompts.TOC_HIERARCHY_SCHEMA_TEMPLATE, toc_md_string=toc_md_section_joined_lines)
    messages=[
        {
        "role": "user",
        "content": [
            {"type": "text", "text": USER_PROMPT},
            {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{encode_page_as_base64(page)}",
            },
            },
        ],
        }
    ]
    response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
    message_content = response.choices[0].message.content
    print(json.dumps(message_content, indent=4))

asyncio.run(main_run())