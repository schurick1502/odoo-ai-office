import structlog

from app.agents.document_parser import DocumentParserAgent
from app.llm import llm_client
from app.schemas.enrich import EnrichRequest, EnrichSuggestion

logger = structlog.get_logger()

SYSTEM_PROMPT = """\
Du bist ein Dokumenten-Klassifikator für eine deutsche Buchhaltung.
Analysiere die folgenden Dokumentinformationen und extrahiere strukturierte Daten.

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt:
{
  "document_type": "invoice|credit_note|receipt|contract|reminder|other",
  "invoice_date": "YYYY-MM-DD oder null",
  "invoice_number": "Rechnungsnummer oder null",
  "amount_total": "Betrag als Zahl oder null",
  "partner_name": "Lieferantenname oder null",
  "description": "Kurzbeschreibung des Dokuments"
}

Setze Felder auf null wenn du dir nicht sicher bist."""

USER_PROMPT = """\
Dokumente:
{documents}

Bekannter Kontext:
- Lieferant: {partner_name}
- Periode: {period}

Klassifiziere diese Dokumente und extrahiere alle erkennbaren Felder."""

# LLM confidence per field (lower than context, higher than filename regex)
LLM_CONFIDENCE = {
    "document_type": 0.80,
    "invoice_date": 0.75,
    "invoice_number": 0.75,
    "amount_total": 0.70,
    "partner_name": 0.70,
    "description": 0.65,
}


class EnrichmentAgent:
    """Orchestrates document parsing and LLM-based enrichment for a case.

    Pipeline:
    1. Run DocumentParserAgent (regex-based extraction from filenames)
    2. Run LLM classification (document type, additional metadata)
    3. Deduplicate and consolidate (highest confidence wins per field)
    """

    def __init__(self):
        self.parser = DocumentParserAgent()

    async def run(self, request: EnrichRequest) -> list[EnrichSuggestion]:
        # Step 1: Regex-based extraction
        raw_suggestions = await self.parser.run(request)

        # Step 2: LLM-based extraction
        llm_suggestions = await self._extract_with_llm(request)
        raw_suggestions.extend(llm_suggestions)

        # Step 3: Deduplicate - keep highest confidence per field
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

    async def _extract_with_llm(self, request: EnrichRequest) -> list[EnrichSuggestion]:
        """Use LLM to classify document type and extract metadata."""
        if not request.documents:
            return []

        docs_text = "\n".join(
            f"  - {doc.filename} ({doc.mimetype}, {doc.size_bytes} bytes)"
            for doc in request.documents
        )

        user_prompt = USER_PROMPT.format(
            documents=docs_text,
            partner_name=request.context.get("partner_name", "Unbekannt"),
            period=request.context.get("period", "unbekannt"),
        )

        response = await llm_client.complete(SYSTEM_PROMPT, user_prompt)
        if not response:
            logger.info("llm_enrichment_skipped", reason="no_response")
            return []

        parsed = llm_client.parse_json(response)
        if not parsed:
            logger.warning("llm_enrichment_parse_error", raw=response[:200])
            return []

        suggestions = []
        for field, value in parsed.items():
            if value is None or value == "null" or field not in LLM_CONFIDENCE:
                continue
            suggestions.append(
                EnrichSuggestion(
                    field=field,
                    value=str(value),
                    confidence=LLM_CONFIDENCE[field],
                    source="llm",
                )
            )

        logger.info("llm_enrichment_success", fields=len(suggestions))
        return suggestions
