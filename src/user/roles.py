"""Shared role groups used by authorization and domain services."""

from src.user.models import Role


CASE_WORKER_ROLES = frozenset({Role.OFFICER, Role.MANAGER})
AUTHORITY_ROLES = frozenset({Role.DISPATCHER, Role.OFFICER, Role.MANAGER})
OFFICE_REQUIRED_ROLES = frozenset({Role.OFFICER, Role.MANAGER})
