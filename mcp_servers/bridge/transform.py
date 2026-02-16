"""Transform DocumentFlow job data into Odoo AI Office format."""

# Tax key → Vorsteuer account mapping (SKR03)
TAX_KEY_TO_ACCOUNT = {
    "19": "1576",
    "7": "1571",
    "0": None,
}

# Contra accounts (not expense accounts)
CONTRA_ACCOUNTS = {"1600", "1200", "1400", "1800"}


def transform_job_to_case_vals(job: dict) -> dict:
    """Transform a DocumentFlow job into Odoo case creation values.

    Returns a dict suitable for OdooAiOfficeClient.create_case().
    """
    doc_data = job.get("document_data") or {}

    period = _extract_period(doc_data.get("date_document"))

    return {
        "partner_name": doc_data.get("sender_name", ""),
        "period": period,
        "source_model": "docflow.job",
        "source_id": job.get("id", 0),
    }


def transform_enrichment_suggestions(job: dict) -> list[dict]:
    """Extract enrichment-type suggestions from DocumentFlow document_data.

    Returns a list of suggestion dicts ready for OdooAiOfficeClient.add_suggestion().
    """
    doc_data = job.get("document_data") or {}
    confidence = doc_data.get("confidence", 0.7)
    suggestions = []

    field_map = {
        "invoice_number": "invoice_number",
        "date_document": "invoice_date",
        "sender_name": "partner_name",
        "total_gross": "amount_total",
        "total_net": "amount_net",
        "vat_amount": "tax_amount",
    }

    for df_field, odoo_field in field_map.items():
        value = doc_data.get(df_field)
        if value is not None and value != "":
            suggestions.append({
                "suggestion_type": "enrichment",
                "payload": {"field": odoo_field, "value": str(value)},
                "confidence": confidence,
                "risk_score": 0.0,
                "explanation": "Extracted %s from DocumentFlow OCR/LLM" % odoo_field,
                "agent_name": "docflow_bridge",
            })

    return suggestions


def transform_bookings_to_suggestion(job: dict, bookings: list[dict]) -> dict:
    """Transform DocumentFlow bookings into an accounting_entry suggestion.

    If bookings are available, converts them to balanced Odoo lines.
    Falls back to accounting_suggestion from document_data if no bookings.

    Returns a suggestion dict ready for OdooAiOfficeClient.add_suggestion().
    """
    doc_data = job.get("document_data") or {}
    acct_suggestion = doc_data.get("accounting_suggestion") or {}

    lines = _build_lines_from_bookings(bookings)

    if not lines:
        lines = _build_lines_from_acct_suggestion(doc_data, acct_suggestion)

    confidence = acct_suggestion.get("confidence", doc_data.get("confidence", 0.5))
    risk_score = calculate_risk(doc_data)

    # Determine expense account from lines or suggestion
    expense_account = acct_suggestion.get("booking_account", "6300")
    for line in lines:
        if line["account"] not in CONTRA_ACCOUNTS and line["account"] not in ("1576", "1571"):
            expense_account = line["account"]
            break

    # Determine tax rate
    tax_rate = doc_data.get("vat_rate")
    if tax_rate is None:
        tax_key = acct_suggestion.get("tax_key", "19")
        tax_rate = 0.19 if tax_key == "19" else (0.07 if tax_key == "7" else 0.0)

    return {
        "suggestion_type": "accounting_entry",
        "payload": {
            "lines": lines,
            "amount": doc_data.get("total_gross", 0.0),
            "net_amount": doc_data.get("total_net", 0.0),
            "tax_amount": doc_data.get("vat_amount", 0.0),
            "tax_rate": tax_rate,
            "expense_account": expense_account,
            "skr_chart": "SKR03",
            "source": "documentflow",
            "docflow_job_id": job.get("id"),
        },
        "confidence": confidence,
        "risk_score": risk_score,
        "explanation": "Imported from DocumentFlow job #%s (%s)" % (
            job.get("id", "?"),
            doc_data.get("sender_name", "unknown"),
        ),
        "agent_name": "docflow_bridge",
    }


def calculate_risk(doc_data: dict) -> float:
    """Calculate risk score from DocumentFlow confidence and data completeness."""
    confidence = doc_data.get("confidence", 0.5)
    base_risk = 1.0 - confidence

    if not doc_data.get("sender_name"):
        base_risk += 0.1
    if not doc_data.get("invoice_number"):
        base_risk += 0.05
    if not doc_data.get("total_gross") or doc_data.get("total_gross", 0) <= 0:
        base_risk += 0.1

    return min(round(base_risk, 2), 1.0)


# ── Internal helpers ────────────────────────────────────────


def _extract_period(date_str: str | None) -> str:
    """Extract YYYY-MM period from a date string."""
    if not date_str:
        return ""
    try:
        # Handle YYYY-MM-DD and similar formats
        parts = str(date_str).split("-")
        if len(parts) >= 2:
            return "%s-%s" % (parts[0], parts[1].zfill(2))
    except (ValueError, IndexError):
        pass
    return ""


def _build_lines_from_bookings(bookings: list[dict]) -> list[dict]:
    """Convert DocumentFlow bookings (Soll/Haben) to Odoo suggestion lines."""
    if not bookings:
        return []

    lines = []
    for booking in bookings:
        amount = float(booking.get("amount", 0))
        if amount <= 0:
            continue

        debit_account = booking.get("debit_account", "")
        credit_account = booking.get("credit_account", "")
        description = booking.get("booking_text", "")

        if debit_account:
            lines.append({
                "account": debit_account,
                "debit": amount,
                "credit": 0.0,
                "description": description,
            })
        if credit_account:
            lines.append({
                "account": credit_account,
                "debit": 0.0,
                "credit": amount,
                "description": description,
            })

    return lines


def _build_lines_from_acct_suggestion(doc_data: dict, acct: dict) -> list[dict]:
    """Build Odoo-compatible lines from DocumentFlow's accounting_suggestion."""
    total_gross = float(doc_data.get("total_gross", 0) or 0)
    total_net = float(doc_data.get("total_net", 0) or 0)
    vat_amount = float(doc_data.get("vat_amount", 0) or 0)

    if total_gross <= 0:
        return []

    # If net/tax not provided, calculate from gross
    if total_net <= 0:
        tax_key = acct.get("tax_key", "19")
        rate = 0.19 if tax_key == "19" else (0.07 if tax_key == "7" else 0.0)
        total_net = round(total_gross / (1 + rate), 2) if rate > 0 else total_gross
        vat_amount = round(total_gross - total_net, 2)

    booking_account = acct.get("booking_account", "6300")
    counter_account = acct.get("counter_account", "1600")
    tax_key = acct.get("tax_key", "19")
    description = acct.get("booking_text", doc_data.get("sender_name", ""))

    vorsteuer_account = TAX_KEY_TO_ACCOUNT.get(tax_key)

    lines = [
        {
            "account": booking_account,
            "debit": total_net,
            "credit": 0.0,
            "description": description,
        },
    ]

    if vorsteuer_account and vat_amount > 0:
        lines.append({
            "account": vorsteuer_account,
            "debit": vat_amount,
            "credit": 0.0,
            "description": "Vorsteuer %s%%" % tax_key,
        })

    lines.append({
        "account": counter_account,
        "debit": 0.0,
        "credit": total_gross,
        "description": "Verbindlichkeiten %s" % (doc_data.get("sender_name", "")),
    })

    return lines
