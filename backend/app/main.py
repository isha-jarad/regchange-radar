from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import comparisons, health
from app.services.impact_rules import get_default_ruleset


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_default_ruleset()  # fail fast at startup if the rules file is invalid
    yield


app = FastAPI(
    title="RegChange Radar",
    description=(
        "Version-aware regulatory document comparison API. Detects textual "
        "changes between two document versions and flags potential review "
        "impact using deterministic, explainable rules. Flags are review "
        "aids, not legal advice."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(comparisons.router)