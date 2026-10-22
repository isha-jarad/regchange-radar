class DocumentError(Exception):
    """Base class for problems with an uploaded document."""


class EmptyFileError(DocumentError):
    """The uploaded file contains no bytes."""


class InvalidFileTypeError(DocumentError):
    """The upload is not a PDF (wrong extension or wrong content)."""


class FileTooLargeError(DocumentError):
    """The upload exceeds the configured size limit."""


class ExtractionError(DocumentError):
    """The PDF could not be opened or its text could not be read."""


class EncryptedPdfError(ExtractionError):
    """The PDF is password-protected."""


class NoTextFoundError(ExtractionError):
    """The PDF has no extractable text (for example, a scanned document)."""