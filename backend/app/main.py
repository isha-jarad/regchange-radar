from fastapi import FastAPI

from app.api import health

app = FastAPI(
    title="RegChange Radar",
    description=(
        "Version-aware regulatory document comparison API. Detects textual "
        "changes between two document versions and flags potential review "
        "impact using deterministic, explainable rules. Flags are review "
        "aids, not legal advice."
    ),
    version="0.1.0",
)

app.include_router(health.router)