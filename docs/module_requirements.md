# Module Requirements Traceability

This document maps the principal course requirements to concrete backend components and verification points.

## Ad-hoc workflow

The ticket domain implements an actor-controlled processing path with a fixed entry and terminal outcome but a variable number and order of intermediate steps.

Evidence:

- `src/ticket/services/workflow_commands.py`
  - dispatch to an office,
  - select or replace the primary officer,
  - forward current responsibility to another employee,
  - request and complete a cosignature,
  - escalate to a selected manager and record a decision,
  - request additional citizen input and return responsibility afterward,
  - return a wrongly assigned case to dispatch,
  - complete the ticket with a public outcome.
- `src/ticket/services/workflow_queries.py` calculates actions allowed for the current state and actor.
- `scripts/seed/seed_tickets.py` creates different paths and path lengths instead of one fixed sequence.

The next participant is selected by the acting user for forwarding, cosignature, escalation, and dispatch. This preserves the central characteristic of an ad-hoc workflow: the path between submission and completion is not a single predetermined chain.

## Event sourcing for at least two entities

### Tickets

- Pure aggregate evolution: `src/ticket/domain/aggregate.py`
- Typed event payloads: `src/ticket/domain/payloads.py`
- Append-only event table: `TicketEvent` in `src/ticket/models/ticket.py`
- Event store and synchronous projection update: `src/ticket/services/event_store.py`
- Deterministic replay: `rebuild_ticket()` and `TicketEventStore.rebuild()`
- Current query model: `Ticket`

Ticket comments and ticket image changes are also represented as immutable ticket events.

### Appointments

- Pure aggregate evolution: `src/appointment/domain/aggregate.py`
- Typed event payloads: `src/appointment/domain/payloads.py`
- Append-only event table: `AppointmentEvent` in `src/appointment/models.py`
- Event store and synchronous projection update: `src/appointment/event_store.py`
- Deterministic replay: `rebuild_appointment()` and `AppointmentEventStore.rebuild()`
- Current query model: `Appointment`

Appointment document versions append `DOCUMENT_VERSION_ADDED` events without changing scheduling state.

## Complete and genuine CRUD entity

`Info` is an ordinary mutable SQLAlchemy entity:

- Create: `POST /api/v1/infos`
- Read: list and detail endpoints
- Update: `PUT /api/v1/infos/{info_id}` mutates the existing row
- Delete: `DELETE /api/v1/infos/{info_id}` physically removes the row

There is no content version table, soft delete, tombstone, or event-sourced projection for Info. Owned status rows, addresses, images, and files are removed with the Info according to their transaction and cascade rules.

## Server-side input validation and error output

- Pydantic request schemas enforce lengths, required fields, enum values, timezone awareness, interval ordering, and strict unknown-field rejection.
- Domain services enforce cross-record rules such as office ownership, active-state checks, slot availability, workflow transitions, and related-ticket ownership.
- Database constraints provide a final integrity layer for uniqueness, foreign keys, valid statuses, positive sizes, and event sequence numbers.
- `src/core/error_handlers.py` converts validation, domain, HTTP, integrity, and unexpected exceptions into a consistent JSON error envelope with stable error codes and optional field details.

## User management and role-specific rights

Supported roles:

- `CITIZEN`
- `DISPATCHER`
- `OFFICER`
- `MANAGER`
- `ADMIN`

Authorization is implemented through FastAPI dependencies and object-level access policies. The roles intentionally have different scopes:

- citizens manage their own submissions and appointments,
- dispatchers route central-inbox tickets,
- officers process assigned tickets and office appointments,
- managers assign staff and make management decisions,
- administrators manage users and offices but do not receive general ticket workflow privileges.

## Object-relational mapping

SQLAlchemy declarative models are used consistently for all persisted domains. `src/models.py` imports the complete model registry so metadata and Alembic autogeneration see the same tables and relationships.

Examples of consistent ORM use include:

- explicit foreign keys and relationships,
- owned addresses with `delete-orphan` and `single_parent`,
- append-only event relationships,
- partial unique indexes for current covers and document versions,
- repository classes around `AsyncSession` queries.

## Migrations

Alembic migrations cover the complete schema from the initial revision to one current head. The verification script checks:

```bash
alembic heads
alembic upgrade base:head --sql
alembic downgrade head:base --sql
```

PostgreSQL-specific integration tests verify behavior that cannot be represented reliably by lightweight substitutes, including row locks, partial indexes, and concurrent commands.

## Seeding

`scripts/seed/run_seed.py` runs one idempotent transaction in this order:

1. administrator,
2. offices and addresses,
3. remaining role-specific users,
4. ticket scenarios and event histories,
5. Info CRUD scenarios and media,
6. appointment slots, event histories, ticket links, and PDF versions.

The seeders use application services and event stores where domain behavior is involved. This keeps events, projections, relationships, and media metadata consistent with normal API writes.

## Additional course-relevant backend support

Search, filtering, sorting, and pagination are available for the main list resources. The backend exposes OpenAPI metadata for client generation and preserves anonymous access semantics for public endpoints. Client-side accessibility and platform-independent user interfaces remain responsibilities of the separate frontend projects.
