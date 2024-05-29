import fitz
import base64

def identify_toc_pages(pdf_path):
    doc = fitz.open(pdf_path)
    toc_pages = []

    for page_num in range(doc.page_count):
        page = doc[page_num]
        page_rect = page.rect
        # define the right rectangle
        right_rect = fitz.Rect(page_rect.width * 0.7, 0, page_rect.width, page_rect.height)
        # get the words within the right rectangle
        words = page.get_text("words", clip=right_rect)

        words = [w for w in words if fitz.Rect(w[:4]) in right_rect]

        page_num_count = sum(1 for w in words if w[4].isdigit())
        percentage = page_num_count / len(words) if len(words) > 0 else 0
        if percentage > 0.4:
            toc_pages.append(page_num)

    return toc_pages

# Define the paths to the PDFs
pdf_paths = [
    f"/Users/jamesqxd/Documents/norgai-docs/TAX/C2024C00046VOL0{vol_num}.pdf" for vol_num in range(1, 10)
] + ["/Users/jamesqxd/Documents/norgai-docs/EBA/Woolworths/WW2018_trunc.pdf"] + ["/Users/jamesqxd/Documents/norgai-docs/EBA/RamsayHealth/RH_VIC_NURSES2025.pdf"]

for path in pdf_paths:
    toc_pages = identify_toc_pages(path)
    print(f"ToC candidates in {path}: {toc_pages}")
