from parser.pdf_parser import PDFParser
import asyncio
import json
import llm, prompts


async def main_run():
    vol_num = 3
    pdf_path = f"/Users/jamesqxd/Documents/norgai-docs/TAX/C2024C00046VOL0{vol_num}.pdf"
    
    parser = PDFParser()
    # await parser.load_document(pdf_path)
    # toc = await parser.extract_toc()
    # with open(f"zz_{vol_num}.json", "w") as f:
    #     json.dump(toc, f, indent=4)

    
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

asyncio.run(main_run())

# json_str = '{"section": "Part", "number": "3-1", "title": "Capital gains and losses: general topics"}'
# json = json.loads(json_str.split(" - Split ")[0])
# for key, value in json.items():
#     print(key, value)

# load document
# extract toc
# biuld master toc
# generate chunked content

# with open("toc.md", "r") as f:
#     toc_md_lines = f.readlines()

# toc_md_section_lines = [line for line in toc_md_lines if line.startswith('#')]
# toc_md_section_joined_lines = '\n'.join(toc_md_section_lines)
# print(toc_md_section_joined_lines)
# import time
# async def main():
#     for i in range(1, 20):
#             messages = [
#                 {"role": "system", "content": prompts.TOC_HIERARCHY_SYS_PROMPT},
#                 {"role": "user", "content": prompts.TOC_HIERARCHY_USER_PROMPT.format(TOC_HIERARCHY_SCHEMA_TEMPLATE=prompts.TOC_HIERARCHY_SCHEMA_TEMPLATE, toc_md_string=toc_md_section_joined_lines)}
#             ]
#             response = await llm.openai_chat_completion_request(messages, model="gpt-4o", response_format="json")
#             try:
#                 schema = json.loads(response['choices'][0]['message']['content'])
#                 print(f"schema {i}: {schema}")
#             except Exception as e:
#                 print(f"Error: {e}")
#                 print(response)




# start_time = time.time()
# asyncio.run(main())
# print("--- %s seconds ---" % (time.time() - start_time))