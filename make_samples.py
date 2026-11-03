"""Generate sample invoices for fictional companies (one clean, one with a deliberate total error)."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

OUT = Path(__file__).parent / "samples"
OUT.mkdir(exist_ok=True)
ss = getSampleStyleSheet()


def invoice(path, vendor, addr, number, date, due, customer, items, tax_rate, shipping, printed_total=None, cur="$"):
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm)
    subtotal = round(sum(q * p for _, q, p in items), 2)
    tax = round(subtotal * tax_rate, 2)
    total = round(subtotal + tax + shipping, 2) if printed_total is None else printed_total
    s = [
        Paragraph(f"<b>{vendor}</b>", ss["Title"]),
        Paragraph(addr, ss["Normal"]),
        Spacer(1, 8 * mm),
        Paragraph(f"<b>INVOICE</b> &nbsp; No. {number}", ss["Heading2"]),
        Paragraph(f"Date: {date} &nbsp;&nbsp; Due: {due}", ss["Normal"]),
        Paragraph(f"Bill to: {customer}", ss["Normal"]),
        Spacer(1, 6 * mm),
    ]
    rows = [["Description", "Qty", "Unit price", "Amount"]]
    rows += [[d, str(q), f"{cur}{p:,.2f}", f"{cur}{q * p:,.2f}"] for d, q, p in items]
    rows += [["", "", "Subtotal", f"{cur}{subtotal:,.2f}"],
             ["", "", f"Tax ({tax_rate * 100:.0f}%)", f"{cur}{tax:,.2f}"],
             ["", "", "Shipping", f"{cur}{shipping:,.2f}"],
             ["", "", "TOTAL", f"{cur}{total:,.2f}"]]
    t = Table(rows, colWidths=[90 * mm, 15 * mm, 35 * mm, 35 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, len(items)), 0.4, colors.grey),
        ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    s += [t, Spacer(1, 10 * mm), Paragraph("Payment terms: Net 30. Thank you for your business.", ss["Italic"])]
    doc.build(s)


invoice(OUT / "sample_invoice_clean.pdf", "Northwind Office Supply Co.", "412 Harbor Lane, Portland, OR 97201 · EIN 00-0000000",
        "NW-20431", "2026-10-14", "2026-11-13", "Bluefin Design Studio",
        [("Ergonomic chair, mesh back", 4, 189.00), ("Standing desk frame", 2, 349.50),
         ("Monitor arm, dual", 3, 74.99), ("Cable management kit", 5, 12.40)], 0.08, 45.00)

invoice(OUT / "sample_invoice_with_error.pdf", "Lakeside Catering Ltd.", "9 Mill Road, Leeds LS1 4AB · VAT GB000000000",
        "LC-7782", "2026-09-30", "2026-10-30", "Orchard Events",
        [("Buffet lunch, per head", 40, 18.50), ("Coffee & tea service", 40, 3.25), ("Staff hours", 6, 22.00)],
        0.20, 0.0, printed_total=1250.00, cur="£")
print("samples written to", OUT)
