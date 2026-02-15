from app.schemas.orchestrate import OrchestrateRequest, Suggestion


class DummyAgent:
    async def run(self, request: OrchestrateRequest) -> list[Suggestion]:
        return [
            Suggestion(
                suggestion_type="accounting_entry",
                payload={
                    "lines": [
                        {"account": "4400", "debit": 119.00, "credit": 0.00},
                        {"account": "1200", "debit": 0.00, "credit": 119.00},
                    ],
                    "amount": 119.00,
                },
                confidence=0.85,
                risk_score=0.1,
                explanation="Dummy suggestion for MVP testing",
                requires_human=True,
                agent_name="dummy_agent",
            )
        ]
