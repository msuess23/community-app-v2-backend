"""Revision-aware ticket image endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile, status
from fastapi.responses import FileResponse

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user, get_optional_current_user
from src.core.database import get_db
from src.ticket.services.images import TicketImageService
from src.ticket.schemas import (
  TicketImageRemoveRequest, TicketImageResponse,
)
from src.user.models import User


router = APIRouter()

@router.get("/{ticket_id}/images", response_model=list[TicketImageResponse])
async def list_ticket_images(
  ticket_id: uuid.UUID,
  include_removed: bool = Query(False),
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User | None = Depends(get_optional_current_user),
):
  """Lists active ticket images or the full staff audit view."""

  return await TicketImageService.list_images(
    db,
    ticket_id,
    current_user,
    include_removed=include_removed,
  )


@router.post(
  "/{ticket_id}/images",
  response_model=TicketImageResponse,
  status_code=status.HTTP_201_CREATED,
)
async def upload_ticket_image(
  ticket_id: uuid.UUID,
  file: UploadFile = File(...),
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(get_current_user),
):
  """Uploads an image and records immutable metadata in the ticket stream."""

  return await TicketImageService.add_image(db, ticket_id, file, current_user)


@router.put(
  "/{ticket_id}/images/{image_id}/cover",
  response_model=TicketImageResponse,
)
async def set_ticket_cover_image(
  ticket_id: uuid.UUID,
  image_id: uuid.UUID,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(get_current_user),
):
  """Select the image used as the ticket cover."""

  return await TicketImageService.set_cover(
    db,
    ticket_id,
    image_id,
    current_user,
  )


@router.delete(
  "/{ticket_id}/images/{image_id}",
  status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_ticket_image(
  ticket_id: uuid.UUID,
  image_id: uuid.UUID,
  request: TicketImageRemoveRequest = Body(default_factory=TicketImageRemoveRequest),
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(get_current_user),
):
  """Removes an image from the current projection without deleting its file."""

  await TicketImageService.remove_image(
    db,
    ticket_id,
    image_id,
    request,
    current_user,
  )


@router.get("/{ticket_id}/images/{image_id}/content", response_class=FileResponse)
async def get_ticket_image_content(
  ticket_id: uuid.UUID,
  image_id: uuid.UUID,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User | None = Depends(get_optional_current_user),
):
  """Streams current images and authorized historical image revisions."""

  path, image = await TicketImageService.get_content(
    db,
    ticket_id,
    image_id,
    current_user,
  )
  return FileResponse(
    path=path,
    media_type=image.mime_type,
    filename=image.original_filename,
  )
