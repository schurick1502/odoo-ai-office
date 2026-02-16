import structlog

from app.llm import llm_client
from app.schemas.orchestrate import OrchestrateRequest, Suggestion

logger = structlog.get_logger()

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

SYSTEM_PROMPT = """\
Du bist ein erfahrener deutscher Buchhalter. Deine Aufgabe ist es, \
Eingangsrechnungen nach dem SKR03-Kontenrahmen zu klassifizieren.

Verfügbare Aufwandskonten:
{accounts}

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt (kein weiterer Text):
{{"account": "<4-stellige Kontonummer>", "description": "<Kontenbezeichnung>", "reasoning": "<kurze Begründung>"}}
"""

USER_PROMPT = """\
Lieferant: {partner_name}
Bruttobetrag: {amount:.2f} EUR
MwSt-Satz: {tax_rate_pct}%
Periode: {period}
{extra}
Welches SKR03-Aufwandskonto passt am besten?"""


class KontierungsAgent:
    """Hybrid account assignment agent: LLM classification with rule-based fallback.

    1. Tries LLM-based classification using partner name and invoice context
    2. Falls back to policy matching or SKR03 default on LLM failure
    """

    def __init__(self):
        accounts_text = "\n".join(
            f"  {code}: {name}" for code, name in sorted(SKR03_ACCOUNTS.items())
        )
        self._system_prompt = SYSTEM_PROMPT.format(accounts=accounts_text)

    async def run(self, request: OrchestrateRequest) -> list[Suggestion]:
        context = request.context
        amount_total = self._parse_amount(context.get("amount_total"))
        tax_rate = context.get("tax_rate", 0.19)
        policies = context.get("policies", [])
        partner_name = context.get("partner_name", "")

        # Step 1: Policy match (highest priority)
        policy_account, policy_matched = self._match_policy(policies)

        # Step 2: Calculate net/tax split
        has_amount = amount_total > 0
        if has_amount:
            net_amount = round(amount_total / (1 + tax_rate), 2)
            tax_amount = round(amount_total - net_amount, 2)
        else:
            net_amount = 100.00
            tax_amount = 19.00
            amount_total = 119.00

        # Step 3: LLM classification (if no policy match)
        llm_account = None
        llm_reasoning = None
        if not policy_matched:
            llm_account, llm_reasoning = await self._classify_with_llm(
                partner_name, amount_total, tax_rate, context,
            )

        # Step 4: Determine final expense account
        if policy_matched:
            expense_account = policy_account
            confidence = 0.92
            risk_score = 0.05
            explanation = "Kontierung via Supplier-Policy: Konto %s (%s)" % (
                expense_account, SKR03_ACCOUNTS.get(expense_account, ""),
            )
        elif llm_account:
            expense_account = llm_account
            confidence = 0.88
            risk_score = 0.08
            explanation = "LLM-Kontierung: Konto %s (%s)\n\n%s" % (
                expense_account,
                SKR03_ACCOUNTS.get(expense_account, ""),
                llm_reasoning or "",
            )
        elif has_amount:
            expense_account = FALLBACK_EXPENSE
            confidence = 0.55
            risk_score = 0.30
            explanation = "Fallback-Kontierung (SKR03): Konto %s – kein Policy-Match, LLM nicht verfügbar" % expense_account
        else:
            expense_account = FALLBACK_EXPENSE
            confidence = 0.40
            risk_score = 0.40
            explanation = "Fallback-Kontierung: Konto %s (kein Betrag, kein Policy-Match)" % expense_account

        # Step 5: Build accounting lines
        vorsteuer_account = VORSTEUER_19 if tax_rate >= 0.19 else VORSTEUER_7
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
                    "llm_classified": llm_account is not None,
                },
                confidence=confidence,
                risk_score=risk_score,
                explanation=explanation,
                requires_human=not policy_matched,
                agent_name="kontierung_agent",
            )
        ]

    async def _classify_with_llm(
        self,
        partner_name: str,
        amount: float,
        tax_rate: float,
        context: dict,
    ) -> tuple[str | None, str | None]:
        """Ask LLM to classify the expense account.

        Returns (account_code, reasoning) or (None, None) on failure.
        """
        extra_parts = []
        if context.get("invoice_number"):
            extra_parts.append(f"Rechnungsnummer: {context['invoice_number']}")
        if context.get("description"):
            extra_parts.append(f"Beschreibung: {context['description']}")

        user_prompt = USER_PROMPT.format(
            partner_name=partner_name or "Unbekannt",
            amount=amount,
            tax_rate_pct=int(tax_rate * 100),
            period=context.get("period", "unbekannt"),
            extra="\n".join(extra_parts),
        )

        response = await llm_client.complete(self._system_prompt, user_prompt)
        if not response:
            logger.info("llm_classification_skipped", reason="no_response")
            return None, None

        parsed = llm_client.parse_json(response)
        if not parsed:
            logger.warning("llm_classification_parse_error", raw=response[:200])
            return None, None

        account = str(parsed.get("account", "")).strip()
        if account not in SKR03_ACCOUNTS:
            logger.warning("llm_classification_invalid_account", account=account)
            return None, None

        reasoning = parsed.get("reasoning", "")
        logger.info("llm_classification_success", account=account, reasoning=reasoning)
        return account, reasoning

    def _match_policy(self, policies: list[dict]) -> tuple[str, bool]:
        for policy in sorted(policies, key=lambda p: 0 if p.get("scope") == "supplier" else 1):
            rules = policy.get("rules", {})
            if rules.get("default_account"):
                return rules["default_account"], True
        return FALLBACK_EXPENSE, False

    def _parse_amount(self, value) -> float:
        if value is None:
            return 0.0
        try:
            return float(str(value).replace(",", "."))
        except (ValueError, TypeError):
            return 0.0
