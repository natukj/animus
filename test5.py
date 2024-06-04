import json
import asyncio
from typing import Any, Dict, List, Tuple, Union
from collections import defaultdict, Counter
import llm, prompts, utils
import tiktoken

with open("levels.json", "r") as f:
    levels = json.load(f)

def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """
    count the number of tokens in the given text using the specified encoding.
    """
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(text))
    return num_tokens

with open("toc_hierarchy_schema.json", "r") as f:
    toc_hierarchy_schema = json.load(f)

async def filter_schema(toc_hierarchy_schema: Dict[str, str], content: str, num_sections: int = 5) -> Dict[str, str]:
        """
        Filter the schema to reduce size and complexity.
        """
        with open("zztoc_md_string.md", "r") as f:
            toc_md_string = f.read()
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
        result = {heading: level for level, heading in sorted_headings[:num_sections]}
        # dynamically adjust the schema based on whats present in the content
        for heading, level in toc_hierarchy_schema.items():
            formatted_heading = heading
            if formatted_heading in content and heading not in result:
                result[heading] = level
        return result

async def generate_toc_schema(levels: Dict[str, str] = None, content: str = None, depth: int = 0, max_depth: int = None) -> List[Dict[str, Any]]:
        """
        Generate a custom schema for the ToC based on the hierarchy schema.
        """
        if levels is None:
            top_level = min(toc_hierarchy_schema.values(), key=lambda x: x.count('#'))
            top_level_count = top_level.count('#')
            if top_level_count > 1:
                adjust_count = top_level_count - 1
                levels_unfiltered = {k: v[adjust_count:] for k, v in toc_hierarchy_schema.items()}
                adjusted_toc_hierarchy_schema = levels_unfiltered
                levels = await filter_schema(levels_unfiltered, content, 2)
                #print(f"Adjusted ToC Hierarchy Schema: {json.dumps(levels, indent=4)}")
            else:    
                levels = await filter_schema(toc_hierarchy_schema, content, 2)
                #print(f"UNadjusted ToC Hierarchy Schema: {json.dumps(levels, indent=4)}")

        if max_depth is None:
            max_depth = max(marker.count('#') for marker in levels.values())

        if depth >= max_depth:
            return [], levels

        current_depth_levels = [name for name, marker in levels.items() if marker.count('#') == depth + 1]
        children, _ = await generate_toc_schema(levels, content, depth + 1, max_depth)

        toc_schema = [
            {
                "section": f"string (type of the section, e.g., {level_name})",
                "number": "string (numeric or textual identifier of the section or empty string if not present)",
                "title": "string (title of the section or empty string if not present)",
                "children": children if children else [
                    {
                        "number": "string (numeric or textual identifier of the section)",
                        "title": "string (title of the section)"
                    },
                    {
                        "number": "string (numeric or textual identifier of the section)",
                        "title": "string (title of the section)"
                    }
                ]
            } for level_name in current_depth_levels
        ]
        return toc_schema, levels

async def process_level_no_md(level_title, level_content, sublevel_title=None, subsublevel_title=None):
    if "content" in level_content:
        if level_content["content"].count('\n') == 1:
            level_title_dict = json.loads(level_title)
            if not level_title_dict["title"]:
                level_title_dict["title"] = level_content["content"]
                level_title = json.dumps(level_title_dict)
        else:
            custom_schema, custom_levels = await generate_toc_schema(content=level_content["content"])
            TOC_SCHEMA = {"contents": [json.dumps(custom_schema, indent=4)]}
            section_types = ", ".join(custom_levels.keys())
            level_title_dict = json.loads(level_title)
            level_title_str = f"{level_title_dict['section']} {level_title_dict.get('number', '')} {level_title_dict['title']}"
            messages = [
                    {"role": "system", "content": prompts.TOC_SCHEMA_SYS_PROMPT_PLUS},
                    {"role": "user", "content": prompts.TOC_SCHEMA_USER_PROMPT.format(level_title=level_title_str, section_types=section_types, TOC_SCHEMA=TOC_SCHEMA, content=level_content["content"])}
                ]
            messages_str = json.dumps(messages, indent=4)
            utils.print_coloured(f"{level_title_str}{sublevel_title} ({count_tokens(messages_str)} tokens)", "red")
            if "Part 35" in level_title_str:
                print(json.dumps(custom_schema, indent=4))
            
            

    if "children" in level_content:
        # process each child level recursively
        for child_title, child_content in level_content["children"].items():
            if "children" in child_content:
                # process further children, process them as subsublevels
                for subchild_title, subchild_content in child_content["children"].items():
                    await process_level_no_md(level_title, subchild_content, child_title, subchild_title)
            else:
                await process_level_no_md(level_title, child_content, child_title)

async def main():
    for level_title, level_content in levels.items():
        await process_level_no_md(level_title, level_content)

asyncio.run(main())