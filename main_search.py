import json
import asyncio
import llm, prompts, utils, clustering
import pandas as pd
import numpy as np
from tqdm.asyncio import tqdm_asyncio
from tqdm import tqdm
import ast

SEARCH = True
if SEARCH:
    df = pd.read_csv("ztest_tax_output/final_formatted_tax_data_clustered.csv")
    df['embedding'] = df['embedding'].apply(utils.strvec_to_numpy)
    
    async def main_search():
        d_df = df[df['depth'].isin([0, 1])]
        hl_df = df[df['hierarchy_level'] == 0]
        
        while True:
            user_query = input("\nEnter your query: ")
            if user_query.lower() == "q":
                break
            
            embedding = await llm.openai_client_embedding_request(user_query)
            res = await utils.df_semantic_search(d_df, np.array(embedding), top_n=2)
            seen_clusters = set()
            seen_content_paths = set()
            content_str = ""
            for _, row in res.iterrows():
                path = row['path']
                d_cluster = row['d_cluster']
                utils.print_coloured(f"{path} [{d_cluster}] ({row['similarities']:.4f})", "yellow")
                
                path_df = hl_df[hl_df['path'].str.startswith(tuple(d_df[d_df['d_cluster'] == d_cluster]['path']))]
                res_hl = await utils.df_semantic_search(path_df, np.array(embedding), top_n=10)
                for _, row_hl in res_hl.iterrows():
                    hl_cluster = row_hl['hl_cluster']
                    if hl_cluster not in seen_clusters:
                        seen_clusters.add(hl_cluster)
                        cluster_rows = path_df[path_df['hl_cluster'] == hl_cluster]
                        total_tokens = 0
                        # TODO: maybe use hl_df>path_df and rerank cluster rows to limit the amount of content
                        for i, (_, cluster_row) in enumerate(cluster_rows.iterrows(), 1):
                            content_tokens = utils.count_tokens(cluster_row['content'])
                            total_tokens += content_tokens
                            if cluster_row['path'] in seen_content_paths:
                                continue
                            content_str += cluster_row['path'] + "\n"
                            seen_content_paths.add(cluster_row['path'])
                            content_str += cluster_row['content'] + "\n\n"
                            
                            if 'references' in cluster_row and 'self_ref' in hl_df.columns:
                                refs = ast.literal_eval(cluster_row['references'])
                                item_refs = [item for item in hl_df['self_ref'] if item in refs]
                                if item_refs:
                                    content_str += "Referenced Items:\n"
                                    for ref in item_refs:
                                        ref_row = hl_df[hl_df['self_ref'] == ref].iloc[0]
                                        ref_tokens = utils.count_tokens(ref_row['content'])
                                        if ref_tokens <= 8000:
                                            total_tokens += ref_tokens
                                            if ref_row['path'] in seen_content_paths:
                                                continue
                                            content_str += f"- {ref_row['path']}\n"
                                            seen_content_paths.add(ref_row['path'])
                                            content_str += f"\t{ref_row['content']}\n\n"

                        utils.print_coloured(f"Total Tokens for Cluster {hl_cluster}: {total_tokens}", "red")
            formatted_answer_prompt = prompts.TRAVERSAL_USER_ANSWER_REFS_CLAUDE.format(query=user_query, doc_content=content_str)
            utils.print_coloured(utils.count_tokens(formatted_answer_prompt), "yellow")
            utils.is_correct()
            messages = [{"role": "user", "content": formatted_answer_prompt}]
            result = await llm.claude_client_chat_completion_request(messages)
            claude_thinking_answer = utils.extract_between_tags("thinking", result, strip=True)
            utils.print_coloured(claude_thinking_answer, "cyan")
            claude_refs = utils.extract_between_tags("references", result, strip=True)
            utils.print_coloured(claude_refs, "yellow")
            claude_answer = utils.extract_between_tags("answer", result, strip=True)
            utils.print_coloured(claude_answer, "green")
            if claude_refs:
                refs_dict = json.loads(claude_refs)
                for key, ref in refs_dict.items():
                    utils.print_coloured(f"{key} -> {ref}", "magenta")
                    ref_row = hl_df[hl_df['self_ref'] == ref].iloc[0]
                    utils.print_coloured(ref_row['path'], "blue")
                    utils.print_coloured(ref_row['content'], "green")
                    


    asyncio.run(main_search())
