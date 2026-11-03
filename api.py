"""REST API: used by the n8n workflow (and anything else that can send HTTP).

Run:  uvicorn api:app --host 0.0.0.0 --port 8000
Auth: set API_KEY to require an `X-API-Key` header.
"""
from __future__ import annotations

import os

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel

from extractor import ledger, pipeline

app = FastAPI(title="Invoice Autopilot API", version="1.0")
MAX_BYTES = 15 * 1024 * 1024


def auth(x_api_key: str | None = Header(default=None)):
    expected = os.getenv("API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


class Review(BaseModel):
    status: str  # approved | rejected
    note: str | None = None


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/extract", dependencies=[Depends(auth)])
async def extract(file: UploadFile = File(...), source: str = Query("api"), save: bool = Query(True)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File too large (15 MB max)")
    try:
        return pipeline.process_bytes(data, file.filename or "upload.pdf", source=source, save=save)
    except ValueError as e:
        raise HTTPException(415, str(e))


@app.get("/invoices", dependencies=[Depends(auth)])
def invoices(status: str = "all", vendor: str | None = None):
    return ledger.list_invoices(status=status, vendor=vendor)


@app.get("/invoices/{invoice_id}", dependencies=[Depends(auth)])
def invoice(invoice_id: int):
    row = ledger.get(invoice_id)
    if not row:
        raise HTTPException(404, "Not found")
    return row


@app.post("/invoices/{invoice_id}/review", dependencies=[Depends(auth)])
def review(invoice_id: int, body: Review):
    if not ledger.get(invoice_id):
        raise HTTPException(404, "Not found")
    try:
        return ledger.set_status(invoice_id, body.status, body.note)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/reports/spend", dependencies=[Depends(auth)])
def spend(group_by: str = "vendor"):
    return ledger.spend_summary(group_by)


@app.get("/reports/upcoming", dependencies=[Depends(auth)])
def upcoming(days: int = 14):
    return ledger.upcoming_payments(days)
