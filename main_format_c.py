import json
import os
import pandas as pd
from pathlib import Path
import formatters, utils, llm, clustering
import numpy as np
import pandas as pd
import asyncio
from tqdm import tqdm
from tqdm.asyncio import tqdm_asyncio

parsed_path = os.environ.get("PARSED_JSON_PATH", "")
output_path = os.environ.get("OUTPUT_PATH", "")
csv_path = os.environ.get("CSV_PATH", "")

TO_CSV = False
EMBED = False
CLUSTER = False
TEST = True
import ast
def parse_references(x, self_ref):
    if pd.isna(x):
        return []
    if isinstance(x, str):
        try:
            refs = ast.literal_eval(x)
        except (ValueError, SyntaxError):
            refs = x.split(',') if ',' in x else [x]
    elif isinstance(x, list):
        refs = x
    else:
        return []
    # check if self_ref is not NaN and is a string starting with 'A'
    if not pd.isna(self_ref) and isinstance(self_ref, str) and self_ref.startswith('A'):
        refs = [ref.strip() for ref in refs if ref.strip() != 'Appendix A']
    else:
        refs = [ref.strip() for ref in refs]
    return refs

if TEST:
    df = pd.read_csv(csv_path)
    df_path_and_refs = df[['path', 'self_ref' , 'references']]
    df['references'] = df.apply(lambda row: parse_references(row['references'], row['self_ref']), axis=1)
    for _, row in df.iterrows():
        print(f"{row['path']} ({row['self_ref']} {type(row['self_ref'])})")
        for ref in row['references']:
            print(f"    {ref}")

if CLUSTER:
    df = pd.read_csv(csv_path)
    depth_counts = df['depth'].value_counts().sort_index()
    hierarchy_counts = df['hierarchy_level'].value_counts().sort_index()
    max_depth = df['depth'].max()
    min_hl = df['hierarchy_level'].min()
    def cluster_level(filtered_df: pd.DataFrame, n_clusters: int = None):
        filtered_df = filtered_df.copy()
        filtered_df['embedding'] = filtered_df['embedding'].apply(utils.strvec_to_numpy)
        filtered_df = filtered_df.dropna(subset=['embedding'])
        embedding_dim = len(filtered_df['embedding'].iloc[0])
        filtered_df = filtered_df[filtered_df['embedding'].apply(lambda x: len(x) == embedding_dim)]
        embeddings_array = np.array(filtered_df['embedding'].tolist())
        cluster_labels, _, _ = clustering.cluster_vectors(embeddings_array, method='kmeans', n_clusters=n_clusters)
        return cluster_labels
    df['d_cluster'] = np.nan
    for depth in tqdm(depth_counts.index, desc="Clustering by depth"):
        mask = df['depth'] == depth
        filtered_df = df[mask]
        cluster_labels = cluster_level(filtered_df)
        df.loc[mask, 'd_cluster'] = cluster_labels
    df['hl_cluster'] = np.nan
    for hl in tqdm(hierarchy_counts.index, desc="Clustering by hierarchy level"):
        mask = df['hierarchy_level'] == hl
        filtered_df = df[mask]
        cluster_labels = cluster_level(filtered_df)
        df.loc[mask, 'hl_cluster'] = cluster_labels
    output_file = os.path.join(output_path, "GNU_C_clustered.csv")
    df.to_csv(output_file, index=False)

if EMBED:
    SEM_MAX = 1000
    df_w_app = pd.read_csv(csv_path)
    df = df_w_app.iloc[:735] # cut appendices for now
    print(f"{len(df)} entries in CSV.")
    count = [0]
    async def embed_content(sem: asyncio.Semaphore, row: pd.Series):
        async with sem:
            content = row['title']
            count[0] += 1 
            return await llm.openai_client_embedding_request(content)

    async def main_embed():
        sem = asyncio.Semaphore(SEM_MAX)
        tasks = [embed_content(sem, row) for _, row in df.iterrows()]
        embeddings = await tqdm_asyncio.gather(*tasks, desc="Creating embeddings")
        df['embedding'] = embeddings
        print(f"Added {count[0]} embeddings for a total of {len(embeddings)} embeddings to CSV...")
        output_file = os.path.join(output_path, "GNU_C_embedded.csv")
        df.to_csv(output_file, index=False)
    asyncio.run(main_embed())
if TO_CSV:
    try:
        with open(parsed_path, "r") as f:
            data = json.load(f)["contents"]
    except FileNotFoundError:
        print(f"File not found: {parsed_path}")
        exit(1)
    except json.JSONDecodeError:
        print(f"Invalid JSON in file: {parsed_path}")
        exit(1)

    depth_hierarchy_data, all_references = utils.traverse_contents_depth(data)

    depth_hierarchy_df = pd.DataFrame(depth_hierarchy_data)

    # sort the df by path to ensure parent nodes come before children (should already be the case)
    depth_hierarchy_df = depth_hierarchy_df.sort_values('path')
    # calculate has_children
    depth_hierarchy_df['has_children'] = depth_hierarchy_df.apply(
        lambda row: any(other_path.startswith(row['path'] + '>') for other_path in depth_hierarchy_df['path']),
        axis=1
    )
    # calculate the hierarchy_level as the maximum depth of its descendants minus its own depth
    depth_hierarchy_df['hierarchy_level'] = depth_hierarchy_df.apply(
        lambda row: 0 if not row['has_children'] else depth_hierarchy_df[depth_hierarchy_df['path'].str.startswith(row['path'] + '>')]['depth'].max() - row['depth'],
        axis=1
    )

    depth_hierarchy_df.drop(columns=['has_children'], inplace=True)
    final_df = formatters.add_refs_to_df(depth_hierarchy_df, all_references)
    cols = ['path', 'title', 'content', 'self_ref', 'depth', 'hierarchy_level', 'references']
    final_df = final_df[cols]
    output_file = os.path.join(output_path, "depth_hierarchy.csv")
    final_df.to_csv(output_file, index=False)
    print(f"DataFrame saved to {output_file}")