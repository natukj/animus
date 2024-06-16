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
from deepdiff import DeepDiff
import copy

"""COMPLEX ATYPICAL"""
def compare_schemas(original, corrected):
    # Compare dictionaries
    diff = DeepDiff(original, corrected, ignore_order=True)
    return diff

def encode_page_as_base64(page: fitz.Page):
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 1))
    return base64.b64encode(pix.tobytes()).decode('utf-8')

pages = list(range(0, 59))
#grouped_pages = [pages[i:i+2] for i in range(0, len(pages), 2)]
grouped_pages = [pages[:2]] + [pages[i:i+4] for i in range(2, len(pages), 4)]

doc = fitz.open("/Users/jamesqxd/Documents/norgai-docs/ACTS/ukCOMPANIESACT2006.pdf")
async def main_run():
    # toc_file_path = "toc.md"
    # with open(toc_file_path, "r") as f:
    #     toc_md_str = f.read()
    # toc_md_lines = [line.strip() for line in toc_md_str.split("\n") if line.strip()]
    # section_lines = [line for line in toc_md_lines if not re.match(r'^\s*\d+[\s\.].*', line)]
    # toc_md_toc_section_str = "\n".join(section_lines)
    # with open("uk_toc_section.md", "w") as f:
    #     f.write(toc_md_toc_section_str)
    # exit()
    #toc_section_list = utils.to_markdownOG(doc=doc, pages=pages, page_chunks=True)
    with open("uk_toc_section_list.json", "r") as f:
        toc_section_list = json.load(f)

    individual_page_texts = {page: toc_section_list[pages.index(page)].get("text", "") for page in pages}
    grouped_pages_text = {tuple(group): [individual_page_texts[page] for page in group] for group in grouped_pages}
    end_pages = []
    end_pages_text = ""
    appendix_break = False
    for group in list(reversed(grouped_pages)):
        remaining_group_pages = []
        for page in reversed(group):
            page_text = individual_page_texts[page]
            if any(keyword in page_text.lower() for keyword in ['schedule', 'appendix', 'appendices']) and not appendix_break:
                end_pages.append(page)
                end_pages_text += page_text
            else:
                appendix_break = True
                remaining_group_pages.insert(0, page)

        remaining_group_text = "".join(individual_page_texts[page] for page in remaining_group_pages)
        if remaining_group_pages:
            grouped_pages_text[tuple(remaining_group_pages)] = remaining_group_text
            if tuple(remaining_group_pages) != tuple(group):
                del grouped_pages_text[tuple(group)]
        else:
            del grouped_pages_text[tuple(group)]

    grouped_end_pages_text = {tuple(end_pages): end_pages_text} if end_pages else {}

    # for i, (group, text) in enumerate(grouped_pages_text.items()):
    #     print(f"Pages({i}) {group}: {len(text)}")
    # for group, text in grouped_end_pages_text.items():
    #     print(f"END Pages {group}: {len(text)}")

    async def process_page(page_nums_and_text: tuple, prior_schema: dict = None, example: str = None):
        page_nums, toc_md_toc_section_str = page_nums_and_text
        if not prior_schema:
            USER_PROMPT = prompts.TOC_HIERARCHY_USER_VISION.format(toc_md_string=toc_md_toc_section_str)
        else:
            USER_PROMPT = prompts.TOC_HIERARCHY_USER_VISION_PLUS.format(initial_toc_hierarchy_schema=json.dumps(prior_schema, indent=4), example=example, num_levels=len(prior_schema), toc_md_string=toc_md_toc_section_str)
        if not example:
            page = doc[page_nums[0]]
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": USER_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encode_page_as_base64(page)}",
                            },
                        }
                    ]
                }
            ]
            if len(page_nums) > 1:
                for next_page_num in page_nums[1:]:
                    next_page = doc[next_page_num]
                    messages[0]["content"].append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encode_page_as_base64(next_page)}",
                            },
                        }
                    )
        else:
            messages = [
                    {"role": "system", "content": prompts.TOC_HIERARCHY_SYS_PROMPT},
                    {"role": "user", "content": prompts.TOC_HIERARCHY_USER_PLUS.format(prior_schema_template=json.dumps(prior_schema, indent=2), example=example, num_levels=len(prior_schema), toc_md_string=toc_md_toc_section_str)}
                ]
            #utils.print_coloured(f"Prompt: {prompts.TOC_HIERARCHY_USER_PLUS.format(prior_schema=json.dumps(prior_schema, indent=2), prior_schema_descriptions=example, num_levels=len(prior_schema), toc_md_string=toc_md_toc_section_str)}", "cyan")
        while True:
            response = await llm.openai_client_chat_completion_request(messages, model="gpt-4-turbo", temperature=0)
            try:
                message_content = response.choices[0].message.content
                toc_hierarchy_schema = json.loads(message_content)
                utils.print_coloured(f"{json.dumps(toc_hierarchy_schema, indent=2)}", "yellow")
                return toc_hierarchy_schema
            except json.JSONDecodeError as e:
                print(f"JSONDecodeError: {e}")
                print(f"Message content: {message_content}")
                print("Retrying...")
                continue
            except Exception as e:
                print(f"Error: {e}")
                print("Retrying...")
                continue
                
    # prior_schema = {
    #     "Part": {
    #         "level": "#",
    #         "description": "Top-level section representing major divisions of the document",
    #         "lines": [
    #         "**PART 1**",
    #         "**PART 2**",
    #         "**PART 3**"
    #         ]
    #     },
    #     "Part Titles": {
    #         "level": "#",
    #         "description": "Titles of the top-level sections",
    #         "lines": [
    #         "GENERAL INTRODUCTORY PROVISIONS",
    #         "COMPANY FORMATION",
    #         "A COMPANY\u2019S CONSTITUTION"
    #         ]
    #     },
    #     "Chapter": {
    #         "level": "##",
    #         "description": "Second-level section representing subdivisions within parts",
    #         "lines": [
    #         "**CHAPTER 1**",
    #         "**CHAPTER 2**",
    #         "**CHAPTER 3**",
    #         "**CHAPTER 4**"
    #         ]
    #     },
    #     "Chapter Titles": {
    #         "level": "##",
    #         "description": "Titles of the second-level sections",
    #         "lines": [
    #         "INTRODUCTORY",
    #         "ARTICLES OF ASSOCIATION",
    #         "RESOLUTIONS AND AGREEMENTS AFFECTING A COMPANY\u2019S CONSTITUTION",
    #         "MISCELLANEOUS AND SUPPLEMENTARY PROVISIONS"
    #         ]
    #     },
    #     "Section": {
    #         "level": "###",
    #         "description": "Third-level section representing specific topics within chapters, containing items",
    #         "lines": [
    #         "_Companies and Companies Acts_",
    #         "_Types of company_",
    #         "_General_",
    #         "_Requirements for registration_",
    #         "_Registration and its effect_",
    #         "_General_",
    #         "_Alteration of articles_",
    #         "_Supplementary_",
    #         "_Statement of company\u2019s objects_"
    #         ]
    #     }
    # }
    
    #appendix_schema = await process_page(next(iter(grouped_end_pages_text.items())))
    appendix_schema, prior_schema = await asyncio.gather(
        process_page(next(iter(grouped_end_pages_text.items()))),
        process_page(next(iter(grouped_pages_text.items())))
    )
    #utils.print_coloured(f"Appendix Schema: {json.dumps(appendix_schema, indent=2)}", "green")
    prior_schema_descriptions = []
    for key, value in prior_schema.items():
        if "description" in value:
            prior_schema_descriptions.append(f"(array of strings, ALL verbatim {key} section lines from the text identified as the {value['description']})")
            del value["description"]
    prior_schema_template = copy.deepcopy(prior_schema) 
    utils.print_coloured(json.dumps(prior_schema, indent=2), "green")
    for key, description in zip(list(prior_schema_template.keys()), prior_schema_descriptions):
        prior_schema_template[key]["lines"] = description
    utils.print_coloured(json.dumps(prior_schema_template, indent=2), "yellow")
    ######### EXAMPLE TEXT #########
    prior_schema_example = copy.deepcopy(prior_schema) 
    _, text = next(iter(grouped_pages_text.items()))
    initial_toc_md_lines = text.split("\n")
    found_flags = {key: False for key in prior_schema.keys()}
    levels = {details["level"]: key for key, details in prior_schema.items()}
    found_lines = {level: [] for level in levels}
    first_idx = None
    last_idx = None
    for idx, line in enumerate(initial_toc_md_lines):
        for section, details in prior_schema_example.items():
            if line in details["lines"]:
                found_flags[section] = True
                found_lines[details["level"]].append((line, idx))

                if first_idx is None or idx < first_idx:
                    first_idx = idx
                if last_idx is None or idx > last_idx:
                    last_idx = idx
                if all(found_flags.values()):
                    break
        if all(found_flags.values()):
            break
    example_substring = '\n'.join(initial_toc_md_lines[first_idx:last_idx + 1])
    example_substring_lines = set(example_substring.split('\n'))
    example = f"<example_text>\n{example_substring}\n</example_text>\n\n"
    for key, details in prior_schema_example.items():
        details["lines"] = [line for line in details["lines"] if line in example_substring_lines]
    example += f"<example_output>{json.dumps(prior_schema_example, indent=2)}</example_output>"
    utils.print_coloured(json.dumps(prior_schema_example, indent=2), "blue")
    ######### EXAMPLE TEXT #########
    for i in range(0, 15):
        print(f"Sleeping for {15-i} seconds...")
        await asyncio.sleep(1)
    toc_hierarchy_schemas = await asyncio.gather(
        *[
            process_page(page_nums, prior_schema=prior_schema_template, example=example)
            for page_nums in list(grouped_pages_text.items())
        ]
    )
    # entry = list(grouped_pages_text.items())[7]

    # toc_hierarchy_schemas = await asyncio.gather(
    #     process_page(entry, prior_schema=prior_schema_template, example=example)
    # )
    # exit()

    combined_toc_hierarchy_schema = {}
    for details in prior_schema.values():
        for line in details["lines"]:
            if line not in combined_toc_hierarchy_schema:
                combined_toc_hierarchy_schema[line] = details["level"]
    for details in appendix_schema.values():
        for line in details["lines"]:
            if line not in combined_toc_hierarchy_schema:
                combined_toc_hierarchy_schema[line] = details["level"]
    for schema in toc_hierarchy_schemas:
        for details in schema.values():
            for line in details["lines"]:
                if line not in combined_toc_hierarchy_schema:
                    combined_toc_hierarchy_schema[line] = details["level"]

    ordered_items = sorted(combined_toc_hierarchy_schema.items(), key=lambda x: x[1].count('#'))
    ordered_dict = dict(ordered_items)
    utils.print_coloured(f"{json.dumps(ordered_dict, indent=4)}", "green")
    with open("uuk_toc_hierarchy_schema.json", "w") as f:
        json.dump(ordered_dict, f, indent=2)
        
    
asyncio.run(main_run())