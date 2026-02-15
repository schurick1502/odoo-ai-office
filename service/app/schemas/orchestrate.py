from pydantic import BaseModel


class OrchestrateRequest(BaseModel):
    case_id: int
    request_id: str
    context: dict = {}


class Suggestion(BaseModel):
    suggestion_type: str
    payload: dict
    confidence: float
    risk_score: float
    explanation: str
    requires_human: bool
    agent_name: str


class OrchestrateResponse(BaseModel):
    case_id: int
    request_id: str
    suggestions: list[Suggestion]
    status: str = "ok"
