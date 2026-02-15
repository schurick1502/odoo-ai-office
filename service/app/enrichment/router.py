from fastapi import APIRouter

from app.agents.enrichment_agent import EnrichmentAgent
from app.schemas.enrich import EnrichRequest, EnrichResponse

router = APIRouter(prefix="/v1")

enrichment_agent = EnrichmentAgent()


@router.post("/enrich", response_model=EnrichResponse)
async def enrich(request: EnrichRequest) -> EnrichResponse:
    suggestions = await enrichment_agent.run(request)
    return EnrichResponse(
        case_id=request.case_id,
        request_id=request.request_id,
        suggestions=suggestions,
    )
