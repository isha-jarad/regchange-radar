from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Shape of the response returned by the health-check endpoint."""

    status: str
    service: str