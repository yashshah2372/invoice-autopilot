"""Turn an uploaded file into page images (and text, when the PDF has a text layer)."""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

MAX_PAGES = 5
MAX_SIDE = 1800  # px; keeps requests small without hurting legibility


@dataclass
class Document:
    images: list[bytes]  # PNG bytes, one per page
    text: str            # embedded text layer ("" for scans and photos)
    pages: int


def _to_png(img: Image.Image) -> bytes:
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def load(path: str | Path) -> Document:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        n = min(len(pdf), MAX_PAGES)
        images, texts = [], []
        for i in range(n):
            page = pdf[i]
            images.append(_to_png(page.render(scale=2).to_pil()))
            texts.append(page.get_textpage().get_text_range())
        return Document(images=images, text="\n\n".join(t for t in texts if t.strip()), pages=len(pdf))
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}:
        return Document(images=[_to_png(Image.open(path))], text="", pages=1)
    raise ValueError(f"Unsupported file type: {suffix}. Upload a PDF or an image.")
