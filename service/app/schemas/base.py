from pydantic import BaseModel


class ComponentHealth(BaseModel):
    """Health status of an individual component."""
    status: str
    latency_ms: float | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    checks: dict[str, ComponentHealth] = {}
