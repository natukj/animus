import asyncio
import json
from parsers import PDFParserRouter

"""
✔ Modern Awards
✔ Fair Work Act 2009
✔ Income Tax Assessment Act 1997
Goods and Services Tax Act 1999
✔ Corporations Act 2001 (UK)
✔ UK Income Tax Act
Privacy Act 1988
Competition and Consumer Act 2010
Work Health and Safety Act 2011
Environment Protection and Biodiversity Conservation Act 1999
Superannuation Guarantee (Administration) Act 1992
National Employment Standards
Australian Securities and Investments Commission Act 2001
"""

async def main_run():
    for i in range(2, 11):
        vol_num = f"{i:02d}"
        pdf_path = f"/Users/jamesqxd/Documents/norgai-docs/TAX/C2024C00046VOL{vol_num}.pdf"
        print(f"Processing {pdf_path}")
        router = PDFParserRouter()
        parsed_content = await router.parse(pdf_path)
        with open(f"/Users/jamesqxd/Documents/norgai-docs/TAX/parsed/final_aus_tax_{vol_num}.json", "w") as f:
            json.dump(parsed_content, f, indent=4)
asyncio.run(main_run())

async def main_crane():
    pdf_path = "/Users/jamesqxd/Documents/norgai-docs/EBA/Crane/CraneEBA2022.pdf"
    router = PDFParserRouter()
    parsed_content = await router.parse(pdf_path)
    with open(f"/Users/jamesqxd/Documents/norgai-docs/EBA/Crane/final_crane_eba.json", "w") as f:
        json.dump(parsed_content, f, indent=4)
#asyncio.run(main_crane())
