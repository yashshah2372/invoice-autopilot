"""Deterministic checks on extracted data.

The model reads the document; plain Python checks the arithmetic. Anything that
fails a check is flagged for human review instead of silently trusted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .schema import Invoice

TOLERANCE = 0.02  # absolute tolerance for rounding on printed amounts


@dataclass
class Check:
    name: str
    status: str  # "pass", "fail" or "skip"
    detail: str


def _close(a: float, b: float, tol: float = TOLERANCE) -> bool:
    return abs(a - b) <= max(tol, abs(b) * 0.001)


def _parse_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def run_checks(inv: Invoice) -> list[Check]:
    checks: list[Check] = []

    # 1. Required fields
    missing = [f for f in ("vendor_name", "invoice_date", "total") if getattr(inv, f) in (None, "")]
    checks.append(
        Check("Required fields", "fail" if missing else "pass",
              f"Missing: {', '.join(missing)}" if missing else "Vendor, date and total found")
    )

    # 2. Each line: quantity x unit price = amount
    bad_lines, tested = [], 0
    for i, li in enumerate(inv.line_items, 1):
        if li.quantity is not None and li.unit_price is not None and li.amount is not None:
            tested += 1
            expected = round(li.quantity * li.unit_price, 2)
            if not _close(expected, li.amount):
                bad_lines.append(f"line {i}: {li.quantity} x {li.unit_price} = {expected}, printed {li.amount}")
    if tested == 0:
        checks.append(Check("Line arithmetic", "skip", "No lines with quantity, unit price and amount"))
    else:
        checks.append(Check("Line arithmetic", "fail" if bad_lines else "pass",
                            "; ".join(bad_lines) if bad_lines else f"{tested} line(s) add up"))

    # 3. Sum of lines = subtotal
    amounts = [li.amount for li in inv.line_items if li.amount is not None]
    if inv.subtotal is not None and amounts:
        s = round(sum(amounts), 2)
        ok = _close(s, inv.subtotal)
        checks.append(Check("Lines = subtotal", "pass" if ok else "fail",
                            f"Lines sum to {s}, subtotal printed {inv.subtotal}"))
    else:
        checks.append(Check("Lines = subtotal", "skip", "Subtotal or line amounts not printed"))

    # 4. Subtotal - discount + tax + shipping = total
    base = inv.subtotal if inv.subtotal is not None else (round(sum(amounts), 2) if amounts else None)
    if base is not None and inv.total is not None:
        expected = round(base - (inv.discount or 0) + (inv.tax or 0) + (inv.shipping or 0), 2)
        ok = _close(expected, inv.total)
        checks.append(Check("Total reconciles", "pass" if ok else "fail",
                            f"Expected {expected}, printed {inv.total}"))
    else:
        checks.append(Check("Total reconciles", "skip", "Not enough amounts to reconcile"))

    # 5. Dates are valid and in order
    d_inv, d_due = _parse_iso(inv.invoice_date), _parse_iso(inv.due_date)
    if inv.invoice_date and d_inv is None:
        checks.append(Check("Dates", "fail", f"Invoice date not a valid date: {inv.invoice_date}"))
    elif d_inv and d_due and d_due < d_inv:
        checks.append(Check("Dates", "fail", f"Due date {d_due} is before invoice date {d_inv}"))
    elif d_inv:
        checks.append(Check("Dates", "pass", "Dates valid" + (" and in order" if d_due else "")))
    else:
        checks.append(Check("Dates", "skip", "No dates printed"))

    return checks


def needs_review(checks: list[Check]) -> bool:
    return any(c.status == "fail" for c in checks)
