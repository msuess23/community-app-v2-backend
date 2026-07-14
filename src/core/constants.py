import uuid


# Stable technical principal used for migrations, seed data, and scheduled
# system actions. It is an inactive, non-login user persisted in the users
# table so audit actor foreign keys always reference a real principal.
SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
SYSTEM_USER_EMAIL = "system@internal.example.com"
