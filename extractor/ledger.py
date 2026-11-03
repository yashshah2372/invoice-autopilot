"""SQLite ledger of processed invoices: the agent's memory.

Stores every extracted document with its checks and a review status, so the MCP
server, the API and n8n all work from the same source of truth.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from .schema import Invoice
from .validate import Check, needs_review

DB_PATH = Path(os.getenv("LEDGER_DB", Path(__file__).resolve().parent.parent / "data" / "ledger.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash     TEXT UNIQUE,
    source        TEXT,
    vendor        TEXT,
    invoice_number TEXT,
    invoice_date  TEXT,
    due_date      TEXT,
    currency      TEXT,
    total         REAL,
    status        TEXT NOT NULL,          -- needs_review | approved | auto_approved | rejected
    review_note   TEXT,
    data_json     TEXT NOT NULL,
    checks_json   TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
"""


@contextmanager
def connect(db_path: Path | str | None = None):
    path = Path(db_path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_by_hash(h: str, db_path=None) -> dict | None:
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM invoices WHERE file_hash = ?", (h,)).fetchone()
        return _row(row) if row else None


def find_duplicate(inv: Invoice, db_path=None) -> dict | None:
    """Same vendor + invoice number already in the ledger (likely double billing)."""
    if not (inv.vendor_name and inv.invoice_number):
        return None
    with connect(db_path) as con:
        row = con.execute(
            "SELECT * FROM invoices WHERE lower(vendor) = lower(?) AND invoice_number = ?",
            (inv.vendor_name, inv.invoice_number),
        ).fetchone()
        return _row(row) if row else None


def save(inv: Invoice, checks: list[Check], source: str, fhash: str, db_path=None) -> dict:
    status = "needs_review" if needs_review(checks) else "auto_approved"
    with connect(db_path) as con:
        cur = con.execute(
            """INSERT INTO invoices (file_hash, source, vendor, invoice_number, invoice_date, due_date,
                                     currency, total, status, data_json, checks_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (fhash, source, inv.vendor_name, inv.invoice_number, inv.invoice_date, inv.due_date,
             inv.currency, inv.total, status, inv.model_dump_json(),
             json.dumps([c.__dict__ for c in checks]), datetime.now().isoformat(timespec="seconds")),
        )
        row = con.execute("SELECT * FROM invoices WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row(row)


def get(invoice_id: int, db_path=None) -> dict | None:
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        return _row(row, full=True) if row else None


def list_invoices(status: str | None = None, vendor: str | None = None, db_path=None) -> list[dict]:
    q, args = "SELECT * FROM invoices WHERE 1=1", []
    if status and status != "all":
        q += " AND status = ?"
        args.append(status)
    if vendor:
        q += " AND lower(vendor) LIKE ?"
        args.append(f"%{vendor.lower()}%")
    q += " ORDER BY id DESC"
    with connect(db_path) as con:
        return [_row(r) for r in con.execute(q, args).fetchall()]


def set_status(invoice_id: int, status: str, note: str | None = None, db_path=None) -> dict | None:
    if status not in {"approved", "rejected", "needs_review"}:
        raise ValueError("status must be approved, rejected or needs_review")
    with connect(db_path) as con:
        con.execute("UPDATE invoices SET status = ?, review_note = ? WHERE id = ?", (status, note, invoice_id))
    return get(invoice_id, db_path)


def spend_summary(group_by: str = "vendor", db_path=None) -> list[dict]:
    """Total spend (approved + auto_approved) grouped by vendor or month, per currency."""
    key = {"vendor": "vendor", "month": "substr(invoice_date, 1, 7)"}.get(group_by)
    if key is None:
        raise ValueError("group_by must be 'vendor' or 'month'")
    with connect(db_path) as con:
        rows = con.execute(
            f"""SELECT {key} AS grp, currency, COUNT(*) AS invoices, ROUND(SUM(total), 2) AS total
                FROM invoices WHERE status IN ('approved', 'auto_approved')
                GROUP BY grp, currency ORDER BY total DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def upcoming_payments(days: int = 14, today: date | None = None, db_path=None) -> list[dict]:
    """Approved invoices due within `days` (including overdue ones)."""
    today = today or date.today()
    horizon = (today + timedelta(days=days)).isoformat()
    with connect(db_path) as con:
        rows = con.execute(
            """SELECT * FROM invoices WHERE status IN ('approved', 'auto_approved')
               AND due_date IS NOT NULL AND due_date <= ? ORDER BY due_date""",
            (horizon,),
        ).fetchall()
    out = []
    for r in rows:
        d = _row(r)
        d["overdue"] = d["due_date"] < today.isoformat()
        out.append(d)
    return out


def _row(row: sqlite3.Row, full: bool = False) -> dict:
    d = dict(row)
    data, checks = json.loads(d.pop("data_json")), json.loads(d.pop("checks_json"))
    d.pop("file_hash", None)
    d["failed_checks"] = [c for c in checks if c["status"] == "fail"]
    if full:
        d["data"], d["checks"] = data, checks
    return d
