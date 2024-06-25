import asyncio
import json
import os
import formatters, utils
import pandas as pd

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