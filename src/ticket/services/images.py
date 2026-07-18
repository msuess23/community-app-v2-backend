"""Event-sourced ticket image commands and revision-aware reads."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import (
  ConflictException,
  ForbiddenException,
  ResourceNotFoundException,
)
from src.media.cover import (
  apply_cover_change,
  new_image_should_be_cover,
  plan_cover_after_removal,
  plan_cover_selection,
)
from src.media.storage import (
  ImageStorageConfig,
  ImageStorageErrorCodes,
  LocalImageStorage,
)
from src.ticket.domain import (
  TicketCoverImageChangedPayload,
  TicketEventType,
  TicketImageAddedPayload,
  TicketImageRemovedPayload,
  TicketWorkflowState,
)
from src.ticket.models import Ticket, TicketImage
from src.ticket.repositories.image import TicketImageRepository
from src.ticket.repositories.ticket import TicketProjectionRepository
from src.ticket.schemas import TicketImageRemoveRequest, TicketImageResponse
from src.ticket.services.access_policy import TicketAccessPolicy
from src.ticket.services.event_store import TicketEventStore
from src.ticket.services.loaders import require_ticket
from src.user.models import Role, User
from src.user.roles import CASE_WORKER_ROLES


class TicketImageService:
  """Coordinate ticket permissions, image events and current projections."""

  @staticmethod
  def _storage_config() -> ImageStorageConfig:
    """Build the ticket-specific configuration for the shared image store."""

    return ImageStorageConfig(
      root=settings.TICKET_MEDIA_ROOT,
      max_bytes=settings.TICKET_IMAGE_MAX_BYTES,
      allowed_mime_types=frozenset(settings.TICKET_IMAGE_ALLOWED_MIME_TYPES),
      fallback_filename="ticket-image",
      subject="ticket",
      errors=ImageStorageErrorCodes(
        unsupported_type="UNSUPPORTED_TICKET_IMAGE_TYPE",
        too_large="TICKET_IMAGE_TOO_LARGE",
        empty="EMPTY_TICKET_IMAGE",
        invalid_content="INVALID_TICKET_IMAGE_CONTENT",
        type_mismatch="TICKET_IMAGE_TYPE_MISMATCH",
        invalid_dimensions="INVALID_TICKET_IMAGE_DIMENSIONS",
        file_not_found="TICKET_IMAGE_FILE_NOT_FOUND",
      ),
    )

  @staticmethod
  def _image_url(ticket_id: uuid.UUID, image_id: uuid.UUID) -> str:
    """Build the stable API URL for one ticket image."""

    return f"{settings.BASE_URL}/tickets/{ticket_id}/images/{image_id}/content"

  @staticmethod
  def _response(image: TicketImage) -> TicketImageResponse:
    """Convert one image projection into its API metadata representation."""

    return TicketImageResponse(
      id=image.id,
      ticket_id=image.ticket_id,
      url=TicketImageService._image_url(image.ticket_id, image.id),
      original_filename=image.original_filename,
      mime_type=image.mime_type,
      size_bytes=image.size_bytes,
      width=image.width,
      height=image.height,
      uploaded_at=image.uploaded_at,
      is_active=image.is_active,
      is_cover=image.is_cover,
      removed_at=image.removed_at,
    )

  @staticmethod
  async def _require_manage_permission(
    db: AsyncSession,
    ticket: Ticket,
    current_user: User,
  ) -> None:
    """Apply the immutable-submission rule and staff workflow permissions."""

    if current_user.role == Role.CITIZEN:
      if current_user.id != ticket.creator_user_id:
        raise ForbiddenException("Only the ticket creator may manage these images")
      if ticket.workflow_state != TicketWorkflowState.NEW:
        raise ConflictException(
          "Ticket images can no longer be changed after processing has started.",
          error_code="TICKET_ALREADY_IN_PROCESS",
        )
      return

    if current_user.role not in CASE_WORKER_ROLES:
      raise ForbiddenException("Only assigned authority staff may manage ticket images")
    if ticket.workflow_state == TicketWorkflowState.COMPLETED:
      raise ConflictException(
        "Images cannot be changed after the ticket is completed.",
        error_code="TICKET_COMPLETED",
      )
    if not TicketAccessPolicy.can_manage_images(ticket, current_user):
      raise ForbiddenException("The user has no internal access to this ticket")

  @staticmethod
  async def list_images(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User | None,
    *,
    include_removed: bool = False,
  ) -> list[TicketImageResponse]:
    """List current images or, for authorized staff, the complete audit list."""

    ticket = await TicketProjectionRepository.get_by_id(db, ticket_id)
    if ticket is None or not TicketAccessPolicy.can_view(ticket, current_user):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")

    if include_removed:
      if current_user is None or current_user.role not in CASE_WORKER_ROLES:
        raise ForbiddenException("Only authority staff may view removed ticket images")
      if not TicketAccessPolicy.can_view_internal(ticket, current_user):
        raise ForbiddenException("The user has no internal access to this ticket")

    images = await TicketImageRepository.get_images(
      db,
      ticket_id,
      include_removed=include_removed,
    )
    return [TicketImageService._response(image) for image in images]

  @staticmethod
  async def add_image(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    upload: UploadFile,
    current_user: User,
  ) -> TicketImageResponse:
    """Store a new immutable file and record its metadata in the event stream."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    await TicketImageService._require_manage_permission(db, ticket, current_user)

    image_id = uuid.uuid4()
    storage_config = TicketImageService._storage_config()
    stored = await LocalImageStorage.save_upload(
      upload,
      owner_path=str(ticket.id),
      image_id=image_id,
      config=storage_config,
    )
    active_images = await TicketImageRepository.get_images(
      db,
      ticket.id,
      include_removed=False,
      for_update=True,
    )
    is_cover = new_image_should_be_cover(active_images)

    try:
      event = await TicketEventStore.append(
        db,
        ticket,
        actor_user_id=current_user.id,
        event_type=TicketEventType.TICKET_IMAGE_ADDED,
        payload=TicketImageAddedPayload(
          image_id=image_id,
          storage_key=stored.storage_key,
          original_filename=stored.original_filename,
          mime_type=stored.mime_type,
          size_bytes=stored.size_bytes,
          width=stored.width,
          height=stored.height,
          is_cover=is_cover,
        ),
      )
      image = TicketImage(
        id=image_id,
        ticket_id=ticket.id,
        storage_key=stored.storage_key,
        original_filename=stored.original_filename,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        width=stored.width,
        height=stored.height,
        uploaded_by_user_id=current_user.id,
        uploaded_at=event.occurred_at,
        is_active=True,
        is_cover=is_cover,
        added_event_id=event.id,
        cover_selected_event_id=(event.id if is_cover else None),
      )
      TicketImageRepository.add_image(db, image)
      await db.flush()
    except Exception:
      # Failures before the request commit must not leave an unreferenced file.
      LocalImageStorage.delete_file(stored.storage_key, config=storage_config)
      raise

    return TicketImageService._response(image)

  @staticmethod
  async def set_cover(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    image_id: uuid.UUID,
    current_user: User,
  ) -> TicketImageResponse:
    """Change the cover projection while preserving the decision as an event."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    await TicketImageService._require_manage_permission(db, ticket, current_user)
    images = await TicketImageRepository.get_images(
      db,
      ticket.id,
      include_removed=False,
      for_update=True,
    )
    try:
      change = plan_cover_selection(images, image_id)
    except ValueError as exc:
      raise ResourceNotFoundException(
        "Ticket image not found",
        error_code="TICKET_IMAGE_NOT_FOUND",
      ) from exc

    selected = next(image for image in images if image.id == image_id)
    if not change.changed:
      return TicketImageService._response(selected)

    event = await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_COVER_IMAGE_CHANGED,
      payload=TicketCoverImageChangedPayload(image_id=selected.id),
    )
    selected = apply_cover_change(images, change)
    assert selected is not None
    selected.cover_selected_event_id = event.id
    await db.flush()
    return TicketImageService._response(selected)

  @staticmethod
  async def remove_image(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    image_id: uuid.UUID,
    request: TicketImageRemoveRequest,
    current_user: User,
  ) -> None:
    """Deactivate an image projection but intentionally retain its file."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    await TicketImageService._require_manage_permission(db, ticket, current_user)
    images = await TicketImageRepository.get_images(
      db,
      ticket.id,
      include_removed=False,
      for_update=True,
    )
    try:
      cover_change = plan_cover_after_removal(images, image_id)
    except ValueError as exc:
      raise ResourceNotFoundException(
        "Ticket image not found",
        error_code="TICKET_IMAGE_NOT_FOUND",
      ) from exc
    image = next(item for item in images if item.id == image_id)

    removed_at = datetime.now(timezone.utc)
    removed_event = await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_IMAGE_REMOVED,
      payload=TicketImageRemovedPayload(image_id=image.id, reason=request.reason),
      occurred_at=removed_at,
    )
    image.is_active = False
    image.is_cover = False
    image.removed_at = removed_at
    image.removed_by_user_id = current_user.id
    image.removed_event_id = removed_event.id

    selected = apply_cover_change(images, cover_change)
    if cover_change.changed and selected is not None:
      # The replacement is a separate event because the cover affects public output.
      cover_event = await TicketEventStore.append(
        db,
        ticket,
        actor_user_id=current_user.id,
        event_type=TicketEventType.TICKET_COVER_IMAGE_CHANGED,
        payload=TicketCoverImageChangedPayload(image_id=selected.id),
      )
      selected.cover_selected_event_id = cover_event.id
    await db.flush()

  @staticmethod
  async def get_content(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    image_id: uuid.UUID,
    current_user: User | None,
  ) -> tuple[Path, TicketImage]:
    """Return image bytes, including removed revisions only for internal staff."""

    ticket = await TicketProjectionRepository.get_by_id(db, ticket_id)
    image = await TicketImageRepository.get_image(db, ticket_id, image_id)
    if ticket is None or image is None:
      raise ResourceNotFoundException(
        "Ticket image not found",
        error_code="TICKET_IMAGE_NOT_FOUND",
      )

    if image.is_active:
      if not TicketAccessPolicy.can_view(ticket, current_user):
        raise ResourceNotFoundException(
          "Ticket image not found",
          error_code="TICKET_IMAGE_NOT_FOUND",
        )
    else:
      if current_user is None or current_user.role not in CASE_WORKER_ROLES:
        raise ResourceNotFoundException(
          "Ticket image not found",
          error_code="TICKET_IMAGE_NOT_FOUND",
        )
      if not TicketAccessPolicy.can_view_internal(ticket, current_user):
        raise ResourceNotFoundException(
          "Ticket image not found",
          error_code="TICKET_IMAGE_NOT_FOUND",
        )

    path = LocalImageStorage.resolve_file(
      image.storage_key,
      config=TicketImageService._storage_config(),
    )
    return path, image
