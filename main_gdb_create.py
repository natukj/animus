import os
import asyncio
import pandas as pd
import gdb, utils
import warnings

csv_path = os.environ.get("CSV_PATH", "")
ma_dir = os.environ.get("OUTPUT_PATH", "")

def main_create():
    uri = "neo4j://localhost:7687"
    user = "neo4j"
    password = os.environ.get("LOCAL_GDB_PW")
    csv_files = [f for f in os.listdir(ma_dir) if f.endswith('.csv')]
    for csv_file in csv_files:
        input_path = os.path.join(ma_dir, csv_file)
        doc_id = os.path.splitext(os.path.basename(input_path))[0].split('-')[0]
        doc_title = os.path.splitext(os.path.basename(input_path))[0].split('-')[1]
        df = pd.read_csv(input_path)
        builder = gdb.GraphDatabaseBuilder(uri, user, password)
        print(f"Processing: {doc_id} (The {doc_title} Award)")
        try:
            title = f"The {doc_title} Award"
            doc_tags = ["Award", "Australia"]
            metadata = {
                "jurisdiction": "Australia",
                "year": 2023,
                "volumes": "1"
            }
            builder.build_document_graph_from_df(df, doc_id, title, doc_tags, metadata)
            print(f"Finished: {doc_id}")
        except Exception as e:
            print(f"An error occurred: {str(e)}")
        

# def main_create():
#     df = pd.read_csv(csv_path)
#     uri = "neo4j://localhost:7687"
#     user = "neo4j"
#     password = os.environ.get("LOCAL_GDB_PW")
    
#     builder = gdb.GraphDatabaseBuilder(uri, user, password)
#     try:
#         doc_id = "gnu_c_2023"
#         title = "The GNU C Library Reference Manual"
#         doc_tags = ["GNU C", "C Library", "Reference Manual"]
#         metadata = {
#             "jurisdiction": "GNU",
#             "year": 2023,
#             "volumes": "2.38"
#         }
#         builder.build_document_graph_from_df(df, doc_id, title, doc_tags, metadata)

#     except Exception as e:
#         print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    warnings.filterwarnings("ignore", message="Exception ignored in.*StreamWriter.__del__")
    main_create()

# def main_create():
#     df = pd.read_csv("ztest_tax_output/final4_formatted_tax_data_clustered_updated.csv")
#     # df['embedding'] = df['embedding'].apply(utils.strvec_to_numpy)
#     uri = "neo4j://localhost:7687"
#     user = "neo4j"
#     password = os.environ.get("LOCAL_GDB_PW")
    
#     builder = gdb.GraphDatabaseBuilder(uri, user, password)
#     try:
#         doc_id = "aus_income_tax_1997"
#         title = "Income Tax Assessment Act 1997"
#         doc_tags = ["Income Tax", "Australia"]
#         metadata = {
#             "jurisdiction": "Australia",
#             "year": 1997,
#             "volumes": "1-10"
#         }
#         builder.build_document_graph_from_df(df, doc_id, title, doc_tags, metadata)

#     except Exception as e:
#         print(f"An error occurred: {str(e)}")

# if __name__ == "__main__":
#     warnings.filterwarnings("ignore", message="Exception ignored in.*StreamWriter.__del__")
#     main_create()