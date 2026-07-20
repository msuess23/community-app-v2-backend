"""Canonical FastAPI routes for the Info CRUD domain."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import role_required
from src.core.database import get_db
from src.core.filters import SortOrder, get_bbox_filter
from src.core.query_params import PageParams, SearchParams, get_page_params, get_search_params
from src.core.schemas import PaginatedResponse
from src.info.image_service import InfoImageService
from src.info.models import InfoCategory, InfoSortField, InfoStatus
from src.info.schemas import (
  InfoCreateRequest,
  InfoImageResponse,
  InfoResponse,
  InfoStatusCreateRequest,
  InfoStatusResponse,
  InfoUpdateRequest,
)
from src.info.service import InfoService
from src.user.models import Role, User


router = APIRouter()


@router.get("", response_model=PaginatedResponse[InfoResponse])
async def list_infos(
  office_id: uuid.UUID | None = Query(None),
  category: InfoCategory | None = Query(None),
  info_status: InfoStatus | None = Query(None, alias="status"),
  starts_from: datetime | None = Query(None),
  ends_to: datetime | None = Query(None),
  bbox: Optional[Tuple[float, float, float, float]] = Depends(get_bbox_filter),
  sort_by: InfoSortField = Query(InfoSortField.STARTS_AT),
  order: SortOrder = Query(SortOrder.ASC),
  page_params: PageParams = Depends(get_page_params),
  search_params: SearchParams = Depends(get_search_params),
  db: AsyncSession = Depends(get_db, scope="function"),
):
  """List Infos with search, filters, deterministic sorting and pagination."""

  return await InfoService.list_infos(
    db,
    page=page_params.page,
    size=page_params.size,
    office_id=office_id,
    category=category,
    status=info_status,
    starts_from=starts_from,
    ends_to=ends_to,
    search=search_params.q,
    bbox=bbox,
    sort_by=sort_by,
    order=order,
  )


@router.get("/{info_id}", response_model=InfoResponse)
async def get_info(
  info_id: uuid.UUID,
  db: AsyncSession = Depends(get_db, scope="function"),
):
  """Return one current Info row."""

  return await InfoService.get_info(db, info_id)


@router.get("/{info_id}/status", response_model=list[InfoStatusResponse])
async def get_info_status_history(
  info_id: uuid.UUID,
  db: AsyncSession = Depends(get_db, scope="function"),
):
  """Return the simple public status history in reverse chronological order."""

  return await InfoService.get_status_history(db, info_id)


@router.get(
  "/{info_id}/status/current",
  response_model=InfoStatusResponse | None,
)
async def get_current_info_status(
  info_id: uuid.UUID,
  response: Response,
  db: AsyncSession = Depends(get_db, scope="function"),
):
  """Return the latest status or HTTP 204 when no status exists."""

  current = await InfoService.get_current_status(db, info_id)
  if current is None:
    response.status_code = status.HTTP_204_NO_CONTENT
  return current


@router.post("", response_model=InfoResponse, status_code=status.HTTP_201_CREATED)
async def create_info(
  request: InfoCreateRequest,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(
    role_required(Role.OFFICER, Role.MANAGER, Role.ADMIN)
  ),
):
  """Create an Info for the user's office or, as admin, any active office."""

  return await InfoService.create_info(db, request, current_user)


@router.put("/{info_id}", response_model=InfoResponse)
async def update_info(
  info_id: uuid.UUID,
  request: InfoUpdateRequest,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(
    role_required(Role.OFFICER, Role.MANAGER, Role.ADMIN)
  ),
):
  """Mutate the existing Info row without creating a historical revision."""

  return await InfoService.update_info(db, info_id, request, current_user)


@router.delete("/{info_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_info(
  info_id: uuid.UUID,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(
    role_required(Role.OFFICER, Role.MANAGER, Role.ADMIN)
  ),
):
  """Physically delete an Info and its owned address and status rows."""

  await InfoService.delete_info(db, info_id, current_user)


@router.put("/{info_id}/status", response_model=InfoStatusResponse)
async def update_info_status(
  info_id: uuid.UUID,
  request: InfoStatusCreateRequest,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(
    role_required(Role.OFFICER, Role.MANAGER, Role.ADMIN)
  ),
):
  """Append one status message and update the Info's current status."""

  return await InfoService.add_status(db, info_id, request, current_user)


@router.get(
  "/{info_id}/images",
  response_model=list[InfoImageResponse],
)
async def list_info_images(
  info_id: uuid.UUID,
  db: AsyncSession = Depends(get_db, scope="function"),
):
  """List every current image owned by one public Info."""

  return await InfoImageService.list_images(db, info_id)


@router.post(
  "/{info_id}/images",
  response_model=InfoImageResponse,
  status_code=status.HTTP_201_CREATED,
)
async def upload_info_image(
  info_id: uuid.UUID,
  file: UploadFile = File(...),
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(
    role_required(Role.OFFICER, Role.MANAGER, Role.ADMIN)
  ),
):
  """Upload one validated current image without creating a revision."""

  return await InfoImageService.add_image(db, info_id, file, current_user)


@router.put(
  "/{info_id}/images/{image_id}/cover",
  response_model=InfoImageResponse,
)
async def set_info_cover_image(
  info_id: uuid.UUID,
  image_id: uuid.UUID,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(
    role_required(Role.OFFICER, Role.MANAGER, Role.ADMIN)
  ),
):
  """Select the image exposed as the Info cover."""

  return await InfoImageService.set_cover(
    db,
    info_id,
    image_id,
    current_user,
  )


@router.delete(
  "/{info_id}/images/{image_id}",
  status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_info_image(
  info_id: uuid.UUID,
  image_id: uuid.UUID,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(
    role_required(Role.OFFICER, Role.MANAGER, Role.ADMIN)
  ),
):
  """Physically delete one image row and its file after commit."""

  await InfoImageService.delete_image(
    db,
    info_id,
    image_id,
    current_user,
  )


@router.get(
  "/{info_id}/images/{image_id}/content",
  response_class=FileResponse,
)
async def get_info_image_content(
  info_id: uuid.UUID,
  image_id: uuid.UUID,
  db: AsyncSession = Depends(get_db, scope="function"),
):
  """Stream one current public Info image."""

  path, image = await InfoImageService.get_content(db, info_id, image_id)
  return FileResponse(
    path=path,
    media_type=image.mime_type,
    filename=image.original_filename,
    content_disposition_type="inline",
  )
