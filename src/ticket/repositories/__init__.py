"""Repository mixins composed by the compatibility TicketRepository facade."""

from src.ticket.repositories.event import TicketEventRepository as TicketEventRepository
from src.ticket.repositories.image import TicketImageRepository as TicketImageRepository
from src.ticket.repositories.ticket import TicketProjectionRepository as TicketProjectionRepository
from src.ticket.repositories.vote import TicketVoteRepository as TicketVoteRepository
from src.ticket.repositories.work_item import TicketWorkItemRepository as TicketWorkItemRepository
