import time

import structlog
from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator

from app.logging_config import setup_logging
from app.llm import llm_client
from app.orchestrator.router import router as orchestrator_router
from app.enrichment.router import router as enrichment_router
from app.opos.router import router as opos_router
from app.schemas.base import ComponentHealth, HealthResponse

setup_logging()
logger = structlog.get_logger()

app = FastAPI(
    title="AI Office Service",
    version="0.3.0",
)

# Prometheus metrics: auto-instruments all endpoints
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

app.include_router(orchestrator_router)
app.include_router(enrichment_router)
app.include_router(opos_router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every request with structlog context."""
    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round(elapsed_ms, 2),
    )
    return response


@app.on_event("shutdown")
async def shutdown():
    await llm_client.close()


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Enhanced health check with component readiness."""
    llm_ok = await llm_client.health_check()
    checks = {
        "self": ComponentHealth(status="ok"),
        "llm": ComponentHealth(
            status="ok" if llm_ok else "degraded",
            detail=f"{llm_client.provider}:{llm_client.model}",
        ),
    }
    all_ok = all(c.status == "ok" for c in checks.values())
    return HealthResponse(
        status="ok" if all_ok else "degraded",
        version="0.4.0",
        checks=checks,
    )
