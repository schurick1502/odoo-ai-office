import re

from app.schemas.enrich import EnrichRequest, EnrichSuggestion


class DocumentParserAgent:
    """MVP document parser that extracts metadata from filenames and context.

    For MVP, this uses rule-based extraction from filenames.
    Future versions will integrate OCR and LLM-based extraction.
    """

    DATE_PATTERN = re.compile(r"(\d{4}[-_]?\d{2}[-_]?\d{2})")
    AMOUNT_PATTERN = re.compile(r"(\d+[.,]\d{2})")
    INVOICE_NUMBER_PATTERN = re.compile(
        r"(?:RE|INV|RG|RNR?)[-_]?(\d+)", re.IGNORECASE
    )

    async def run(self, request: EnrichRequest) -> list[EnrichSuggestion]:
        """Extract metadata from document filenames and context."""
        suggestions: list[EnrichSuggestion] = []

        for doc in request.documents:
            suggestions.extend(self._parse_filename(doc.filename))

        suggestions.extend(self._parse_context(request.context))

        return suggestions

    def _parse_filename(self, filename: str) -> list[EnrichSuggestion]:
        """Extract structured data from a document filename."""
        results: list[EnrichSuggestion] = []
        name_part = filename.rsplit(".", 1)[0] if "." in filename else filename

        date_match = self.DATE_PATTERN.search(name_part)
        if date_match:
            raw_date = date_match.group(1).replace("_", "-")
            results.append(EnrichSuggestion(
                field="invoice_date",
                value=raw_date,
                confidence=0.6,
                source="filename_parser",
            ))

        inv_match = self.INVOICE_NUMBER_PATTERN.search(name_part)
        if inv_match:
            results.append(EnrichSuggestion(
                field="invoice_number",
                value=inv_match.group(0),
                confidence=0.7,
                source="filename_parser",
            ))

        amount_match = self.AMOUNT_PATTERN.search(name_part)
        if amount_match:
            results.append(EnrichSuggestion(
                field="amount_total",
                value=amount_match.group(1).replace(",", "."),
                confidence=0.5,
                source="filename_parser",
            ))

        return results

    def _parse_context(self, context: dict) -> list[EnrichSuggestion]:
        """Extract enrichment suggestions from case context."""
        results: list[EnrichSuggestion] = []

        if context.get("partner_name"):
            results.append(EnrichSuggestion(
                field="partner_name",
                value=context["partner_name"],
                confidence=0.9,
                source="context",
            ))

        if context.get("period"):
            results.append(EnrichSuggestion(
                field="period",
                value=context["period"],
                confidence=0.95,
                source="context",
            ))

        return results
