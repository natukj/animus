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
    search.print_duplicate_nodes()
    # to skip: What this Division is about, Effect of this Division

if __name__ == "__main__":
    asyncio.run(main())