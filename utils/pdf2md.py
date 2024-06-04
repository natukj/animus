"""
https://github.com/pymupdf/RAG/blob/main/helpers/pymupdf_rag.py
"""
import string
from pprint import pprint
import fitz

def to_markdown(doc: fitz.Document, pages: list = None) -> str:
    """Process the document and return the text of its selected pages."""
    SPACES = set(string.whitespace)  # used to check relevance of text pieces
    if not pages:  # use all pages if argument not given
        pages = range(doc.page_count)

    class IdentifyHeaders:
        """Compute data for identifying header text."""

        def __init__(self, doc, pages: list = None, body_limit: float = None):
            """Read all text and make a dictionary of fontsizes.

            Args:
                pages: optional list of pages to consider
                body_limit: consider text with larger font size as some header
            """
            if pages is None:  # use all pages if omitted
                pages = range(doc.page_count)
            fontsizes = {}
            for pno in pages:
                page = doc[pno]
                blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]
                for span in [  # look at all non-empty horizontal spans
                    s
                    for b in blocks
                    for l in b["lines"]
                    for s in l["spans"]
                    if not SPACES.issuperset(s["text"])
                ]:
                    fontsz = round(span["size"])
                    count = fontsizes.get(fontsz, 0) + len(span["text"].strip())
                    fontsizes[fontsz] = count

            # maps a fontsize to a string of multiple # header tag characters
            self.header_id = {}
            if body_limit is None:  # body text fontsize if not provided
                body_limit = sorted(
                    [(k, v) for k, v in fontsizes.items()],
                    key=lambda i: i[1],
                    reverse=True,
                )[0][0]

            sizes = sorted(
                [f for f in fontsizes.keys() if f > body_limit], reverse=True
            )

            # make the header tag dictionary
            for i, size in enumerate(sizes):
                self.header_id[size] = "#" * (i + 1) + " "

        def get_header_id(self, span):
            """Return appropriate markdown header prefix.

            Given a text span from a "dict"/"radict" extraction, determine the
            markdown header prefix string of 0 to many concatenated '#' characters.
            """
            fontsize = round(span["size"])  # compute fontsize
            hdr_id = self.header_id.get(fontsize, "")
            return hdr_id

    def resolve_links(links, span):
        """Accept a span bbox and return a markdown link string."""
        bbox = fitz.Rect(span["bbox"])  # span bbox
        # a link should overlap at least 70% of the span
        bbox_area = 0.7 * abs(bbox)
        for link in links:
            hot = link["from"]  # the hot area of the link
            if not abs(hot & bbox) >= bbox_area:
                continue  # does not touch the bbox
            text = f'[{span["text"].strip()}]({link["uri"]})'
            return text

    def write_text(page, clip, hdr_prefix):
        """Output the text found inside the given clip."""
        out_string = ""
        code = False  # mode indicator: outputting code

        # extract URL type links on page
        links = [l for l in page.get_links() if l["kind"] == 2]

        blocks = page.get_text(
            "dict",
            clip=clip,
            flags=fitz.TEXTFLAGS_TEXT,
            sort=True,
        )["blocks"]

        for block in blocks:  # iterate textblocks
            previous_y = 0
            for line in block["lines"]:  # iterate lines in block
                if line["dir"][1] != 0:  # only consider horizontal lines
                    continue
                spans = [s for s in line["spans"]]

                this_y = line["bbox"][3]  # current bottom coord

                # check for still being on same line
                same_line = abs(this_y - previous_y) <= 3 and previous_y > 0

                if same_line and out_string.endswith("\n"):
                    out_string = out_string[:-1]

                # are all spans in line in a mono-spaced font?
                all_mono = all([s["flags"] & 8 for s in spans])

                # compute text of the line
                text = "".join([s["text"] for s in spans])
                if not same_line:
                    previous_y = this_y
                    if not out_string.endswith("\n"):
                        out_string += "\n"

                if all_mono:
                    if not code:
                        out_string += "```\n"
                        code = True
                    out_string += text
                    continue

                bold_text = ""
                italic_text = ""
                for i, s in enumerate(spans):  
                    if code:
                        if s["text"].endswith("```"):  # switch off code mode
                            code = False
                            out_string = out_string[:-3] + f"{s['text']}\n"
                        else:
                            out_string += s["text"]
                        continue

                    mono = s["flags"] & 8
                    bold = s["flags"] & 16
                    italic = s["flags"] & 2

                    if mono:
                        out_string += s["text"]
                    else: 
                        if i == 0:
                            hdr_string = hdr_prefix.get_header_id(s)
                        else:
                            hdr_string = ""

                        # handle bold and italic text accumulation
                        if bold and italic:
                            if bold_text:
                                ltext = resolve_links(links, {'text': bold_text, 'bbox': s['bbox']})
                                if ltext:
                                    out_string += f"{hdr_string}**{ltext}**"
                                else:
                                    out_string += f"{hdr_string}**{bold_text}**"
                                bold_text = ""
                            if italic_text:
                                ltext = resolve_links(links, {'text': italic_text, 'bbox': s['bbox']})
                                if ltext:
                                    out_string += f"_{ltext}_"
                                else:
                                    out_string += f"_{italic_text}_"
                                italic_text = ""
                            bold_text += s['text']
                            italic_text += s['text'] 
                        elif bold:
                            if italic_text:
                                ltext = resolve_links(links, {'text': italic_text, 'bbox': s['bbox']})
                                if ltext:
                                    out_string += f"_{ltext}_"
                                else:
                                    out_string += f"_{italic_text}_"
                                italic_text = ""
                            bold_text += s['text']
                        elif italic:
                            if bold_text:
                                ltext = resolve_links(links, {'text': bold_text, 'bbox': s['bbox']})
                                if ltext:
                                    out_string += f"{hdr_string}**{ltext}**"
                                else:
                                    out_string += f"{hdr_string}**{bold_text}**"
                                bold_text = ""
                            italic_text += s['text']
                        else:
                            # if previous text was bold or italic, apply formatting
                            if bold_text:
                                ltext = resolve_links(links, {'text': bold_text, 'bbox': s['bbox']})
                                if ltext:
                                    out_string += f"{hdr_string}**{ltext}**"
                                else:
                                    out_string += f"{hdr_string}**{bold_text}**"
                                bold_text = "" 
                            if italic_text:
                                ltext = resolve_links(links, {'text': italic_text, 'bbox': s['bbox']})
                                if ltext:
                                    out_string += f"_{ltext}_"
                                else:
                                    out_string += f"_{italic_text}_"
                                italic_text = ""

                            # handle regular text
                            ltext = resolve_links(links, s) 
                            if ltext:
                                out_string += f"{hdr_string}{ltext} "
                            else:
                                if s['text'].strip() == "":
                                    continue
                                out_string += f"{hdr_string}{s['text'].strip()} "

                        # handle replacements for Markdown
                        out_string = (
                            out_string.replace("<", "&lt;")
                            .replace(">", "&gt;")
                            .replace(chr(0xF0B7), "-")
                            .replace(chr(0xB7), "-")
                            .replace(chr(8226), "-")
                            .replace(chr(9679), "-")
                            .replace(r".) ", ".) ")
                            .replace(" ;", ";")
                            .replace(" :", ":")
                            .replace("( ", "(")
                            .replace(" )", ")")
                        ) 
                # check if bold or italic segments are pending at the end of the line
                if bold_text:
                    ltext = resolve_links(links, {'text': bold_text, 'bbox': s['bbox']})
                    if ltext:
                        out_string += f"**{ltext}**"
                    else:
                        out_string += f"**{bold_text}**"
                    bold_text = "" 
                if italic_text:
                    ltext = resolve_links(links, {'text': italic_text, 'bbox': s['bbox']})
                    if ltext:
                        out_string += f"_{ltext}_"
                    else:
                        out_string += f"_{italic_text}_"
                    italic_text = ""

                previous_y = this_y
                if not code:
                    out_string += "\n"
            out_string += "\n"
        if code:
            out_string += "```\n"  
            code = False
        return out_string.replace(" \n", "\n")

    hdr_prefix = IdentifyHeaders(doc, pages=pages)
    #hdr_prefix = IdentifyHeaders(doc, pages=pages, body_limit=9) # change threshold for header detection
    md_string = ""

    for pno in pages:
        page = doc[pno]
        # 1. first locate all tables on page
        tabs = page.find_tables()

        # 2. make a list of table boundary boxes, sort by top-left corner.
        # Must include the header bbox, which may be external.
        tab_rects = sorted(
            [
                (fitz.Rect(t.bbox) | fitz.Rect(t.header.bbox), i)
                for i, t in enumerate(tabs.tables)
            ],
            key=lambda r: (r[0].y0, r[0].x0),
        )

        # 3. final list of all text and table rectangles
        text_rects = []
        # compute rectangles outside tables and fill final rect list
        for i, (r, idx) in enumerate(tab_rects):
            if i == 0:  # compute rect above all tables
                tr = page.rect
                tr.y1 = r.y0
                if not tr.is_empty:
                    text_rects.append(("text", tr, 0))
                text_rects.append(("table", r, idx))
                continue
            # read previous rectangle in final list: always a table!
            _, r0, idx0 = text_rects[-1]

            # check if a non-empty text rect is fitting in between tables
            tr = page.rect
            tr.y0 = r0.y1
            tr.y1 = r.y0
            if not tr.is_empty:  # empty if two tables overlap vertically!
                text_rects.append(("text", tr, 0))

            text_rects.append(("table", r, idx))

            # there may also be text below all tables
            if i == len(tab_rects) - 1:
                tr = page.rect
                tr.y0 = r.y1
                if not tr.is_empty:
                    text_rects.append(("text", tr, 0))

        if not text_rects:  # this will happen for table-free pages
            text_rects.append(("text", page.rect, 0))
        else:
            rtype, r, idx = text_rects[-1]
            if rtype == "table":
                tr = page.rect
                tr.y0 = r.y1
                if not tr.is_empty:
                    text_rects.append(("text", tr, 0))

        # we have all rectangles and can start outputting their contents
        for rtype, r, idx in text_rects:
            if rtype == "text":  # a text rectangle
                md_string += write_text(page, r, hdr_prefix)  # write MD content
                md_string += "\n"
            else:  # a table rect
                md_string += tabs[idx].to_markdown(clean=False)

        md_string += "\n-----\n\n"

    return md_string