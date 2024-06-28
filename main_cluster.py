import json
import asyncio
import llm, prompts, utils, clustering
import pandas as pd
import numpy as np
from tqdm.asyncio import tqdm_asyncio
from tqdm import tqdm

GET_DEPTH = False
EMBED = False
CLUSTER = False
CLUSTER_ALL = False
CHECK_CLUSTERS = True

if CHECK_CLUSTERS:
    df = pd.read_csv("ztest_tax_output/final_formatted_tax_data_clustered.csv")
    def check_and_print_nan(df):
        # Find columns that are not 'summary' or 'self_ref'
        columns_to_check = [col for col in df.columns if 'summary' not in col.lower() and 'self_ref' not in col.lower()]
        
        # Find rows with NaN values in the columns we're checking
        rows_with_nan = df[df[columns_to_check].isna().any(axis=1)]
        
        if rows_with_nan.empty:
            print("No NaN values found in the relevant columns of the DataFrame.")
            return

        print(f"Found {len(rows_with_nan)} rows with NaN values in relevant columns.")
        print("\nDisplaying 'path' and columns with NaN for each row:")
        print("-" * 80)

        for index, row in rows_with_nan.iterrows():
            print(f"Row index: {index}")
            print(f"Path: {row['path']}")
            
            # Get columns with NaN for this row, excluding 'summary' and 'self_ref' columns
            nan_columns = [col for col in columns_to_check if pd.isna(row[col])]
            
            print("Columns with NaN:")
            for col in nan_columns:
                print(f"  {col}")
            
            print("-" * 80)
    def print_cluster_info(df, column, cluster_column):
        print(f"\n{column.capitalize()} Clustering Information:")
        print("-" * 40)
        
        for level in sorted(df[column].unique()):
            level_df = df[df[column] == level]
            num_entries = len(level_df)
            num_clusters = level_df[cluster_column].nunique()
            
            print(f"{column.capitalize()} {level}:")
            print(f"  Number of entries: {num_entries}")
            print(f"  Number of clusters: {num_clusters}")

    #print_cluster_info(df, 'depth', 'd_cluster')

    # print_cluster_info(df, 'hierarchy_level', 'hl_cluster')
    # non_df=df[df['hierarchy_level'].isna()]
    # for _, row in non_df.iterrows():
    #     print(row['path'])
    #     print(row['hierarchy_level'])
    check_and_print_nan(df)



if CLUSTER_ALL:
    tax_df_path = "ztest_tax_output/all_formatted_tax_data_embedded_depth.csv"
    df = pd.read_csv(tax_df_path)
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
        if len(filtered_df) > 1:
            n_clusters = 300 if depth == max_depth else None
            cluster_labels = cluster_level(filtered_df, n_clusters=n_clusters)
            df.loc[mask, 'd_cluster'] = cluster_labels
    df['hl_cluster'] = np.nan
    for hl in tqdm(hierarchy_counts.index, desc="Clustering by hierarchy level"):
        mask = df['hierarchy_level'] == hl
        filtered_df = df[mask]
        if len(filtered_df) > 1: 
            n_clusters = 446 if hl == min_hl else None
            cluster_labels = cluster_level(filtered_df, n_clusters=n_clusters)
            df.loc[mask, 'hl_cluster'] = cluster_labels

    df.to_csv("ztest_tax_output/final_formatted_tax_data_clustered.csv", index=False)



if GET_DEPTH:
    tax_df_path = "ztest_tax_output/formatted_tax_data_embedded.csv"
    df = pd.read_csv(tax_df_path)
    filtered_depth_df = df[(df['depth'] == 1)]
    for _, row in filtered_depth_df.iterrows():
        print(row['title'])
        print("-" * 50)
        depth_1_path = row['path']
        depth_2_df = df[(df['depth'] == 2) & (df['path'].str.startswith(depth_1_path + '/'))]  
        for _, depth_2_row in depth_2_df.iterrows():
            print(f"  - {depth_2_row['title']}")
            depth_3_df = df[(df['depth'] == 3) & (df['path'].str.startswith(depth_2_row['path'] + '/'))]
            for _, depth_3_row in depth_3_df.iterrows():
                hl = depth_3_row['hierarchy_level']
                print(f"    - {depth_3_row['title']} [{hl}]")
                if hl == 2:
                    depth_4_df = df[(df['depth'] == 4) & (df['path'].str.startswith(depth_3_row['path'] + '/'))]
                    for _, depth_4_row in depth_4_df.iterrows():
                        print(f"      - {depth_4_row['title']} [{depth_4_row['hierarchy_level']}]")
                        depth_5_df = df[(df['depth'] == 5) & (df['path'].str.startswith(depth_4_row['path'] + '/'))]
                        for _, depth_5_row in depth_5_df.iterrows():
                            print(f"        - {depth_5_row['title']} [{depth_5_row['hierarchy_level']}]")
                elif hl == 1:
                    depth_4_df = df[(df['depth'] == 4) & (df['path'].str.startswith(depth_3_row['path'] + '/'))]
                    for _, depth_4_row in depth_4_df.iterrows():
                        print(f"      - {depth_4_row['title']} [{depth_4_row['hierarchy_level']}]")
        print("=" * 50)

    depth_counts = df['depth'].value_counts().sort_index()
    for depth, count in depth_counts.items():
        print(f"Depth {depth}: {count} entries")
    hierarchy_counts = df['hierarchy_level'].value_counts().sort_index()
    for level, count in hierarchy_counts.items():
        print(f"Level {level}: {count} entries")

if EMBED:
    tax_df_path = "ztest_tax_output/formatted_tax_data_embedded.csv"
    df = pd.read_csv(tax_df_path)
    filtered_depth_df = df[(df['depth'] == 1)]
    async def embed_content(sem: asyncio.Semaphore, row: pd.Series):
        async with sem:
            content = row['title']
            return await llm.openai_client_embedding_request(content)
    async def main_embed():
        sem = asyncio.Semaphore(500)
        tasks = [embed_content(sem, row) for _, row in filtered_depth_df.iterrows()]
        embeddings = await asyncio.gather(*tasks)
        return embeddings
    embeddings = asyncio.run(main_embed())
    embeddings_array = np.array(embeddings)

    cluster_labels, n_clusters, cluster_proximities = clustering.cluster_vectors(embeddings_array, method='kmeans', n_clusters=25)
    filtered_depth_df = filtered_depth_df.copy()
    filtered_depth_df['cluster'] = cluster_labels

    print("Clusters, Titles, and Proximities:")
    for cluster in range(n_clusters):
        print(f"\nCluster {cluster}:")
        cluster_titles = filtered_depth_df[filtered_depth_df['cluster'] == cluster]['title'].tolist()
        for title in cluster_titles:
            print(f"  - {title}")
        
        closest_clusters = clustering.get_closest_clusters(cluster, cluster_proximities, top_n=1)
        for close_cluster, distance in closest_clusters:
            print(f"    Cluster {close_cluster} (Distance: {distance:.4f}):")
            close_cluster_titles = filtered_depth_df[filtered_depth_df['cluster'] == close_cluster]['title'].tolist()
            for title in close_cluster_titles[:3]:  # Print only first 3 titles from each close cluster
                print(f"      - {title}")
            if len(close_cluster_titles) > 3:
                print(f"      ... and {len(close_cluster_titles) - 3} more")

if CLUSTER:
    tax_df_path = "ztest_tax_output/formatted_tax_data_embedded.csv"
    df = pd.read_csv(tax_df_path)
    filtered_df = df[(df['hierarchy_level'] == 0) & (df['embedding'].apply(lambda x: isinstance(x, str)))]
    filtered_df = filtered_df.copy()
    filtered_df['embedding'] = filtered_df['embedding'].apply(utils.strvec_to_numpy)
    filtered_df = filtered_df.dropna(subset=['embedding'])
    embedding_dim = len(filtered_df['embedding'].iloc[0])
    filtered_df = filtered_df[filtered_df['embedding'].apply(lambda x: len(x) == embedding_dim)]
    embeddings_array = np.array(filtered_df['embedding'].tolist())
    cluster_labels, n_clusters, cluster_proximities = clustering.cluster_vectors(embeddings_array, method='kmeans', n_clusters=446)

    filtered_df['cluster'] = cluster_labels

    for cluster in range(n_clusters):
        cluster_titles = filtered_df[filtered_df['cluster'] == cluster]['title'].tolist()
        print(f"Cluster {cluster}:")
        for title in cluster_titles:
            print(f"  - {title}")