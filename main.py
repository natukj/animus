from parser.pdf_parser import PDFParser
from parser.pdf_parser_ToC import PDFToCParser
import asyncio
import json
import llm, prompts

"""
✔ Modern Awards
✔ Fair Work Act 2009
✔ Income Tax Assessment Act 1997
Goods and Services Tax Act 1999
✔ Corporations Act 2001
Privacy Act 1988
Competition and Consumer Act 2010
Work Health and Safety Act 2011
Environment Protection and Biodiversity Conservation Act 1999
Superannuation Guarantee (Administration) Act 1992
National Employment Standards
Australian Securities and Investments Commission Act 2001
"""
# router = PDFParserRouter()
# parsed_content = router.parse("path/to/your/pdf.pdf")
# print(parsed_content) 


async def main_run():
    #vol_num = "UKCOMPANIESACT2006"
    vol_num = 9
    pdf_path = f"/Users/jamesqxd/Documents/norgai-docs/TAX/C2024C00046VOL0{vol_num}.pdf"
    #pdf_path = "/Users/jamesqxd/Documents/norgai-docs/ACTS/ukCOMPANIESACT2006.pdf"
    parser = PDFToCParser(pdf_path)
    print(await parser.determine_toc_structure())
    # parser = PDFParser()
    # content_dict = await parser.parse(pdf_path)
    # with open(f"master_toc{vol_num}_content.json", "w") as f:
    #     json.dump(content_dict, f, indent=4)

    

asyncio.run(main_run())