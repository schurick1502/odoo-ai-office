"""OPOS (Offene-Posten-Abstimmung) matching agent.

Rule-based open item matching for receivables/payables reconciliation.
MVP strategies: combined (amount+ref), exact_amount, reference_only.
"""

import re

from app.schemas.orchestrate import OrchestrateRequest, Suggestion

# Prefixes to strip from references for normalization
_REF_PREFIXES = re.compile(r"^(re|inv|rg|rnr)[-_]?", re.IGNORECASE)


class OPOSMatchingAgent:
    """Match open debit/credit items for reconciliation."""

    async def run(self, request: OrchestrateRequest) -> list[Suggestion]:
        context = request.context
        open_lines = context.get("open_lines", [])

        debit_lines = [ln for ln in open_lines if ln.get("balance", 0) > 0]
        credit_lines = [ln for ln in open_lines if ln.get("balance", 0) < 0]

        matches: list[dict] = []
        used_debit: set[int] = set()
        used_credit: set[int] = set()

        # Priority 1: combined (amount + reference)
        self._match_combined(debit_lines, credit_lines, matches, used_debit, used_credit)
        # Priority 2: exact amount only
        self._match_exact_amount(debit_lines, credit_lines, matches, used_debit, used_credit)
        # Priority 3: reference only
        self._match_reference(debit_lines, credit_lines, matches, used_debit, used_credit)

        unmatched_debit = [ln["id"] for ln in debit_lines if ln["id"] not in used_debit]
        unmatched_credit = [ln["id"] for ln in credit_lines if ln["id"] not in used_credit]

        if not matches:
            return [Suggestion(
                suggestion_type="reconciliation",
                payload={"matches": [], "unmatched_debit": unmatched_debit, "unmatched_credit": unmatched_credit},
                confidence=0.0,
                risk_score=0.0,
                explanation="No matching open items found.",
                requires_human=True,
                agent_name="opos_agent",
            )]

        avg_conf = sum(m["confidence"] for m in matches) / len(matches)
        return [Suggestion(
            suggestion_type="reconciliation",
            payload={
                "matches": matches,
                "unmatched_debit": unmatched_debit,
                "unmatched_credit": unmatched_credit,
            },
            confidence=round(avg_conf, 2),
            risk_score=round(1.0 - avg_conf, 2),
            explanation="Found %d match(es). %d debit and %d credit lines unmatched." % (
                len(matches), len(unmatched_debit), len(unmatched_credit),
            ),
            requires_human=True,
            agent_name="opos_agent",
        )]

    # ── Matching strategies ───────────────────────────────────────────

    def _match_combined(self, debits, credits, matches, used_d, used_c):
        """Match by exact amount AND matching reference (highest confidence)."""
        for d in debits:
            if d["id"] in used_d:
                continue
            for c in credits:
                if c["id"] in used_c:
                    continue
                if self._amounts_equal(d, c) and self._refs_match(d.get("ref", ""), c.get("ref", "")):
                    amount = min(abs(d.get("amount_residual", d["balance"])),
                                 abs(c.get("amount_residual", c["balance"])))
                    matches.append({
                        "debit_line_id": d["id"],
                        "credit_line_id": c["id"],
                        "amount": amount,
                        "match_type": "combined",
                        "confidence": 0.95,
                        "reason": "Exact amount (%.2f) and reference match." % amount,
                    })
                    used_d.add(d["id"])
                    used_c.add(c["id"])
                    break

    def _match_exact_amount(self, debits, credits, matches, used_d, used_c):
        """Match by exact amount only."""
        for d in debits:
            if d["id"] in used_d:
                continue
            for c in credits:
                if c["id"] in used_c:
                    continue
                if self._amounts_equal(d, c):
                    amount = min(abs(d.get("amount_residual", d["balance"])),
                                 abs(c.get("amount_residual", c["balance"])))
                    matches.append({
                        "debit_line_id": d["id"],
                        "credit_line_id": c["id"],
                        "amount": amount,
                        "match_type": "exact_amount",
                        "confidence": 0.80,
                        "reason": "Exact amount match (%.2f)." % amount,
                    })
                    used_d.add(d["id"])
                    used_c.add(c["id"])
                    break

    def _match_reference(self, debits, credits, matches, used_d, used_c):
        """Match by reference only (different amounts)."""
        for d in debits:
            if d["id"] in used_d:
                continue
            for c in credits:
                if c["id"] in used_c:
                    continue
                if self._refs_match(d.get("ref", ""), c.get("ref", "")):
                    amount = min(abs(d.get("amount_residual", d["balance"])),
                                 abs(c.get("amount_residual", c["balance"])))
                    matches.append({
                        "debit_line_id": d["id"],
                        "credit_line_id": c["id"],
                        "amount": amount,
                        "match_type": "reference",
                        "confidence": 0.60,
                        "reason": "Reference match ('%s')." % d.get("ref", ""),
                    })
                    used_d.add(d["id"])
                    used_c.add(c["id"])
                    break

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _amounts_equal(debit_line: dict, credit_line: dict) -> bool:
        d_amt = abs(debit_line.get("amount_residual", debit_line.get("balance", 0)))
        c_amt = abs(credit_line.get("amount_residual", credit_line.get("balance", 0)))
        return abs(d_amt - c_amt) < 0.01

    @staticmethod
    def _refs_match(ref1: str, ref2: str) -> bool:
        if not ref1 or not ref2:
            return False
        norm1 = _REF_PREFIXES.sub("", ref1.strip().lower().replace("-", "").replace("_", ""))
        norm2 = _REF_PREFIXES.sub("", ref2.strip().lower().replace("-", "").replace("_", ""))
        if not norm1 or not norm2:
            return False
        return norm1 == norm2 or norm1 in norm2 or norm2 in norm1
