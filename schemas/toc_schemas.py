from __future__ import annotations
from pydantic import BaseModel, create_model
from typing import Union, Optional, List, Dict, NewType, Any, Type
import json
from collections import OrderedDict

JSONstr = NewType('JSONstr', str)

class TableOfContentsChild(BaseModel):
    number: str
    title: str

class TableOfContents(BaseModel):
    section: str
    number: str
    title: str
    children: Optional[List[Union[TableOfContents, TableOfContentsChild]]]

    def find_child(self, section: Optional[str], number: str) -> Optional[Union[TableOfContents, TableOfContentsChild]]:
        """Find an existing child by section and number."""
        if not self.children:
            return None
        for child in self.children:
            if isinstance(child, TableOfContents) and child.section == section and child.number == number:
                return child
            if isinstance(child, TableOfContentsChild) and child.number == number:
                return child
        return None

    def add_child(self, child: Union[TableOfContents, TableOfContentsChild]):
        """Add a new child or merge with an existing one."""
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

def preprocess_levels_dict(levels_dict: Dict[str, Any]) -> Dict[str, Any]:
    """sections that don't have a size hierarchy but are nested in the ToC are represented as empty dictionaries, eg:
    {\"section\": \"Subdivision\", \"number\": \"842-B\", \"title\": \"Some items of Australian source income of foreign residents that are exempt from income tax\"}": {},
    This function processes these empty dictionaries and their children into a proper hierarchy
    NOTE currently this add proceeding sections to {} section until the next {} section is found, this may not be the desired behavior and will need to be improved
    """
    # if the top level of data has only one key (ToC header), skip it and start from its children
    if len(levels_dict) == 1 and 'children' in next(iter(levels_dict.values())):
        levels_dict = next(iter(levels_dict.values()))['children']
        print("Skipping top level")
    def process_level(level_data: Dict[str, Any]) -> Dict[str, Any]:
        keys = list(level_data.keys())
        processed_data = {}
        i = 0

        while i < len(keys):
            key = keys[i]
            value = level_data[key]

            if value == {}:
                # start a new section for the empty value
                processed_data[key] = {"children": {}}
                i += 1
                while i < len(keys) and level_data[keys[i]] != {}:
                    # collect subsequent keys and values into the current empty dictionary's children
                    processed_data[key]["children"][keys[i]] = level_data[keys[i]]
                    i += 1
            else:
                if "children" in value:
                    # recursively process nested children
                    value["children"] = process_level(value["children"])
                processed_data[key] = value
                i += 1

        return processed_data

    return process_level(levels_dict)

def merge_keys_and_delete_next(levels_dict: Dict[str, Any]) -> Dict[str, Any]:
    """used when ToC has section titles on separate lines, eg:
    "{\"section\": \"PART\", \"number\": \"47\", \"title\": \"\"}": {},
    "{\"section\": \"\", \"number\": \"\", \"title\": \"FINAL PROVISIONS\"}"
    -> "{\"section\": \"PART\", \"number\": \"47\", \"title\": \"FINAL PROVISIONS\"}"""
    new_levels_dict = OrderedDict()
    items = list(levels_dict.items())
    i = 0
    while i < len(items):
        key, value = items[i]
        while value == {} and i + 1 < len(items):
            following_key, following_value = items[i + 1]
            details = json.loads(key)
            next_details = json.loads(following_key)
            if not details.get('title') and next_details.get('title'):
                details['title'] = next_details['title']
                key = json.dumps(details, ensure_ascii=False)
                value = following_value
                i += 1  # continue merging with next item
            else:
                break  # break if no merge is needed
        if isinstance(value, dict):
            value = merge_keys_and_delete_next(value)
        new_levels_dict[key] = value
        i += 1
    return new_levels_dict

def parse_toc_dict(data: Dict[str, Any], pre_process: bool = True) -> List[TableOfContents]:
    def create_toc(item: Dict[str, Any], key: Optional[str] = None, parent_toc: Optional[TableOfContents] = None) -> Union[TableOfContents, TableOfContentsChild, None]:
        if 'children' in item:
            key_split = key.rsplit('}', 1)
            if len(key_split) == 2:
                key = key_split[0] + '}'
            details = json.loads(key)
            toc = TableOfContents(
                section=details.get('section'),
                number=details.get('number'),
                title=details.get('title'),
                children=[]
            )
            for child_key, child_value in item['children'].items():
                child_toc = create_toc(child_value, child_key, toc)
                if child_toc:
                    toc.children.append(child_toc)
            return toc
        elif 'contents' in item and isinstance(item['contents'], list):
            children = [TableOfContentsChild(number=content['number'], title=content['title']) for content in
                        item['contents']]
            if key:
                key_split = key.rsplit('}', 1)
                if len(key_split) == 2:
                    key = key_split[0] + '}'
                details = json.loads(key)
                return TableOfContents(
                    section=details.get('section'),
                    number=details.get('number'),
                    title=details.get('title'),
                    children=children
                )
            else:
                # if no key, append to parent's children
                parent_toc.children.extend(children)
        else:
            # empty dictionary: implicit children indicator
            if key:
                print(f"Empty dictionary: {key}")
                key_split = key.rsplit('}', 1)
                if len(key_split) == 2:
                    key = key_split[0] + '}'
                details = json.loads(key)
                toc = TableOfContents(
                    section=details.get('section'),
                    number=details.get('number'),
                    title=details.get('title'),
                    children=[]
                )
                # Only append to parent here, no return needed
                if parent_toc:
                    parent_toc.children.append(toc)

    root_toc = TableOfContents(
        section="",
        number="",
        title="Root",
        children=[]
    )
    if pre_process:
        preprocessed_data = preprocess_levels_dict(data)
    else:
        preprocessed_data = merge_keys_and_delete_next(data)
    for top_level_key, top_level_value in preprocessed_data.items():
        top_level_toc = create_toc(top_level_value, top_level_key, root_toc)
        if top_level_toc:
            root_toc.children.append(top_level_toc)

    
    return root_toc.children

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

## NOTE don't know if i need below code
class Contents(BaseModel):
    levels: Dict[str, JSONstr] = {}
    toc: List[Union[TableOfContents, TableOfContentsChild]]

    @classmethod
    def from_dict(cls, levels: Dict[str, JSONstr], toc: List[Union[TableOfContents, TableOfContentsChild]]) -> Contents:
        return cls(levels=levels, toc=toc)

    def to_dict(self) -> Dict[str, Any]:
        return {"levels": self.levels, "toc": self.toc}

    def add_level(self, level_name: str, level_value: JSONstr) -> None:
        self.levels[level_name] = level_value

def generate_contents_class(max_depth: int) -> Type[BaseModel]:
    """
    Dynamically generate the Contents class with the given number of sublevels.
    
    :param max_depth: The maximum depth for sublevels.
    :return: A dynamically created Contents class.
    """
    fields = {
        'level': (Optional[JSONstr], None),
        'toc': (List[Union[TableOfContents, TableOfContentsChild]], ...)
    }

    for i in range(1, max_depth):
        sublevel_name = 'sub' * i + 'level'
        fields[sublevel_name] = (Optional[JSONstr], None)

    return create_model('Contents', **fields)


class TableOfContentsDict(BaseModel):
    contents: List[Contents]

def merge_children(existing_children: Optional[List[Union[TableOfContents, TableOfContentsChild]]], new_children: List[Union[TableOfContents, TableOfContentsChild]]) -> List[Union[TableOfContents, TableOfContentsChild]]:
    """Merge a list of new children into existing children."""
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