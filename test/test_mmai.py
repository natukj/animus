from typing import Union, Any, Optional, Dict, Tuple, List, NewType
import json
import asyncio
import base64
import fitz
import pathlib
import llm, prompts, utils

vol_num=9
doc = fitz.open(f"/Users/jamesqxd/Documents/norgai-docs/TAX/C2024C00046VOL0{vol_num}.pdf")
pages = list(range(2, 32))
grouped_pages = [pages[i:i+2] for i in range(0, len(pages), 2)]
async def main():
    toc_pages_md = utils.to_markdownOG(doc, pages=pages, page_chunks=True)
    # grouped_pages_text = {}
    # for group in grouped_pages:
    #     total_text = ""
    #     for page in group:
    #         page_index = pages.index(page)
    #         total_text += toc_pages_md[page_index].get("text", "")
    #     grouped_pages_text[tuple(group)] = total_text
    # for k in grouped_pages_text.keys():
    #     print(f"Pages {k}:\n{len(grouped_pages_text[k])}")
    for page in toc_pages_md:
        print(type(toc_pages_md))
        print(page)
        print(type(page))
        print(page.keys())
        print(page['metadata']['title'])
        break
    

#asyncio.run(main())
prior_schema = {
  "Part": {
    "level": "#",
    "description": "Top-level sections of the document, indicating major divisions such as 'Part 1', 'Part 2', etc.",
    "lines": [
      "**PART 1**",
      "**PART 2**",
      "**PART 3**"
    ]
  },
  "Chapter": {
    "level": "##",
    "description": "Second-level sections within each part, indicating subdivisions such as 'Chapter 1', 'Chapter 2', etc.",
    "lines": [
      "**CHAPTER 1**",
      "**CHAPTER 2**",
      "**CHAPTER 3**",
      "**CHAPTER 4**"
    ]
  },
  "Section": {
    "level": "###",
    "description": "Third-level sections within each chapter, indicating specific topics or areas covered. This is the lowest level of hierarchy that contains items.",
    "lines": [
      "_Companies and Companies Acts_",
      "_Types of company_",
      "_General_",
      "_Requirements for registration_",
      "_Registration and its effect_",
      "_General_",
      "_Alteration of articles_",
      "_Supplementary_",
      "_Statement of company\u2019s objects_"
    ]
  }
}
def generate_toc_json(schema):
    # Initialize a dictionary to store the dynamic JSON structure
    json_structure = {}

    # Iterate through each item in the schema to build the JSON structure
    for key, details in schema.items():
        level = details['level']
        description = details['description']
        lines = details['lines']

        json_structure[level] = {
            "lines": f"(array of strings, verbatim {description} Include any enumerations and Markdown formatting, e.g., {', '.join(lines)}",
        }

    formatted_json = json.dumps(json_structure, indent=4)  # Pretty print the JSON
    return formatted_json
import re
def split_text_by_lines(toc_md, schema):
    parts_lines = schema["Part"]["lines"]
    chapters_lines = schema["Chapter"]["lines"]
    sections_lines = schema["Section"]["lines"]
    
    # Create a regex pattern to match any Part line
    part_pattern = re.compile('|'.join(re.escape(line) for line in parts_lines))
    
    # Split the text by Parts
    part_splits = part_pattern.split(toc_md)
    
    result = {}
    for i, part_text in enumerate(part_splits[1:], 1):  # Skip the first entry which is before the first "Part"
        part_title = parts_lines[i-1]
        result[part_title] = {"text": part_text.strip(), "found_lines": {}}
        
        # Check for Chapter and Section lines in the part_text
        for section, section_lines in [("Chapter", chapters_lines), ("Section", sections_lines)]:
            found_lines = [line for line in section_lines if line in part_text]
            if found_lines:
                result[part_title]["found_lines"][section] = found_lines
                
    return result
with open("toc.md") as f:
    toc_md_toc_section_str = f.read()
toc_md_toc_section_lines = toc_md_toc_section_str.split("\n")
levels = {details["level"]: key for key, details in prior_schema.items()}
found_flags = {level: False for level in levels}
found_lines = {level: [] for level in levels}
first_idx = None
last_idx = None
for idx, line in enumerate(toc_md_toc_section_lines):
    for details in prior_schema.values():
        if line in details["lines"]:
            found_flags[details["level"]] = True
            found_lines[details["level"]].append((line, idx))

            if first_idx is None or idx < first_idx:
                first_idx = idx
            if last_idx is None or idx > last_idx:
                last_idx = idx
            if all(found_flags.values()):
                break
    if all(found_flags.values()):
        break
      

if first_idx is not None and last_idx is not None:
    substring = '\n'.join(toc_md_toc_section_lines[first_idx:last_idx + 1])
    lines_within_range = toc_md_toc_section_lines[first_idx:last_idx + 1]
else:
    substring = ""
    lines_within_range = []

example = f"{substring}"
for key, lines in found_lines.items():
    example += f"\n\nFrom the above text the {key} key sections are:\n"
    for line, idx in lines:
        example += f"{line} (at line {idx})\n"
# print("Found Lines:", found_lines)
# print("Shortest Substring:\n", substring)
# print("Lines within Range:", lines_within_range)
print(example)