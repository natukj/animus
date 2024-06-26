import json
import asyncio
import llm, prompts, utils
import pandas as pd
import numpy as np
from tqdm.asyncio import tqdm_asyncio
from typing import List, Dict

SEARCH = False
RECURSIVE_SEARCH = False
ASK_CLAUDE = True
ASK_CLAUDE_Q = False
EMBED = False
REVERSE_HIERARCHY = False

def filter_and_structure_results(results: List[Dict]) -> Dict:
    filtered_results = {}
    for item in results:
        if item['hierarchy_level'] == 0:
            filtered_results[item['path']] = {
                'title': item['title'],
                'similarities': item['similarities'],
                'content': item['content']
            }
        if 'children' in item and item['children']:
            filtered_results.update(filter_and_structure_results(item['children']))
    return filtered_results

if ASK_CLAUDE_Q:
    user_query = "what are my possible personal tax deductions?"
    async def main_ask_claude_q():
        formatted_answer_prompt = prompts.REWRITE_USER_QUERY_CLAUDE.format(query=user_query)
        messages = [{"role": "user", "content": formatted_answer_prompt}]
        while True:
            result = await llm.claude_client_chat_completion_request(messages)
            utils.print_coloured(result, "yellow")
            claude_thinking_answer = utils.extract_between_tags("thinking", result, strip=True)
            utils.print_coloured(claude_thinking_answer, "cyan")
            claude_additional_info = utils.extract_between_tags("additional_info", result, strip=True)
            if claude_additional_info:
                utils.print_coloured(claude_additional_info, "magenta")
                user_additional_info = input("Enter additional information: ")
                messages.append({"role": "assistant", "content": result})
                messages.append({"role": "user", "content": user_additional_info})
            else:
                claude_answer = utils.extract_between_tags("answer", result, strip=True)
                utils.print_coloured(claude_answer, "green")
                break
    asyncio.run(main_ask_claude_q())
        
if RECURSIVE_SEARCH:
    tax_embedded_path = "ztest_tax_output/tax_data_embedded.csv"
    tax_embedded_df = pd.read_csv(tax_embedded_path)
    tax_embedded_df['embedding'] = tax_embedded_df.embedding.apply(eval).apply(np.array)
    query = "comprehensive allowable deductions individuals Tax Income Assessment Act 1997 Australian personal tax complete list claimable expenses"
    def print_tree(node, level=0):
        print(f"{'    ' * level}- {node['title']} (Similarity: {node['similarities']:.4f})")
        for child in node.get('children', []):
            print_tree(child, level + 1)
    async def main_recursive_search():      
        hierarchical_results = await utils.df_recursive_semantic_search(tax_embedded_df, query, start_level=4, top_n=5)
        filtered_results = filter_and_structure_results(hierarchical_results)
        total_content_tokens = 0
        for value in filtered_results.values():
            content_tokens = utils.count_tokens(value['content'])
            total_content_tokens += content_tokens
        with open("ztest_tax_output/recursive_search_results.json", "w") as f:
            json.dump(filtered_results, f, indent=4)
        for result in hierarchical_results:
            print_tree(result)
        print(f"Total content tokens: {total_content_tokens} from {len(filtered_results)} items")
    asyncio.run(main_recursive_search())

if ASK_CLAUDE:
    query = "what are my possible personal tax deductions?"
    with open("ztest_tax_output/recursive_search_results.json",'r') as f:
        recursive_search_results = json.load(f)
    doc_content = ""
    for key, value in recursive_search_results.items():
        doc_content += f"Path: {key}\n\n{value['content']}\n\n"
    async def main_ask_claude():
        formatted_answer_prompt = prompts.TRAVERSAL_USER_ANSWER_CLAUDE.format(query=query, doc_content=doc_content)
        print(utils.count_tokens(formatted_answer_prompt))
        messages = [{"role": "user", "content": formatted_answer_prompt}]
        result = await llm.claude_client_chat_completion_request(messages)
        utils.print_coloured(result, "yellow")
        claude_thinking_answer = utils.extract_between_tags("thinking", result, strip=True)
        utils.print_coloured(claude_thinking_answer, "cyan")
        claude_answer = utils.extract_between_tags("answer", result, strip=True)
        utils.print_coloured(claude_answer, "green")
    asyncio.run(main_ask_claude())

if SEARCH:
    tax_embedded_path = "ztest_tax_output/tax_data_embedded.csv"
    tax_embedded_df = pd.read_csv(tax_embedded_path)
    tax_embedded_df['embedding'] = tax_embedded_df.embedding.apply(eval).apply(np.array)

    def print_children(parent_path, items_df):
        matched_items = items_df[items_df['path'].str.startswith(parent_path)]
        if not matched_items.empty:
            for _, item in matched_items.iterrows():
                utils.print_coloured(f"- {item['title']}", "green")
                #utils.print_coloured(f"\t {item['references']}", "yellow")
        else:
            print(f"\nNo items found under '{parent_path}'")
    async def main_search():
        while True:
            user_query = input("\nEnter your query: ")
            if user_query == "q":
                break
            hierarchy_level = int(input("Enter hierarchy level (0 is bottom, -1 is all): "))
            if hierarchy_level == -1:
                filtered_df = tax_embedded_df
            else:
                filtered_df = utils.filter_embedded_df_by_hierarchy(tax_embedded_df, hierarchy_level)
            res = await utils.df_semantic_search(filtered_df, user_query, top_n=7)
            for _, row in res.iterrows():
                utils.print_coloured(f"{row['path']}", "blue")
                utils.print_coloured(f"{row['title']}({row['similarities']:.4f})", "green")
                # if hierarchy_level > 0:
                #     print_children(row['path'], tax_embedded_df)
    asyncio.run(main_search())

if EMBED:
    SEM_MAX = 1000
    tax_df_path = "ztest_tax_output/tax_data_with_hierarchy.csv"
    df = pd.read_csv(tax_df_path)
    print(f"embedding {len(df)} items...")
    async def embed_content(sem: asyncio.Semaphore, row: pd.Series):
        async with sem:
            if utils.count_tokens(row['content']) > 8000:
                content = row['title']
            else:
                content = row['content']
            return await llm.openai_client_embedding_request(content)

    async def main_embed():
        sem = asyncio.Semaphore(SEM_MAX)
        tasks = [embed_content(sem, row) for _, row in df.iterrows()]
        embeddings = await tqdm_asyncio.gather(*tasks, desc="Creating embeddings")
        df['embedding'] = embeddings
        print(f"Saving {len(embeddings)} embeddings to CSV...")
        df.to_csv("ztest_tax_output/tax_data_embedded.csv", index=False)
        print("Done!")
    asyncio.run(main_embed())

if REVERSE_HIERARCHY:
    tax_df_path = "ztest_tax_output/processed_tax_data.csv"
    df = pd.read_csv(tax_df_path)
    df['depth'] = df['path'].str.count('/')
    df_w_hierarchy = utils.add_reverse_hierarchy(df)
    df_w_hierarchy.to_csv("ztest_tax_output/tax_data_with_hierarchy.csv", index=False)

    hierarchy_summary = df_w_hierarchy['hierarchy_level'].value_counts().sort_index()
    print("\nHierarchy level distribution:")
    for level, count in hierarchy_summary.items():
        print(f"Level {level}: {count} items")
        

