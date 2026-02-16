"""Shared test fixtures for MCP server tests."""


SAMPLE_JOB = {
    "id": 42,
    "status": "approved",
    "document_data": {
        "document_type": "Rechnung",
        "sender_name": "Test Lieferant GmbH",
        "sender_address": "Teststr. 1, 12345 Berlin",
        "date_document": "2024-01-15",
        "date_due": "2024-02-15",
        "invoice_number": "RE-2024-001",
        "total_gross": 119.00,
        "total_net": 100.00,
        "vat_amount": 19.00,
        "vat_rate": 0.19,
        "confidence": 0.92,
        "accounting_suggestion": {
            "booking_account": "6300",
            "counter_account": "1600",
            "tax_key": "19",
            "booking_text": "Büromaterial",
            "confidence": 0.88,
        },
        "line_items": [
            {
                "position": 1,
                "description": "Druckerpapier A4",
                "quantity": 10,
                "unit_price_net": 5.00,
                "line_total_net": 50.00,
                "vat_rate": 0.19,
            },
            {
                "position": 2,
                "description": "Kugelschreiber",
                "quantity": 20,
                "unit_price_net": 2.50,
                "line_total_net": 50.00,
                "vat_rate": 0.19,
            },
        ],
    },
}

SAMPLE_BOOKINGS = [
    {
        "id": 1,
        "job_id": 42,
        "debit_account": "6300",
        "credit_account": "1600",
        "amount": 100.00,
        "tax_key": "9",
        "booking_text": "Büromaterial",
        "is_approved": True,
    },
    {
        "id": 2,
        "job_id": 42,
        "debit_account": "1576",
        "credit_account": "1600",
        "amount": 19.00,
        "tax_key": "0",
        "booking_text": "Vorsteuer 19%",
        "is_approved": True,
    },
]

SAMPLE_POSITIONS = [
    {
        "id": 1,
        "job_id": 42,
        "position": 1,
        "description": "Druckerpapier A4",
        "quantity": 10,
        "unit_price_net": 5.00,
        "line_total_net": 50.00,
        "vat_rate": 0.19,
    },
    {
        "id": 2,
        "job_id": 42,
        "position": 2,
        "description": "Kugelschreiber",
        "quantity": 20,
        "unit_price_net": 2.50,
        "line_total_net": 50.00,
        "vat_rate": 0.19,
    },
]

SAMPLE_JOBS_LIST = {
    "items": [SAMPLE_JOB],
    "total": 1,
    "page": 1,
    "page_size": 50,
}
