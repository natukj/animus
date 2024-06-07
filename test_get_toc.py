import os
import string
import fitz
from utils.get_text_lines import get_raw_lines, is_white
from utils.multi_column import column_boxes

class IdentifyHeaders:
    """Compute data for identifying header text."""

    def __init__(
        self,
        doc: str,
        pages: list = None,
        body_limit: float = None,
    ):
        """Read all text and make a dictionary of fontsizes.

        Args:
            pages: optional list of pages to consider
            body_limit: consider text with larger font size as some header
        """
        if isinstance(doc, fitz.Document):
            mydoc = doc
        else:
            mydoc = fitz.open(doc)

        if pages is None:  # use all pages if omitted
            pages = range(mydoc.page_count)

        fontsizes = {}
        for pno in pages:
            page = mydoc.load_page(pno)
            blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]
            for span in [  # look at all non-empty horizontal spans
                s
                for b in blocks
                for l in b["lines"]
                for s in l["spans"]
                if not is_white(s["text"])
            ]:
                fontsz = round(span["size"])
                count = fontsizes.get(fontsz, 0) + len(span["text"].strip())
                fontsizes[fontsz] = count
                
                # if fontsz > 9:
                #     print(span["text"], fontsz)

        print(fontsizes)
        body_limit = max(fontsizes, key=fontsizes.get)
        print(f"Body text limit: {body_limit}")
        higher_keys = [k for k in fontsizes if k > body_limit]
        sum_higher_values = sum(fontsizes[k] for k in higher_keys)
        total_sum_values = sum(fontsizes.values())
        if total_sum_values > 0:
            percentage_higher_values = (sum_higher_values / total_sum_values) * 100
            print(f"Percentage of values for keys higher than the highest value key: {percentage_higher_values:.2f}%")
        else:
            print("Total sum of values is zero, cannot calculate percentage.")

        if mydoc != doc:
            # if opened here, close it now
            mydoc.close()

        # maps a fontsize to a string of multiple # header tag characters
        self.header_id = {}

        # If not provided, choose the most frequent font size as body text.
        # If no text at all on all pages, just use 12.
        # In any case all fonts not exceeding
        temp = sorted(
            [(k, v) for k, v in fontsizes.items()],
            key=lambda i: i[1],
            reverse=True,
        )
        if temp:
            b_limit = max(body_limit, temp[0][0])
        else:
            b_limit = body_limit

        # identify up to 6 font sizes as header candidates
        sizes = sorted(
            [f for f in fontsizes.keys() if f > b_limit],
            reverse=True,
        )[:6]
        # make the header tag dictionary
        for i, size in enumerate(sizes):
            self.header_id[size] = "#" * (i + 1) + " "

    def get_header_id(self, span: dict, page=None) -> str:
        """Return appropriate markdown header prefix.

        Given a text span from a "dict"/"rawdict" extraction, determine the
        markdown header prefix string of 0 to n concatenated '#' characters.
        """
        fontsize = round(span["size"])  # compute fontsize
        hdr_id = self.header_id.get(fontsize, "")
        return hdr_id
vol_num = 9    
doc = fitz.open(f"/Users/jamesqxd/Documents/norgai-docs/TAX/C2024C00046VOL0{vol_num}.pdf")
docuk = fitz.open("/Users/jamesqxd/Documents/norgai-docs/ACTS/ukCOMPANIESACT2006.pdf")
vol9pages = list(range(2, 32))
ukpages = list(range(0, 59))

hdr_info = IdentifyHeaders(doc, pages=vol9pages)
print(hdr_info.header_id)
hdr_info = IdentifyHeaders(docuk, pages=ukpages)
print(hdr_info.header_id)
def find_page_no(document: fitz.Document, keywords=None):
    if keywords is None:
        raise ValueError("Keywords must be provided.")
    
    for page_number in range(document.page_count):
        page = document[page_number]
        text = page.get_text().lower()  
        
        if any(keyword.lower() in text for keyword in keywords):
            print(f"Table of Contents found on page: {page_number + 1}")
            # document.close()
            return page_number + 1
    
    print("Table of Contents not found.")
    # document.close()
    return None

def find_first_toc_page_no(document: fitz.Document):
    consecutive_toc_like_pages = 0

    for page_number in range(document.page_count):
        page = document[page_number]
        blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]
        if is_toc_like_page(blocks):
            consecutive_toc_like_pages += 1
            if consecutive_toc_like_pages >= 2:  # requires at least two consecutive TOC-like pages
                return page_number - 1
        else:
            consecutive_toc_like_pages = 0
    print("Table of Contents not found.")
    return 0

def is_toc_like_page(blocks):
    toc_indicators = 0
    for block in blocks:
        for line in block['lines']:
            spans = line['spans']
            if spans and is_toc_entry(spans):
                toc_indicators += 1

    # check if the majority of text blocks on the page look like TOC entries
    return toc_indicators >= len(blocks) / 2

def check_larger_font_transition(previous_fonts, current_fonts):
    prev_max_font = max(previous_fonts, key=previous_fonts.get)
    current_max_font = max(current_fonts, key=current_fonts.get)

    # check if the current page starts using a significantly larger font more predominantly
    return current_max_font > prev_max_font and current_fonts[current_max_font] > previous_fonts.get(current_max_font, 0)


def is_toc_entry(spans):
    """assess if the spans in a line are characteristic of TOC entries: small font, consistent, number-heavy."""
    text = " ".join(span['text'] for span in spans)
    font_sizes = [span['size'] for span in spans]
    # criteria: small and consistent font sizes, presence of numbers (page numbers)
    if all(span['size'] < 12 for span in spans) and '...' not in text and any(char.isdigit() for char in text):
        return True
    return False

def find_last_toc_page_no(document: fitz.Document, start_page):
    current_fonts = {}
    previous_fonts = {}
    toc_end_page = start_page
    
    for page_number in range(start_page, document.page_count):
        page = document[page_number]
        blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]
        current_fonts = {}

        for block in blocks:
            for line in block['lines']:
                for span in line['spans']:
                    font_size = round(span['size'])
                    if font_size not in current_fonts:
                        current_fonts[font_size] = len(span['text'].strip())
                    else:
                        current_fonts[font_size] += len(span['text'].strip())

        # compare font sizes distributions between current and previous page
        if previous_fonts:
            # check if there's a significant increase in larger fonts usage
            larger_font_transition = check_larger_font_transition(previous_fonts, current_fonts)
            if larger_font_transition:
                toc_end_page = page_number - 1
                break
        
        previous_fonts = current_fonts.copy()

    return toc_end_page + 1
directory = '/Users/jamesqxd/Documents/norgai-docs/TAX'

# Loop through each file in the directory
for filename in os.listdir(directory):
    # Check if the file is a PDF
    if filename.endswith('.pdf'):
        filepath = os.path.join(directory, filename)
        doc = fitz.open(filepath)
        first_toc_page = find_first_toc_page_no(doc)
        last_toc_page = find_last_toc_page_no(doc, first_toc_page)
        pages = list(range(first_toc_page, last_toc_page))
        hdr_info = IdentifyHeaders(doc, pages=pages)
        print(f"{filename}: {hdr_info.header_id}")