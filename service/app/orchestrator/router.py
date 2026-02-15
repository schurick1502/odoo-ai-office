from fastapi import APIRouter

from app.agents.kontierung_agent import KontierungsAgent
from app.agents.validation_agent import ValidationAgent
from app.schemas.orchestrate import OrchestrateRequest, OrchestrateResponse

router = APIRouter(prefix="/v1")

kontierung_agent = KontierungsAgent()
validation_agent = ValidationAgent()


@router.post("/orchestrate", response_model=OrchestrateResponse)
async def orchestrate(request: OrchestrateRequest) -> OrchestrateResponse:
    suggestions = await kontierung_agent.run(request)
    validation_results = await validation_agent.run(request, suggestions)
    return OrchestrateResponse(
        case_id=request.case_id,
        request_id=request.request_id,
        suggestions=suggestions + validation_results,
    )
