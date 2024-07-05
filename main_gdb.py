import os
import asyncio
import argparse
import json
import time
import gdb, llm, prompts, utils

async def process_query(user_query, doc_id, search, use_cluster=True, use_reranking=True):
    embedding = await llm.openai_client_embedding_request(user_query)
    if use_cluster:
        results = search.tree_cluster(doc_id, embedding)
    else:
        results = search.tree(doc_id, embedding)
    print(f"Total results: {len(results)}")

    formatted_final_result = ""
    processed_ids = set()

    if use_reranking:
        results_dict = {result['content']: result for result in results}
        docs_with_ids = [(result['content'], result['id']) for result in results]
        docs_content = [doc[0] for doc in docs_with_ids]
        rerank_content = await llm.rerank_documents(user_query, docs_content, len(results))

        print("Top reranked results:")
        reranked_num = 0
        for i, item in enumerate(rerank_content['results']):
            relevance_score = item['relevance_score']
            if relevance_score >= 0.08:
                reranked_num += 1
                original_index = item['index']
                original_content = docs_content[original_index]
                original_result = results_dict[original_content]
                
                formatted_final_result += format_result(original_result, doc_id, processed_ids)
                if utils.count_tokens(formatted_final_result) > 80000 or i >= 20:
                    utils.print_coloured(f"breaking at {i+1} reranked results with token count {utils.count_tokens(formatted_final_result)}", "yellow")
                    break
            else:
                break
        print(f"Reranked results: {reranked_num}")
    else:
        for i, result in enumerate(results):
            formatted_final_result += format_result(result, doc_id, processed_ids)
            if utils.count_tokens(formatted_final_result) > 80000 or i >= 20:
                    utils.print_coloured(f"breaking at {i+1} results with token count {utils.count_tokens(formatted_final_result)}", "yellow")
                    break
    return formatted_final_result


async def process_query_branch(user_query, doc_id, search, use_cluster=True, use_reranking=True):
    embedding = await llm.openai_client_embedding_request(user_query)
    if use_cluster:
        results = search.tree_cluster_branch(doc_id, embedding)
    else:
        results = search.tree_branch(doc_id, embedding)
    print(f"Total branches: {len(results)}")

    formatted_branches = {}

    if use_reranking:
        for branch_id, branch_results in results.items():
            results_dict = {result['content']: result for result in branch_results}
            docs_with_ids = [(result['content'], result['id']) for result in branch_results]
            docs_content = [doc[0] for doc in docs_with_ids]
            rerank_content = await llm.rerank_documents(user_query, docs_content, len(branch_results))

            formatted_branch = ""
            processed_ids = set()
            reranked_num = 0

            print(f"Reranking branch {branch_id}:")
            for i, item in enumerate(rerank_content['results']):
                relevance_score = item['relevance_score']
                if relevance_score >= 0.08:
                    reranked_num += 1
                    original_index = item['index']
                    original_content = docs_content[original_index]
                    original_result = results_dict[original_content]
                    
                    formatted_branch += format_result(original_result, doc_id, processed_ids)
                    if utils.count_tokens(formatted_branch) > 80000:
                        break
                else:
                    break
            print(f"Reranked results in branch {branch_id}: {reranked_num}")
            formatted_branches[branch_id] = formatted_branch
    else:
        for branch_id, branch_results in results.items():
            formatted_branch = ""
            processed_ids = set()
            for result in branch_results:
                formatted_branch += format_result(result, doc_id, processed_ids)
                if utils.count_tokens(formatted_branch) > 80000:
                    break
            formatted_branches[branch_id] = formatted_branch

    return formatted_branches

def format_result(result, doc_id, processed_ids):
    formatted_result = ""
    result_id = result['id']
    if result_id not in processed_ids:
        processed_ids.add(result_id)
        stripped_id = result_id.replace(f"{doc_id}||", "")
        print(f"{result['title']} ({result['self_ref']} [{result['score']:.2f}])")
        formatted_result += f"{stripped_id} (ref: {result['self_ref']})\n"
        formatted_result += f"{result.get('content', 'N/A')}\n"
        
        references = result.get('references', [])
        if references:
            formatted_result += "References:\n"
            for ref in references:
                ref_id = ref.get('id')
                if ref_id and ref_id not in processed_ids and '995' not in ref_id:
                    processed_ids.add(ref_id)
                    ref_id = ref_id.replace(f"{doc_id}||", "")
                    print(f"  - {ref.get('title', 'N/A')} ({ref['self_ref']})")
                    formatted_result += f"  - {ref_id} (ref: {ref['self_ref']}):\n"
                    formatted_result += f"    {ref.get('content', 'N/A')}\n"
        
        formatted_result += "\n"
    return formatted_result

async def process_branch(branch_id, content, user_query):
    formatted_answer_prompt = prompts.TRAVERSAL_USER_ANSWER_REFS_GPT.format(query=user_query, doc_content=content)
    utils.print_coloured(f"Branch {branch_id} token count: {utils.count_tokens(formatted_answer_prompt)}", "blue")
    
    if utils.count_tokens(formatted_answer_prompt) > 80000:
        utils.print_coloured(f"Branch {branch_id} token count exceeds 100,000. Truncating...", "yellow")
        utils.is_correct()

    messages = [{"role": "system", "content": prompts.TRAVERSAL_USER_ANSWER_REFS_GPT_SYS}, 
                {"role": "user", "content": formatted_answer_prompt}]
    response = await llm.openai_client_chat_completion_request(messages)
    return branch_id, response.choices[0].message.content

async def main():
    parser = argparse.ArgumentParser(description="Process a query using Neo4j and GPT.")
    parser.add_argument("query", type=str, help="The user query to process.")
    parser.add_argument("--method", choices=["query", "branch"], default="query", help="Processing method: 'query' or 'branch'")
    parser.add_argument("--use-cluster", action="store_true", help="Use clustering in branch method")
    parser.add_argument("--use-reranking", action="store_true", help="Use reranking")
    args = parser.parse_args()

    uri = "neo4j://localhost:7687"
    user = "neo4j"
    password = os.environ.get("LOCAL_GDB_PW")
    search = gdb.Neo4jSearch(uri, user, password)
    
    try:
        doc_id = "aus_income_tax_1997"
        start_time = time.time()

        if args.method == "query":
            formatted_result = await process_query(args.query, doc_id, search, args.use_cluster, use_reranking=args.use_reranking)
            formatted_answer_prompt = prompts.TRAVERSAL_USER_ANSWER_REFS_GPT.format(query=args.query, doc_content=formatted_result)
            utils.print_coloured(f"Token count: {utils.count_tokens(formatted_answer_prompt)}", "blue")
            
            utils.is_correct()

            messages = [{"role": "system", "content": prompts.TRAVERSAL_USER_ANSWER_REFS_GPT_SYS}, 
                        {"role": "user", "content": formatted_answer_prompt}]
            response = await llm.openai_client_chat_completion_request(messages)
            responses = [("main", response.choices[0].message.content)]
        else:  # branch method not that good
            formatted_branches = await process_query_branch(args.query, doc_id, search, use_cluster=args.use_cluster, use_reranking=args.use_reranking)
            tasks = [process_branch(branch_id, content, args.query) for branch_id, content in formatted_branches.items()]
            responses = await asyncio.gather(*tasks)

        print(f"Time taken: {time.time() - start_time:.2f}s")

        for branch_id, response_str in responses:
            utils.print_coloured(f"Response for branch {branch_id}:", "cyan")
            try:
                response_dict = json.loads(response_str)
                response_answer = response_dict['answer']
                response_refs = response_dict['references']
                utils.print_coloured(response_answer, "green")
                utils.print_coloured(response_refs, "yellow")
            except json.JSONDecodeError:
                utils.print_coloured(response_str, "red")
            print("\n" + "="*50 + "\n")

    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        search.close()

if __name__ == "__main__":
    asyncio.run(main())