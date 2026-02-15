from app.schemas.orchestrate import OrchestrateRequest, Suggestion

# Valid SKR03 account code ranges
VALID_SKR03_RANGES = [
    (200, 999),    # Anlagevermögen
    (1000, 1999),  # Finanz- und Privatkonten
    (2000, 2999),  # Abgrenzungskonten
    (3000, 3999),  # Wareneingang/Bestand
    (4000, 4999),  # Betriebliche Aufwendungen
    (6000, 6999),  # Betriebliche Aufwendungen (Fortsetzung)
    (7000, 7999),  # Bestände
    (8000, 8999),  # Erlöse
    (9000, 9999),  # Vortrags-/Statistische Konten
]


class ValidationAgent:
    """Validates accounting entry suggestions against compliance rules.

    Checks balanced entries, valid account codes, and policy thresholds.
    Runs after KontierungsAgent in the orchestrator pipeline.
    """

    async def run(
        self,
        request: OrchestrateRequest,
        suggestions: list[Suggestion],
    ) -> list[Suggestion]:
        """Validate suggestions and return a validation-type suggestion."""
        context = request.context
        policies = context.get("policies", [])
        errors: list[str] = []
        warnings: list[str] = []

        entry_suggestions = [
            s for s in suggestions if s.suggestion_type == "accounting_entry"
        ]

        if not entry_suggestions:
            errors.append("No accounting entry suggestion to validate.")
            return [self._build_result(errors, warnings, passed=False)]

        for entry in entry_suggestions:
            lines = entry.payload.get("lines", [])
            self._check_lines_complete(lines, errors, warnings)
            self._check_balanced(lines, errors)
            self._check_account_codes(lines, warnings)
            self._check_thresholds(entry, policies, errors, warnings)

        passed = len(errors) == 0
        return [self._build_result(errors, warnings, passed=passed)]

    def _check_lines_complete(self, lines: list[dict], errors: list[str], warnings: list[str]):
        """Every line must have account and nonzero debit or credit."""
        for i, line in enumerate(lines):
            if not line.get("account"):
                errors.append(f"Line {i + 1}: missing account code.")
            debit = line.get("debit", 0.0)
            credit = line.get("credit", 0.0)
            if debit <= 0 and credit <= 0:
                errors.append(f"Line {i + 1}: debit or credit must be > 0.")
            if not line.get("description"):
                warnings.append(f"Line {i + 1}: missing description.")

    def _check_balanced(self, lines: list[dict], errors: list[str]):
        """Sum of debits must equal sum of credits."""
        total_debit = sum(line.get("debit", 0.0) for line in lines)
        total_credit = sum(line.get("credit", 0.0) for line in lines)
        if abs(total_debit - total_credit) > 0.01:
            errors.append(
                f"Entry not balanced: debit={total_debit:.2f}, credit={total_credit:.2f}"
            )

    def _check_account_codes(self, lines: list[dict], warnings: list[str]):
        """Check that account codes are valid SKR03 numbers."""
        for i, line in enumerate(lines):
            code = line.get("account", "")
            try:
                code_int = int(code)
            except (ValueError, TypeError):
                warnings.append(f"Line {i + 1}: account '{code}' is not a valid number.")
                continue
            if not any(lo <= code_int <= hi for lo, hi in VALID_SKR03_RANGES):
                warnings.append(f"Line {i + 1}: account '{code}' outside SKR03 ranges.")

    def _check_thresholds(
        self,
        entry: Suggestion,
        policies: list[dict],
        errors: list[str],
        warnings: list[str],
    ):
        """Check confidence and risk against policy thresholds."""
        confidence_threshold = 0.8
        risk_score_max = 0.3
        for policy in policies:
            rules = policy.get("rules", {})
            if "confidence_threshold" in rules:
                confidence_threshold = rules["confidence_threshold"]
            if "risk_score_max" in rules:
                risk_score_max = rules["risk_score_max"]

        if entry.confidence < confidence_threshold:
            warnings.append(
                f"Confidence {entry.confidence:.2f} below threshold {confidence_threshold:.2f}."
            )

        if entry.risk_score > risk_score_max:
            errors.append(
                f"Risk score {entry.risk_score:.2f} exceeds maximum {risk_score_max:.2f}."
            )

    def _build_result(
        self,
        errors: list[str],
        warnings: list[str],
        passed: bool,
    ) -> Suggestion:
        """Build a validation-type suggestion."""
        status = "pass" if passed else "fail"
        explanation_parts = []
        if errors:
            explanation_parts.append("**Errors:**\n" + "\n".join(f"- {e}" for e in errors))
        if warnings:
            explanation_parts.append("**Warnings:**\n" + "\n".join(f"- {w}" for w in warnings))
        if not explanation_parts:
            explanation_parts.append("All validation checks passed.")

        return Suggestion(
            suggestion_type="validation",
            payload={
                "status": status,
                "errors": errors,
                "warnings": warnings,
            },
            confidence=1.0 if passed else 0.0,
            risk_score=0.0 if passed else 1.0,
            explanation="\n\n".join(explanation_parts),
            requires_human=not passed,
            agent_name="validation_agent",
        )
