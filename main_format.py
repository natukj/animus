import asyncio
import json
import os
import formatters, utils, llm
import pandas as pd
from tqdm.asyncio import tqdm_asyncio

def main():
    with open("/Users/jamesqxd/Documents/norgai-docs/TAX/parsed/final_aus_tax.json", "r") as f:
        tax_data = json.load(f)["contents"]
    processed_df = formatters.add_refs_to_contents(tax_data)
    output_dir = "ztest_tax_output"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "processed_tax_data.csv")
    processed_df.to_csv(output_file, index=False)
    
    print(f"Processed data saved to {output_file}")
    print(f"DataFrame shape: {processed_df.shape}")
    print("\nFirst few rows:")
    print(processed_df.head())

 
if __name__ == "__main__":
    main()

# create end items and their parents
tax_df_path = "ztest_tax_output/processed_tax_data.csv"

df = pd.read_csv(tax_df_path)

df['depth'] = df['path'].str.count('/')

def find_end_items(df):
    end_items = []
    all_paths = df['path'].tolist()
    
    for index, row in df.iterrows():
        current_path = row['path']
        is_parent = any(path.startswith(current_path + '/') for path in all_paths if path != current_path)
        
        if not is_parent:
            end_items.append(row)
    
    return pd.DataFrame(end_items)

def get_unique_parents(end_items_df):
    all_parents = set()
    for path in end_items_df['path']:
        parent_path = path.rsplit('/', 1)[0]  # Split at the last '/'
        all_parents.add(parent_path)
    return all_parents

async def main_trav():
    # specific_level_paths = df[df['depth'] == 11]['path'].tolist()

    # print("Top-level paths:")
    # for path in specific_level_paths:
    #     print(path)

    # print(f"\nTotal number of top-level paths: {len(specific_level_paths)}")

    depth_summary = df['depth'].value_counts().sort_index()
    for depth, count in depth_summary.items():
        print(f"Depth {depth}: {count} items")

    end_items_df = find_end_items(df)
    end_items_df.to_csv("ztest_tax_output/tax_end_items.csv", index=False)

    end_items_depth = end_items_df['depth'].value_counts().sort_index()
    print("\nDepth distribution of end items:")
    for depth, count in end_items_depth.items():
        print(f"Depth {depth}: {count} items")

    unique_parents = get_unique_parents(end_items_df)
    parents_df = df[df['path'].isin(unique_parents)]
    parents_df.to_csv("ztest_tax_output/tax_parents.csv", index=False)
    print("\nFirst few rows of end_items.csv:")
    print(end_items_df.head())

    print("\nFirst few rows of parent_items.csv:")
    print(parents_df.head())
EMBED = False
if EMBED:
    tax_df_path = "ztest_tax_output/processed_tax_data.csv"
    end_items_path = "ztest_tax_output/tax_end_items.csv"
    parents_path = "ztest_tax_output/tax_parents.csv"

    df = pd.read_csv(tax_df_path)
    df['depth'] = df['path'].str.count('/')
    items_df = pd.read_csv(end_items_path)
    parents_df = pd.read_csv(parents_path)

    SEM_MAX = 200

    async def embed_content(sem: int, row: pd.Series, col_name: str = 'content'):
        async with sem:
            content = row[col_name]
            return await llm.openai_client_embedding_request(content)

    async def main_embed():
        sem = asyncio.Semaphore(SEM_MAX)
        tasks = [embed_content(sem, row) for _, row in parents_df.iterrows()]
        embeddings = await tqdm_asyncio.gather(*tasks, desc="Creating embeddings")
        parents_df['embedding'] = embeddings
        parents_df.to_csv("ztest_tax_output/tax_parents_embedded.csv", index=False)

    asyncio.run(main_embed())

SEARCH = False
if SEARCH:
    end_items_path = "ztest_tax_output/tax_end_items.csv"
    tax_items_df = pd.read_csv(end_items_path)

    tax_parent_embedded_path = "ztest_tax_output/tax_parents_embedded.csv"
    tax_parent_embedded_df = pd.read_csv(tax_parent_embedded_path)
    tax_parent_embedded_df['embedding'] = tax_parent_embedded_df.embedding.apply(eval).apply(np.array)

    def print_matched_items(parent_path, items_df):
        matched_items = items_df[items_df['path'].str.startswith(parent_path)]
        if not matched_items.empty:
            utils.print_coloured(f"\nItems under '{parent_path}':", "blue")
            for _, item in matched_items.iterrows():
                utils.print_coloured(f"- {item['title']}", "green")
                utils.print_coloured(f"\t {item['references']}", "yellow")
        else:
            print(f"\nNo items found under '{parent_path}'")
    async def main_search():
        user_query = "What can I claim as a tax deduction as a PAYG employee?"
        res = await utils.df_semantic_search(tax_parent_embedded_df, user_query)
        for _, row in res.iterrows():
            print(f"\nParent: {row['title']}")
            print(f"Similarity: {row['similarities']:.4f}")
            print_matched_items(row['path'], tax_items_df)
    asyncio.run(main_search())