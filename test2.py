from __future__ import annotations
from pydantic import BaseModel, ValidationError
from typing import Union, Any, Optional, Dict, Tuple, List, NewType
import json
import asyncio
from thefuzz import process  
import llm, prompts, utils

JSONstr = NewType('JSONstr', str)

class TableOfContentsChild(BaseModel):
    number: str
    title: str

class TableOfContents(BaseModel):
    section: Optional[str]
    number: str
    title: str
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
    toc: List[Union[TableOfContents, TableOfContentsChild]]


class TableOfContentsDict(BaseModel):
    contents: List[Contents]

def merge_children(existing_children: Optional[List[Union[TableOfContents, TableOfContentsChild]]], new_children: List[Union[TableOfContents, TableOfContentsChild]]) -> List[Union[TableOfContents, TableOfContentsChild]]:
    """merge a list of new children into existing children."""
    if existing_children is None:
        existing_children = []

    existing_dict = {child.number: child for child in existing_children if isinstance(child, TableOfContents)}

    for new_child in new_children:
        if isinstance(new_child, TableOfContents):
            if new_child.number in existing_dict:
                existing_child = existing_dict[new_child.number]
                existing_child.children = merge_children(existing_child.children, new_child.children or [])
            else:
                existing_children.append(new_child)
        else:
            if not any(isinstance(child, TableOfContentsChild) and child.number == new_child.number for child in existing_children):
                existing_children.append(new_child)

    return existing_children

async def find_existing_section(toc: List[TableOfContents], section: str, number: str) -> Optional[TableOfContents]:
        """find an existing section by section and number."""
        for item in toc:
            if item.section == section and item.number == number:
                return item
        return None
    
async def nest_toc(content: Contents) -> TableOfContents:
    def parse_level(level_json: JSONstr):
        level_dict = json.loads(level_json)
        return level_dict['section'], level_dict['number'], level_dict['title']
    def find_nested_toc(tocs: List[Union[TableOfContents, TableOfContentsChild]], section: str, number: str) -> Optional[TableOfContents]:
        """recursively search for a TableOfContents by section and number in nested children."""
        for toc in tocs:
            if isinstance(toc, TableOfContents):
                if toc.section == section and toc.number == number:
                    return toc
                found = find_nested_toc(toc.children or [], section, number)
                if found:
                    return found
        return None

    
    level_section, level_number, level_title = parse_level(content.level)
    result_toc = TableOfContents(section=level_section, number=level_number, title=level_title, children=[])

    if content.sublevel == "Complete":
        level_toc = find_nested_toc(content.toc, level_section, level_number)
        if level_toc:
            utils.print_coloured(f"level_toc: {level_toc}", "red")
            result_toc.children = level_toc.children
        else:
            result_toc.children = content.toc 
    else:
        sublevel_section, sublevel_number, sublevel_title = parse_level(content.sublevel)
        sublevel_toc = TableOfContents(section=sublevel_section, number=sublevel_number, title=sublevel_title, children=[])
        result_toc.children = [sublevel_toc] 

        if content.subsublevel == "Complete":
            found_sublevel_toc = find_nested_toc(content.toc, sublevel_section, sublevel_number)
            if found_sublevel_toc:
                utils.print_coloured(f"sublevel_toc: {found_sublevel_toc}", "cyan")
                sublevel_toc.children = [found_sublevel_toc]
            else:
                sublevel_toc.children = content.toc
        else:
            subsublevel_section, subsublevel_number, subsublevel_title = parse_level(content.subsublevel)
            subsublevel_toc = TableOfContents(section=subsublevel_section, number=subsublevel_number, title=subsublevel_title, children=[])
            sublevel_toc.children = [subsublevel_toc]

            found_subsublevel_toc = find_nested_toc(content.toc, subsublevel_section, subsublevel_number)
            if found_subsublevel_toc:
                utils.print_coloured(f"subsublevel_toc: {found_subsublevel_toc}", "green")
                subsublevel_toc.children = [found_subsublevel_toc]
            else:
                subsublevel_toc.children = content.toc

    return result_toc
    
async def merge_toc(master_toc: List[TableOfContents], toc: List[TableOfContents], ) -> List[TableOfContents]:
    """
    Merge a new ToC sections.
    """
    toc_hierarchy_schema = {
        "Chapter": "##",
        "Part": "###",
        "Division": "####",
        "Subdivision": "#####"
    }
    sorted_schema = sorted(toc_hierarchy_schema.items(), key=lambda item: len(item[1]))
    top_level_type = sorted_schema[0][0]
    existing_level = await find_existing_section(master_toc, top_level_type, toc.number)
    if existing_level:
        existing_level.children = merge_children(existing_level.children, toc.children or [])
    else:
        master_toc.append(toc)

def save_toc_to_file(toc: List[TableOfContents], file_name: str):
    """temp for testing"""
    with open(file_name, "w") as file:
        json.dump(toc, file, indent=2, default=lambda x: x.dict())

async def build_master_toc(data: TableOfContentsDict) -> List[TableOfContents]:
    """
    Build the master ToC from the split ToC parts.
    """
    master_toc: List[TableOfContents] = []
    for content in data.contents:
        toc = await nest_toc(content)
        await merge_toc(master_toc, toc)
    master_toc = [toc.model_dump() for toc in master_toc]
    return master_toc


async def main():
    with open("toc.json", "r") as file:
        data = json.load(file)
    try:
        toc_dict = TableOfContentsDict(**data)
        master_toc = await build_master_toc(toc_dict)
        save_toc_to_file(master_toc, "zzzzzz.json")
    except ValidationError as e:
        print(e)

asyncio.run(main())