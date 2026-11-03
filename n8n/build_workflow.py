"""Generates n8n/invoice_autopilot.workflow.json (kept as code so it stays reviewable)."""
import json
import uuid
from pathlib import Path

API = "={{ $env.AUTOPILOT_API_URL || 'http://api:8000' }}"

SPLIT_JS = r"""// One item per PDF/image attachment, normalised to binary field "data"
const out = [];
for (const item of $input.all()) {
  for (const [key, bin] of Object.entries(item.binary || {})) {
    const mime = bin.mimeType || '';
    if (!/pdf|image/i.test(mime)) continue;
    // skip email-signature logos and tracking pixels: images under ~40 kB
    const m = String(bin.fileSize || '').match(/([\d.]+)\s*(kB|MB|B)/i);
    const bytes = m ? parseFloat(m[1]) * ({ b: 1, kb: 1e3, mb: 1e6 })[m[2].toLowerCase()] : Infinity;
    if (/image/i.test(mime) && bytes < 40000) continue;
    out.push({
      json: {
        fileName: bin.fileName,
        emailSubject: item.json.subject || null,
        emailFrom: (item.json.from && item.json.from.text) || null,
        source: item.json.subject ? 'gmail' : 'webhook',
      },
      binary: { data: bin },
    });
  }
}
return out;"""

SLACK_TEXT = (
    "=:warning: *Invoice needs review* (#{{ $json.invoice_id }})\n"
    "*Vendor:* {{ $json.data.vendor_name }}  |  *Invoice:* {{ $json.data.invoice_number }}  |  "
    "*Total:* {{ $json.data.total }} {{ $json.data.currency }}\n"
    "*From email:* {{ $('Split attachments').item.json.emailSubject || 'webhook upload' }}\n"
    "*Failed checks:*\n{{ $json.checks.filter(c => c.status === 'fail').map(c => '• ' + c.name + ': ' + c.detail).join('\\n') }}\n"
    "Approve: POST /invoices/{{ $json.invoice_id }}/review  or ask Claude via the MCP server."
)

SHEET_COLUMNS = {
    "Invoice ID": "={{ $json.invoice_id }}",
    "Status": "={{ $json.status }}",
    "Vendor": "={{ $json.data.vendor_name }}",
    "Invoice #": "={{ $json.data.invoice_number }}",
    "Invoice date": "={{ $json.data.invoice_date }}",
    "Due date": "={{ $json.data.due_date }}",
    "Currency": "={{ $json.data.currency }}",
    "Total": "={{ $json.data.total }}",
    "Failed checks": "={{ $json.checks.filter(c => c.status === 'fail').map(c => c.name).join(', ') }}",
    "Source": "={{ $('Split attachments').item.json.fileName }}",
}


def node(name, type_, version, pos, params, **extra):
    n = {"parameters": params, "id": str(uuid.uuid4()), "name": name, "type": type_,
         "typeVersion": version, "position": pos}
    n.update(extra)
    return n


nodes = [
    node("Gmail: new invoice email", "n8n-nodes-base.gmailTrigger", 1.2, [0, 0], {
        "pollTimes": {"item": [{"mode": "everyMinute"}]},
        "simple": False,
        "filters": {"q": "has:attachment (invoice OR receipt OR bill) -label:ap-processed"},
        "options": {"downloadAttachments": True},
    }),
    node("Webhook: upload invoice", "n8n-nodes-base.webhook", 2, [0, 220], {
        "httpMethod": "POST", "path": "invoice-autopilot", "responseMode": "onReceived", "options": {},
    }, webhookId=str(uuid.uuid4())),
    node("Split attachments", "n8n-nodes-base.code", 2, [240, 100], {"jsCode": SPLIT_JS}),
    node("Extract + check (AI)", "n8n-nodes-base.httpRequest", 4.2, [480, 100], {
        "method": "POST",
        "url": API + "/extract",
        "sendQuery": True,
        "queryParameters": {"parameters": [{"name": "source", "value": "={{ $json.source }}"}]},
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "X-API-Key", "value": "={{ $env.AUTOPILOT_API_KEY || '' }}"}]},
        "sendBody": True,
        "contentType": "multipart-form-data",
        "bodyParameters": {"parameters": [
            {"parameterType": "formBinaryData", "name": "file", "inputDataFieldName": "data"}
        ]},
        "options": {"timeout": 120000},
    }, retryOnFail=True, maxTries=3, waitBetweenTries=5000),
    node("Already processed?", "n8n-nodes-base.if", 2.2, [720, 100], {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
            "conditions": [{
                "id": str(uuid.uuid4()),
                "leftValue": "={{ $json.skipped }}",
                "rightValue": "",
                "operator": {"type": "string", "operation": "exists", "singleValue": True},
            }],
            "combinator": "and",
        },
        "options": {},
    }),
    node("Log to Google Sheets", "n8n-nodes-base.googleSheets", 4.5, [960, 180], {
        "operation": "append",
        "documentId": {"__rl": True, "mode": "url", "value": "PASTE_YOUR_SHEET_URL"},
        "sheetName": {"__rl": True, "mode": "name", "value": "Invoices"},
        "columns": {
            "mappingMode": "defineBelow",
            "value": SHEET_COLUMNS,
            "matchingColumns": [],
            "schema": [{"id": k, "displayName": k, "required": False, "defaultMatch": False,
                        "display": True, "type": "string", "canBeUsedToMatch": True} for k in SHEET_COLUMNS],
        },
        "options": {},
    }),
    node("Needs review?", "n8n-nodes-base.if", 2.2, [1200, 180], {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
            "conditions": [{
                "id": str(uuid.uuid4()),
                "leftValue": "={{ $('Extract + check (AI)').item.json.needs_review }}",
                "rightValue": "",
                "operator": {"type": "boolean", "operation": "true", "singleValue": True},
            }],
            "combinator": "and",
        },
        "options": {},
    }),
    node("Slack: ask a human", "n8n-nodes-base.slack", 2.3, [1440, 100], {
        "select": "channel",
        "channelId": {"__rl": True, "mode": "name", "value": "#ap-review"},
        "text": SLACK_TEXT.replace("$json.", "$('Extract + check (AI)').item.json."),
        "otherOptions": {},
    }),
    node("Done (auto-approved)", "n8n-nodes-base.noOp", 1, [1440, 280], {}),
    node("Skip duplicate file", "n8n-nodes-base.noOp", 1, [960, 0], {}),
]

conn = lambda *targets: {"main": [[{"node": t, "type": "main", "index": 0} for t in branch] for branch in targets]}
connections = {
    "Gmail: new invoice email": conn(["Split attachments"]),
    "Webhook: upload invoice": conn(["Split attachments"]),
    "Split attachments": conn(["Extract + check (AI)"]),
    "Extract + check (AI)": conn(["Already processed?"]),
    "Already processed?": conn(["Skip duplicate file"], ["Log to Google Sheets"]),
    "Log to Google Sheets": conn(["Needs review?"]),
    "Needs review?": conn(["Slack: ask a human"], ["Done (auto-approved)"]),
}

workflow = {
    "name": "Invoice Autopilot: Gmail → AI extraction → Sheets + Slack review",
    "nodes": nodes,
    "connections": connections,
    "active": False,
    "settings": {"executionOrder": "v1"},
    "pinData": {},
    "meta": {"templateCredsSetupCompleted": False},
}

out = Path(__file__).parent / "invoice_autopilot.workflow.json"
out.write_text(json.dumps(workflow, indent=2, ensure_ascii=False))
print("wrote", out)
