"""Compatibility facade for the split authority-side workflow services."""

from src.ticket.services.access_policy import TicketAccessPolicy
from src.ticket.services.mapper import TicketResponseMapper
from src.ticket.services.workflow.assignment import TicketAssignmentService
from src.ticket.services.workflow.dispatcher import TicketWorkflowDispatcher
from src.ticket.services.workflow.queries import TicketWorkflowQueryService
from src.ticket.services.workflow.work_items import TicketWorkItemService
from src.ticket.services.workflow.commands import TicketWorkflowCommandService


class TicketWorkflowService(
  TicketWorkflowQueryService,
  TicketAssignmentService,
  TicketWorkflowDispatcher,
  TicketWorkItemService,
):
  """Preserves the original workflow API while delegating focused concerns."""

  _ticket_internal_response = staticmethod(TicketResponseMapper.to_internal_ticket)
  _event_response = staticmethod(TicketResponseMapper.to_event)
  _work_item_response = staticmethod(TicketResponseMapper.to_work_item)
  can_view_internal_ticket = staticmethod(TicketAccessPolicy.can_view_internal)
  respond_as_citizen = staticmethod(TicketWorkflowCommandService.respond_as_citizen)
