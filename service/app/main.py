from fastapi import FastAPI

from app.orchestrator.router import router as orchestrator_router
from app.enrichment.router import router as enrichment_router
from app.opos.router import router as opos_router
from app.schemas.base import HealthResponse

app = FastAPI(
    title="AI Office Service",
    version="0.2.0",
)

app.include_router(orchestrator_router)
app.include_router(enrichment_router)
app.include_router(opos_router)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version="0.2.0")
