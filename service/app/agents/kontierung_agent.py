from app.schemas.orchestrate import OrchestrateRequest, Suggestion

# SKR03 common expense accounts
SKR03_ACCOUNTS = {
    "6300": "Sonstige betriebliche Aufwendungen",
    "4400": "Erlöse 19% USt",
    "4910": "Fremdleistungen",
    "4200": "Raumkosten",
    "4500": "Fahrzeugkosten",
    "4600": "Werbekosten",
    "4650": "Bewirtungskosten",
    "4800": "Reparaturen und Instandhaltung",
    "4900": "Verschiedene betriebliche Aufwendungen",
    "4930": "Bürobedarf",
    "4940": "Zeitschriften und Bücher",
    "4946": "EDV-Kosten",
    "4950": "Rechts- und Beratungskosten",
    "4955": "Buchführungskosten",
    "4960": "Miete für Geschäftsräume",
    "4970": "Nebenkosten des Geldverkehrs",
    "6800": "Abschreibungen",
}

# Standard accounts
VORSTEUER_19 = "1576"  # Abziehbare Vorsteuer 19%
VORSTEUER_7 = "1571"   # Abziehbare Vorsteuer 7%
VERBINDLICHKEITEN = "1600"  # Verbindlichkeiten aus L.u.L.
FALLBACK_EXPENSE = "6300"  # Sonstige betriebliche Aufwendungen


class KontierungsAgent:
    """Rule-based account assignment agent using SKR03 chart of accounts.

    For MVP, uses policy matching and hardcoded SKR03 defaults.
    Future versions will integrate LLM-based classification.
    """

    async def run(self, request: OrchestrateRequest) -> list[Suggestion]:
        """Generate accounting entry suggestions from case context."""
        context = request.context
        amount_total = self._parse_amount(context.get("amount_total"))
        tax_rate = context.get("tax_rate", 0.19)
        policies = context.get("policies", [])
        partner_name = context.get("partner_name", "")

        # Step 1: Find matching policy
        expense_account, policy_matched = self._match_policy(policies)

        # Step 2: Calculate net/tax split
        if amount_total > 0:
            net_amount = round(amount_total / (1 + tax_rate), 2)
            tax_amount = round(amount_total - net_amount, 2)
        else:
            net_amount = 100.00
            tax_amount = 19.00
            amount_total = 119.00

        # Step 3: Determine tax account
        vorsteuer_account = VORSTEUER_19 if tax_rate >= 0.19 else VORSTEUER_7

        # Step 4: Build accounting lines
        lines = [
            {
                "account": expense_account,
                "debit": net_amount,
                "credit": 0.00,
                "description": SKR03_ACCOUNTS.get(expense_account, "Aufwand"),
            },
            {
                "account": vorsteuer_account,
                "debit": tax_amount,
                "credit": 0.00,
                "description": "Vorsteuer %d%%" % int(tax_rate * 100),
            },
            {
                "account": VERBINDLICHKEITEN,
                "debit": 0.00,
                "credit": amount_total,
                "description": "Verbindlichkeiten %s" % (partner_name or ""),
            },
        ]

        # Step 5: Confidence scoring
        if policy_matched:
            confidence = 0.92
            risk_score = 0.05
            explanation = "Kontierung via Supplier-Policy: Konto %s" % expense_account
        elif amount_total > 0:
            confidence = 0.75
            risk_score = 0.15
            explanation = "Regelbasierte Kontierung (SKR03): Konto %s" % expense_account
        else:
            confidence = 0.55
            risk_score = 0.30
            explanation = "Fallback-Kontierung: Konto %s (kein Betrag erkannt)" % expense_account

        return [
            Suggestion(
                suggestion_type="accounting_entry",
                payload={
                    "lines": lines,
                    "amount": amount_total,
                    "net_amount": net_amount,
                    "tax_amount": tax_amount,
                    "tax_rate": tax_rate,
                    "expense_account": expense_account,
                    "skr_chart": "SKR03",
                    "policy_matched": policy_matched,
                },
                confidence=confidence,
                risk_score=risk_score,
                explanation=explanation,
                requires_human=not policy_matched,
                agent_name="kontierung_agent",
            )
        ]

    def _match_policy(self, policies: list[dict]) -> tuple[str, bool]:
        """Match supplier or company policies to determine expense account.

        Returns (account_code, was_policy_matched).
        Priority: supplier policy > company policy > SKR03 fallback.
        """
        # Sort: supplier policies first, then company
        for policy in sorted(policies, key=lambda p: 0 if p.get("scope") == "supplier" else 1):
            rules = policy.get("rules", {})
            if rules.get("default_account"):
                return rules["default_account"], True

        return FALLBACK_EXPENSE, False

    def _parse_amount(self, value) -> float:
        """Parse amount from context, handling string and numeric values."""
        if value is None:
            return 0.0
        try:
            return float(str(value).replace(",", "."))
        except (ValueError, TypeError):
            return 0.0
