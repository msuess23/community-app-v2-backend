"""Response mapping for mutable Info rows and their current image metadata."""

from __future__ import annotations

from src.info.media import info_image_content_url
from src.info.models import Info, InfoImage, InfoStatusEntry
from src.info.schemas import InfoImageResponse, InfoResponse, InfoStatusResponse


class InfoResponseMapper:
  """Convert loaded Info domain rows into stable API response models."""

  @staticmethod
  def status_response(entry: InfoStatusEntry) -> InfoStatusResponse:
    """Map one Info status row to its public response."""

    return InfoStatusResponse.model_validate(entry)

  @staticmethod
  def image_response(image: InfoImage) -> InfoImageResponse:
    """Map one Info image row to public metadata and a content URL."""

    return InfoImageResponse(
      id=image.id,
      info_id=image.info_id,
      url=info_image_content_url(image.info_id, image.id),
      original_filename=image.original_filename,
      mime_type=image.mime_type,
      size_bytes=image.size_bytes,
      width=image.width,
      height=image.height,
      uploaded_at=image.uploaded_at,
      is_cover=image.is_cover,
    )

  @staticmethod
  def info_response(
    info: Info,
    current_status: InfoStatusEntry,
  ) -> InfoResponse:
    """Map an Info row and its latest status to the public response."""

    cover = next(
      (image for image in getattr(info, "images", ()) if image.is_cover),
      None,
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
      current_status=InfoResponseMapper.status_response(current_status),
      image_url=(
        info_image_content_url(info.id, cover.id)
        if cover is not None
        else None
      ),
    )
