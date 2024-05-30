from parser.pdf_parser import PDFParser
import asyncio
import json
import llm, prompts


async def main_run():
    vol_num = "RH_VIC_NURSES2025"
    #pdf_path = f"/Users/jamesqxd/Documents/norgai-docs/TAX/C2024C00046VOL0{vol_num}.pdf"
    pdf_path = "/Users/jamesqxd/Documents/norgai-docs/EBA/RamsayHealth/RH_VIC_NURSES2025.pdf"
    
    parser = PDFParser()
    content_dict = await parser.parse(pdf_path)
    with open(f"master_toc{vol_num}_content.json", "w") as f:
        json.dump(content_dict, f, indent=4)

    

asyncio.run(main_run())