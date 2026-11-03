"""Data model for an extracted invoice / receipt."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str = Field(description="Item or service description as printed")
    quantity: Optional[float] = Field(default=None, description="Quantity, if printed")
    unit_price: Optional[float] = Field(default=None, description="Price per unit, if printed")
    amount: Optional[float] = Field(default=None, description="Line total as printed")


class Invoice(BaseModel):
    document_type: str = Field(default="invoice", description="invoice, receipt, bill or other")
    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None
    vendor_tax_id: Optional[str] = Field(default=None, description="VAT / GST / EIN if printed")
    customer_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = Field(default=None, description="ISO format YYYY-MM-DD")
    due_date: Optional[str] = Field(default=None, description="ISO format YYYY-MM-DD")
    currency: Optional[str] = Field(default=None, description="ISO 4217 code, e.g. USD, EUR, INR")
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Optional[float] = None
    discount: Optional[float] = None
    tax: Optional[float] = None
    shipping: Optional[float] = None
    total: Optional[float] = None
    notes: Optional[str] = Field(default=None, description="Payment terms or other notes")


FIELD_LABELS = {
    "document_type": "Document type",
    "vendor_name": "Vendor",
    "vendor_address": "Vendor address",
    "vendor_tax_id": "Vendor tax ID",
    "customer_name": "Customer",
    "invoice_number": "Invoice #",
    "invoice_date": "Invoice date",
    "due_date": "Due date",
    "currency": "Currency",
    "subtotal": "Subtotal",
    "discount": "Discount",
    "tax": "Tax",
    "shipping": "Shipping",
    "total": "Total",
    "notes": "Notes",
}
