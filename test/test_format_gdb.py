import pandas as pd
from tqdm import tqdm
import ast
import logging
logging.basicConfig(level=logging.INFO)

def add_parent_path(df):
    # Create a dictionary to store paths by their depths
    paths_by_depth = {depth: {} for depth in df['depth'].unique()}

    # Populate the dictionary with paths
    for index, row in df.iterrows():
        paths_by_depth[row['depth']][row['path']] = index

    # Create an empty list to store the parent paths
    parent_paths = [None] * len(df)

    # Iterate through each row in the DataFrame with tqdm for progress visualization
    for index, row in tqdm(df.iterrows(), total=len(df), desc="Processing paths"):
        current_path = row['path']
        current_depth = row['depth']

        # Skip rows where depth is 0
        if current_depth == 0:
            continue

        # Look for potential parent paths in the dictionary
        parent_depth = current_depth - 1
        potential_parents = paths_by_depth.get(parent_depth, {})

        # Find the correct parent path
        found_parent = False
        for potential_parent_path in potential_parents:
            if current_path.startswith(potential_parent_path):
                parent_paths[index] = potential_parent_path
                found_parent = True
                break

        # Print out if no parent path is found
        if not found_parent:
            print(f"No parent path found for: {current_path}")

    # Add the parent paths to the DataFrame
    df['parent_path'] = parent_paths

    return df

def sample_paths(df, num_samples=20):
    sample_df = df.sample(n=num_samples)
    for _, row in sample_df.iterrows():
        print(f"Path: {row['path']}")
        print(f"Parent Path: {row['parent_path']}")
        print()
def check_parent_paths(df):
    # List to store paths without a parent path
    no_parent_paths = df[df['parent_path'].isna()]['path'].tolist()

    # Print all paths without a parent path
    if no_parent_paths:
        print("Paths without parent paths:")
        for path in no_parent_paths:
            print(path)
    else:
        print("All paths have parent paths.")
def check_unique_self_ref(df):
    # Filter rows where hierarchy_level == 0
    df_hl_0 = df[df['hierarchy_level'] == 0]

    # Check for duplicates in the 'self_ref' column
    duplicates = df_hl_0[df_hl_0.duplicated('self_ref', keep=False)]

    # Print the duplicate self_refs
    if not duplicates.empty:
        print("Duplicate self_refs found:")
        print(duplicates[['self_ref', 'path']])
    else:
        print("All self_refs are unique.")

def clean_references(df):
    # Filter to get rows where hierarchy_level == 0
    df_hl_0 = df[df['hierarchy_level'] == 0]

    # Get unique self_refs from filtered DataFrame
    valid_self_refs = set(df_hl_0['self_ref'].unique())

    # Function to clean references by checking if they are in valid_self_refs
    def filter_references(refs):
        # Ensure references are a list if not None or empty
        refs_list = ast.literal_eval(refs) if isinstance(refs, str) and refs else []
        # Filter references to include only those that are in valid_self_refs
        filtered_refs = [ref for ref in refs_list if ref in valid_self_refs]
        removed_refs = [ref for ref in refs_list if ref not in valid_self_refs]

        # Print the references kept and removed for verification
        if removed_refs:
            print(f"Kept: {filtered_refs}, Removed: {removed_refs}")

        return filtered_refs, removed_refs

    # Apply the filtering function to the 'references' column and separate the results
    results = df['references'].apply(filter_references)
    df['references'] = results.apply(lambda x: x[0])
    df['section_references'] = results.apply(lambda x: x[1])

    return df

def validate_dataframe(df: pd.DataFrame):
    required_columns = [
        'path', 'title', 'content', 'self_ref', 'references', 'depth',
        'hierarchy_level', 'summary', 'embedding', 'd_cluster', 'hl_cluster', 'parent_path'
    ]
    
    # Check if all required columns are present
    missing_columns = set(required_columns) - set(df.columns)
    if missing_columns:
        raise ValueError(f"Missing columns in dataframe: {missing_columns}")

    # Check data types and formats
    for _, row in df.iterrows():
        try:
            assert isinstance(row['path'], str), f"Path should be a string: {row['path']}"
            assert isinstance(row['title'], str), f"Title should be a string: {row['title']}"
            assert isinstance(row['content'], str), f"Content should be a string: {row['content']}"
            if row['hierarchy_level'] == 0:
                assert isinstance(row['self_ref'], str), f"Self_ref should be a string: {row['self_ref']}"
            
            # Check references
            if pd.notna(row['references']):
                references = ast.literal_eval(row['references']) if isinstance(row['references'], str) else row['references']
                assert isinstance(references, list), f"References should be a list: {row['references']}"
            
            assert isinstance(row['depth'], (int, float)), f"Depth should be a number: {row['depth']}"
            assert isinstance(row['hierarchy_level'], (int, float)), f"Hierarchy_level should be a number: {row['hierarchy_level']}"
            if pd.notna(row['summary']):
                assert isinstance(row['summary'], str), f"Summary should be a string: {row['summary']}"
            
            # Check embedding
            if pd.notna(row['embedding']):
                embedding = ast.literal_eval(row['embedding']) if isinstance(row['embedding'], str) else row['embedding']
                assert isinstance(embedding, list), f"Embedding should be a list: {row['embedding']}"
                assert all(isinstance(x, (int, float)) for x in embedding), f"Embedding should contain only numbers: {row['embedding']}"
            
            assert isinstance(row['d_cluster'], (int, float)), f"D_cluster should be a number: {row['d_cluster']}"
            assert isinstance(row['hl_cluster'], (int, float)), f"Hl_cluster should be a number: {row['hl_cluster']}"
            
            if pd.notna(row['parent_path']):
                assert isinstance(row['parent_path'], str), f"Parent_path should be a string: {row['parent_path']}"
        
        except AssertionError as e:
            logging.error(f"Error in row {_}: {str(e)}")
            raise

    logging.info("All rows validated successfully")

def test_build_document_graph_from_df(df: pd.DataFrame):
    # Test document metadata
    doc_id = "test_doc"
    title = "Test Document"
    doc_tags = ["test", "validation"]
    metadata = {"author": "Test Author"}

    # Validate dataframe
    validate_dataframe(df)

    # Simulate the build process
    logging.info(f"Building graph for document {doc_id}: {title}")
    
    # Simulate adding nodes
    for _, row in df.iterrows():
        if row['hierarchy_level'] > 0:
            logging.info(f"Adding section node: {row['path']}")
        else:
            logging.info(f"Adding content node: {row['path']}")

    # Simulate adding relationships
    for _, row in df.iterrows():
        logging.info(f"Adding CONTAINS relationship: {row['parent_path']} -> {row['path']}")
        
        if pd.notna(row['references']):
            references = ast.literal_eval(row['references']) if isinstance(row['references'], str) else row['references']
            for ref in references:
                logging.info(f"Adding REFERENCES relationship: {row['path']} -> {ref}")

    logging.info("Graph building simulation completed successfully")

def main():
    df= pd.read_csv("ztest_tax_output/final3_formatted_tax_data_clustered.csv")    
    test_build_document_graph_from_df(df)


if __name__ == "__main__":
    main()