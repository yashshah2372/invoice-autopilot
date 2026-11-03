"""One entry point used by the API, the MCP server and the UI."""
from __future__ import annotations

import tempfile
from pathlib import Path

from . import ingest, ledger, llm
from .validate import Check, run_checks


def process_bytes(data: bytes, filename: str, source: str = "upload", save: bool = True, db_path=None) -> dict:
    """Extract + check one document. Skips files already processed (same bytes)."""
    fhash = ledger.file_hash(data)
    if save:
        existing = ledger.find_by_hash(fhash, db_path)
        if existing:
            return {"skipped": "already processed", "invoice": existing}

    suffix = Path(filename).suffix or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        doc = ingest.load(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    inv = llm.extract(doc)
    checks = run_checks(inv)

    dup = ledger.find_duplicate(inv, db_path) if save else None
    if dup:
        checks.append(Check("Duplicate", "fail",
                            f"Invoice {inv.invoice_number} from {inv.vendor_name} already in ledger as #{dup['id']}"))

    result = {
        "data": inv.model_dump(),
        "checks": [c.__dict__ for c in checks],
        "needs_review": any(c.status == "fail" for c in checks),
    }
    if save:
        row = ledger.save(inv, checks, source=f"{source}:{filename}", fhash=fhash, db_path=db_path)
        result["invoice_id"], result["status"] = row["id"], row["status"]
    return result


def process_path(path: str | Path, source: str = "file", save: bool = True, db_path=None) -> dict:
    path = Path(path).expanduser()
    return process_bytes(path.read_bytes(), path.name, source=source, save=save, db_path=db_path)
