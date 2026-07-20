"""Seed event-sourced tickets with varied ad-hoc workflow histories."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seed.context import SeedContext
from scripts.seed.media_factory import image_upload
from src.address.schemas import AddressCreate
from src.ticket.domain import (
  EscalationDecision,
  TicketCategory,
  TicketCompletionOutcome,
  TicketVisibility,
  TicketWorkflowAction,
)
from src.ticket.models import Ticket
from src.ticket.schemas import (
  TicketImageResponse,
  CompleteTicketAction,
  CosignTicketAction,
  DecideEscalationAction,
  EscalateTicketAction,
  ForwardTicketAction,
  PrimaryOfficerAssignmentRequest,
  RequestCitizenResponseAction,
  RequestCosignatureAction,
  ReturnToDispatchAction,
  TicketCancelRequest,
  TicketCommentCreateRequest,
  TicketCreateRequest,
  TicketDispatchRequest,
  TicketUpdateRequest,
)
from src.ticket.services.comments import TicketCommentService
from src.ticket.services.images import TicketImageService
from src.ticket.services.ticket_commands import TicketCommandService
from src.ticket.services.workflow_commands import TicketWorkflowCommandService
from src.user.models import User

logger = logging.getLogger(__name__)

TICKET_SEED_TITLES = (
  "[Demo] Schlagloch am Rathausplatz",
  "[Demo] Zurückgezogene Lärmbeschwerde",
  "[Demo] Defekte Straßenlaterne",
  "[Demo] Beschädigter Gehweg",
  "[Demo] Baustellenabsicherung weitergeleitet",
  "[Demo] Baumfällung wartet auf Mitzeichnung",
  "[Demo] Sondernutzung wartet auf Entscheidung",
  "[Demo] Ummeldung wartet auf Bürgerantwort",
  "[Demo] Verkehrsschild vollständig bearbeitet",
  "[Demo] Unzuständiger Antrag abgelehnt",
  "[Demo] Falsch zugeordnetes Anliegen",
)


async def _find_ticket(db: AsyncSession, title: str) -> Ticket | None:
  """Load a previously seeded ticket by its stable demo title."""

  result = await db.execute(select(Ticket).where(Ticket.title == title).limit(1))
  return result.scalar_one_or_none()


async def _create_ticket(
  db: AsyncSession,
  *,
  citizen: User,
  title: str,
  description: str,
  category: TicketCategory,
  visibility: TicketVisibility = TicketVisibility.PUBLIC,
  address: AddressCreate | None = None,
) -> Ticket:
  """Create one ticket through the public command service and reload its projection."""

  response = await TicketCommandService.create_ticket(
    db,
    TicketCreateRequest(
      title=title,
      description=description,
      category=category,
      visibility=visibility,
      address=address,
    ),
    citizen,
  )
  ticket = await _find_ticket(db, response.title)
  if ticket is None:
    raise RuntimeError(f"Seed ticket was not persisted: {title}")
  return ticket


async def _dispatch_and_assign(
  db: AsyncSession,
  *,
  ticket: Ticket,
  dispatcher: User,
  manager: User,
  officer: User,
  office_id: uuid.UUID,
) -> None:
  """Route a ticket to an office and assign its first permanent officer."""

  await TicketWorkflowCommandService.dispatch_ticket(
    db,
    ticket.id,
    TicketDispatchRequest(
      office_id=office_id,
      comment="Seeded routing decision.",
    ),
    dispatcher,
  )
  await TicketWorkflowCommandService.assign_primary_officer(
    db,
    ticket.id,
    PrimaryOfficerAssignmentRequest(
      primary_officer_id=officer.id,
      comment="Seeded primary case assignment.",
    ),
    manager,
  )


async def _add_ticket_image(
  db: AsyncSession,
  *,
  ticket: Ticket,
  actor: User,
  filename: str,
  rgb: tuple[int, int, int],
) -> TicketImageResponse:
  """Attach one generated PNG through the event-sourced image service."""

  upload = image_upload(filename, rgb=rgb)
  try:
    return await TicketImageService.add_image(db, ticket.id, upload, actor)
  finally:
    await upload.close()


async def _seed_scenario(
  db: AsyncSession,
  *,
  title: str,
  builder: Callable[[], Awaitable[None]],
) -> None:
  """Run one ticket scenario only when its stable title does not exist."""

  if await _find_ticket(db, title) is not None:
    logger.info("Skipped existing ticket scenario: %s", title)
    return
  await builder()
  logger.info("Created ticket scenario: %s", title)


async def run_ticket_seeder(db: AsyncSession, context: SeedContext) -> None:
  """Seed diverse tickets and variable-length event histories idempotently."""

  logger.info("Seeding ticket scenarios")
  bauamt = context.office("Bauamt")
  buergeramt = context.office("Bürgeramt")
  manager1 = context.user("manager1@bauamt.com")
  manager2 = context.user("manager2@bauamt.com")
  manager3 = context.user("manager3@buergeramt.com")
  dispatcher1 = context.user("dispatcher1@bauamt.com")
  dispatcher2 = context.user("dispatcher2@buergeramt.com")
  officer1 = context.user("officer1@bauamt.com")
  officer2 = context.user("officer2@bauamt.com")
  officer3 = context.user("officer3@buergeramt.com")
  citizen1 = context.user("citizen1@test.com")
  citizen2 = context.user("citizen2@test.com")
  citizen3 = context.user("citizen3@test.com")

  async def new_ticket() -> None:
    ticket = await _create_ticket(
      db,
      citizen=citizen1,
      title=TICKET_SEED_TITLES[0],
      description="A deep pothole is visible next to the town hall entrance.",
      category=TicketCategory.INFRASTRUCTURE,
      address=AddressCreate(
        street="Rathausplatz",
        house_number="3",
        zip_code="12345",
        city="Musterstadt",
        latitude=52.5204,
        longitude=13.4054,
      ),
    )
    first = await _add_ticket_image(
      db,
      ticket=ticket,
      actor=citizen1,
      filename="pothole-overview.png",
      rgb=(155, 118, 84),
    )
    second = await _add_ticket_image(
      db,
      ticket=ticket,
      actor=citizen1,
      filename="pothole-closeup.png",
      rgb=(91, 75, 62),
    )
    await TicketImageService.set_cover(db, ticket.id, second.id, citizen1)
    await TicketCommandService.update_ticket(
      db,
      ticket.id,
      TicketUpdateRequest(
        description=(
          "A deep pothole is visible next to the town hall entrance. "
          "Two photographs document the current condition."
        )
      ),
      citizen1,
    )
    await TicketCommentService.add_comment(
      db,
      ticket.id,
      TicketCommentCreateRequest(
        text=f"The overview image identifier is {first.id}.",
        is_internal=False,
      ),
      citizen1,
    )

  async def cancelled_ticket() -> None:
    ticket = await _create_ticket(
      db,
      citizen=citizen2,
      title=TICKET_SEED_TITLES[1],
      description="A temporary noise complaint that was resolved privately.",
      category=TicketCategory.NOISE,
      visibility=TicketVisibility.PRIVATE,
    )
    await TicketCommandService.cancel_ticket(
      db,
      ticket.id,
      TicketCancelRequest(reason="The disturbance ended before authority action."),
      citizen2,
    )

  async def awaiting_assignment() -> None:
    ticket = await _create_ticket(
      db,
      citizen=citizen3,
      title=TICKET_SEED_TITLES[2],
      description="The streetlight remains dark throughout the night.",
      category=TicketCategory.SAFETY,
    )
    await TicketWorkflowCommandService.dispatch_ticket(
      db,
      ticket.id,
      TicketDispatchRequest(
        office_id=bauamt.id,
        comment="Electrical infrastructure falls within the Bauamt queue.",
      ),
      dispatcher1,
    )

  async def active_ticket() -> None:
    ticket = await _create_ticket(
      db,
      citizen=citizen1,
      title=TICKET_SEED_TITLES[3],
      description="Loose paving stones create a trip hazard near the service entrance.",
      category=TicketCategory.INFRASTRUCTURE,
    )
    await _dispatch_and_assign(
      db,
      ticket=ticket,
      dispatcher=dispatcher2,
      manager=manager3,
      officer=officer3,
      office_id=buergeramt.id,
    )
    await TicketCommentService.add_comment(
      db,
      ticket.id,
      TicketCommentCreateRequest(
        text="Citizen reports that the damaged area is approximately two metres wide.",
        is_internal=False,
      ),
      citizen1,
    )
    await TicketCommentService.add_comment(
      db,
      ticket.id,
      TicketCommentCreateRequest(
        text="Internal inspection request added to the weekly route.",
        is_internal=True,
      ),
      officer3,
    )

  async def forwarded_ticket() -> None:
    ticket = await _create_ticket(
      db,
      citizen=citizen2,
      title=TICKET_SEED_TITLES[4],
      description="Temporary barriers require a second technical assessment.",
      category=TicketCategory.SAFETY,
    )
    await _dispatch_and_assign(
      db,
      ticket=ticket,
      dispatcher=dispatcher1,
      manager=manager1,
      officer=officer1,
      office_id=bauamt.id,
    )
    await TicketWorkflowCommandService.assign_primary_officer(
      db,
      ticket.id,
      PrimaryOfficerAssignmentRequest(
        primary_officer_id=officer2.id,
        comment="Primary ownership changed to the road-safety specialist.",
      ),
      manager1,
    )
    await TicketWorkflowCommandService.forward_ticket(
      db,
      ticket.id,
      ForwardTicketAction(
        action=TicketWorkflowAction.FORWARD,
        target_user_id=manager2.id,
        comment="Management coordination is required for the contractor response.",
      ),
      officer2,
    )

  async def cosignature_ticket() -> None:
    ticket = await _create_ticket(
      db,
      citizen=citizen3,
      title=TICKET_SEED_TITLES[5],
      description="A planned tree removal requires a second technical opinion.",
      category=TicketCategory.OTHER,
    )
    await _dispatch_and_assign(
      db,
      ticket=ticket,
      dispatcher=dispatcher1,
      manager=manager1,
      officer=officer1,
      office_id=bauamt.id,
    )
    await TicketWorkflowCommandService.request_cosignature(
      db,
      ticket.id,
      RequestCosignatureAction(
        action=TicketWorkflowAction.REQUEST_COSIGNATURE,
        target_user_id=officer2.id,
        comment="Please confirm the traffic-safety assessment.",
      ),
      officer1,
    )

  async def escalation_ticket() -> None:
    ticket = await _create_ticket(
      db,
      citizen=citizen1,
      title=TICKET_SEED_TITLES[6],
      description="A special-use request exceeds the normal approval threshold.",
      category=TicketCategory.OTHER,
    )
    await _dispatch_and_assign(
      db,
      ticket=ticket,
      dispatcher=dispatcher1,
      manager=manager1,
      officer=officer2,
      office_id=bauamt.id,
    )
    await TicketWorkflowCommandService.escalate_ticket(
      db,
      ticket.id,
      EscalateTicketAction(
        action=TicketWorkflowAction.ESCALATE,
        manager_user_id=manager2.id,
        reason="The projected cost exceeds the officer approval threshold.",
      ),
      officer2,
    )

  async def citizen_response_ticket() -> None:
    ticket = await _create_ticket(
      db,
      citizen=citizen2,
      title=TICKET_SEED_TITLES[7],
      description="The submitted relocation request lacks the moving date.",
      category=TicketCategory.OTHER,
      visibility=TicketVisibility.PRIVATE,
    )
    await _dispatch_and_assign(
      db,
      ticket=ticket,
      dispatcher=dispatcher2,
      manager=manager3,
      officer=officer3,
      office_id=buergeramt.id,
    )
    await TicketWorkflowCommandService.request_citizen_response(
      db,
      ticket.id,
      RequestCitizenResponseAction(
        action=TicketWorkflowAction.REQUEST_CITIZEN_RESPONSE,
        question="On which date did the move take place?",
      ),
      officer3,
    )

  async def completed_ticket() -> None:
    ticket = await _create_ticket(
      db,
      citizen=citizen3,
      title=TICKET_SEED_TITLES[8],
      description="A bent traffic sign requires replacement and final inspection.",
      category=TicketCategory.SAFETY,
      address=AddressCreate(
        street="Parkstraße",
        house_number="18",
        zip_code="12345",
        city="Musterstadt",
        latitude=52.5191,
        longitude=13.3988,
      ),
    )
    await _dispatch_and_assign(
      db,
      ticket=ticket,
      dispatcher=dispatcher1,
      manager=manager1,
      officer=officer1,
      office_id=bauamt.id,
    )
    await TicketWorkflowCommandService.request_cosignature(
      db,
      ticket.id,
      RequestCosignatureAction(
        action=TicketWorkflowAction.REQUEST_COSIGNATURE,
        target_user_id=officer2.id,
        comment="Confirm the replacement location before installation.",
      ),
      officer1,
    )
    await TicketWorkflowCommandService.cosign_ticket(
      db,
      ticket.id,
      CosignTicketAction(
        action=TicketWorkflowAction.COSIGN,
        comment="Location and visibility requirements confirmed.",
      ),
      officer2,
    )
    await TicketWorkflowCommandService.escalate_ticket(
      db,
      ticket.id,
      EscalateTicketAction(
        action=TicketWorkflowAction.ESCALATE,
        manager_user_id=manager1.id,
        reason="Replacement requires release of the maintenance budget.",
      ),
      officer1,
    )
    await TicketWorkflowCommandService.decide_escalation(
      db,
      ticket.id,
      DecideEscalationAction(
        action=TicketWorkflowAction.DECIDE_ESCALATION,
        decision=EscalationDecision.APPROVED,
        comment="Budget release approved.",
      ),
      manager1,
    )
    await TicketCommentService.add_comment(
      db,
      ticket.id,
      TicketCommentCreateRequest(
        text="Replacement installed and photographed during final inspection.",
        is_internal=True,
      ),
      officer1,
    )
    await TicketWorkflowCommandService.complete_ticket(
      db,
      ticket.id,
      CompleteTicketAction(
        action=TicketWorkflowAction.COMPLETE,
        outcome=TicketCompletionOutcome.RESOLVED,
        message="The damaged traffic sign was replaced successfully.",
      ),
      officer1,
    )

  async def rejected_ticket() -> None:
    ticket = await _create_ticket(
      db,
      citizen=citizen1,
      title=TICKET_SEED_TITLES[9],
      description="A request was submitted to an office without legal responsibility.",
      category=TicketCategory.OTHER,
      visibility=TicketVisibility.PRIVATE,
    )
    await _dispatch_and_assign(
      db,
      ticket=ticket,
      dispatcher=dispatcher2,
      manager=manager3,
      officer=officer3,
      office_id=buergeramt.id,
    )
    await TicketWorkflowCommandService.forward_ticket(
      db,
      ticket.id,
      ForwardTicketAction(
        action=TicketWorkflowAction.FORWARD,
        target_user_id=manager3.id,
        comment="Manager review required before rejecting the request.",
      ),
      officer3,
    )
    await TicketWorkflowCommandService.complete_ticket(
      db,
      ticket.id,
      CompleteTicketAction(
        action=TicketWorkflowAction.COMPLETE,
        outcome=TicketCompletionOutcome.REJECTED,
        message="The request must be filed with the responsible external authority.",
      ),
      manager3,
    )

  async def returned_ticket() -> None:
    ticket = await _create_ticket(
      db,
      citizen=citizen2,
      title=TICKET_SEED_TITLES[10],
      description="The initial routing selected the wrong specialist office.",
      category=TicketCategory.CLEANING,
    )
    await _dispatch_and_assign(
      db,
      ticket=ticket,
      dispatcher=dispatcher1,
      manager=manager1,
      officer=officer2,
      office_id=bauamt.id,
    )
    await TicketWorkflowCommandService.return_to_dispatch(
      db,
      ticket.id,
      ReturnToDispatchAction(
        action=TicketWorkflowAction.RETURN_TO_DISPATCH,
        reason="The issue concerns waste collection rather than construction.",
      ),
      officer2,
    )

  scenarios = zip(
    TICKET_SEED_TITLES,
    (
      new_ticket,
      cancelled_ticket,
      awaiting_assignment,
      active_ticket,
      forwarded_ticket,
      cosignature_ticket,
      escalation_ticket,
      citizen_response_ticket,
      completed_ticket,
      rejected_ticket,
      returned_ticket,
    ),
    strict=True,
  )
  for title, builder in scenarios:
    await _seed_scenario(db, title=title, builder=builder)
