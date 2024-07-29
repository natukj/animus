import asyncio
import argparse
import json
import os
from parsers import PDFParserRouter

async def main_run(pdf_path, output_dir, checkpoint, verbose):
    pdf_filename = os.path.basename(pdf_path)
    file_name_without_ext = os.path.splitext(pdf_filename)[0]
    
    router = PDFParserRouter(output_dir, file_name_without_ext, checkpoint, verbose)
    parsed_content = await router.parse(pdf_path)
    
    output_filename = f"{file_name_without_ext}_parsed.json"
    output_path = os.path.join(output_dir, output_filename)
    
    with open(output_path, "w") as f:
        json.dump(parsed_content, f, indent=4)
    print(f"Output saved to: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse PDF documents and extract structured content.")
    parser.add_argument("pdf_path", help="Path to the input PDF file")
    parser.add_argument("-o", "--output_dir", help="Directory to save output files (default: same as input PDF)")
    parser.add_argument("--no-checkpoint", action="store_false", dest="checkpoint", help="Disable checkpoints during parsing")
    parser.add_argument("--no-verbose", action="store_false", dest="verbose", help="Disable verbose output")
    
    args = parser.parse_args()
    
    # default output directory same as input PDF
    if args.output_dir is None:
        args.output_dir = os.path.dirname(os.path.abspath(args.pdf_path))
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    asyncio.run(main_run(args.pdf_path, args.output_dir, args.checkpoint, args.verbose))
