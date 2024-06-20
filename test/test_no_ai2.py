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
import llm, prompts, schemas, utils
from parsers.pdf_parser import BaseParser

"""COMPLEX TYPICAL"""
# pages = list(range(2, 32))
# grouped_pages = [pages[i:i+2] for i in range(0, len(pages), 2)]
# vol_num=9
# doc = fitz.open(f"/Users/jamesqxd/Documents/norgai-docs/TAX/C2024C00046VOL0{vol_num}.pdf")
# base_parser = BaseParser()
# content_pages = list(range(32, doc.page_count))
# toc_md_str = base_parser.to_markdown(doc=doc, pages=content_pages, page_chunks=False)
# pathlib.Path(f"vol{vol_num}content.md").write_bytes(toc_md_str.encode())
async def main_run():
    with open("vol9tocnew.json", "r") as f:
        levels_dict = json.load(f)
    # # if the top level of data has only one key (ToC header), skip it and start from its children
    # if len(levels_dict) == 1 and 'children' in next(iter(levels_dict.values())):
    #     levels_dict = next(iter(levels_dict.values()))['children']
    master_toc = schemas.parse_toc_dict(levels_dict)
    master_toc_dump = [toc.model_dump() for toc in master_toc]
    with open("vol9master_toc.json", "w") as f:
        json.dump(master_toc_dump, f, indent=2, default=lambda x: x.dict())
        # json.dump(master_toc.model_dump(), f, indent=2)

#asyncio.run(main_run())

def format_section_name(section: str, number: str, title: str) -> str:
    formatted_parts = []
    if section and not section in title:
        formatted_parts.append(section)
    if number and not number in title:
        formatted_parts.append(number)
    if title:
        formatted_parts.append(title)

    return f'{" ".join(formatted_parts)}'

async def main_content():
    with open("vol9master_toc.json", "r") as f:
        master_toc = json.load(f)
    with open("vol9content.md", "r") as f:
        content_md_lines = f.readlines()
    content_md_section_lines = [(line, idx) for idx, line in enumerate(content_md_lines) if line.startswith('#')]
    def traverse_and_update_toc(master_toc: List[Dict[str, Any]]):
        levels_dict = {"contents": []}

        def convert_to_model(data: Dict[str, Any]) -> Union[schemas.TableOfContents, schemas.TableOfContentsChild]:
            if 'children' in data:
                data['children'] = [convert_to_model(child) for child in data['children']]
                return schemas.TableOfContents(**data)
            else:
                return schemas.TableOfContentsChild(**data)

        def flatten_toc(toc_models: List[Union[schemas.TableOfContents, schemas.TableOfContentsChild]]) -> List[Union[schemas.TableOfContents, schemas.TableOfContentsChild]]:
            flattened = []
            for model in toc_models:
                if isinstance(model, schemas.TableOfContents):
                    flattened.append(model)
                    if model.children:
                        flattened.extend(flatten_toc(model.children))
                elif isinstance(model, schemas.TableOfContentsChild):
                    flattened.append(model)
            return flattened
        
        remaining_content_md_section_lines = content_md_section_lines.copy()
        def get_section_content(next_section: Tuple[str, str, str], section: Tuple[str, str, str] = None) -> Tuple[str, int]:
            nonlocal remaining_content_md_section_lines
            if section:
                formatted_section_name = format_section_name(*section)
                start_matches = process.extractBests(formatted_section_name, [line for line, _ in remaining_content_md_section_lines], score_cutoff=80, limit=10)
                if start_matches:
                    start_highest_score = max(start_matches, key=lambda x: x[1])[1]
                    start_highest_score_matches = [match for match in start_matches if match[1] == start_highest_score]
                    start_matched_line = min(start_highest_score_matches, key=lambda x: next(idx for line, idx in remaining_content_md_section_lines if line == x[0]))[0]
                    start_line_idx = next(idx for line, idx in remaining_content_md_section_lines if line == start_matched_line)
                    utils.print_coloured(f"Start Match: {formatted_section_name}: {start_matched_line} [{start_line_idx}]", "cyan")
                else:
                    print(f"Could not match start: {formatted_section_name}")
                    start_line_idx = remaining_content_md_section_lines[0][1]
            else:
                start_line_idx = remaining_content_md_section_lines[0][1]

            if next_section:
                next_formatted_section_name = format_section_name(*next_section)
                next_number = next_section[1] if next_section[1] else ""
                if next_number:
                    filtered_remaining_content_md_section_lines = [(line, idx) for line, idx in remaining_content_md_section_lines if next_number in line]
                    matches = process.extractBests(next_formatted_section_name, [line for line, _ in filtered_remaining_content_md_section_lines], score_cutoff=80, limit=10)
                else:
                    matches = process.extractBests(next_formatted_section_name, [line for line, _ in remaining_content_md_section_lines], score_cutoff=80, limit=10)
                if matches:
                    highest_score = max(matches, key=lambda x: x[1])[1]
                    unique_scores = sorted(set([match[1] for match in matches]))
                    if len(unique_scores) > 1:
                        second_highest_score = sorted(set([match[1] for match in matches]))[-2]
                        if highest_score - second_highest_score <= 5 and second_highest_score >= 95:
                            #Match: 160 Appointment of directors of public company to be voted on individually: 160 (appointment of directors of public company to be voted on individually). [4746]
                            # from: [('160 (appointment of directors of public company to be voted on individually).', 99), ('**160****Appointment of directors of public company to be voted on individually**', 98), ('**1160 Meaning of “subsidiary” etc: power to amend**', 86)]
                            highest_score_matches = [match for match in matches if match[1] == highest_score]
                            second_highest_score_matches = [match for match in matches if match[1] == second_highest_score]
                            formatted_highest_matches = [match for match in highest_score_matches if match[0].lstrip().startswith(('#', '*', '_'))]
                            formatted_second_highest_matches = [match for match in second_highest_score_matches if match[0].lstrip().startswith(('#', '*', '_'))]
                            if formatted_second_highest_matches and not formatted_highest_matches:
                                highest_score = second_highest_score
                    highest_score_matches = [match for match in matches if match[1] == highest_score]
                    matched_line = min(highest_score_matches, key=lambda x: next(idx for line, idx in remaining_content_md_section_lines if line == x[0]))[0]
                    line_idx = next(idx for line, idx in remaining_content_md_section_lines if line == matched_line)
                    utils.print_coloured(f"Match: {next_formatted_section_name}: {matched_line} [{line_idx}]", "yellow")
                    if "172 Duty to promote the success of the company" in next_formatted_section_name:
                        print(f"Match: {next_formatted_section_name}: {matched_line} [{line_idx}]")
                        print("from:", matches)
                else:
                    i = 0
                    for line, idx in remaining_content_md_section_lines:
                        print(f"Line: {line} [{idx}]")
                        i += 1
                        if i > 10:
                            break
                    raise ValueError(f"Could not match end: {next_formatted_section_name}")
            else:
                line_idx = len(content_md_lines)

            section_content = "\n".join(content_md_lines[start_line_idx:line_idx-1])
            num_tokens = len(section_content.split())
            remaining_content_md_section_lines = [item for item in remaining_content_md_section_lines if item[1] >= line_idx]
            return section_content, num_tokens
                

        def traverse_sections(sections: List[Union[schemas.TableOfContents, schemas.TableOfContentsChild]], parent_dict: Dict[str, Any], flattened_toc: List[Union[schemas.TableOfContents, schemas.TableOfContentsChild]]):
            for section in sections:
                if isinstance(section, schemas.TableOfContents):
                    #formatted_section_name = format_section_name(section.section, section.number, section.title)
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
                        section_content, section_tokens = get_section_content(next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, schemas.TableOfContents) else ("", next_item.number, next_item.title))
                        # if len(section_content) > len(formatted_section_name)*1.3:
                        #     section_dict["content"] = section_content
                        #     section_dict["tokens"] = section_tokens


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
                        section_content, section_tokens = get_section_content(next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, schemas.TableOfContents) else ("", next_item.number, next_item.title))
                        child_dict["content"] = section_content
                        child_dict["tokens"] = section_tokens
                    else:
                        section_content, section_tokens = get_section_content(next_section="")
                        child_dict["content"] = section_content
                        child_dict["tokens"] = section_tokens
        
        toc_models = [convert_to_model(item) for item in master_toc]
        flattened_toc = flatten_toc(toc_models)
        
        for item in toc_models:
            formatted_section_name = format_section_name(item.section, item.number, item.title)
            section_dict = {
                "section": item.section,
                "number": item.number,
                "title": item.title,
                "content": "",
                "tokens": 0,
                "children": []
            }
            levels_dict["contents"].append(section_dict)
            
            current_index = flattened_toc.index(item)
            if current_index + 1 < len(flattened_toc):
                next_item = flattened_toc[current_index + 1]
                section_content, section_tokens = get_section_content(section=(item.section, item.number, item.title), next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, schemas.TableOfContents) else ("", next_item.number, next_item.title))
                if len(section_content) > len(formatted_section_name)*1.3:
                    section_dict["content"] = section_content
                    section_dict["tokens"] = section_tokens
            
            traverse_sections(item.children, section_dict, flattened_toc)
        
        return levels_dict

    content_dict = traverse_and_update_toc(master_toc)
    with open("vol9content.json", "w") as f:
        json.dump(content_dict, f, indent=2)

asyncio.run(main_content())
