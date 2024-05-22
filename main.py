from parser.pdf_parser import PDFParser
import asyncio
import json


async def main():
    vol_num = 3
    pdf_path = f"/Users/jamesqxd/Documents/norgai-docs/TAX/C2024C00046VOL0{vol_num}.pdf"
    
    parser = PDFParser()
    #await parser.load_document(pdf_path)
    
    #toc = await parser.split_toc()
    #print(json.dumps(toc, indent=4))
    # toc = await parser.extract_toc()
    # with open(f"toc_vol_{vol_num}.json", "w") as f:
    #     json.dump(toc, f, indent=4)

    #await parser.load_and_build_toc(f"toc_vol_{vol_num}.json")
    # levels = await parser.run_find_levels_from_json_path(f"master_toc.json")
    # for level in levels:
    #     print(level)
    content_dict = await parser.parse(pdf_path)
    with open(f"zcontent_vol_{vol_num}.json", "w") as f:
        json.dump(content_dict, f, indent=4)

# asyncio.run(main())

# load document
# extract toc
# biuld master toc
# generate chunked content

with open("toc.md", "r") as f:
    example_text = f.read()
second_level_type = "### Part"
print(second_level_type.split(" ")[0])
lines = example_text.split("\n")
for i, line in enumerate(lines):
    if line.startswith(second_level_type):
        current_part = line.strip()
        j = 1
        while i + j < len(lines) and lines[i + j].startswith(second_level_type.split(" ")[0]):
            next_line = lines[i + j].strip().lstrip('#').strip()
            current_part += ' ' + next_line
            j += 1

        print(current_part)
