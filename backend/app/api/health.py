from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Report that the API process is up and able to answer requests."""
    return HealthResponse(status="ok", service="regchange-radar")


@router.get("/health/db", response_model=HealthResponse)
def database_health_check(
    db: Annotated[Session, Depends(get_db)],
) -> HealthResponse:
    """Report whether the API can reach PostgreSQL."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # Deliberately generic: never leak connection details to the client.
        raise HTTPException(status_code=503, detail="Database unavailable")
    return HealthResponse(status="ok", service="database")