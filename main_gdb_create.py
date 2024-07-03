import os
import asyncio
import pandas as pd
import gdb
import warnings

async def main_create():
    df = pd.read_csv("ztest_tax_output/final3_formatted_tax_data_clustered.csv")
    uri = "neo4j://localhost:7687"
    user = "neo4j"
    password = os.environ.get("LOCAL_GDB_PW")
    
    builder = gdb.AsyncGraphDatabaseBuilder(uri, user, password)
    try:
        await builder.init()
        print("Connection successful")
        # await builder.clear_database()
        # print("Database cleared")
        doc_id = "AUS_INCOME_TAX"
        title = "Income Tax Assessment Act 1997"
        doc_tags = ["Income Tax", "Australia"]
        metadata = {
            "jurisdiction": "Australia",
            "year": 1997,
            "volumes": "1-10"
        }
        #await builder.build_document_graph_from_df(df, doc_id, title, doc_tags, metadata)
        await builder.create_vector_index("section_embedding", "Section", "embedding", dimensions=1536)
        print("section index created")
        await builder.create_vector_index("content_embedding", "Content", "embedding", dimensions=1536)
        print("content index created")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        await builder.close()

if __name__ == "__main__":
    warnings.filterwarnings("ignore", message="Exception ignored in.*StreamWriter.__del__")
    asyncio.run(main_create())