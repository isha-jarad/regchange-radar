import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass

import pymupdf

from app.services.exceptions import (
    DocumentError,
    EncryptedPdfError,
    ExtractionError,
    NoTextFoundError,
)

logger = logging.getLogger(__name__)

# A word split across lines by a hyphen: "regu-\nlation" -> "regulation"
_HYPHEN_LINE_BREAK = re.compile(r"(?<=[a-z])-\s*\n\s*(?=[a-z])")
_WHITESPACE = re.compile(r"\s+")
# Blocks that are only a page number: "3", "Page 3", "Page 3 of 10", "- 3 -", "3/10"
_PAGE_NUMBER_ONLY = re.compile(
    r"^[-–—\s]*(page\s+)?\d{1,4}(\s*(of|/)\s*\d{1,4})?[-–—\s]*$", re.IGNORECASE
)


@dataclass(frozen=True)
class Paragraph:
    index: int  # position in the document, starting at 0
    page: int  # page the paragraph starts on, starting at 1
    text: str


@dataclass(frozen=True)
class ExtractedDocument:
    sha256: str
    page_count: int
    paragraphs: list[Paragraph]


def normalize_text(text: str) -> str:
    """Make text comparable: fix ligatures and odd spaces, rejoin hyphenated words, collapse whitespace."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00ad", "")  # soft hyphen
    text = _HYPHEN_LINE_BREAK.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


def extract_document(data: bytes) -> ExtractedDocument:
    """Extract normalized paragraphs from a text-based PDF held in memory."""
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # third-party parser boundary: any failure means "unreadable"
        logger.warning("PDF could not be opened: %s", type(exc).__name__)
        raise ExtractionError("The PDF could not be read. It may be corrupted.") from exc

    paragraphs: list[Paragraph] = []
    try:
        with doc:
            if doc.needs_pass:
                raise EncryptedPdfError("The PDF is password-protected.")
            page_count = doc.page_count
            if page_count == 0:
                raise ExtractionError("The PDF has no pages.")

            for page_number, page in enumerate(doc, start=1):
                for block in page.get_text("blocks", sort=True):
                    if block[6] != 0:  # 0 = text block; skip images
                        continue
                    text = normalize_text(block[4])
                    if not text or _PAGE_NUMBER_ONLY.match(text):
                        continue
                    paragraphs.append(
                        Paragraph(index=len(paragraphs), page=page_number, text=text)
                    )
    except DocumentError:
        raise
    except Exception as exc:
        logger.warning("Text extraction failed: %s", type(exc).__name__)
        raise ExtractionError("Text could not be extracted from the PDF.") from exc

    if not paragraphs:
        raise NoTextFoundError(
            "No extractable text was found. Scanned PDFs are not supported."
        )

    return ExtractedDocument(
        sha256=hashlib.sha256(data).hexdigest(),
        page_count=page_count,
        paragraphs=paragraphs,
    )