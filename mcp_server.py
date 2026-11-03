"""MCP server: gives Claude Desktop, Cursor or any MCP client accounts-payable tools.

Example asks once connected:
  "Process every invoice in ~/Downloads/invoices and tell me which need review"
  "What do we owe in the next 14 days?"
  "Approve invoice 3, the total was confirmed with the vendor"
  "Who did we spend the most with this quarter?"
"""
from __future__ import annotations

from pathlib import Path

try:  # MCP Python SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from extractor import ledger, pipeline

SUPPORTED = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

mcp = _Server(
    "invoice-autopilot",
    instructions=(
        "Accounts-payable tools. Extraction is done by a vision model; arithmetic, dates and duplicates "
        "are verified in code. Never approve an invoice that failed checks unless the user explicitly says so."
    ),
)


def _brief(r: dict) -> dict:
    if "skipped" in r:
        inv = r["invoice"]
        return {"skipped": r["skipped"], "invoice_id": inv["id"], "vendor": inv["vendor"], "status": inv["status"]}
    d = r["data"]
    return {
        "invoice_id": r.get("invoice_id"),
        "status": r.get("status"),
        "vendor": d["vendor_name"],
        "invoice_number": d["invoice_number"],
        "total": d["total"],
        "currency": d["currency"],
        "due_date": d["due_date"],
        "failed_checks": [c["detail"] for c in r["checks"] if c["status"] == "fail"],
    }


@mcp.tool()
def process_invoice(file_path: str) -> dict:
    """Extract, check and log one invoice/receipt (PDF or image) from a local file path."""
    try:
        return _brief(pipeline.process_path(file_path, source="mcp"))
    except Exception as e:  # return a readable reason (missing key, bad path, unsupported type)
        return {"error": str(e)}


@mcp.tool()
def process_folder(folder: str, limit: int = 25) -> dict:
    """Process every PDF/image in a folder (non-recursive). Already-processed files are skipped."""
    files = sorted(p for p in Path(folder).expanduser().iterdir() if p.suffix.lower() in SUPPORTED)[:limit]
    results = []
    for p in files:
        try:
            results.append({"file": p.name, **_brief(pipeline.process_path(p, source="mcp"))})
        except Exception as e:  # keep going; report the failure
            results.append({"file": p.name, "error": str(e)})
    return {
        "processed": len(results),
        "needs_review": [r for r in results if r.get("status") == "needs_review"],
        "results": results,
    }


@mcp.tool()
def list_invoices(status: str = "all", vendor: str | None = None) -> list[dict]:
    """List logged invoices. status: all | needs_review | approved | auto_approved | rejected."""
    return ledger.list_invoices(status=status, vendor=vendor)


@mcp.tool()
def get_invoice(invoice_id: int) -> dict:
    """Full extracted data, line items and check results for one invoice."""
    return ledger.get(invoice_id) or {"error": f"No invoice #{invoice_id}"}


@mcp.tool()
def review_invoice(invoice_id: int, decision: str, note: str | None = None) -> dict:
    """Record a human decision on an invoice. decision: approved | rejected."""
    if not ledger.get(invoice_id):
        return {"error": f"No invoice #{invoice_id}"}
    return ledger.set_status(invoice_id, decision, note)


@mcp.tool()
def spend_summary(group_by: str = "vendor") -> list[dict]:
    """Approved spend grouped by 'vendor' or 'month', per currency."""
    return ledger.spend_summary(group_by)


@mcp.tool()
def upcoming_payments(days: int = 14) -> list[dict]:
    """Approved invoices due within the next N days, including overdue ones."""
    return ledger.upcoming_payments(days)


@mcp.prompt()
def weekly_ap_review() -> str:
    """Weekly accounts-payable review."""
    return (
        "Run a weekly accounts-payable review: list invoices that need review and explain each failed check, "
        "list payments due in the next 14 days (flag overdue ones), and summarise spend by vendor. "
        "End with a short action list. Do not approve anything without asking me."
    )


if __name__ == "__main__":
    mcp.run()  # stdio transport (Claude Desktop / Cursor)
