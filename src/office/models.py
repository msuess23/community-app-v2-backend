import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from src.core.database import Base

class Office(Base):
  """
  Represents a department or authority office (e.g., Building Department).
  Used for routing in the ticket workflow.
  """
  __tablename__ = "offices"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  name = Column(String, nullable=False, unique=False)
  description = Column(String, nullable=True)
  contact_email = Column(String, nullable=True)
  phone = Column(String, nullable=True)
  services = Column(ARRAY(String), default=list)
  opening_hours = Column(JSONB, default=dict)
  is_active = Column(Boolean, default=True)
  created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
  deactivated_at = Column(DateTime(timezone=True), nullable=True)
  address_id = Column(UUID(as_uuid=True), ForeignKey("addresses.id"), nullable=True)
  address = relationship("Address", backref="offices")


class OfficeHistory(Base):
  """
  Audit trail for Office changes to ensure revision security.
  """
  __tablename__ = "office_history"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  office_id = Column(UUID(as_uuid=True), ForeignKey("offices.id"), index=True)
  
  name = Column(String)
  description = Column(String, nullable=True)
  contact_email = Column(String, nullable=True)
  phone = Column(String, nullable=True)
  services = Column(ARRAY(String), default=list)
  opening_hours = Column(JSONB, default=dict)
  address_snapshot = Column(String, nullable=True)
  is_active = Column(Boolean, nullable=False, default=True)
  changed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
  changed_by_user_id = Column(UUID(as_uuid=True))
  change_reason = Column(String, nullable=False)