import uuid
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_optional_current_user, role_required
from src.core.database import get_db
from src.core.filters import LifecycleStatusFilter, SortOrder, get_bbox_filter
from src.core.query_params import (
  DateRangeParams,
  PageParams,
  SearchParams,
  get_history_date_range,
  get_page_params,
  get_search_params,
)
from src.core.schemas import PaginatedResponse
from src.office.models import OfficeSortField
from src.office.schemas import (
  OfficeCreate,
  OfficeDeactivateRequest,
  OfficeHistoryResponse,
  OfficeResponse,
  OfficeUpdate,
)
from src.office.service import OfficeService
from src.user.models import Role, User


router = APIRouter()


@router.get("", response_model=PaginatedResponse[OfficeResponse])
async def get_all_offices(
  bbox: Optional[Tuple[float, float, float, float]] = Depends(get_bbox_filter),
  status_filter: LifecycleStatusFilter = Query(
    LifecycleStatusFilter.ACTIVE,
    alias="status",
  ),
  sort_by: OfficeSortField = OfficeSortField.NAME,
  order: SortOrder = SortOrder.ASC,
  page_params: PageParams = Depends(get_page_params),
  search_params: SearchParams = Depends(get_search_params),
  db: AsyncSession = Depends(get_db),
  current_user: User | None = Depends(get_optional_current_user),
):
  """List offices; only administrators may request inactive records."""

  return await OfficeService.get_all_offices(
    db,
    current_user=current_user,
    page=page_params.page,
    size=page_params.size,
    status=status_filter,
    search=search_params.q,
    bbox=bbox,
    sort_by=sort_by,
    order=order,
  )


@router.get("/{office_id}", response_model=OfficeResponse)
async def get_office(
  office_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User | None = Depends(get_optional_current_user),
):
  include_inactive = current_user is not None and current_user.role == Role.ADMIN
  return await OfficeService.get_office_by_id(
    db,
    office_id,
    include_inactive=include_inactive,
  )


@router.post("", response_model=OfficeResponse, status_code=status.HTTP_201_CREATED)
async def create_office(
  office_data: OfficeCreate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.ADMIN)),
):
  return await OfficeService.create_office(db, office_data, current_user.id)


@router.patch("/{office_id}", response_model=OfficeResponse)
async def update_office(
  office_id: uuid.UUID,
  update_data: OfficeUpdate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.ADMIN)),
):
  target_office = await OfficeService.get_office_by_id(
    db,
    office_id,
    include_inactive=True,
  )
  return await OfficeService.update_office(
    db,
    target_office,
    update_data,
    current_user.id,
  )


@router.delete("/{office_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_office(
  office_id: uuid.UUID,
  request: OfficeDeactivateRequest,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.ADMIN)),
):
  await OfficeService.deactivate_office(
    db,
    office_id,
    current_user.id,
    request.change_reason,
  )


@router.get(
  "/{office_id}/history",
  response_model=PaginatedResponse[OfficeHistoryResponse],
)
async def get_office_history(
  office_id: uuid.UUID,
  page_params: PageParams = Depends(get_page_params),
  date_range: DateRangeParams = Depends(get_history_date_range),
  db: AsyncSession = Depends(get_db),
  _current_user: User = Depends(role_required(Role.ADMIN)),
):
  return await OfficeService.get_office_history(
    db,
    office_id,
    page=page_params.page,
    size=page_params.size,
    start_date=date_range.start,
    end_date=date_range.end,
  )
