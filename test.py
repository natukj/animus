from parser.pdf_parser import PDFParser
import asyncio
import json
import llm, prompts
from thefuzz import process
from collections import Counter, defaultdict
from typing import List, Dict, Union, Any
import re

async def process_heading(current_part):
    try:
        formatted_line = {
            "section": current_part,
            "number": current_part,
            "title": current_part
        }
        return formatted_line
    except Exception as e:
        print(f"Error: {e}")

async def split_toc_parts_into_parts(lines: List[str], level_types: List[str]) -> Dict[str, Union[str, Dict]]:
    """
    Split the ToC parts into sub-parts based on the sub-part type
    """
    parts = {}
    stack = []

    i = 0
    while i < len(lines):
        line = lines[i]
        level = None
        for j, level_type in enumerate(level_types):
            if line.startswith(level_type):
                level = j
                break

        if level is not None:
            heading = line.strip()
            # concatenate multi-line headings
            j = 1
            while i + j < len(lines) and lines[i + j].startswith(level_types[level].split(" ")[0]):
                next_line = lines[i + j].strip().lstrip('#').strip()
                heading += ' ' + next_line
                j += 1

            heading = await process_heading(heading)

            # pop stack until we reach the correct level
            while stack and stack[-1][0] >= level:
                stack.pop()

            if stack:
                parent = stack[-1][1]
                if "children" not in parent:
                    parent["children"] = {}
                parent["children"][json.dumps(heading)] = {}
                stack.append((level, parent["children"][json.dumps(heading)]))
            else:
                parts[json.dumps(heading)] = {}
                stack.append((level, parts[json.dumps(heading)]))

            i += j
        else:
            if stack:
                if line.strip():
                    if "content" not in stack[-1][1]:
                        stack[-1][1]["content"] = ""
                    stack[-1][1]["content"] += line.strip() + '\n'
            i += 1

    return parts


async def split_toc_into_parts(toc_md_string: str, toc_hierarchy_schema: Dict[str, str]) -> Dict[str, Union[str, Dict[str, str]]]:
    """
    Split the ToC into parts based on the hierarchy schema and token count
    """
    lines = toc_md_string.split('\n')
    grouped_schema = defaultdict(list)
    for key, value in toc_hierarchy_schema.items():
        grouped_schema[value].append(key)

    def find_most_common_heading(headings: List[str], lines: List[str]):
        counts = Counter()
        for line in lines:
            for heading in headings:
                if heading in line:
                    counts[heading] += 1
        most_common_heading = counts.most_common(1)[0][0] if counts else None
        return most_common_heading
    
    most_common_headings = {}
    for level, headings in grouped_schema.items():
        if len(headings) > 1:
            most_common_heading = find_most_common_heading(headings, lines)
            most_common_headings[level] = most_common_heading
        else:
            most_common_headings[level] = headings[0]

    sorted_headings = sorted(most_common_headings.items(), key=lambda x: len(x[0]))
    level_types = [f"{level[0]} {level[1]}" for level in sorted_headings][:3]
    print(level_types[:3])

    return await split_toc_parts_into_parts(lines, level_types)

async def extract_toc() -> Dict[str, Any]:
    """
    Main function to extract and format the ToC.
    """
    with open("toc_parts.json", "r") as f:
        levels = json.load(f)

    tasks = []
    all_level_schemas = {"contents": []}

    async def process_level(level_title, level_content, sublevel_title=None, subsublevel_title=None):
        if "content" in level_content:
            # If there is content, generate the formatted ToC entry
            print(f"Level: {level_title}, Sublevel: {sublevel_title}, Subsublevel: {subsublevel_title}")
            task = asyncio.create_task(generate_formatted_toc(level_title, sublevel_title, subsublevel_title, level_content["content"]))
            tasks.append(task)

        if "children" in level_content:
            # If there are children, process each child level recursively
            for child_title, child_content in level_content["children"].items():
                if "children" in child_content:
                    # If the child level has further children, process them as subsublevels
                    for subchild_title, subchild_content in child_content["children"].items():
                        print(f"Level: {level_title}, Sublevel: {child_title}, Subsublevel: {subchild_title}")
                        await process_level(level_title, subchild_content, child_title, subchild_title)
                else:
                    # If the child level has no further children, process it as a sublevel
                    print(f"Level: {level_title}, Sublevel: {child_title}")
                    await process_level(level_title, child_content, child_title)

    for level_title, level_content in levels.items():
        await process_level(level_title, level_content)

    try:
        results = await asyncio.gather(*tasks)
        for level_title, sublevel_title, subsublevel_title, result in results:
            if result and result.get('contents'):
                all_level_schemas["contents"].append({
                    "level": level_title,
                    "sublevel": sublevel_title,
                    "subsublevel": subsublevel_title,
                    "toc": result['contents']
                })
    except Exception as e:
        print(f"Error extracting ToC: {e}")

    return all_level_schemas

async def generate_formatted_toc(level_title, sublevel_title, subsublevel_title, content):
    # Simulating the API call result
    simulated_result = {
        "contents": f"Formatted ToC for Level: {level_title}, Sublevel: {sublevel_title}, Subsublevel: {subsublevel_title}"
    }
    return level_title, sublevel_title, subsublevel_title, simulated_result

async def main_run():
    toc_hierarchy_schema = {
        "Anti-overlap provisions": "#####",
        "Basic case and concepts": "#####",
        "Boat capital gains": "#####",
        "Chapter": "##",
        "Compulsory acquisitions of adjacent land only": "#####",
        "Demutualisation of Tower Corporation": "#####",
        "Division": "####",
        "Dwellings acquired from deceased estates": "#####",
        "Employment partly full-time and partly part-time": "#####",
        "Employment wholly full-time or wholly part-time": "#####",
        "Exempt assets": "#####",
        "Exempt or loss-denying transactions": "#####",
        "General": "#####",
        "General rules": "#####",
        "Guide to Division": "#####",
        "Keeping records for CGT purposes": "#####",
        "Long service leave taken at less than full pay": "#####",
        "Look-through earnout rights": "#####",
        "Main provisions": "#####",
        "Operative provisions": "#####",
        "Part": "###",
        "Partial exemption rules": "#####",
        "Record keeping": "#####",
        "Roll-overs under Subdivision 126-A": "#####",
        "Rules that may extend the exemption": "#####",
        "Rules that may limit the exemption": "#####",
        "Special disability trusts": "#####",
        "Special valuation rules": "#####",
        "Step 1—Have you made a capital gain or a capital loss?": "#####",
        "Step 2—Work out the amount of the capital gain or loss": "#####",
        "Step 3—Work out your net capital gain or loss for the income year": "#####",
        "Subdivision": "#####",
        "Takeovers and restructures": "#####",
        "Units in pooled superannuation trusts": "#####",
        "Venture capital investment": "#####",
        "Venture capital: investment by superannuation funds for foreign residents": "#####",
        "What does **_not_** **form part of the cost base**": "#####"
    }
    
    with open("toc.md", "r") as f:
        toc_md_string = f.read()

    # section_types = re.findall(r"#{3,}\s+(\w+)", content)
    # section_types = list(set(section_types))
    # result = await split_toc_into_parts(toc_md_string, toc_hierarchy_schema)
    # with open("toc_parts.json", "w") as f:
    #     json.dump(result, f, indent=4)
    # with open("toc_parts.json", "r") as f:
    #     levels = json.load(f)


 


asyncio.run(main_run())
