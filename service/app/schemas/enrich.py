from pydantic import BaseModel


class DocumentMeta(BaseModel):
    """Metadata about a single document attached to a case."""
    filename: str
    mimetype: str
    size_bytes: int = 0


class EnrichRequest(BaseModel):
    """Request to enrich a case with document metadata extraction."""
    case_id: int
    request_id: str
    documents: list[DocumentMeta] = []
    context: dict = {}


class EnrichSuggestion(BaseModel):
    """A single enrichment suggestion extracted from document analysis."""
    field: str
    value: str
    confidence: float
    source: str


class EnrichResponse(BaseModel):
    """Response containing enrichment suggestions for a case."""
    case_id: int
    request_id: str
    suggestions: list[EnrichSuggestion]
    status: str = "ok"
