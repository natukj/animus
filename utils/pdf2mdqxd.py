"""
Largely taken from: https://github.com/pymupdf/RAG/blob/main/pymupdf4llm/pymupdf4llm/helpers/pymupdf_rag.py

Dependencies
-------------
PyMuPDF v1.24.2 or later

Copyright and License
----------------------
Copyright 2024 Artifex Software, Inc.
License GNU Affero GPL 3.0

TODO: to use this commerically I need to make a PR to the PyMuPDF repo as per above license
although i'm so far ahead/behind 
"""

import os
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional, Callable, Union, Any
from collections import Counter
try:
    import pymupdf as fitz 
except ImportError:
    import fitz

from utils.get_text_lines import get_raw_lines, is_white
from utils.multi_column import column_boxes

@dataclass
class PageOutput:
    metadata: Dict
    toc_items: List
    tables: List
    images: List
    graphics: List
    text: str
    def to_dict(self):
        return asdict(self)

if fitz.pymupdf_version_tuple < (1, 24, 2):
    raise NotImplementedError("PyMuPDF version 1.24.2 or later is needed.")

bullet = ("- ", "* ", chr(0xF0A7), chr(0xF0B7), chr(0xB7), chr(8226), chr(9679))
GRAPHICS_TEXT = "\n![%s](%s)\n"


class IdentifyHeaders:
    """Compute data for identifying header text."""

    def __init__(self, doc: str, pages: list = None, body_limit: float = None):
        """Read all text and make a dictionary of fontsizes.

        Args:
            doc: Path to the PDF document or a fitz.Document object
            pages: optional list of pages to consider
            body_limit: consider text with larger font size as some header
        """
        self.mydoc = doc if isinstance(doc, fitz.Document) else fitz.open(doc)
        self.pages = pages or range(self.mydoc.page_count)
        self.fontsizes = self._compute_fontsizes()
        self.body_limit = self._determine_body_limit(body_limit)
        self.header_id = self._create_header_id()

        if self.mydoc != doc:
            self.mydoc.close()

    def _compute_fontsizes(self):
        fontsizes = Counter()
        for pno in self.pages:
            page = self.mydoc.load_page(pno)
            blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]
            for span in [s for b in blocks for l in b["lines"] for s in l["spans"] if not is_white(s["text"])]:
                fontsizes[round(span["size"])] += len(span["text"].strip())
        print(f"Fontsizes: {dict(fontsizes)}")
        return fontsizes

    def _determine_body_limit(self, provided_limit):
        most_common_size = max(self.fontsizes, key=self.fontsizes.get)
        print(f"Most common font size: {most_common_size}")
        
        if provided_limit is None:
            temp = sorted(self.fontsizes.items(), key=lambda i: i[1], reverse=True)
            b_limit = max(most_common_size, temp[0][0]) if temp else most_common_size
        else:
            b_limit = provided_limit
        
        print(f"Body text limit: {b_limit}")
        return b_limit

    def _create_header_id(self):
        sizes = sorted([f for f in self.fontsizes.keys() if f > self.body_limit], reverse=True)[:6]
        return {size: "#" * (i + 1) + " " for i, size in enumerate(sizes)}

    def get_header_id(self, span: dict, page=None) -> str:
        """Return appropriate markdown header prefix.

        Given a text span from a "dict"/"rawdict" extraction, determine the
        markdown header prefix string of 0 to n concatenated '#' characters.
        """
        fontsize = round(span["size"])
        return self.header_id.get(fontsize, "")


def to_markdown(
    doc: fitz.Document,
    *,
    pages: Optional[List[int]] = None,
    hdr_info: Optional[object] = None,
    write_images: bool = False,
    page_chunks: bool = False,
    margins: Tuple[float, float, float, float] = (0, 50, 0, 50),
) -> Union[str, List[PageOutput]]:
    """Process the document and return the text of its selected pages."""

    pages = pages or list(range(doc.page_count))
    margins = _normalize_margins(margins)

    get_header_id = _get_header_id_function(doc, pages, hdr_info)

    document_output = [] if page_chunks else ""
    toc = doc.get_toc()
    textflags = fitz.TEXT_DEHYPHENATE | fitz.TEXT_MEDIABOX_CLIP

    for pno in pages:
        page_output, images, tables, graphics = get_page_output(
            doc, pno, margins, textflags, get_header_id, write_images
        )

        if page_chunks:
            page_tocs = [t for t in toc if t[-1] == pno + 1]
            metadata = get_metadata(doc, pno)
            page_data = PageOutput(
                metadata=metadata,
                toc_items=page_tocs,
                tables=tables,
                images=images,
                graphics=graphics,
                text=page_output,
            )
            document_output.append(page_data.to_dict())
        else:
            document_output += page_output

    return document_output

def _normalize_margins(margins: Union[float, Tuple[float, ...], List[float]]) -> Tuple[float, float, float, float]:
    if isinstance(margins, (int, float)):
        return (0, margins, 0, margins)
    if len(margins) == 2:
        return (0, margins[0], 0, margins[1])
    if len(margins) == 4:
        return tuple(margins)
    raise ValueError("margins must have length 2 or 4 or be a number.")

def _get_header_id_function(doc: fitz.Document, pages: List[int], hdr_info: Optional[object]) -> Callable:
    if callable(hdr_info):
        return hdr_info
    if hasattr(hdr_info, "get_header_id") and callable(hdr_info.get_header_id):
        return hdr_info.get_header_id
    
    hdr_info = IdentifyHeaders(doc, pages=pages)
    print(f"Header ID: {hdr_info.header_id}")
    return hdr_info.get_header_id

def get_page_output(doc: fitz.Document, pno: int, margins: Tuple[float, float, float, float], 
                    textflags: int, get_header_id: Callable, write_images: bool) -> Tuple[str, List, List, List]:
    page = doc[pno]
    left, top, right, bottom = margins
    clip = page.rect + (left, top, -right, -bottom)
    links = [l for l in page.get_links() if l["kind"] == 2]
    textpage = page.get_textpage(flags=textflags, clip=clip)

    img_info = [img for img in page.get_image_info() if img["bbox"] in clip]
    images = img_info[:]
    tables = []
    graphics = []

    tabs = page.find_tables(clip=clip, strategy="lines_strict")
    tab_rects = _get_table_rects(tabs, tables)
    
    paths = _get_paths(page, tab_rects)
    vg_clusters = _get_vector_graphics_clusters(page, paths, tab_rects)
    
    if write_images:
        vg_clusters += [fitz.Rect(i["bbox"]) for i in img_info]

    vg_clusters = dict(enumerate(vg_clusters))

    text_rects = column_boxes(
        page,
        paths=paths,
        no_image_text=write_images,
        textpage=textpage,
        avoid=list(tab_rects.values()) + list(vg_clusters.values()),
    )

    md_string = _process_text_rects(page, textpage, text_rects, tabs, tab_rects, vg_clusters, links, get_header_id)

    return md_string, images, tables, graphics

def _get_table_rects(tabs: List[Any], tables: List[Dict]) -> Dict[int, fitz.Rect]:
    tab_rects = {}
    for i, t in enumerate(tabs):
        tab_rects[i] = fitz.Rect(t.bbox) | fitz.Rect(t.header.bbox)
        tab_dict = {
            "bbox": tuple(tab_rects[i]),
            "rows": t.row_count,
            "columns": t.col_count,
        }
        tables.append(tab_dict)
    return tab_rects

def _get_paths(page: fitz.Page, tab_rects: Dict[int, fitz.Rect]) -> List[Dict]:
    page_clip = page.rect + (36, 36, -36, -36)
    return [
        p
        for p in page.get_drawings()
        if not intersects_rects(p["rect"], list(tab_rects.values()))
        and p["rect"] in page_clip
        and p["rect"].width < page_clip.width
        and p["rect"].height < page_clip.height
    ]

def _get_vector_graphics_clusters(page: fitz.Page, paths: List[Dict], tab_rects: Dict[int, fitz.Rect]) -> List[fitz.Rect]:
    vg_clusters = []
    for bbox in page.cluster_drawings(drawings=paths):
        if any(_is_stroked_path(p) for p in paths if p["rect"] in bbox):
            vg_clusters.append(bbox)
    
    return [
        r
        for r in vg_clusters
        if not intersects_rects(r, list(tab_rects.values())) and r.height > 20
    ]

def _is_stroked_path(path: Dict) -> bool:
    return path["type"] != "f" or any(item[0] == "c" for item in path["items"])

def _process_text_rects(
    page: fitz.Page, 
    textpage: fitz.TextPage, 
    text_rects: List[fitz.Rect], 
    tabs: List[Any], 
    tab_rects: Dict[int, fitz.Rect], 
    vg_clusters: Dict[int, fitz.Rect], 
    links: List[Dict], 
    get_header_id: Callable) -> str:
    md_string = ""
    for text_rect in text_rects:
        md_string += output_tables(tabs, text_rect, tab_rects)
        md_string += output_images(page, text_rect, vg_clusters)
        md_string += write_text(
            page,
            textpage,
            text_rect,
            tabs=tabs,
            tab_rects=tab_rects,
            img_rects=vg_clusters,
            links=links,
            get_header_id=get_header_id,
        )

    md_string += output_tables(tabs, None, tab_rects)
    md_string += output_images(page, None, vg_clusters)
    md_string += "\n-----\n\n"
    return md_string.lstrip()

def _is_continued_header(hdr_string: str, prev_hdr_string: Optional[str], span0: Dict, prev_span: Optional[Dict]) -> bool:
    if not hdr_string or not prev_hdr_string:
        return False
    if hdr_string != prev_hdr_string:
        return False
    if prev_span is None:
        return False
    # this might be overengineered/overly specific
    # check if this span is on the next line and close enough vertically
    vertical_distance = span0['origin'][1] - prev_span['origin'][1]
    line_height = span0['bbox'].height
    return 0 < vertical_distance <= 1.5 * line_height

# def _is_continued_header(hdr_string: str, prev_hdr_string: Optional[str], span0: Dict) -> bool:
#     return hdr_string and hdr_string == prev_hdr_string and span0['line'] >= 1

def write_text(
    page: fitz.Page,
    textpage: fitz.TextPage,
    clip: fitz.Rect,
    tabs: List[Any],
    tab_rects: Dict[int, fitz.Rect],
    img_rects: Dict[int, fitz.Rect],
    links: List[Dict],
    get_header_id: Callable,
) -> str:
    out_string = ""
    nlines = get_raw_lines(textpage, clip=clip, tolerance=3)

    tab_rects0 = list(tab_rects.values())
    img_rects0 = list(img_rects.values())

    prev_lrect = None
    prev_bno = -1
    code = False
    prev_hdr_string = None
    prev_span = None
    header_content = ""

    for lrect, spans in nlines:
        if intersects_rects(lrect, tab_rects0) or intersects_rects(lrect, img_rects0):
            continue

        out_string += _process_tables_and_images(page, lrect, tabs, tab_rects, img_rects, clip)

        text = " ".join([s["text"] for s in spans])
        all_mono = all([s["flags"] & 8 for s in spans])

        if all_mono:
            out_string += _process_mono_text(code, lrect, clip, spans, text)
            code = True
            continue

        span0 = spans[0]
        bno = span0["block"]
        if bno != prev_bno:
            out_string += "\n"
            prev_bno = bno

        if _need_line_break(prev_lrect, lrect, span0):
            out_string += "\n"
        prev_lrect = lrect

        hdr_string = get_header_id(span0, page=page)
        if _is_continued_header(hdr_string, prev_hdr_string, span0, prev_span):
            header_content += " " + text
        else:
            if header_content:
                out_string += prev_hdr_string + header_content + "\n\n"
                header_content = ""
            
            if hdr_string.startswith("#"):
                header_content = text
            else:
                out_string += _process_regular_text(spans, hdr_string, links, code)

        prev_hdr_string = hdr_string
        prev_span = span0

        if not code:
            out_string += "\n"

    if header_content:
        out_string += prev_hdr_string + header_content + "\n\n"

    out_string += "\n"
    if code:
        out_string += "```\n"

    return out_string.replace(" \n", "\n").replace("  ", " ").replace("\n\n\n", "\n\n")

def _process_regular_text(spans: List[Dict], hdr_string: str, links: List[Dict], code: bool) -> str:
    out_string = ""
    if code:
        out_string += "```\n"
        code = False

    consolidated_spans = consolidate_spans(spans)
    for s in consolidated_spans:
        out_string += _process_span(s, hdr_string, links)

    return out_string

def _process_tables_and_images(page: fitz.Page, lrect: fitz.Rect, tabs: List[Any], 
                               tab_rects: Dict[int, fitz.Rect], img_rects: Dict[int, fitz.Rect], 
                               clip: fitz.Rect) -> str:
    out_string = ""
    for i, tab_rect in sorted(
        [j for j in tab_rects.items() if j[1].y1 <= lrect.y0 and not (j[1] & clip).is_empty],
        key=lambda j: (j[1].y1, j[1].x0),
    ):
        out_string += "\n" + tabs[i].to_markdown(clean=False) + "\n"
        del tab_rects[i]

    for i, img_rect in sorted(
        [j for j in img_rects.items() if j[1].y1 <= lrect.y0 and not (j[1] & clip).is_empty],
        key=lambda j: (j[1].y1, j[1].x0),
    ):
        pathname = save_image(page, img_rect, i)
        if pathname:
            out_string += f"![Image]({pathname})\n"
        del img_rects[i]

    return out_string

def _process_mono_text(code: bool, lrect: fitz.Rect, clip: fitz.Rect, spans: List[Dict], text: str) -> str:
    out_string = ""
    if not code:
        out_string += "```\n"
    delta = int((lrect.x0 - clip.x0) / (spans[0]["size"] * 0.5))
    indent = " " * delta
    out_string += indent + text + "\n"
    return out_string

def _need_line_break(prev_lrect: Optional[fitz.Rect], lrect: fitz.Rect, span0: Dict) -> bool:
    return (
        prev_lrect
        and lrect.y1 - prev_lrect.y1 > lrect.height * 1.5
        or span0["text"].startswith("[")
        or span0["text"].startswith("-")
        or span0["flags"] & 1
    )

def _process_span(s: Dict, hdr_string: str, links: List[Dict]) -> str:
    mono = s["flags"] & 8
    bold = s["flags"] & 16
    italic = s["flags"] & 2

    if mono:
        return f"`{s['text'].strip()}` "

    prefix = ""
    suffix = ""
    if hdr_string == "":
        if bold:
            prefix = "**"
            suffix += "**"
        if italic:
            prefix += "_"
            suffix = "_" + suffix

    ltext = resolve_links(links, s)
    if ltext:
        text = f"{hdr_string}{prefix}{ltext}{suffix} "
    else:
        text = f"{hdr_string}{prefix}{s['text'].strip()}{suffix} "

    if text.startswith("-"):
        text = "-  " + text[1:]
    return text

def resolve_links(links: List[Dict], span: Dict) -> Optional[str]:
    bbox = fitz.Rect(span["bbox"])
    bbox_area = 0.7 * abs(bbox)
    for link in links:
        hot = link["from"]
        if abs(hot & bbox) >= bbox_area:
            return f'[{span["text"].strip()}]({link["uri"]})'
    return None

def save_image(page: fitz.Page, rect: fitz.Rect, i: int) -> Optional[str]:
    filename = page.parent.name.replace("\\", "/")
    image_path = f"{filename}-{page.number}-{i}.png"
    pix = page.get_pixmap(clip=rect)
    pix.save(image_path)
    del pix
    return os.path.basename(image_path)

def consolidate_spans(spans: List[Dict]) -> List[Dict]:
    consolidated = []
    if not spans:
        return consolidated

    current_span = spans[0]
    for next_span in spans[1:]:
        distance = next_span['bbox'].x0 - current_span['bbox'].x1
        vertical_alignment = abs(next_span['bbox'].y0 - current_span['bbox'].y0)

        if distance < 2 and vertical_alignment < 5:
            current_span['text'] += next_span['text']
            current_span['bbox'] = current_span['bbox'] | next_span['bbox']
        else:
            consolidated.append(current_span)
            current_span = next_span
    consolidated.append(current_span)
    return consolidated

def output_tables(tabs: List[Any], text_rect: Optional[fitz.Rect], tab_rects: Dict[int, fitz.Rect]) -> str:
    this_md = ""
    if text_rect is not None:
        for i, trect in sorted(
            [j for j in tab_rects.items() if j[1].y1 <= text_rect.y0],
            key=lambda j: (j[1].y1, j[1].x0),
        ):
            this_md += tabs[i].to_markdown(clean=False)
            del tab_rects[i]
    else:
        for i, trect in sorted(
            tab_rects.items(),
            key=lambda j: (j[1].y1, j[1].x0),
        ):
            this_md += tabs[i].to_markdown(clean=False)
            del tab_rects[i]
    return this_md

def output_images(page: Optional[fitz.Page], text_rect: Optional[fitz.Rect], img_rects: Optional[Dict[int, fitz.Rect]]) -> str:
    if img_rects is None:
        return ""
    this_md = ""
    if text_rect is not None and page is not None:
        for i, img_rect in sorted(
            [j for j in img_rects.items() if j[1].y1 <= text_rect.y0],
            key=lambda j: (j[1].y1, j[1].x0),
        ):
            pathname = save_image(page, img_rect, i)
            if pathname:
                this_md += f"![Image]({pathname})\n"
            del img_rects[i]
    elif page is not None:
        for i, img_rect in sorted(
            img_rects.items(),
            key=lambda j: (j[1].y1, j[1].x0),
        ):
            pathname = save_image(page, img_rect, i)
            if pathname:
                this_md += f"![Image]({pathname})\n"
            del img_rects[i]
    return this_md

def get_metadata(doc: fitz.Document, pno: int) -> Dict[str, Union[str, int]]:
    meta = doc.metadata.copy()
    meta["file_path"] = doc.name
    meta["page_count"] = doc.page_count
    meta["page"] = pno + 1
    return meta

def is_in_rects(rect: fitz.Rect, rect_list: List[fitz.Rect]) -> int:
    for i, r in enumerate(rect_list, start=1):
        if rect in r:
            return i
    return 0

def intersects_rects(rect: fitz.Rect, rect_list: List[fitz.Rect]) -> int:
    for i, r in enumerate(rect_list, start=1):
        if (rect.tl + rect.br) / 2 in r:
            return i
    return 0