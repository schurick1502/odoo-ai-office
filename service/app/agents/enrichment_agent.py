from app.agents.document_parser import DocumentParserAgent
from app.schemas.enrich import EnrichRequest, EnrichSuggestion


class EnrichmentAgent:
    """Orchestrates document parsing and enrichment for a case.

    Coordinates the DocumentParserAgent and applies business rules
    to produce a consolidated set of enrichment suggestions.
    """

    def __init__(self):
        self.parser = DocumentParserAgent()

    async def run(self, request: EnrichRequest) -> list[EnrichSuggestion]:
        """Run the enrichment pipeline.

        1. Run DocumentParserAgent to extract raw metadata
        2. Deduplicate and consolidate suggestions
        3. Return sorted by confidence (highest first)
        """
        raw_suggestions = await self.parser.run(request)

        # Deduplicate: keep highest confidence per field
        best_by_field: dict[str, EnrichSuggestion] = {}
        for suggestion in raw_suggestions:
            existing = best_by_field.get(suggestion.field)
            if existing is None or suggestion.confidence > existing.confidence:
                best_by_field[suggestion.field] = suggestion

        return sorted(
            best_by_field.values(),
            key=lambda s: s.confidence,
            reverse=True,
        )
