from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Shape of error bodies returned by this API (used in the API docs)."""

    detail: str