import os

# SAFETY: tests must never touch the real PostgreSQL database.
# This must be set BEFORE the app is imported, because app.core.config reads
# DATABASE_URL the first time it is imported (and environment variables win over .env).
os.environ["DATABASE_URL"] = "sqlite://"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import models  # noqa: E402,F401  (registers the tables on Base.metadata)
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from tests.pdf_factory import (  # noqa: E402
    SAMPLE_NEW_PARAGRAPHS,
    SAMPLE_OLD_PARAGRAPHS,
    make_pdf_bytes,
)


@pytest.fixture
def client():
    """A test client backed by a brand-new, empty in-memory database for each test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared connection, so every request sees the same data
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:  # "with" also runs the app's startup code
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture(scope="session")
def old_pdf() -> bytes:
    return make_pdf_bytes(SAMPLE_OLD_PARAGRAPHS)


@pytest.fixture(scope="session")
def new_pdf() -> bytes:
    return make_pdf_bytes(SAMPLE_NEW_PARAGRAPHS)