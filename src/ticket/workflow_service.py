"""Compatibility facade for the split authority-side workflow services."""

from src.ticket.services.access_policy import TicketAccessPolicy
from src.ticket.services.mapper import TicketResponseMapper
from src.ticket.services.workflow.assignment import TicketAssignmentService
from src.ticket.services.workflow.commands import TicketWorkflowCommandService
from src.ticket.services.workflow.dispatcher import TicketWorkflowDispatcher
from src.ticket.services.workflow.queries import TicketWorkflowQueryService


class TicketWorkflowService(
  TicketWorkflowQueryService,
  TicketAssignmentService,
  TicketWorkflowDispatcher,
):
  """Preserve the existing workflow import while delegating focused concerns."""

  _ticket_internal_response = staticmethod(TicketResponseMapper.to_internal_ticket)
  _event_response = staticmethod(TicketResponseMapper.to_event)
  can_view_internal_ticket = staticmethod(TicketAccessPolicy.can_view_internal)
  respond_as_citizen = staticmethod(TicketWorkflowCommandService.respond_as_citizen)
