import json
import asyncio
import llm, prompts, utils
import pandas as pd
import numpy as np
from tqdm.asyncio import tqdm_asyncio
import ast

SEARCH = True
if SEARCH:
    tax_df_path = "ztest_tax_output/formatted_tax_data_embedded.csv"
    df = pd.read_csv(tax_df_path)
    filtered_df = df[(df['hierarchy_level'] == 0) & (df['embedding'].apply(lambda x: isinstance(x, str)))]
    def safe_eval_to_numpy(x):
        try:
            return np.array(ast.literal_eval(x))
        except (ValueError, SyntaxError):
            print(f"Error processing embedding...")
            return None
    filtered_df = filtered_df.copy()
    filtered_df['embedding'] = filtered_df['embedding'].apply(safe_eval_to_numpy)
    filtered_df = filtered_df.dropna(subset=['embedding'])
    SYS_PROMPT = "You are a tax expert. You must determine whether the following information is relevant to the user's query: '{query}'. If it is relevant, output 'True'. If it is not relevant, output 'False'."
    semaphore = asyncio.Semaphore(30)
    
    async def main_search():
        async def process_item(content):
            async with semaphore:
                messages = [
                    {"role": "system", "content": SYS_PROMPT.format(query=user_query)},
                    {"role": "user", "content": content}
                ]
                response = await llm.groq_client_chat_completion_request(messages)
                return response.choices[0].message.content
        while True:
            user_query = input("\nEnter your query: ")
            if user_query == "q":
                break
            res = await utils.df_semantic_search(filtered_df, user_query, top_n=100)
            docs_content = [row['content'] for _,row in res.iterrows()]
            #reranking on content seems to work better than summary
            rerank_content = await llm.rerank_documents(user_query, docs_content, 30)
            for i, item in enumerate(rerank_content['results']):
                original_index = item['index']
                row = res.iloc[original_index]
                utils.print_coloured(f"Rerank {i+1} from {original_index}", "blue")
                utils.print_coloured(row['path'], "blue")
                utils.print_coloured(f"Title: {row['title']}", "green")
                refs = ast.literal_eval(row['references'])
                item_refs = [item for item in filtered_df['self_ref'] if item in refs]
                if item_refs:
                    utils.print_coloured("Referenced Items:", "yellow")
                    for ref in item_refs:
                        ref_title = filtered_df[filtered_df['self_ref'] == ref]['title'].values
                        if len(ref_title) > 0:
                            print(f"- {ref_title[0]}")
                else:
                    utils.print_coloured("No references found", "yellow")
                print("-" * 50)
            #instead of groq checking, need to add agent to check if content is relevant and the content references to return all relevant content
            tasks = [process_item(docs_content[item['index']]) for item in rerank_content['results']]
            results = await asyncio.gather(*tasks)
            filtered_content = [docs_content[item['index']] for item, result in zip(rerank_content['results'], results) if "true" in result.lower()]
            utils.print_coloured(f"Filtered content: {len(filtered_content)}/30", "magenta")
            filtered_content_str = "\n\n".join(filtered_content)
            formatted_answer_prompt = prompts.TRAVERSAL_USER_ANSWER_CLAUDE.format(query=user_query, doc_content=filtered_content_str)
            messages = [{"role": "user", "content": formatted_answer_prompt}]
            result = await llm.claude_client_chat_completion_request(messages)
            #utils.print_coloured(result, "yellow")
            claude_thinking_answer = utils.extract_between_tags("thinking", result, strip=True)
            utils.print_coloured(claude_thinking_answer, "cyan")
            claude_answer = utils.extract_between_tags("answer", result, strip=True)
            utils.print_coloured(claude_answer, "green")
 
    asyncio.run(main_search())