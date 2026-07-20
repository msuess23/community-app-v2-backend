"""Aggregate the focused appointment HTTP routers."""

from fastapi import APIRouter
from src.appointment.router.appointments import router as appointments_router
from src.appointment.router.documents import router as documents_router
from src.appointment.router.slots import router as slots_router

router = APIRouter()
router.include_router(slots_router)
router.include_router(appointments_router)
router.include_router(documents_router)
