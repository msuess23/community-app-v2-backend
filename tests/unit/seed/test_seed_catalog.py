"""Pure regression checks for the cross-domain demo seed catalog."""

from __future__ import annotations

from PIL import Image

from scripts.seed.media_factory import image_upload, pdf_upload
from scripts.seed.seed_appointments import APPOINTMENT_SEED_KEYS
from scripts.seed.seed_infos import INFO_SEED_TITLES
from scripts.seed.seed_tickets import TICKET_SEED_TITLES


def test_seed_catalog_contains_varied_unique_domain_scenarios():
  """Keep enough deterministic scenarios to demonstrate every major domain."""

  assert len(TICKET_SEED_TITLES) >= 10
  assert len(INFO_SEED_TITLES) >= 6
  assert len(APPOINTMENT_SEED_KEYS) >= 6
  assert len(set(TICKET_SEED_TITLES)) == len(TICKET_SEED_TITLES)
  assert len(set(INFO_SEED_TITLES)) == len(INFO_SEED_TITLES)
  assert len(set(APPOINTMENT_SEED_KEYS)) == len(APPOINTMENT_SEED_KEYS)


def test_seed_image_factory_produces_a_valid_png():
  """Generate image bytes accepted by the shared Pillow validation pipeline."""

  upload = image_upload("seed.png", rgb=(10, 20, 30))
  assert upload.content_type == "image/png"
  upload.file.seek(0)
  with Image.open(upload.file) as image:
    assert image.format == "PNG"
    assert image.size == (64, 48)


def test_seed_pdf_factory_produces_expected_signatures():
  """Generate PDF bytes accepted by appointment document signature checks."""

  upload = pdf_upload("seed.pdf", title="Seed document")
  assert upload.content_type == "application/pdf"
  payload = upload.file.read()
  assert payload.startswith(b"%PDF-")
  assert b"%%EOF" in payload[-4096:]
