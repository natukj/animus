from __future__ import annotations
from pydantic import BaseModel, ValidationError
from typing import List, Optional, Union

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
    chapter: str
    part: str
    toc: List[TableOfContents]


class Data(BaseModel):
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

def find_existing_section(parent_children: List[TableOfContents], section: str, number: str) -> Optional[TableOfContents]:
    """find an existing section by section type and number."""
    for child in parent_children:
        if child.section == section and child.number == number:
            return child
    return None


def nest_toc(content: Contents) -> TableOfContents:
    chapter_info = content.chapter.split("\u2014")
    chapter_number = chapter_info[0].strip().split(" ")[-1]
    chapter_title = chapter_info[1].strip().rsplit(" ", 1)[0]

    if content.part == "Full Chapter" or content.toc[0].section == "Chapter":
        return TableOfContents(
            section="Chapter",
            number=chapter_number,
            title=chapter_title,
            children=content.toc[0].children
        )
    else:
        part_info = content.part.split("\u2014")
        part_number = part_info[0].strip().split(" ")[-1]
        part_title = part_info[1].strip().split(" - ")[0].rsplit(" ", 1)[0]

        return TableOfContents(
            section="Chapter",
            number=chapter_number,
            title=chapter_title,
            children=[
                TableOfContents(
                    section="Part",
                    number=part_number,
                    title=part_title,
                    children=content.toc[0].children
                )
            ]
        )


def merge_toc(master_toc: List[TableOfContents], new_toc: TableOfContents):
    """merge a new TOC into the master TOC."""
    existing_chapter = find_existing_section(master_toc, "Chapter", new_toc.number)
    if existing_chapter:
        existing_chapter.children = merge_children(existing_chapter.children, new_toc.children or [])
    else:
        master_toc.append(new_toc)


def build_master_toc(data: Data) -> List[TableOfContents]:
    master_toc: List[TableOfContents] = []

    for content in data.contents:
        nested_toc = nest_toc(content)
        merge_toc(master_toc, nested_toc)

    return master_toc


def main():
    # Load the JSON data from a file
    with open(toc_path.format(vol=3), "r") as f:
        json_data = json.load(f)

    try:
        # Validate the JSON data using Pydantic
        data = Data(**json_data)

        # Build the master Table of Contents
        master_toc = build_master_toc(data)

        # Save to a single file
        save_toc_to_file(master_toc, "toc3.json")
        print("Saved master_toc.json")

    except ValidationError as e:
        print(f"Validation error: {e}")


if __name__ == "__main__":
    main()