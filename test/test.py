from __future__ import annotations
from parser.pdf_parser import PDFParser
import asyncio
import json
import llm, prompts
from thefuzz import process
from collections import Counter, defaultdict, OrderedDict
from pydantic import BaseModel, ValidationError
from typing import Union, Any, Optional, Dict, Tuple, List, NewType
import re

JSONstr = NewType('JSONstr', str)

class TableOfContentsChild(BaseModel):
    number: str
    title: str
    content: Optional[str] = None
    tokens: Optional[int] = None


class TableOfContents(BaseModel):
    section: Optional[str]
    number: str
    title: str
    content: Optional[str] = None
    tokens: Optional[int] = None
    children: Optional[List[Union[TableOfContents, TableOfContentsChild]]]

    def find_child(self, section: Optional[str], number: str) -> Optional[Union[TableOfContents, TableOfContentsChild]]:
        """find an existing child by section and number."""
        if not self.children:
            return None
        for child in self.children:
            if isinstance(child, TableOfContents) and child.section == section and child.number == number:
                return child
            if isinstance(child, TableOfContentsChild) and child.number == number:
                return child
        return None

    def add_child(self, child: Union[TableOfContents, TableOfContentsChild]):
        """add a new child or merge with an existing one."""
        if not self.children:
            self.children = []

        if isinstance(child, TableOfContents):
            existing_child = self.find_child(child.section, child.number)
            if existing_child and isinstance(existing_child, TableOfContents):
                existing_child.children = merge_children(existing_child.children, child.children or [])
            else:
                self.children.append(child)
        else:
            if not any(isinstance(existing, TableOfContentsChild) and existing.number == child.number for existing in self.children):
                self.children.append(child)


class Contents(BaseModel):
    level: JSONstr
    sublevel: JSONstr | str
    subsublevel: JSONstr | str
    toc: List[TableOfContents]


class TableOfContentsDict(BaseModel):
    contents: List[Contents]

def merge_children(existing_children: Optional[List[Union[TableOfContents, TableOfContentsChild]]], new_children: List[Union[TableOfContents, TableOfContentsChild]]) -> List[Union[TableOfContents, TableOfContentsChild]]:
    """merge a list of new children into existing children."""
    if existing_children is None:
        existing_children = []

    existing_dict = OrderedDict((child.number, child) for child in existing_children if isinstance(child, TableOfContents))

    for new_child in new_children:
        if isinstance(new_child, TableOfContents):
            if new_child.number in existing_dict:
                existing_child = existing_dict[new_child.number]
                existing_child.children = merge_children(existing_child.children, new_child.children or [])
            else:
                existing_children.append(new_child)
                existing_dict[new_child.number] = new_child
        else:
            if not any(isinstance(child, TableOfContentsChild) and child.number == new_child.number for child in existing_children):
                existing_children.append(new_child)

    return existing_children

def generate_chunked_content(content_md_string: str, master_toc_file: str, adjusted_toc_hierarchy_schema: Dict[str, str] = None, toc_hierarchy_schema: Dict[str, str] = None) -> Dict[str, Dict[str, Any]]:

    # content_md_lines = content_md_string.split("\n")
    # content_md_section_lines = [(line, idx) for idx, line in enumerate(content_md_lines) if line.startswith('#')]
    # section_lines=""
    # for line, idx in content_md_section_lines:
    #     section_lines += f"{line} [{idx}]\n"
    # with open("zzz_section_lines.md", "w") as f:
    #     f.write(section_lines)
    def parse_markdown_headings():
        content_md_lines = content_md_string.split("\n")
        content_md_section_lines = []
        processed_lines = []
        for i in range(len(content_md_lines)):
            line = content_md_lines[i]
            if line.startswith('#') and i not in processed_lines:
                current_part = line.strip()
                j = 1
                while i + j < len(content_md_lines) and content_md_lines[i + j].startswith('#'):
                    next_line = content_md_lines[i + j].strip().lstrip('#').strip()
                    current_part += ' ' + next_line
                    processed_lines.append(i + j)
                    j += 1
                content_md_section_lines.append((current_part, i))

        section_lines = ""
        for heading, idx in content_md_section_lines:
            section_lines += f"{heading} [{idx}]\n"

        with open("zzz_section_lines.md", "w") as f:
            f.write(section_lines)
        
        return content_md_lines, content_md_section_lines
    
    content_md_lines, _ = parse_markdown_headings()
    content_md_section_lines = [(line, idx) for idx, line in enumerate(content_md_lines)]
    
    with open(master_toc_file, "r") as f:
        master_toc = json.load(f)
    
    md_levels = adjusted_toc_hierarchy_schema if adjusted_toc_hierarchy_schema else toc_hierarchy_schema

    def format_section_name(section: str, number: str, title: str) -> str:
        section_match = process.extractOne(section, md_levels.keys(), score_cutoff=98) if section else None
        md_level = md_levels.get(section_match[0], max(md_levels.values(), key=len) + "#") if section_match else max(md_levels.values(), key=len) + "#"
        # if md_level.count('#') > 1:
        #     md_level = '*' * md_level.count('#')

        formatted_parts = []
        if section and not section in title:
            formatted_parts.append(section)
        if number and not number in title:
            formatted_parts.append(number)
        if title:
            formatted_parts.append(title)

        return f'{md_level} {" ".join(formatted_parts)}'

    def traverse_and_update_toc(master_toc: List[Dict[str, Any]]):
        levels_dict = {"contents": []}

        def convert_to_model(data: Dict[str, Any]) -> Union[TableOfContents, TableOfContentsChild]:
            if 'children' in data:
                data['children'] = [convert_to_model(child) for child in data['children']]
                return TableOfContents(**data)
            else:
                return TableOfContentsChild(**data)

        def flatten_toc(toc_models: List[Union[TableOfContents, TableOfContentsChild]]) -> List[Union[TableOfContents, TableOfContentsChild]]:
            flattened = []
            for model in toc_models:
                if isinstance(model, TableOfContents):
                    flattened.append(model)
                    if model.children:
                        flattened.extend(flatten_toc(model.children))
                elif isinstance(model, TableOfContentsChild):
                    flattened.append(model)
            return flattened
        
        remaining_content_md_section_lines = content_md_section_lines.copy()
        #def get_section_content(next_formatted_section_name: str, formatted_section_name: str = None) -> Tuple[str, int]:
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
                else:
                    print(f"Could not match start: {formatted_section_name}")
                    start_line_idx = remaining_content_md_section_lines[0][1]
            else:
                start_line_idx = remaining_content_md_section_lines[0][1]

            if next_section:
                #number_match = re.findall(r'\d+\.?\d*', next_formatted_section_name)
                next_formatted_section_name = format_section_name(*next_section)
                next_number = next_section[1] if next_section[1] else ""
                if next_number:
                    print(f"Next number: {next_number}")
                    filtered_remaining_content_md_section_lines = [(line, idx) for line, idx in remaining_content_md_section_lines if next_number in line]
                    matches = process.extractBests(next_formatted_section_name, [line for line, _ in filtered_remaining_content_md_section_lines], score_cutoff=80, limit=10)
                else:
                    matches = process.extractBests(next_formatted_section_name, [line for line, _ in remaining_content_md_section_lines], score_cutoff=80, limit=10)
                if matches:
                    highest_score = max(matches, key=lambda x: x[1])[1]
                    highest_score_matches = [match for match in matches if match[1] == highest_score]
                    matched_line = min(highest_score_matches, key=lambda x: next(idx for line, idx in remaining_content_md_section_lines if line == x[0]))[0]
                    line_idx = next(idx for line, idx in remaining_content_md_section_lines if line == matched_line)
                    print(f"Matched: {next_formatted_section_name} at {line_idx} with {matched_line}")
                    if "Rules for demutualising health" in next_formatted_section_name:
                        print(f"Matched: {next_formatted_section_name} at {line_idx} with {matched_line}")
                        print(f'from: {matches}')
                        # for line, idx in remaining_content_md_section_lines:
                        #     print(f"{idx}: {line}")
                        exit()
                else:
                    print(remaining_content_md_section_lines)
                    raise ValueError(f"Could not match end: {next_formatted_section_name}")
            else:
                line_idx = len(content_md_lines)

            section_content = "\n".join(content_md_lines[start_line_idx:line_idx-1])
            num_tokens = len(section_content.strip())
            remaining_content_md_section_lines = [item for item in remaining_content_md_section_lines if item[1] >= line_idx]
            return section_content, num_tokens
                

        def traverse_sections(sections: List[Union[TableOfContents, TableOfContentsChild]], parent_dict: Dict[str, Any], flattened_toc: List[Union[TableOfContents, TableOfContentsChild]]):
            for section in sections:
                if isinstance(section, TableOfContents):
                    formatted_section_name = format_section_name(section.section, section.number, section.title)
                    section_dict = {
                        "section": section.section,
                        "number": section.number,
                        "title": section.title,
                        "content": "",
                        "children": []
                    }
                    parent_dict["children"].append(section_dict)

                    current_index = flattened_toc.index(section)
                    if current_index + 1 < len(flattened_toc):
                        next_item = flattened_toc[current_index + 1]
                        #next_formatted_section_name = format_section_name(next_item.section, next_item.number, next_item.title) if isinstance(next_item, TableOfContents) else format_section_name("", next_item.number, next_item.title)
                        #print(next_formatted_section_name)
                        #section_content, _ = get_section_content(next_formatted_section_name=next_formatted_section_name)
                        section_content, _ = get_section_content(next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, TableOfContents) else ("", next_item.number, next_item.title))
                        #section_dict["content"] = section_content
                        if len(section_content) > len(formatted_section_name)*1.3:
                            section_dict["content"] = section_content

                    if section.children:
                        traverse_sections(section.children, section_dict, flattened_toc)
                
                elif isinstance(section, TableOfContentsChild):
                    formatted_section_name = format_section_name("", section.number, section.title)
                    child_dict = {
                        "number": section.number,
                        "title": section.title,
                        "content": ""
                    }
                    parent_dict["children"].append(child_dict)

                    current_index = flattened_toc.index(section)
                    if current_index + 1 < len(flattened_toc):
                        next_item = flattened_toc[current_index + 1]
                        #next_formatted_section_name = format_section_name(next_item.section, next_item.number, next_item.title) if isinstance(next_item, TableOfContents) else format_section_name("", next_item.number, next_item.title)

                        #section_content, _ = get_section_content(next_formatted_section_name=next_formatted_section_name)
                        section_content, _ = get_section_content(next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, TableOfContents) else ("", next_item.number, next_item.title))
                        child_dict["content"] = section_content
                    else:
                        section_content, _ = get_section_content(next_section="")
                        child_dict["content"] = section_content
        
        toc_models = [convert_to_model(item) for item in master_toc]
        flattened_toc = flatten_toc(toc_models)
        
        for item in toc_models:
            formatted_section_name = format_section_name(item.section, item.number, item.title)
            section_dict = {
                "section": item.section,
                "number": item.number,
                "title": item.title,
                "content": "",
                "children": []
            }
            levels_dict["contents"].append(section_dict)
            
            current_index = flattened_toc.index(item)
            if current_index + 1 < len(flattened_toc):
                next_item = flattened_toc[current_index + 1]
                # if isinstance(next_item, TableOfContents):
                #     next_formatted_section_name = format_section_name(next_item.section, next_item.number, next_item.title)
                # elif isinstance(next_item, TableOfContentsChild):
                #     next_formatted_section_name = format_section_name("", next_item.number, next_item.title)
                
                # section_content, _ = get_section_content(formatted_section_name=formatted_section_name, next_formatted_section_name=next_formatted_section_name)
                section_content, section_tokens = get_section_content(section=(item.section, item.number, item.title), next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, TableOfContents) else ("", next_item.number, next_item.title))
                section_dict["content"] = section_content
            
            traverse_sections(item.children, section_dict, flattened_toc)
        
        return levels_dict
    
    return traverse_and_update_toc(master_toc)

async def main_run():
    toc_hierarchy_schema = {
        "Chapter": "##",
        "Part": "###",
        "Division": "####",
        "Guide to Division": "#####",
        "Subdivision": "#####",
        "Rules for policy holders": "#####",
        "Rules for demutualising health insurer": "#####",
        "Rules for other entities": "#####",
        "Guide to Subdivision": "#####",
        "Gains and losses of members, insured entities and successors": "#####",
        "Friendly society\u2019s gains and losses": "#####",
        "Other entities\u2019 gains and losses": "#####",
        "Effects of CGT events happening to interests and assets in trust": "#####",
        "Operative provisions": "#####",
        "What is included in a life insurance company\u2019s assessable income": "#####",
        "Deductions and capital losses": "#####",
        "Income tax, taxable income and tax loss of life insurance companies": "#####",
        "General rules": "#####",
        "Taxable income and tax loss of life insurance companies": "#####",
        "Special rules about roll-overs": "#####",
        "Object of this Subdivision": "#####",
        "Requirements for a roll-over under this Subdivision": "#####",
        "Consequences of a roll-over under this Subdivision": "#####",
        "Object": "#####",
        "Meaning of R&D activities and other terms": "#####",
        "Entitlement to tax offset": "#####",
        "Notional deductions for R&D expenditure": "#####",
        "Notional deductions etc. for decline in value of depreciating assets used for R&D activities": "#####",
        "Integrity Rules": "#####",
        "Clawback of R&D recoupments, feedstock adjustments and balancing adjustments": "#####",
        "Catch up deductions for balancing adjustment events for assets used for R&D activities": "#####",
        "Application to earlier income year R&D expenditure incurred to associates": "#####",
        "Application to R&D partnerships": "#####",
        "Application to Cooperative Research Centres": "#####",
        "Other matters": "#####",
        "Tax incentives for early stage investors in innovation companies": "#####",
        "Films generally (tax offsets for Australian production expenditure)": "####",
        "Tax offsets for Australian expenditure in making a film": "#####",
        "Refundable tax offset for Australian expenditure in making a film (location offset)": "#####",
        "Refundable tax offset for post, digital and visual effects production for a film (PDV offset)": "#####",
        "Refundable tax offset for Australian expenditure in making an Australian film (producer offset)": "#####",
        "Production expenditure and qualifying Australian production expenditure": "#####",
        "Production expenditure\u2014common rules": "#####",
        "Production expenditure\u2014special rules for the location offset": "#####",
        "Qualifying Australian production expenditure\u2014common rules": "#####",
        "Qualifying Australian production expenditure\u2014special rules for the location offset and the PDV offset": "#####",
        "Qualifying Australian production expenditure\u2014special rules for the producer offset": "#####",
        "Expenditure generally\u2014common rules": "#####",
        "Certificates for films and other matters": "#####",
        "Digital games (tax offset for Australian expenditure on digital games)": "####",
        "NRAS certificates issued to individuals, corporate tax entities and superannuation funds": "#####",
        "NRAS certificates issued to NRAS approved participants": "#####",
        "NRAS certificates issued to partnerships and trustees": "#####",
        "Miscellaneous": "#####",
        "Tax offset or extra income tax": "#####",
        "How to work out the comparison rate": "#####",
        "Your gross averaging amount": "#####",
        "Your averaging adjustment": "#####",
        "How to work out your averaging component": "#####",
        "Uplift of tax losses": "#####",
        "Change of ownership of trusts and companies": "#####",
        "Consolidated groups": "#####",
        "Designating infrastructure projects": "#####",
        "Infrastructure project capital expenditure cap": "#####",
        "Entitlement to junior minerals exploration incentive tax offset": "#####",
        "Amount of junior minerals exploration incentive tax offset": "#####"
    }
    top_level = min(toc_hierarchy_schema.values(), key=lambda x: x.count('#'))
    top_level_count = top_level.count('#')
    adjust_count = top_level_count - 1
    adjusted_toc_hierarchy_schema = {k: v[adjust_count:] for k, v in toc_hierarchy_schema.items()}
    with open("zzcontent_md_string.md", "r") as f:
        content_md_string = f.read()

    doc_dict = generate_chunked_content(content_md_string, "master_toc.json", toc_hierarchy_schema=adjusted_toc_hierarchy_schema)
    with open("zzz_content.json", "w") as f:
        json.dump(doc_dict, f, indent=4)
    # for level in doc_dict:
    #     print(level)

asyncio.run(main_run())
