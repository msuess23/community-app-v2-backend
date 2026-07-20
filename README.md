# Community App Fachverfahren Backend

FastAPI backend for citizen tickets, authority-side ad-hoc processing, appointments, public information notices, and role-based administration.

## Technology

- Python 3.11+
- FastAPI and Pydantic v2
- SQLAlchemy 2 with asynchronous PostgreSQL access
- Alembic migrations
- Append-only event streams for tickets and appointments
- Local immutable media storage for ticket images, Info images, and appointment PDFs

## Local setup

Create a `.env` file with at least the application, JWT, and PostgreSQL settings defined in `src/core/config.py`. Then install dependencies and migrate the database:

```bash
pip install -r requirements-dev.txt
alembic upgrade head
```

Start the API with an ASGI server, for example:

```bash
uvicorn src.main:app --reload
```

## Demo seeding

Demo seeding is disabled in production and requires `SEED_DEFAULT_PASSWORD`:

```bash
export ENVIRONMENT=development
export SEED_DEFAULT_PASSWORD='change-me-123'
python -m scripts.seed.run_seed
```

The same seed process can run during application startup by setting:

```text
RUN_SEED_ON_STARTUP=true
```

The seed process is idempotent and runs in one database transaction. It creates:

- three offices with different addresses and service data,
- administrators, dispatchers, managers, officers, and citizens,
- eleven ticket scenarios with variable event histories,
- ticket addresses, comments, and event-sourced images,
- six mutable Info notices with different categories and statuses,
- Info addresses, status histories, and CRUD-owned images,
- available, inactive, booked, released, and consumed appointment slots,
- scheduled, rescheduled, cancelled, completed, no-show, and ticket-linked appointments,
- citizen-visible and internal appointment PDFs, including a replaced document version.

All demo users use the configured `SEED_DEFAULT_PASSWORD`. Stable email addresses are listed in `scripts/seed/seed_users.py`.

## Verification

Run the complete offline verification suite with:

```bash
./scripts/verify_backend.sh
```

The PostgreSQL-specific concurrency and constraint tests additionally require an expendable PostgreSQL database:

```bash
RUN_POSTGRES_TESTS=1 pytest -q
```

## Documentation

- `docs/module_requirements.md` maps the implementation to the principal course requirements.
- OpenAPI is available at the configured API documentation endpoint when the application is running.
- Every class, function, method, and nested function in `src/` has an English docstring. A regression test prevents undocumented source callables from being introduced.
