from parser.toc_parser import ToCParser
import asyncio
import json
from typing import Union, Any, Callable, Dict, Tuple, List


async def main():
    vol_num = 1
    pdf_path = f"/Users/jamesqxd/Documents/norgai-docs/TAX/C2024C00046VOL0{vol_num}.pdf"
    
    parser = ToCParser()
    #await parser.load_document(pdf_path)
    
    #toc = await parser.split_toc()
    #print(json.dumps(toc, indent=4))
    # toc = await parser.extract_toc()
    # with open(f"toc_vol_{vol_num}.json", "w") as f:
    #     json.dump(toc, f, indent=4)

    #await parser.load_and_build_toc(f"toc_vol_{vol_num}.json")
    # levels = await parser.run_find_levels_from_json_path(f"master_toc_vol_{vol_num}.json")
    # for level in levels:
    #     print(level)
    content_dict = await parser.generate_chunked_content()
    with open(f"zcontent_vol_{vol_num}.json", "w") as f:
        json.dump(content_dict, f, indent=4)

asyncio.run(main())
