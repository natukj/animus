import json
import re
import os
import utils
import pandas as pd

def extract_between_tags(tag: str, string: str, strip: bool = False) -> str:
    ext_list = re.findall(f"<{tag}>(.+?)</{tag}>", string, re.DOTALL)
    if ext_list:
        content = ext_list[0]
        return content.strip() if strip else content
    return ""

def calculate_depths_and_hierarchy(data: list, current_path: str = "", depth: int = 0):
    results = []

    for item in data:
        path_components = []
        if item.get('section'):
            path_components.append(item['section'])
        if item.get('number'):
            path_components.append(item['number'])
        if item.get('title'):
            path_components.append(item['title'])

        item_path = " ".join(path_components)
        full_path = "/".join(filter(None, [current_path, item_path]))
        
        has_children = 'children' in item
        
        results.append({
            'path': full_path,
            'depth': depth,
            'has_children': has_children
        })
        
        if has_children:
            children_results = calculate_depths_and_hierarchy(item['children'], full_path, depth + 1)
            results.extend(children_results)

    return results

def traverse_contents(data: list, current_path: str ="", all_references: set = None):
    # fucked up with this should have used '>' not '/' as it got all the depths wrong
    if all_references is None:
        all_references = set()
    results = []
    for item in data:
        path_components = []
        if item.get('section'):
            path_components.append(item['section'])
        if item.get('number'):
            path_components.append(item['number'])
        if item.get('title'):
            path_components.append(item['title'])

        item_path = " ".join(path_components)
        full_path = "/".join(filter(None, [current_path, item_path]))

        if 'content' in item:
            if item.get('section') and item.get('number'):
                self_ref = f"{item['section']} {item['number']}"
                all_references.add(self_ref)
            elif item.get('number'):
                self_ref = item['number']
                all_references.add(self_ref)
            else:
                self_ref = ""

            results.append({
                'path': full_path,
                'title': item.get('title', ''),
                'content': item['content'],
                'self_ref': self_ref
            })
        else:
            utils.print_coloured(f"Missing content for {full_path}", "red")    
        if 'children' in item:
            child_results, _ = traverse_contents(item['children'], full_path, all_references)
            results.extend(child_results)
    
    return results, all_references

def traverse_contents_depth(data: list, current_path: str ="", all_references: set = None, depth: int = 0):
    if all_references is None:
        all_references = set()
    results = []
    for item in data:
        path_components = []
        if item.get('section'):
            path_components.append(item['section'])
        if item.get('number'):
            path_components.append(item['number'])
        if item.get('title'):
            path_components.append(item['title'])

        item_path = " ".join(path_components)
        full_path = "/".join(filter(None, [current_path, item_path]))

        if 'content' in item:
            if item.get('section') and item.get('number'):
                self_ref = f"{item['section']} {item['number']}"
                all_references.add(self_ref)
            elif item.get('number'):
                self_ref = item['number']
                all_references.add(self_ref)
            else:
                self_ref = ""

            results.append({
                'path': full_path,
                'title': item.get('title', ''),
                'content': item['content'],
                'self_ref': self_ref,
                'depth': depth  # forgot to add depth to the results
            })
        else:
            utils.print_coloured(f"Missing content for {full_path}", "red")    
        if 'children' in item:
            child_results, _ = traverse_contents(item['children'], full_path, all_references, depth + 1)
            results.extend(child_results)
    
    return results, all_references


def find_item_from_path(data, target_path, current_path=""):
    def normalise_path(path):
        return ' '.join(path.lower().split())

    def build_path(current, item):
        components = []
        if current:
            components.append(current)
        if item.get('section'):
            components.append(item['section'])
        if item.get('number'):
            components.append(item['number'])
        if item.get('title'):
            components.append(item['title'])
        return "/".join(components)

    target_path_normalised = normalise_path(target_path)

    for item in data:
        full_path = build_path(current_path, item)
        full_path_normalised = normalise_path(full_path)

        if full_path_normalised == target_path_normalised:
            return {
                'path': full_path,
                'content': item.get('content', ''),
                'tokens': item.get('tokens', 0)
            }
        if 'children' in item:
            result = find_item_from_path(item['children'], target_path, full_path)
            if result:
                return result
    return None


def split_content(content: str, target_chunk_tokens: int = 2000) -> list:
    # NOTE not sure how generalisable '___' is
    initial_chunk= ""
    chunks = []
    lines = content.split('\n')
    
    current_chunk = ""
    current_chunk_tokens = 0
    
    for line in lines:
        line_tokens = utils.count_tokens(line)
        if line.startswith('___') and current_chunk and current_chunk_tokens >= target_chunk_tokens:
            chunks.append(current_chunk.strip())
            current_chunk = line
            current_chunk_tokens = line_tokens
        elif line.startswith('___') and not initial_chunk and current_chunk:
            initial_chunk = current_chunk
        else:
            if current_chunk:
                current_chunk += "\n"
            current_chunk += line
            current_chunk_tokens += line_tokens
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return initial_chunk, chunks

def find_references_slow(content: str, references: list):
    found_refs = []
    for ref in references:
        if re.search(r'\b' + re.escape(ref) + r'\b', content):
            found_refs.append(ref)
    return found_refs

def find_references(content: str, references: list):
    pattern = r'\b(?:' + '|'.join(map(re.escape, references)) + r')\b'
    matches = re.findall(pattern, content)
    return list(set(matches))

def process_item(item: dict , all_references: list):
    if isinstance(item, list) and len(item) > 0:
        item = item[0]
    if not isinstance(item, dict):
        raise ValueError(f"Expected item to be a dict, got {type(item)}")
    references_to_search = [ref for ref in all_references if ref != item['self_ref']]
    references = find_references(item['content'], references_to_search)
    # not sure if filtering again is correct
    filtered_references = [ref for ref in references if ref not in item['self_ref']]
    return {
        'path': item['path'],
        'title': item['title'],
        'content': item['content'],
        'self_ref': item['self_ref'],
        'references': filtered_references
    }
# df formatting 
def find_end_items(df: pd.DataFrame) -> pd.DataFrame:
    end_items = []
    all_paths = df['path'].tolist()
    for _, row in df.iterrows():
        current_path = row['path']
        is_parent = any(path.startswith(current_path + '/') for path in all_paths if path != current_path)
        
        if not is_parent:
            end_items.append(row)
    return pd.DataFrame(end_items)
def find_parents(df: pd.DataFrame) -> set:
    all_parents = set()
    for path in df['path']:
        parent_path = path.rsplit('/', 1)[0]  # Split at the last '/'
        all_parents.add(parent_path)
    return all_parents
def add_reverse_hierarchy(df: pd.DataFrame) -> pd.DataFrame:
    end_items_df = find_end_items(df)
    df['hierarchy_level'] = 0
    current_level = 1
    current_parents = find_parents(end_items_df)
    while current_parents:
        df.loc[df['path'].isin(current_parents), 'hierarchy_level'] = current_level
        next_parents = set()
        for path in current_parents:
            if '/' in path:
                next_parents.add(path.rsplit('/', 1)[0])
        current_parents = next_parents
        current_level += 1
    return df
# def add_reverse_hierarchy(df: pd.DataFrame) -> pd.DataFrame:
#     max_depths = {}
#     # first pass: determine the maximum depth for each path
#     for _, row in df.iterrows():
#         path = row['path']
#         depth = row['depth']  
#         while path:
#             if path not in max_depths or depth > max_depths[path]:
#                 max_depths[path] = depth
#             path = path.rsplit('/', 1)[0]  # move up one level
#     # second pass: calculate the reverse hierarchy level
#     df['hierarchy_level'] = df.apply(lambda row: max_depths[row['path']] - row['depth'], axis=1)
#     return df