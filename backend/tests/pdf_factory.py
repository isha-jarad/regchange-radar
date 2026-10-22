import textwrap

import pymupdf

PAGE_WIDTH, PAGE_HEIGHT = 595, 842  # A4, in points
MARGIN = 72
FONT_SIZE = 11
LINE_HEIGHT = 15
PARAGRAPH_GAP = 24


def make_pdf_bytes(paragraphs: list[str]) -> bytes:
    """Build a small text-based PDF in which each string becomes its own paragraph."""
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    y = MARGIN
    for text in paragraphs:
        lines = textwrap.wrap(text, width=80) or [""]
        height = len(lines) * LINE_HEIGHT
        if y + height > PAGE_HEIGHT - MARGIN:
            page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
            y = MARGIN
        for i, line in enumerate(lines):
            page.insert_text((MARGIN, y + (i + 1) * LINE_HEIGHT), line, fontsize=FONT_SIZE)
        y += height + PARAGRAPH_GAP
    data = doc.tobytes()
    doc.close()
    return data