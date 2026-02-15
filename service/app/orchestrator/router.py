from fastapi import APIRouter

from app.agents.dummy_agent import DummyAgent
from app.schemas.orchestrate import OrchestrateRequest, OrchestrateResponse

router = APIRouter(prefix="/v1")

dummy_agent = DummyAgent()


@router.post("/orchestrate", response_model=OrchestrateResponse)
async def orchestrate(request: OrchestrateRequest) -> OrchestrateResponse:
    suggestions = await dummy_agent.run(request)
    return OrchestrateResponse(
        case_id=request.case_id,
        request_id=request.request_id,
        suggestions=suggestions,
    )
