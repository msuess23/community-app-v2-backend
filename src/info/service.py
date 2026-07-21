"""Classical Info CRUD and its small non-versioned status history."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from src.address.service import AddressService
from src.core.exceptions import (
  DomainValidationException,
  ResourceNotFoundException,
)
from src.core.filters import SortOrder
from src.core.schemas import PaginatedResponse
from src.info.access_policy import InfoAccessPolicy
from src.info.mapper import InfoResponseMapper
from src.info.media import register_info_file_deletions
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
from src.user.models import User


class InfoService:
  """Manage Infos as ordinary mutable rows with a physical DELETE."""

  @staticmethod
  def _validate_window(
    starts_at: datetime,
    ends_at: datetime,
  ) -> None:
    """Require a valid start and end time for an Info notice."""

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
    """Require a valid optional time range for Info filtering."""

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
    """Load an active office or raise the canonical validation error."""

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
  async def _validate_create_office(
    db: AsyncSession,
    office_id: uuid.UUID | None,
    current_user: User,
  ) -> None:
    """Validate the office assignment allowed for a new Info notice."""

    InfoAccessPolicy.require_create_permission(office_id, current_user)
    if office_id is not None:
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
    """Return a public filtered and paginated Info list."""

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
      InfoResponseMapper.info_response(info, latest[info.id])
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
    """Return one public Info notice and its latest status."""

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
    return InfoResponseMapper.info_response(info, current)

  @staticmethod
  async def create_info(
    db: AsyncSession,
    request: InfoCreateRequest,
    current_user: User,
  ) -> InfoResponse:
    """Create a mutable Info notice with its initial status row."""

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
    # Initialize the image collection before synchronous response mapping.
    info = Info(
      id=uuid.uuid4(),
      title=request.title,
      description=request.description,
      category=request.category,
      office_id=request.office_id,
      address=address,
      images=[],
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
    return InfoResponseMapper.info_response(info, initial_status)

  @staticmethod
  async def update_info(
    db: AsyncSession,
    info_id: uuid.UUID,
    request: InfoUpdateRequest,
    current_user: User,
  ) -> InfoResponse:
    """Apply an in-place Info update without creating a revision."""

    info = await InfoRepository.get_by_id(db, info_id, for_update=True)
    if info is None:
      raise ResourceNotFoundException(
        "Info not found",
        error_code="INFO_NOT_FOUND",
      )
    InfoAccessPolicy.require_manage_permission(info, current_user)

    if "office_id" in request.model_fields_set:
      InfoAccessPolicy.require_reassignment_permission(
        info,
        request.office_id,
        current_user,
      )
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
    return InfoResponseMapper.info_response(info, current)

  @staticmethod
  async def delete_info(
    db: AsyncSession,
    info_id: uuid.UUID,
    current_user: User,
  ) -> None:
    """Physically delete an Info notice and its owned resources."""

    info = await InfoRepository.get_by_id(db, info_id, for_update=True)
    if info is None:
      raise ResourceNotFoundException(
        "Info not found",
        error_code="INFO_NOT_FOUND",
      )
    InfoAccessPolicy.require_manage_permission(info, current_user)
    register_info_file_deletions(db, list(info.images))
    await InfoRepository.delete(db, info)
    await db.flush()

  @staticmethod
  async def get_status_history(
    db: AsyncSession,
    info_id: uuid.UUID,
  ) -> list[InfoStatusResponse]:
    """Return the chronological public status history of an Info notice."""

    if await InfoRepository.get_by_id(db, info_id) is None:
      raise ResourceNotFoundException(
        "Info not found",
        error_code="INFO_NOT_FOUND",
      )
    entries = await InfoStatusRepository.get_history(db, info_id)
    return [InfoResponseMapper.status_response(entry) for entry in entries]

  @staticmethod
  async def get_current_status(
    db: AsyncSession,
    info_id: uuid.UUID,
  ) -> InfoStatusResponse | None:
    """Return the latest public status of an Info notice."""

    if await InfoRepository.get_by_id(db, info_id) is None:
      raise ResourceNotFoundException(
        "Info not found",
        error_code="INFO_NOT_FOUND",
      )
    entry = await InfoStatusRepository.get_latest(db, info_id)
    return InfoResponseMapper.status_response(entry) if entry is not None else None

  @staticmethod
  async def add_status(
    db: AsyncSession,
    info_id: uuid.UUID,
    request: InfoStatusCreateRequest,
    current_user: User,
  ) -> InfoStatusResponse:
    """Append a status row and update the current Info status atomically."""

    info = await InfoRepository.get_by_id(db, info_id, for_update=True)
    if info is None:
      raise ResourceNotFoundException(
        "Info not found",
        error_code="INFO_NOT_FOUND",
      )
    InfoAccessPolicy.require_manage_permission(info, current_user)

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
    return InfoResponseMapper.status_response(entry)
