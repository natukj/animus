import utils
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from functools import partial
import pandas as pd
import re
from typing import List, Set

#TODO make document specific regex patterns from llm
def find_references(content: str, references: Set[str]) -> List[str]:
    # number sequences with dots (up to 3 decimal places)
    dotted_number_pattern = r'(?<!\S)(\d+(?:\.\d+){1,3})(?!\S)'
    # "Chapter" followed by a number, not followed by ":"
    chapter_pattern = r'Chapter (\d+)(?!:)(?:\s|$)'
    appendix_pattern = r'\b(Appendix [A-Z])\b'
    letter_number_pattern = r'(?<!\S)([A-Z](?:\.\d+)+)(?!\S)'
    combined_pattern = f'({dotted_number_pattern}|{chapter_pattern}|{appendix_pattern}|{letter_number_pattern})'
    potential_refs = re.findall(combined_pattern, content)
    cleaned_refs = [ref for match in potential_refs for ref in match if ref]
    valid_refs = [ref for ref in cleaned_refs if ref in references]
    return list(set(valid_refs))

def process_row(row: pd.Series, all_references: Set[str]) -> List[str]:
    references = find_references(row['content'], all_references)
    filtered_references = [ref for ref in references if ref != row['self_ref']]
    return filtered_references

def add_refs_to_df(df: pd.DataFrame, all_references: Set[str]) -> pd.DataFrame:
    new_df = df.copy()
    new_df['references'] = new_df.apply(lambda row: process_row(row, all_references), axis=1)
    return new_df

def add_refs_to_contents(contents: list) -> pd.DataFrame:
    num_cores = multiprocessing.cpu_count()
    preprocessed_items, all_references = utils.traverse_contents(contents)
    process_item_partial = partial(utils.process_item, all_references=all_references)
    with ProcessPoolExecutor(max_workers=num_cores) as executor:
        processed_items = list(executor.map(process_item_partial, preprocessed_items))
    df = pd.DataFrame(processed_items)
    cols = ['path', 'title', 'content', 'self_ref', 'references']
    return df[cols]