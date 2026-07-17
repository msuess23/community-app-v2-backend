from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.ticket.events import TicketCategory, TicketStatus, TicketVisibility
from src.ticket.schemas import TicketCreateRequest, TicketResponse, TicketStatusResponse


def test_create_request_forbids_citizen_office_selection() -> None:
  with pytest.raises(ValidationError):
    TicketCreateRequest.model_validate(
      {
        "title": "Pothole",
        "category": "INFRASTRUCTURE",
        "officeId": str(uuid4()),
      }
    )


def test_ticket_response_uses_ktor_compatible_camel_case_aliases() -> None:
  now = datetime.now(timezone.utc)
  response = TicketResponse(
    id=uuid4(),
    title="Pothole",
    category=TicketCategory.INFRASTRUCTURE,
    creator_user_id=uuid4(),
    visibility=TicketVisibility.PUBLIC,
    created_at=now,
    current_status=TicketStatusResponse(
      id=uuid4(),
      status=TicketStatus.OPEN,
      created_by_user_id=uuid4(),
      created_at=now,
    ),
    version=1,
  )

  data = response.model_dump(by_alias=True)

  assert "creatorUserId" in data
  assert "currentStatus" in data
  assert "votesCount" in data
  assert "imageUrl" in data
  assert "creator_user_id" not in data


def test_parallel_cosignature_action_rejects_duplicate_users() -> None:
  from src.ticket.events import TicketWorkflowAction
  from src.ticket.schemas import RequestParallelCosignaturesAction

  assignee = uuid4()
  with pytest.raises(ValidationError):
    RequestParallelCosignaturesAction(
      action=TicketWorkflowAction.REQUEST_PARALLEL_COSIGNATURES,
      assigneeUserIds=[assignee, assignee],
    )


def test_workflow_action_uses_camel_case_fields() -> None:
  from src.ticket.events import TicketWorkflowAction, TicketWorkItemOutcome
  from src.ticket.schemas import CompleteWorkItemAction

  action = CompleteWorkItemAction(
    action=TicketWorkflowAction.COMPLETE_WORK_ITEM,
    workItemId=uuid4(),
    outcome=TicketWorkItemOutcome.APPROVED,
  )

  data = action.model_dump(by_alias=True)
  assert "workItemId" in data
  assert "work_item_id" not in data
