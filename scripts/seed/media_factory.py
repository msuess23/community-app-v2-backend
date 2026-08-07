"""Deterministic in-memory media factories used by demo seeders."""

from __future__ import annotations

from io import BytesIO

from fastapi import UploadFile
from PIL import Image
from starlette.datastructures import Headers


def image_upload(
  filename: str,
  *,
  rgb: tuple[int, int, int],
  size: tuple[int, int] = (64, 48),
) -> UploadFile:
  """Create a small valid PNG upload without requiring repository fixtures."""

  buffer = BytesIO()
  Image.new("RGB", size, rgb).save(buffer, format="PNG")
  payload = buffer.getvalue()
  return UploadFile(
    file=BytesIO(payload),
    size=len(payload),
    filename=filename,
    headers=Headers({"content-type": "image/png"}),
  )


def pdf_upload(filename: str, *, title: str) -> UploadFile:
  """Create a minimal valid PDF upload for appointment document seeding."""

  safe_title = title.replace("(", "[").replace(")", "]")
  body = (
    "%PDF-1.4\n"
    "1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    "2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
    "3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 144]"
    "/Contents 4 0 R>>endobj\n"
    f"4 0 obj<</Length {len(safe_title) + 24}>>stream\n"
    f"BT /F1 12 Tf 20 80 Td ({safe_title}) Tj ET\n"
    "endstream endobj\n"
    "trailer<</Root 1 0 R>>\n"
    "%%EOF\n"
  ).encode("utf-8")
  return UploadFile(
    file=BytesIO(body),
    size=len(body),
    filename=filename,
    headers=Headers({"content-type": "application/pdf"}),
  )
