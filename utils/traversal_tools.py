import pandas as pd
import numpy as np
import ast
import asyncio
import llm
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor

# NOTE working with dfs while testing (not GDB)
# utils for main_trav.py Claude traversal
def get_subpaths(df: pd.DataFrame, current_path: str) -> list:
    if current_path == "":
        return df[df['depth'] == 0]['path'].tolist()
    else:
        current_depth = df[df['path'] == current_path]['depth'].iloc[0]
        subpaths = df[(df['path'].str.startswith(current_path + '/')) & (df['depth'] == current_depth + 1)]['path'].tolist()
        if current_depth == 0:
            subpaths += "\n\nYou can not go back further."
        return subpaths

def get_subpath_options(paths: list, current_depth: int) -> str:
    subpath_options = "Subpaths:\n"
    for i, path in enumerate(paths, 1):
        subpath_options += f"{i} -> {path.split('/', current_depth)[-1]}\n"
    return subpath_options

def get_content_and_references(df: pd.DataFrame, path: str) -> tuple:
    content = ""
    row = df[df['path'] == path].iloc[0]
    content += f"'{row['title']}' Content:\n\n"
    content += row['content']
    references = ast.literal_eval(row['references'])
    if references:
        content += f"\n\nTraversal references from '{row['title']}':"
        for i, ref in enumerate(references, 1):
            content += f"\nr{i} -> {ref}"
    return content, references

def get_content(df: pd.DataFrame, path: str) -> tuple:
    content = f"Item path: {path}\n\n"
    row = df[df['path'] == path].iloc[0]
    content += row['content'] + "\n\n"
    return content

def find_path_by_self_ref(df: pd.DataFrame, self_ref: str) -> str:
    matching_rows = df[df['self_ref'] == self_ref]
    if not matching_rows.empty:
        return matching_rows.iloc[0]['path']
    return None
# utils for main_embed_trav.py 
def cosine_similarity(a: np.array, b: np.array) -> float:
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
async def df_semantic_search(df: pd.DataFrame, user_query: str, top_n: int = 10, return_vector: bool = False) -> pd.DataFrame:
    df = df.copy()
    embedding = await llm.openai_client_embedding_request(
        user_query
    )
    df["similarities"] = df.embedding.apply(lambda x: cosine_similarity(x, embedding))
    
    res = (
        df.sort_values("similarities", ascending=False)
        .head(top_n)
    )
    if return_vector:
        return res, embedding
    return res
def filter_embedded_df_by_hierarchy(df: pd.DataFrame, hierarchy_level: int) -> pd.DataFrame:
    return df[df['hierarchy_level'] == hierarchy_level]
def search_level(df: pd.DataFrame, query_embedding: np.array, level: int, parent_path: str = "", top_n: int = 7) -> List[Dict]:
    filtered_df = df[(df['hierarchy_level'] == level) & (df['path'].str.startswith(parent_path))]
    if filtered_df.empty:
        return []
    filtered_df = filtered_df.copy()
    filtered_df["similarities"] = filtered_df.embedding.apply(lambda x: cosine_similarity(x, query_embedding))
    results = filtered_df.sort_values("similarities", ascending=False).head(top_n)
    
    with ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(search_level, df, query_embedding, level - 1, row['path'], top_n)
            for _, row in results.iterrows()
        ]
        children_results = [future.result() for future in futures]
    
    output = []
    for (_, row), children in zip(results.iterrows(), children_results):
        result_dict = row.to_dict()
        result_dict['children'] = children
        output.append(result_dict)
    
    return output
async def df_recursive_semantic_search(df: pd.DataFrame, user_query: str, start_level: int = 4, top_n: int = 7) -> List[Dict]:
    top_filtered_df = df[df['hierarchy_level'] == start_level]
    top_level_res, query_embedding = await df_semantic_search(top_filtered_df, user_query, top_n=top_n, return_vector=True)
    
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor() as pool:
        tasks = [
            loop.run_in_executor(
                pool,
                search_level,
                df, query_embedding, start_level - 1, row['path'], top_n
            )
            for _, row in top_level_res.iterrows()
        ]
        children_results = await asyncio.gather(*tasks)
    
    output = []
    for (_, row), children in zip(top_level_res.iterrows(), children_results):
        result_dict = row.to_dict()
        result_dict['children'] = children
        output.append(result_dict)
    
    return output
# old code
def find_section_titles(tax_data, search_title=None):
    def search_children(children, search_title):
        for child in children:
            if child['title'] == search_title:
                return [(subchild['title'], subchild['content']) for subchild in child.get('children', [])]
        return []

    if search_title is None:
        return [(section['title'], section['content']) for section in tax_data]
    else:
        for section in tax_data:
            if section['title'] == search_title:
                return [(child['title'], child['content']) for child in section.get('children', [])]
            elif 'children' in section:
                result = search_children(section['children'], search_title)
                if result:
                    return result
        return []
def find_section_by_path(tax_data, path):
    def search_children(children, index):
        for child in children:
            if child['title'] == path[index]:
                # check if this is the last component of the path or continue deeper
                if index + 1 == len(path):
                    return [(subchild['title'], subchild['content']) for subchild in child.get('children', [])]
                else:
                    return search_children(child.get('children', []), index + 1)
        return []
    return search_children(tax_data, 0)