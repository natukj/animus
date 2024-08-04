import json
import os
import pandas as pd
from pathlib import Path
import formatters, utils, llm, clustering
import numpy as np
import pandas as pd
import asyncio
from tqdm import tqdm
import re
import ast
from tqdm.asyncio import tqdm_asyncio

# desired
#path,title,content,self_ref,depth,hierarchy_level,references,embedding,d_cluster,hl_cluster

def create_path(df):
    current_part = ""
    current_schedule = ""
    current_main_section = ""
    paths = []
    
    for _, row in df.iterrows():
        enum = str(row['enumeration'])
        heading = row['heading']
        part_heading = row['part_heading']
        
        if enum.startswith('Part'):
            current_part = f"{enum} {part_heading}"
            current_schedule = ""
            current_main_section = ""
            paths.append(current_part)
        elif enum.startswith('Schedule'):
            current_schedule = f"{enum} {heading}"
            current_main_section = ""
            paths.append(current_schedule)
        elif current_schedule:
            # in a schedule
            if re.match(r'^[A-Z]\.\d+$', enum):
                # main section in a schedule (e.g., A.1, B.2)
                current_main_section = f"{current_schedule}>{enum} {heading}"
                paths.append(current_main_section)
            else:
                # subsection in a schedule
                paths.append(f"{current_main_section}>{enum} {heading}")
        elif '.' not in enum:
            # main numbered section
            current_main_section = f"{current_part}>{enum} {heading}"
            paths.append(current_main_section)
        else:
            # subsection of a numbered section
            paths.append(f"{current_main_section}>{enum} {heading}")
    
    return paths


def transform_csv(input_file, output_file):
    df = pd.read_csv(input_file)
    df['path'] = create_path(df)
    
    result_rows = []
    current_main = None
    current_sublevel = None
    current_sublevel_content = ""
    sublevel_content = []
    subsublevel_content = []
    combined_references = set()

    def is_sublevel(enum):
        return '(' in str(enum) and not re.search(r'\([a-z]+\)\([a-z]+\)', str(enum))

    def is_subsublevel(enum):
        return re.search(r'\([a-z]+\)\([a-z]+\)', str(enum))
    
    def safe_content(content):
        if pd.isna(content) or not isinstance(content, str):
            return ""
        return content.strip()
    
    def finalise_sublevel():
        nonlocal current_sublevel, current_sublevel_content, subsublevel_content, sublevel_content
        if current_sublevel:
            full_sublevel = f"\t - ({current_sublevel}) {current_sublevel_content}"
            if subsublevel_content:
                full_sublevel += '\n' + '\n'.join(subsublevel_content)
            sublevel_content.append(full_sublevel)
            current_sublevel = None
            current_sublevel_content = ""
            subsublevel_content = []

    for _, row in df.iterrows():
        enum = str(row['enumeration'])
        content = safe_content(row['content'])
        
        if is_subsublevel(enum):
            subsublevel_label = enum.split(')')[-2].split('(')[-1]
            subsublevel_content.append(f"\t\t - ({subsublevel_label}) {content}")
        elif is_sublevel(enum):
            finalise_sublevel()
            current_sublevel = enum.split('(')[1].rstrip(')')
            current_sublevel_content = content
        else:
            finalise_sublevel()
            if current_main is not None:
                current_main['content'] += '\n' + '\n'.join(sublevel_content)
                current_main['references'] = list(combined_references)
                result_rows.append(current_main)
            
            current_main = row.to_dict()
            current_main['content'] = content
            sublevel_content = []
            subsublevel_content = []
            combined_references = set()
        
        combined_references.update(ast.literal_eval(row['references']))

    finalise_sublevel()
    if current_main is not None:
        if sublevel_content:
            if subsublevel_content:
                sublevel_content[-1] += '\n' + '\n'.join(subsublevel_content)
            current_main['content'] += '\n' + '\n'.join(sublevel_content)
        current_main['references'] = list(combined_references)
        result_rows.append(current_main)

    new_df = pd.DataFrame(result_rows)

    new_df['title'] = new_df['heading']
    new_df['self_ref'] = new_df['enumeration']
    new_df['depth'] = new_df['path'].str.count('>')
    
    new_df = new_df.sort_values('path')
    
    new_df['has_children'] = new_df.apply(
        lambda row: any(other_path.startswith(row['path'] + '>') for other_path in new_df['path']),
        axis=1
    )
    new_df['hierarchy_level'] = new_df.apply(
        lambda row: 0 if not row['has_children'] else new_df[new_df['path'].str.startswith(row['path'] + '>')]['depth'].max() - row['depth'],
        axis=1
    )
    new_df = new_df[['path', 'title', 'content', 'self_ref', 'depth', 'hierarchy_level', 'references']]

    new_df.to_csv(output_file, index=False)

def process_all_csvs(input_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    csv_files = [f for f in os.listdir(input_dir) if f.endswith('.csv')]

    for csv_file in csv_files:
        input_path = os.path.join(input_dir, csv_file)
        output_path = os.path.join(output_dir, csv_file)
        
        print(f"Processing {csv_file}...")
        transform_csv(input_path, output_path)
        print(f"Finished processing {csv_file}")

ma_csv_dir = "/Users/jamesqxd/Documents/norgai-docs/awardcsv_FINAL"
output_path = os.environ.get("OUTPUT_PATH", "")
process_all_csvs(ma_csv_dir, output_path)
# test_path = "/Users/jamesqxd/Documents/norgai-docs/awardcsv_FINAL/MA000093-Marine Tourism and Charter Vessels.csv"
# output_file = os.path.join(output_path, "18tst.csv")
# transform_csv(test_path, output_file)