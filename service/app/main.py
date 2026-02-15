from fastapi import FastAPI

from app.orchestrator.router import router as orchestrator_router
from app.schemas.base import HealthResponse

app = FastAPI(
    title="AI Office Service",
    version="0.1.0",
)

app.include_router(orchestrator_router)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0")
