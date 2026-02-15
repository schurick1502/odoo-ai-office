from fastapi import APIRouter

from app.agents.kontierung_agent import KontierungsAgent
from app.schemas.orchestrate import OrchestrateRequest, OrchestrateResponse

router = APIRouter(prefix="/v1")

kontierung_agent = KontierungsAgent()


@router.post("/orchestrate", response_model=OrchestrateResponse)
async def orchestrate(request: OrchestrateRequest) -> OrchestrateResponse:
    suggestions = await kontierung_agent.run(request)
    return OrchestrateResponse(
        case_id=request.case_id,
        request_id=request.request_id,
        suggestions=suggestions,
    )
