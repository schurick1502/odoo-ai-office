from fastapi import APIRouter

from app.agents.opos_agent import OPOSMatchingAgent
from app.schemas.orchestrate import OrchestrateRequest, OrchestrateResponse

router = APIRouter(prefix="/v1")

opos_agent = OPOSMatchingAgent()


@router.post("/opos/match", response_model=OrchestrateResponse)
async def opos_match(request: OrchestrateRequest) -> OrchestrateResponse:
    suggestions = await opos_agent.run(request)
    return OrchestrateResponse(
        case_id=request.case_id,
        request_id=request.request_id,
        suggestions=suggestions,
    )
