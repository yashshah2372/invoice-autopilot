"""Gradio demo: invoice / receipt -> structured data, checks, Excel and JSON."""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

import gradio as gr

from extractor import export, ingest, llm
from extractor.schema import FIELD_LABELS
from extractor.validate import needs_review, run_checks

SAMPLES = sorted(str(p) for p in (Path(__file__).parent / "samples").glob("*.pdf"))
ICON = {"pass": "✅", "fail": "⚠️", "skip": "➖"}


def process(file_path: str | None):
    if not file_path:
        raise gr.Error("Upload a PDF or image first.")
    t0 = time.time()
    doc = ingest.load(file_path)
    inv = llm.extract(doc)
    checks = run_checks(inv)
    elapsed = time.time() - t0

    fields = [[label, "" if getattr(inv, k) is None else str(getattr(inv, k))] for k, label in FIELD_LABELS.items()]
    lines = [[i, li.description, li.quantity, li.unit_price, li.amount] for i, li in enumerate(inv.line_items, 1)]
    check_rows = [[f"{ICON[c.status]} {c.name}", c.detail] for c in checks]

    status = (
        "### ⚠️ Needs review: one or more checks failed"
        if needs_review(checks)
        else "### ✅ All checks passed"
    )
    status += f"\n{doc.pages} page(s) · {len(inv.line_items)} line item(s) · {elapsed:.1f}s · model provider: {llm.provider()}"

    out = Path(tempfile.mkdtemp())
    stem = Path(file_path).stem
    xlsx = export.to_excel(inv, checks, out / f"{stem}_extracted.xlsx")
    js = export.to_json(inv, checks, out / f"{stem}_extracted.json")
    return status, fields, lines, check_rows, str(xlsx), str(js)


with gr.Blocks(title="Invoice & Receipt Extractor") as demo:
    gr.Markdown(
        "# Invoice & Receipt Extractor\n"
        "Upload an invoice, receipt or bill (PDF, scan or photo). You get the key fields and line items, "
        "**arithmetic checks** that flag anything that doesn't add up, and an Excel/JSON export.\n\n"
        "The model only reads the document; totals are verified in plain Python, so a misread number is "
        "flagged for review instead of passing silently."
    )
    with gr.Row():
        with gr.Column(scale=1):
            f = gr.File(label="Document", file_types=[".pdf", ".png", ".jpg", ".jpeg", ".webp"], type="filepath")
            btn = gr.Button("Extract", variant="primary")
            if SAMPLES:
                gr.Examples(SAMPLES, inputs=f, label="Try a sample (fictional companies)")
            gr.Markdown("Files are processed in memory for this request and not stored.")
        with gr.Column(scale=2):
            status = gr.Markdown()
            checks = gr.Dataframe(headers=["Check", "Detail"], label="Checks", wrap=True)
            fields = gr.Dataframe(headers=["Field", "Value"], label="Fields", wrap=True)
            lines = gr.Dataframe(headers=["#", "Description", "Qty", "Unit price", "Amount"], label="Line items", wrap=True)
            with gr.Row():
                xlsx = gr.File(label="Excel")
                js = gr.File(label="JSON")
    btn.click(process, inputs=f, outputs=[status, fields, lines, checks, xlsx, js])

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft())
