import json
import asyncio
import llm, prompts, utils
import pandas as pd
import numpy as np
from tqdm.asyncio import tqdm_asyncio

EMBED = False
EMBED_ALL = True

if EMBED_ALL:
    SEM_MAX = 1000
    tax_df_path = "ztest_tax_output/formatted_tax_data_embedded.csv"
    df = pd.read_csv(tax_df_path)
    print(f"Found {len(df)} entries in CSV.")
    count = [0]
    async def embed_content(sem: asyncio.Semaphore, row: pd.Series):
        async with sem:
            if pd.isna(row['embedding']):
                content = row['title']
                count[0] += 1 
                return await llm.openai_client_embedding_request(content)
            else:
                return row['embedding'] 
    async def main_embed():
        sem = asyncio.Semaphore(SEM_MAX)
        tasks = [embed_content(sem, row) for _, row in df.iterrows()]
        embeddings = await tqdm_asyncio.gather(*tasks, desc="Creating embeddings")
        df['embedding'] = embeddings
        print(f"Added {count[0]} embeddings for a total of {len(embeddings)} embeddings to CSV...")
        df.to_csv("ztest_tax_output/all_formatted_tax_data_embedded.csv", index=False)
        print("Done!")
    asyncio.run(main_embed())

if EMBED:
    SEM_MAX = 1000
    tax_df_path = "ztest_tax_output/formatted_tax_data_with_hierarchy.csv"
    df = pd.read_csv(tax_df_path)
    async def embed_content(sem: asyncio.Semaphore, row: pd.Series):
        async with sem:
            if row['hierarchy_level'] == 0:
                if utils.count_tokens(row['content']) > 8000:
                    print(f"Content too long for {row['path']}. Skipping formatting.")
                    return ""
                if row['summary']:
                    return await llm.openai_client_embedding_request(row['summary'])
                else:
                    utils.print_coloured(f"Summary not found for {row['path']}. Skipping formatting.", "red")
                    return ""
            else:
                return ""       
    async def main_embed():
        sem = asyncio.Semaphore(SEM_MAX)
        tasks = [embed_content(sem, row) for _, row in df.iterrows()]
        embeddings = await tqdm_asyncio.gather(*tasks, desc="Creating embeddings")
        df['embedding'] = embeddings
        print(f"Saving {len(embeddings)} embeddings to CSV...")
        df.to_csv("ztest_tax_output/formatted_tax_data_embedded.csv", index=False)
        print("Done!")
    asyncio.run(main_embed())