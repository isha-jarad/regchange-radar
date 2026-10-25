import hashlib
import io

import pytest

from app.services.exceptions import (
    EmptyFileError,
    EncryptedPdfError,
    ExtractionError,
    FileTooLargeError,
    InvalidFileTypeError,
    NoTextFoundError,
)
from app.services.pdf_extraction import extract_document, normalize_text
from app.services.upload_validation import read_limited, safe_display_name, validate_pdf_upload
from tests.pdf_factory import make_blank_pdf_bytes, make_encrypted_pdf_bytes, make_pdf_bytes


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  The   sponsor\n shall\u00a0submit  ", "The sponsor shall submit"),
        ("regu-\nlation of the \ufb01le", "regulation of the file"),
        ("follow-up\nitems", "follow-up items"),
        ("caf\u00e9\u00ad", "caf\u00e9"),
        ("", ""),
    ],
    ids=["whitespace", "hyphen-and-ligature", "real-hyphen-kept", "soft-hyphen", "empty"],
)
def test_normalize_text(raw, expected):
    assert normalize_text(raw) == expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("..\\..\\secret\\evil.pdf", "evil.pdf"),
        ("/etc/passwd.pdf", "passwd.pdf"),
        ("a\x00b.pdf", "ab.pdf"),
        (None, "fallback.pdf"),
        ("", "fallback.pdf"),
    ],
)
def test_safe_display_name(filename, expected):
    assert safe_display_name(filename, "fallback.pdf") == expected


def test_safe_display_name_limits_length():
    assert len(safe_display_name("a" * 300 + ".pdf", "fallback.pdf")) == 255


def test_read_limited_accepts_file_at_the_limit():
    assert read_limited(io.BytesIO(b"x" * 10), 10) == b"x" * 10


def test_read_limited_rejects_file_over_the_limit():
    with pytest.raises(FileTooLargeError):
        read_limited(io.BytesIO(b"x" * 11), 10)


@pytest.mark.parametrize(
    ("data", "filename", "error"),
    [
        (b"", "a.pdf", EmptyFileError),
        (b"%PDF-1.7", "a.txt", InvalidFileTypeError),
        (b"%PDF-1.7", None, InvalidFileTypeError),
        (b"hello world", "a.pdf", InvalidFileTypeError),
    ],
    ids=["empty", "wrong-extension", "no-filename", "wrong-content"],
)
def test_validation_rejects_bad_uploads(data, filename, error):
    with pytest.raises(error):
        validate_pdf_upload(data, filename)


def test_validation_accepts_uppercase_extension():
    validate_pdf_upload(b"%PDF-1.7 minimal", "REPORT.PDF")


def test_extracts_paragraphs_and_drops_page_numbers():
    pdf = make_pdf_bytes(
        ["1. Scope", "The sponsor may submit the report.", "Page 1", "Records must be kept."]
    )
    document = extract_document(pdf)
    assert [p.text for p in document.paragraphs] == [
        "1. Scope",
        "The sponsor may submit the report.",
        "Records must be kept.",
    ]
    assert [p.index for p in document.paragraphs] == [0, 1, 2]
    assert document.page_count == 1


def test_long_paragraph_that_wraps_is_one_paragraph():
    document = extract_document(make_pdf_bytes(["word " * 60]))
    assert len(document.paragraphs) == 1
    assert document.paragraphs[0].text == " ".join(["word"] * 60)


def test_paragraphs_record_their_page_number():
    pdf = make_pdf_bytes([f"Paragraph number {i}. " + "word " * 40 for i in range(30)])
    document = extract_document(pdf)
    assert document.page_count >= 2
    assert len(document.paragraphs) == 30
    assert document.paragraphs[0].page == 1
    assert document.paragraphs[-1].page == document.page_count


def test_sha256_matches_the_uploaded_bytes():
    pdf = make_pdf_bytes(["Some text."])
    assert extract_document(pdf).sha256 == hashlib.sha256(pdf).hexdigest()


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (b"%PDF-1.7 this is not really a pdf", ExtractionError),
        (make_blank_pdf_bytes(), NoTextFoundError),
        (make_encrypted_pdf_bytes(), EncryptedPdfError),
    ],
    ids=["corrupt", "no-text", "encrypted"],
)
def test_extraction_failures(data, error):
    with pytest.raises(error):
        extract_document(data)