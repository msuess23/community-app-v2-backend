"""Classical Info CRUD and its small non-versioned status history."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.address.service import AddressService
from src.core.config import settings
from src.core.exceptions import (
  DomainValidationException,
  ForbiddenException,
  ResourceNotFoundException,
)
from src.core.filters import SortOrder
from src.core.schemas import PaginatedResponse
from src.info.models import (
  Info,
  InfoCategory,
  InfoSortField,
  InfoStatus,
  InfoStatusEntry,
)
from src.info.repository import InfoRepository, InfoStatusRepository
from src.info.schemas import (
  InfoCreateRequest,
  InfoResponse,
  InfoStatusCreateRequest,
  InfoStatusResponse,
  InfoUpdateRequest,
)
from src.office.models import Office
from src.office.repository import OfficeRepository
from src.user.models import Role, User
from src.user.roles import CASE_WORKER_ROLES


class InfoService:
  """Manage Infos as ordinary mutable rows with a physical DELETE."""

  @staticmethod
  def _status_response(entry: InfoStatusEntry) -> InfoStatusResponse:
    return InfoStatusResponse.model_validate(entry)

  @staticmethod
  def _response(info: Info, current_status: InfoStatusEntry) -> InfoResponse:
    cover = next(
      (image for image in getattr(info, "images", []) if image.is_cover),
      None,
    )
    image_url = (
      f"{settings.BASE_URL}/infos/{info.id}/images/{cover.id}/content"
      if cover is not None
      else None
    )
    return InfoResponse(
      id=info.id,
      title=info.title,
      description=info.description,
      category=info.category,
      office_id=info.office_id,
      address=info.address,
      created_at=info.created_at,
      updated_at=info.updated_at,
      starts_at=info.starts_at,
      ends_at=info.ends_at,
      current_status=InfoService._status_response(current_status),
      image_url=image_url,
    )

  @staticmethod
  def _validate_window(
    starts_at: datetime,
    ends_at: datetime,
  ) -> None:
    if ends_at <= starts_at:
      raise DomainValidationException(
        "ends_at must be after starts_at.",
        error_code="INFO_INVALID_TIME_RANGE",
      )

  @staticmethod
  def _validate_filter_window(
    starts_from: datetime | None,
    ends_to: datetime | None,
  ) -> None:
    for value in (starts_from, ends_to):
      if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise DomainValidationException(
          "Info date filters must include a timezone.",
          error_code="DATE_TIMEZONE_REQUIRED",
        )
    if starts_from is not None and ends_to is not None and starts_from > ends_to:
      raise DomainValidationException(
        "starts_from must not be after ends_to.",
        error_code="INVALID_DATE_RANGE",
      )

  @staticmethod
  async def _require_active_office(
    db: AsyncSession,
    office_id: uuid.UUID,
  ) -> Office:
    office = await OfficeRepository.get_by_id(db, office_id)
    if office is None:
      raise DomainValidationException(
        "The selected office does not exist.",
        error_code="INFO_OFFICE_NOT_FOUND",
        details=[{"field": "office_id", "message": "Office not found"}],
      )
    if not office.is_active:
      raise DomainValidationException(
        "The selected office is inactive.",
        error_code="INFO_OFFICE_INACTIVE",
        details=[{"field": "office_id", "message": "Office is inactive"}],
      )
    return office

  @staticmethod
  def _require_manage_permission(info: Info, current_user: User) -> None:
    if current_user.role == Role.ADMIN:
      return
    if (
      current_user.role not in CASE_WORKER_ROLES
      or info.office_id is None
      or current_user.office_id != info.office_id
    ):
      raise ForbiddenException()

  @staticmethod
  async def _validate_create_office(
    db: AsyncSession,
    office_id: uuid.UUID | None,
    current_user: User,
  ) -> None:
    if current_user.role == Role.ADMIN:
      if office_id is not None:
        await InfoService._require_active_office(db, office_id)
      return

    if current_user.role not in CASE_WORKER_ROLES:
      raise ForbiddenException()
    if office_id is None or office_id != current_user.office_id:
      raise ForbiddenException(
        "Case workers may create Infos only for their own office."
      )
    await InfoService._require_active_office(db, office_id)

  @staticmethod
  async def list_infos(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    office_id: uuid.UUID | None,
    category: InfoCategory | None,
    status: InfoStatus | None,
    starts_from: datetime | None,
    ends_to: datetime | None,
    search: str | None,
    bbox: tuple[float, float, float, float] | None,
    sort_by: InfoSortField,
    order: SortOrder,
  ) -> PaginatedResponse[InfoResponse]:
    InfoService._validate_filter_window(starts_from, ends_to)
    infos, total = await InfoRepository.get_page(
      db,
      page=page,
      size=size,
      office_id=office_id,
      category=category,
      status=status,
      starts_from=starts_from,
      ends_to=ends_to,
      search=search,
      bbox=bbox,
      sort_by=sort_by,
      order=order,
    )
    latest = await InfoStatusRepository.get_latest_map(
      db,
      [info.id for info in infos],
    )
    responses = [
      InfoService._response(info, latest[info.id])
      for info in infos
      if info.id in latest
    ]
    return PaginatedResponse.create(
      data=responses,
      total=total,
      page=page,
      size=size,
    )

  @staticmethod
  async def get_info(
    db: AsyncSession,
    info_id: uuid.UUID,
  ) -> InfoResponse:
    info = await InfoRepository.get_by_id(db, info_id)
    if info is None:
      raise ResourceNotFoundException(
        "Info not found",
        error_code="INFO_NOT_FOUND",
      )
    current = await InfoStatusRepository.get_latest(db, info.id)
    if current is None:
      raise ResourceNotFoundException(
        "Info status not found",
        error_code="INFO_STATUS_NOT_FOUND",
      )
    return InfoService._response(info, current)

  @staticmethod
  async def create_info(
    db: AsyncSession,
    request: InfoCreateRequest,
    current_user: User,
  ) -> InfoResponse:
    await InfoService._validate_create_office(
      db,
      request.office_id,
      current_user,
    )
    InfoService._validate_window(request.starts_at, request.ends_at)

    address = (
      AddressService.create_address_entity(request.address)
      if request.address is not None
      else None
    )
    now = datetime.now(timezone.utc)
    info = Info(
      id=uuid.uuid4(),
      title=request.title,
      description=request.description,
      category=request.category,
      office_id=request.office_id,
      address=address,
      current_status=InfoStatus.SCHEDULED,
      created_at=now,
      updated_at=now,
      starts_at=request.starts_at,
      ends_at=request.ends_at,
    )
    InfoRepository.add(db, info)
    await db.flush()

    initial_status = InfoStatusEntry(
      id=uuid.uuid4(),
      info_id=info.id,
      status=InfoStatus.SCHEDULED,
      message="Created",
      created_by_user_id=current_user.id,
      created_at=now,
    )
    InfoStatusRepository.add(db, initial_status)
    await db.flush()
    return InfoService._response(info, initial_status)

  @staticmethod
  async def update_info(
    db: AsyncSession,
    info_id: uuid.UUID,
    request: InfoUpdateRequest,
    current_user: User,
  ) -> InfoResponse:
    info = await InfoRepository.get_by_id(db, info_id, for_update=True)
    if info is None:
      raise ResourceNotFoundException(
        "Info not found",
        error_code="INFO_NOT_FOUND",
      )
    InfoService._require_manage_permission(info, current_user)

    if "office_id" in request.model_fields_set:
      if current_user.role != Role.ADMIN and request.office_id != info.office_id:
        raise ForbiddenException("Only administrators may reassign an Info.")
      if request.office_id is not None:
        await InfoService._require_active_office(db, request.office_id)
      info.office_id = request.office_id

    if "address" in request.model_fields_set:
      if request.address is None:
        info.address = None
      elif info.address is None:
        info.address = AddressService.create_address_from_update(request.address)
      else:
        AddressService.update_address_entity(info.address, request.address)

    for field in ("title", "description", "category", "starts_at", "ends_at"):
      if field in request.model_fields_set:
        setattr(info, field, getattr(request, field))

    InfoService._validate_window(info.starts_at, info.ends_at)
    info.updated_at = datetime.now(timezone.utc)
    InfoRepository.add(db, info)
    await db.flush()

    current = await InfoStatusRepository.get_latest(db, info.id)
    if current is None:
      raise ResourceNotFoundException(
        "Info status not found",
        error_code="INFO_STATUS_NOT_FOUND",
      )
    return InfoService._response(info, current)

  @staticmethod
  async def delete_info(
    db: AsyncSession,
    info_id: uuid.UUID,
    current_user: User,
  ) -> None:
    info = await InfoRepository.get_by_id(db, info_id, for_update=True)
    if info is None:
      raise ResourceNotFoundException(
        "Info not found",
        error_code="INFO_NOT_FOUND",
      )
    InfoService._require_manage_permission(info, current_user)
    from src.info.image_service import InfoImageService

    InfoImageService.register_file_deletions(db, list(info.images))
    await InfoRepository.delete(db, info)
    await db.flush()

  @staticmethod
  async def get_status_history(
    db: AsyncSession,
    info_id: uuid.UUID,
  ) -> list[InfoStatusResponse]:
    if await InfoRepository.get_by_id(db, info_id) is None:
      raise ResourceNotFoundException(
        "Info not found",
        error_code="INFO_NOT_FOUND",
      )
    entries = await InfoStatusRepository.get_history(db, info_id)
    return [InfoService._status_response(entry) for entry in entries]

  @staticmethod
  async def get_current_status(
    db: AsyncSession,
    info_id: uuid.UUID,
  ) -> InfoStatusResponse | None:
    if await InfoRepository.get_by_id(db, info_id) is None:
      raise ResourceNotFoundException(
        "Info not found",
        error_code="INFO_NOT_FOUND",
      )
    entry = await InfoStatusRepository.get_latest(db, info_id)
    return InfoService._status_response(entry) if entry is not None else None

  @staticmethod
  async def add_status(
    db: AsyncSession,
    info_id: uuid.UUID,
    request: InfoStatusCreateRequest,
    current_user: User,
  ) -> InfoStatusResponse:
    info = await InfoRepository.get_by_id(db, info_id, for_update=True)
    if info is None:
      raise ResourceNotFoundException(
        "Info not found",
        error_code="INFO_NOT_FOUND",
      )
    InfoService._require_manage_permission(info, current_user)

    now = datetime.now(timezone.utc)
    entry = InfoStatusEntry(
      id=uuid.uuid4(),
      info_id=info.id,
      status=request.status,
      message=request.message,
      created_by_user_id=current_user.id,
      created_at=now,
    )
    info.current_status = request.status
    info.updated_at = now
    InfoStatusRepository.add(db, entry)
    await db.flush()
    return InfoService._status_response(entry)
