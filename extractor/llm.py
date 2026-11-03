"""Vision-LLM extraction with structured output.

Provider is chosen by environment variables:
  LLM_PROVIDER = "anthropic" | "gemini" | "openai" (auto-detected from whichever key is set)
  ANTHROPIC_API_KEY / GEMINI_API_KEY / OPENAI_API_KEY
  LLM_MODEL (optional override)
"""
from __future__ import annotations

import base64
import json
import os

from .ingest import Document
from .schema import Invoice

PROMPT = """You extract data from invoices, receipts and bills.
Return ONLY values that are printed on the document. If a field is not printed, use null.
Never compute or guess a value that is not printed (for example, do not calculate a missing total).
Dates must be ISO YYYY-MM-DD. Amounts are plain numbers without currency symbols or thousands separators.
Copy line items in the order printed. Currency is the ISO 4217 code implied by the symbol or text.
"""


def provider() -> str:
    p = os.getenv("LLM_PROVIDER", "").lower()
    if p:
        return p
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    raise RuntimeError("No API key configured. Set ANTHROPIC_API_KEY, GEMINI_API_KEY or OPENAI_API_KEY.")


def _user_text(doc: Document) -> str:
    t = "Extract the fields from this document."
    if doc.text.strip():
        t += "\n\nEmbedded text layer (may help with exact numbers):\n" + doc.text[:12000]
    return t


def _extract_openai(doc: Document) -> Invoice:
    from openai import OpenAI

    client = OpenAI()
    content = [{"type": "text", "text": _user_text(doc)}]
    for png in doc.images:
        b64 = base64.b64encode(png).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
    resp = client.beta.chat.completions.parse(
        model=os.getenv("LLM_MODEL", "gpt-4.1-mini"),
        temperature=0,
        messages=[{"role": "system", "content": PROMPT}, {"role": "user", "content": content}],
        response_format=Invoice,
    )
    return resp.choices[0].message.parsed


def _extract_gemini(doc: Document) -> Invoice:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    parts = [types.Part.from_bytes(data=png, mime_type="image/png") for png in doc.images]
    resp = client.models.generate_content(
        model=os.getenv("LLM_MODEL", "gemini-2.5-flash"),
        contents=parts + [_user_text(doc)],
        config=types.GenerateContentConfig(
            system_instruction=PROMPT,
            temperature=0,
            response_mime_type="application/json",
            response_schema=Invoice,
        ),
    )
    if getattr(resp, "parsed", None) is not None:
        return resp.parsed
    return Invoice.model_validate(json.loads(resp.text))


def _inline_refs(schema: dict) -> dict:
    """Resolve $ref/$defs so the tool schema is self-contained."""
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            return {k: walk(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def _parse_json(text: str) -> Invoice:
    """Pull the JSON object out of a model reply (tolerates code fences or stray prose)."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    i, j = t.find("{"), t.rfind("}")
    if i == -1 or j == -1:
        raise ValueError("No JSON object in model reply")
    return Invoice.model_validate_json(t[i:j + 1])


def _extract_anthropic(doc: Document) -> Invoice:
    """Claude: ask for JSON matching the schema, validate with Pydantic, retry once on invalid output."""
    import anthropic

    client = anthropic.Anthropic()
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                     "data": base64.b64encode(png).decode()}}
        for png in doc.images
    ]
    schema = json.dumps(_inline_refs(Invoice.model_json_schema()), separators=(",", ":"))
    content.append({"type": "text", "text": _user_text(doc) +
                    "\n\nReply with ONLY one JSON object that matches this JSON Schema, no prose:\n" + schema})
    messages = [{"role": "user", "content": content}]
    model = os.getenv("LLM_MODEL", "claude-sonnet-5-5")

    last_err = None
    for _ in range(2):
        resp = client.messages.create(model=model, max_tokens=4096, system=PROMPT, messages=messages)
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        try:
            return _parse_json(text)
        except Exception as e:  # invalid JSON or schema mismatch -> show the error and ask again
            last_err = e
            messages = messages + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"That was not valid for the schema ({e}). Reply with only the corrected JSON object."},
            ]
    raise RuntimeError(f"Model did not return valid JSON: {last_err}")


def extract(doc: Document) -> Invoice:
    p = provider()
    if p == "anthropic":
        return _extract_anthropic(doc)
    if p == "openai":
        return _extract_openai(doc)
    if p == "gemini":
        return _extract_gemini(doc)
    raise RuntimeError(f"Unknown LLM_PROVIDER: {p}")
