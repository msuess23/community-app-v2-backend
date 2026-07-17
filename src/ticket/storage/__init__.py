"""Storage adapters used by ticket assets."""

from src.ticket.storage.image_storage import LocalTicketMediaStorage, StoredTicketImage

__all__ = ["LocalTicketMediaStorage", "StoredTicketImage"]
