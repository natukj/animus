import utils
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from functools import partial
import pandas as pd

def add_refs_to_contents(contents: list) -> pd.DataFrame:
    num_cores = multiprocessing.cpu_count()
    preprocessed_items, all_references = utils.traverse_contents(contents)
    process_item_partial = partial(utils.process_item, all_references=all_references)
    with ProcessPoolExecutor(max_workers=num_cores) as executor:
        processed_items = list(executor.map(process_item_partial, preprocessed_items))
    df = pd.DataFrame(processed_items)
    cols = ['path', 'title', 'content', 'self_ref', 'references']
    return df[cols]