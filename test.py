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
        def get_section_content(next_formatted_section_name: str, formatted_section_name: str = None) -> Tuple[str, int]:
            nonlocal remaining_content_md_section_lines
            if formatted_section_name:
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

            if next_formatted_section_name:
                number_match = re.findall(r'\d+\.?\d*', next_formatted_section_name)
                if number_match:
                    if number_match[0] == "4.5":
                        number_match = ["**4.5** **** **** **ROSTERS**"]
                    filtered_remaining_content_md_section_lines = [(line, idx) for line, idx in remaining_content_md_section_lines if number_match[0] in line]
                    matches = process.extractBests(next_formatted_section_name, [line for line, _ in filtered_remaining_content_md_section_lines], score_cutoff=80, limit=10)
                else:
                    matches = process.extractBests(next_formatted_section_name, [line for line, _ in remaining_content_md_section_lines], score_cutoff=80, limit=10)
                if matches:
                    highest_score = max(matches, key=lambda x: x[1])[1]
                    highest_score_matches = [match for match in matches if match[1] == highest_score]
                    matched_line = min(highest_score_matches, key=lambda x: next(idx for line, idx in remaining_content_md_section_lines if line == x[0]))[0]
                    line_idx = next(idx for line, idx in remaining_content_md_section_lines if line == matched_line)
                    print(f"Matched: {next_formatted_section_name} at {line_idx} with {matched_line}")
                    if "Rosters 4.5" in next_formatted_section_name:
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
                        next_formatted_section_name = format_section_name(next_item.section, next_item.number, next_item.title) if isinstance(next_item, TableOfContents) else format_section_name("", next_item.number, next_item.title)
                        #print(next_formatted_section_name)
                        section_content, _ = get_section_content(next_formatted_section_name=next_formatted_section_name)
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
                        next_formatted_section_name = format_section_name(next_item.section, next_item.number, next_item.title) if isinstance(next_item, TableOfContents) else format_section_name("", next_item.number, next_item.title)

                        section_content, _ = get_section_content(next_formatted_section_name=next_formatted_section_name)
                        child_dict["content"] = section_content
                    else:
                        section_content, _ = get_section_content(next_formatted_section_name="")
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
                if isinstance(next_item, TableOfContents):
                    next_formatted_section_name = format_section_name(next_item.section, next_item.number, next_item.title)
                elif isinstance(next_item, TableOfContentsChild):
                    next_formatted_section_name = format_section_name("", next_item.number, next_item.title)
                
                section_content, _ = get_section_content(formatted_section_name=formatted_section_name, next_formatted_section_name=next_formatted_section_name)
                section_dict["content"] = section_content
            
            traverse_sections(item.children, section_dict, flattened_toc)
        
        return levels_dict
    
    return traverse_and_update_toc(master_toc)

async def main_run():
    toc_hierarchy_schema = {
        "PART": "#",
        "Title": "##",
        "Date of Operation": "##",
        "Scope of Agreement": "##",
        "Relationship to Other Industrial Instruments": "##",
        "Posting of the Agreement": "##",
        "Variation of Agreement": "##",
        "Negotiation of Further Agreements": "##",
        "Definitions": "##",
        "Consultation and Cooperation": "##",
        "Confidentiality": "##",
        "Consultation regarding Change": "##",
        "Grievance and Dispute Resolution": "##",
        "Managing Performance and Conduct": "##",
        "Flexibility Arrangements": "##",
        "Anti-Discrimination, Bullying and Harassment": "##",
        "Diversity": "##",
        "Employment Categories and Contract of Employment": "##",
        "Full Time Employees": "##",
        "Part Time Employees": "##",
        "Casual Employees": "##",
        "Probationary Period": "##",
        "Duties": "##",
        "Location of Hospital": "##",
        "Request for Transfer": "##",
        "Termination of Employment": "##",
        "Redundancy and Redeployment": "##",
        "Transmission of Business": "##",
        "Portability of Entitlements": "##",
        "Professional Development, Training and Careers": "##",
        "Uniforms": "##",
        "Amenities": "##",
        "Ordinary Hours": "##",
        "Working a 38 hour week / Accruing Days Off": "##",
        "Overtime (Authorised)": "##",
        "On-call and Recall": "##",
        "Rosters": "##",
        "Meal Hours and Rest Breaks": "##",
        "Banking of Ordinary Hours": "##",
        "Payment of Wages": "##",
        "Payment on Termination": "##",
        "Overpayment of Salaries": "##",
        "Underpayment of Salaries": "##",
        "Classifications and Progression Through Pay Points": "##",
        "Recognition of Previous Service and Experience": "##",
        "Time Not Worked": "##",
        "Higher Duties": "##",
        "Penalty Rates": "##",
        "Allowances": "##",
        "Superannuation": "##",
        "Salary Packaging": "##",
        "Annual Leave": "##",
        "Personal/Carer\u2019s Leave": "##",
        "Public Holidays": "##",
        "Parental Leave": "##",
        "Compassionate Leave": "##",
        "Community Service Leave": "##",
        "Long Service Leave": "##",
        "Study Leave": "##",
        "Professional Development Leave": "##",
        "Representative Leave / Trade Union Training Leave": "##",
        "Family Violence Leave": "##",
        "Leave Without Pay": "##",
        "Pandemic Leave": "##",
        "Schedules": "#",
        "Appendices": "#",
        "Time and Wages Record": "##",
        "Daylight Savings": "##",
        "Staffing, Workload Management and Demand Escalation": "##",
        "Employer Direction to Take Annual Leave \u2013 Close Down": "##",
        "Paid or Unpaid Leave Due to Low Occupancy or Cancellations": "##",
        "Occupational Health and Safety": "##",
        "Union involvement": "##",
        "Agreement Implementation Committee": "##",
        "Union Delegates": "##",
        "Hospitals to be covered by Agreement": "##",
        "Classification Definitions and Grades": "##",
        "Advanced Enrolled Nurse Criteria": "##",
        "Clinical Nurse Specialist Criteria": "##",
        "Wage Rates and Timetables for Increases": "##",
        "Allowances and Timetables for Increases": "##",
        "Declared Full Time Shifts Lengths": "##"
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
