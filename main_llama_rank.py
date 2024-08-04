import os
import asyncio
import argparse
import json
import time
import gdb, llm, prompts, utils

async def main():
    uri = "neo4j://localhost:7687"
    user = "neo4j"
    password = os.environ.get("LOCAL_GDB_PW")
    search = gdb.Neo4jSearch(uri, user, password)
    doc_id = "aus_income_tax_1997"
    try:
        user_query = input("Enter a query: ")
        start_time = time.time()
        embedding = await llm.openai_client_embedding_request(user_query)
        all_docs = search.tree(doc_id, embedding, top_k=20, return_refs=True)
        num_all_docs = len(all_docs)
        relevant_docs = await llm.llama_rank_docs(user_query, all_docs, model="llama3-8b-8192")
        num_relevant_docs = len(relevant_docs)
        utils.print_coloured(f"Number of relevant docs: {num_relevant_docs}/{num_all_docs}", "green")
        print(f"Time taken: {time.time() - start_time:.2f}s")
        print("Relevant documents:")
        print(json.dumps(relevant_docs, indent=4))
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        search.close()

if __name__ == "__main__":
    asyncio.run(main())
            