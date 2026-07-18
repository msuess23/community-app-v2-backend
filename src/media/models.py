"""Shared SQLAlchemy columns for domain-owned images."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID


class ImageMetadataMixin:
  """Reusable immutable image metadata without ownership relationships.

  Concrete domains keep their own tables and foreign keys. This preserves
  referential integrity while avoiding duplicate technical metadata columns.
  """

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  storage_key = Column(String(500), nullable=False, unique=True)
  original_filename = Column(String(255), nullable=False)
  mime_type = Column(String(100), nullable=False)
  size_bytes = Column(BigInteger, nullable=False)
  width = Column(Integer, nullable=True)
  height = Column(Integer, nullable=True)
  uploaded_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
  )
  is_cover = Column(Boolean, nullable=False, default=False)
