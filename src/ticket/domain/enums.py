"""Enumerations used by the ticket aggregate and API."""

import enum


class TicketCategory(str, enum.Enum):
  """Categories retained from the previous Ktor ticket API."""

  INFRASTRUCTURE = "INFRASTRUCTURE"
  CLEANING = "CLEANING"
  SAFETY = "SAFETY"
  NOISE = "NOISE"
  OTHER = "OTHER"


class TicketVisibility(str, enum.Enum):
  """Controls whether a ticket is visible in the public community list."""

  PUBLIC = "PUBLIC"
  PRIVATE = "PRIVATE"


class TicketStatus(str, enum.Enum):
  """Coarse processing status that may be exposed to citizens."""

  OPEN = "OPEN"
  IN_PROGRESS = "IN_PROGRESS"
  RESOLVED = "RESOLVED"
  REJECTED = "REJECTED"
  CANCELLED = "CANCELLED"


class TicketWorkflowState(str, enum.Enum):
  """Small internal state set supporting the sequential ad-hoc workflow."""

  NEW = "NEW"
  AWAITING_PRIMARY_ASSIGNMENT = "AWAITING_PRIMARY_ASSIGNMENT"
  IN_PROGRESS = "IN_PROGRESS"
  WAITING_FOR_COSIGNATURE = "WAITING_FOR_COSIGNATURE"
  WAITING_FOR_CITIZEN = "WAITING_FOR_CITIZEN"
  WAITING_FOR_DECISION = "WAITING_FOR_DECISION"
  COMPLETED = "COMPLETED"


class EscalationDecision(str, enum.Enum):
  """Possible decisions for a pending management escalation."""

  APPROVED = "APPROVED"
  REJECTED = "REJECTED"


class TicketCompletionOutcome(str, enum.Enum):
  """Terminal outcomes exposed through the public ticket status."""

  RESOLVED = "RESOLVED"
  REJECTED = "REJECTED"


class TicketEventType(str, enum.Enum):
  """Events kept in the simplified append-only ticket stream."""

  TICKET_SUBMITTED = "TICKET_SUBMITTED"
  TICKET_DETAILS_UPDATED = "TICKET_DETAILS_UPDATED"
  TICKET_CANCELLED = "TICKET_CANCELLED"
  TICKET_DISPATCHED = "TICKET_DISPATCHED"
  PRIMARY_OFFICER_ASSIGNED = "PRIMARY_OFFICER_ASSIGNED"
  TICKET_FORWARDED = "TICKET_FORWARDED"
  COSIGNATURE_REQUESTED = "COSIGNATURE_REQUESTED"
  TICKET_COSIGNED = "TICKET_COSIGNED"
  CITIZEN_RESPONSE_REQUESTED = "CITIZEN_RESPONSE_REQUESTED"
  CITIZEN_RESPONDED = "CITIZEN_RESPONDED"
  TICKET_ESCALATED = "TICKET_ESCALATED"
  ESCALATION_DECIDED = "ESCALATION_DECIDED"
  TICKET_COMPLETED = "TICKET_COMPLETED"
  TICKET_COMMENTED = "TICKET_COMMENTED"
  TICKET_IMAGE_ADDED = "TICKET_IMAGE_ADDED"
  TICKET_IMAGE_REMOVED = "TICKET_IMAGE_REMOVED"
  TICKET_COVER_IMAGE_CHANGED = "TICKET_COVER_IMAGE_CHANGED"


class TicketWorkflowAction(str, enum.Enum):
  """Commands exposed by the simplified authority-side workflow."""

  DISPATCH = "DISPATCH"
  ASSIGN_PRIMARY_OFFICER = "ASSIGN_PRIMARY_OFFICER"
  FORWARD = "FORWARD"
  REQUEST_COSIGNATURE = "REQUEST_COSIGNATURE"
  COSIGN = "COSIGN"
  ESCALATE = "ESCALATE"
  DECIDE_ESCALATION = "DECIDE_ESCALATION"
  REQUEST_CITIZEN_RESPONSE = "REQUEST_CITIZEN_RESPONSE"
  COMPLETE = "COMPLETE"
