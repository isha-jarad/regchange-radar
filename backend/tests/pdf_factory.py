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



# --- Shared sample data and helpers for the tests ---

SAMPLE_OLD_PARAGRAPHS = [
    "Guidance on Adverse Event Reporting",
    "1. Scope",
    "This guidance applies to all sponsors conducting clinical studies in the region.",
    "2. Reporting requirements",
    "The sponsor may submit the safety report within 30 days of becoming aware of the event.",
    "Records of each report should be kept for three years.",
    "3. Definitions",
    "Adverse event means any untoward medical occurrence in a participant.",
    "4. Enforcement",
    "A penalty applies to late submissions.",
    "Contact the office for general questions.",
]

SAMPLE_NEW_PARAGRAPHS = [
    "Guidance on Adverse Event Reporting",
    "1. Scope",
    "This guidance applies to all sponsors and contract research organisations conducting clinical studies in the region.",
    "2. Reporting requirements",
    "The sponsor shall submit the safety report within 15 days of becoming aware of the event.",
    "Records of each report must be kept for five years.",
    "3. Definitions",
    "Adverse event is defined as any untoward medical occurrence in a participant.",
    "4. Enforcement",
    "Contact the office for general questions.",
    "5. Transition period",
    "Sponsors have 90 days to comply with these requirements.",
]


def make_blank_pdf_bytes() -> bytes:
    """A valid PDF with one page and no text (like a scanned document)."""
    doc = pymupdf.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def make_encrypted_pdf_bytes() -> bytes:
    """A PDF that needs a password to open."""
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    data = doc.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="user", owner_pw="owner"
    )
    doc.close()
    return data