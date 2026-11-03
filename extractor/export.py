"""Export extracted data to Excel and JSON."""
from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from .schema import FIELD_LABELS, Invoice
from .validate import Check

BOLD = Font(bold=True)
HEAD = PatternFill("solid", fgColor="E8EEF7")
FAIL = PatternFill("solid", fgColor="FBE3E3")
PASS = PatternFill("solid", fgColor="E3F4E8")


def to_excel(inv: Invoice, checks: list[Check], path: str | Path) -> Path:
    wb = Workbook()

    ws = wb.active
    ws.title = "Summary"
    ws.append(["Field", "Value"])
    for c in ws[1]:
        c.font, c.fill = BOLD, HEAD
    for key, label in FIELD_LABELS.items():
        ws.append([label, getattr(inv, key)])
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 48

    li = wb.create_sheet("Line items")
    li.append(["#", "Description", "Quantity", "Unit price", "Amount"])
    for c in li[1]:
        c.font, c.fill = BOLD, HEAD
    for i, item in enumerate(inv.line_items, 1):
        li.append([i, item.description, item.quantity, item.unit_price, item.amount])
    if inv.line_items:
        n = len(inv.line_items) + 1
        li.append(["", "Sum of lines", "", "", f"=SUM(E2:E{n})"])
        li.cell(row=n + 1, column=2).font = BOLD
    for col, w in zip("ABCDE", (5, 48, 10, 12, 12)):
        li.column_dimensions[col].width = w

    ck = wb.create_sheet("Checks")
    ck.append(["Check", "Result", "Detail"])
    for c in ck[1]:
        c.font, c.fill = BOLD, HEAD
    for chk in checks:
        ck.append([chk.name, chk.status.upper(), chk.detail])
        fill = FAIL if chk.status == "fail" else PASS if chk.status == "pass" else None
        if fill:
            ck.cell(row=ck.max_row, column=2).fill = fill
    for col, w in zip("ABC", (20, 10, 70)):
        ck.column_dimensions[col].width = w

    path = Path(path)
    wb.save(path)
    return path


def to_json(inv: Invoice, checks: list[Check], path: str | Path) -> Path:
    payload = {
        "data": inv.model_dump(),
        "checks": [c.__dict__ for c in checks],
        "needs_review": any(c.status == "fail" for c in checks),
    }
    path = Path(path)
    path.write_text(json.dumps(payload, indent=2))
    return path
