import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone

from src.core.database import Base

class Office(Base):
  """
  Represents a department or authority office (e.g., Building Department).
  Used for routing in the ticket workflow.
  """
  __tablename__ = "offices"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  name = Column(String, nullable=False, unique=True)
  is_active = Column(Boolean, default=True)
  created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class OfficeHistory(Base):
  """
  Audit trail for Office changes to ensure revision security.
  """
  __tablename__ = "office_history"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  office_id = Column(UUID(as_uuid=True), ForeignKey("offices.id"), index=True)
  
  name = Column(String)
  changed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
  changed_by_user_id = Column(UUID(as_uuid=True))
  change_reason = Column(String, nullable=False)