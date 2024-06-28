import asyncio
import json
import os
import formatters, utils, llm
import pandas as pd
from tqdm.asyncio import tqdm_asyncio

CODE_FIX = False
if CODE_FIX:
    # FIX DEPTH AND HIERARCHY FUCK UP
    def main():
        with open("/Users/jamesqxd/Documents/norgai-docs/TAX/parsed/final_aus_tax.json", "r") as f:
            tax_data = json.load(f)["contents"]
        depth_hierarchy_data = utils.calculate_depths_and_hierarchy(tax_data)
        depth_hierarchy_df = pd.DataFrame(depth_hierarchy_data)

        # calculate the hierarchy_level as the maximum depth of its descendants minus its own depth
        depth_hierarchy_df['hierarchy_level'] = depth_hierarchy_df.apply(
            lambda row: 0 if not row['has_children'] else depth_hierarchy_df[depth_hierarchy_df['path'].str.startswith(row['path'] + '/')]['depth'].max() - row['depth'],
            axis=1
        )
        existing_df = pd.read_csv("ztest_tax_output/all_formatted_tax_data_embedded.csv")

        depth_dict = dict(zip(depth_hierarchy_df['path'], depth_hierarchy_df['depth']))
        hierarchy_dict = dict(zip(depth_hierarchy_df['path'], depth_hierarchy_df['hierarchy_level']))
        existing_df['depth'] = existing_df['path'].map(depth_dict)
        existing_df['hierarchy_level'] = existing_df['path'].map(hierarchy_dict)

        existing_df.to_csv("ztest_tax_output/all_formatted_tax_data_embedded_depth.csv", index=False)

    if __name__ == "__main__":
        main()

FORMAT = False
if FORMAT:
    SEM_MAX = 200
    tax_df_path = "ztest_tax_output/tax_data_with_hierarchy.csv"
    df = pd.read_csv(tax_df_path)
    async def format_content(sem: asyncio.Semaphore, row: pd.Series):
        async with sem:
            if row['hierarchy_level'] == 0:
                if utils.count_tokens(row['content']) > 8000:
                    print(f"Content too long for {row['path']}. Skipping formatting.")
                    return row['content'], ""
                else:
                    gpt_formatted_content, gpt_summary = await formatters.format_content_plus_summary_gpt(row['content'], row['path'])
                    return gpt_formatted_content, gpt_summary
            else:
                return row['content'], ""
    async def main_format():
        sem = asyncio.Semaphore(SEM_MAX)
        tasks = [format_content(sem, row) for _, row in df.iterrows()]
        results = await tqdm_asyncio.gather(*tasks, desc="Formatting...")
        df['content'], df['summary'] = zip(*results)
        df.to_csv("ztest_tax_output/formatted_tax_data_with_hierarchy.csv", index=False)
    asyncio.run(main_format())

REFORMAT = True
if REFORMAT:
    summary_prompt = """Please return a summary of the following item content, from the Tax Income Assesment Act 1997, within the context of what user queries the content would aid in answering. This summary should only consist of questions that the content would help answer, and should be formatted as a single paragraph. Make sure to use the path as context when generating the summary and do not include any specific references or section numbers.

    Item Path: {path}

    Item Content:

    {content}

    You must output a JSON object with the following structure:

    {{
        "summary": "string (Your summary of the item content here)"
    }}

    KEEP THE SUMMARY SHORT AND TO THE POINT.
    """
    tax_df_path = "ztest_tax_output/formatted_tax_data_with_hierarchy.csv"
    df = pd.read_csv(tax_df_path)
    async def reformat_content():
        changes_made = False
        for index, row in df.iterrows():
            should_summarize = (utils.count_tokens(row['content']) > 4000 and utils.count_tokens(row['content']) < 8000) or \
                                (row['path'] == "Chapter 3 Specialist liability rules/Part 3-3 Capital gains and losses: special topics/Division 130 Investments/Subdivision 130-A Bonus shares and units/Subdivision 130-F Exploration investments/130-110 Reducing the reduced cost base before disposal")
            
            if should_summarize and pd.isna(row['summary']):
                max_retries = 3
                for _ in range(max_retries):
                    try:
                        messages = [
                            {"role": "system", "content": "You are an AI assistant skilled in formatting legal documents as a JSON object."},
                            {"role": "user", "content": summary_prompt.format(path=row['path'], content=row['content'])}
                        ]
                        result = await llm.openai_client_chat_completion_request(messages)
                        result_str = result.choices[0].message.content
                        formatted_result = json.loads(result_str)
                        summary = formatted_result["summary"]
                        if summary:
                            df.at[index, 'summary'] = summary
                            changes_made = True
                            utils.print_coloured(f"Added summary for: {row['path']}", "green")
                        break
                    except json.JSONDecodeError:
                        utils.print_coloured(f"Error decoding JSON response: {result_str}", "red")
                    except Exception as e:
                        utils.print_coloured(f"Error processing row: {e}", "red")
                else:
                    utils.print_coloured(f"Failed to add summary after {max_retries} attempts for: {row['path']}", "red")
        
        if changes_made:
            df.to_csv(tax_df_path, index=False)
            utils.print_coloured("Changes saved to CSV file.", "green")
        else:
            utils.print_coloured("No changes were made to the CSV file.", "yellow")
    asyncio.run(reformat_content())
            

CODE = False
if CODE:
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
#### CRAP BELOW ####
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