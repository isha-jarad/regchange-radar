from typing import BinaryIO

from app.services.exceptions import EmptyFileError, FileTooLargeError, InvalidFileTypeError

PDF_MAGIC = b"%PDF-"


def read_limited(fileobj: BinaryIO, max_bytes: int) -> bytes:
    """Read an upload, refusing anything larger than max_bytes.

    Reads at most max_bytes + 1, so memory use stays bounded even for huge uploads.
    """
    data = fileobj.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise FileTooLargeError("The file exceeds the maximum allowed size.")
    return data


def validate_pdf_upload(data: bytes, filename: str | None) -> None:
    """Check that an upload looks like a PDF. Does not parse it."""
    if not data:
        raise EmptyFileError("The uploaded file is empty.")
    if not filename or not filename.lower().endswith(".pdf"):
        raise InvalidFileTypeError("Only .pdf files are accepted.")
    # The PDF spec allows a little junk before the header, so look in the first 1 KB.
    if PDF_MAGIC not in data[:1024]:
        raise InvalidFileTypeError("The file content is not a valid PDF.")


def safe_display_name(filename: str | None, fallback: str) -> str:
    """Return a clean, display-only file name (never used as a filesystem path)."""
    name = (filename or "").replace("\\", "/").split("/")[-1]
    name = "".join(ch for ch in name if ch.isprintable())
    return name[:255] or fallback