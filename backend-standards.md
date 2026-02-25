Backend Standards & Development Guidelines (FastAPI)

This document defines the backend architecture, coding standards, and synchronization patterns for this project.

Tech Stack: FastAPI, uv (Package Manager), SQLModel (ORM), Alembic (Migrations), Pydantic v2 (Validation), psycopg (Driver).

1. Project Management (uv)

Package Manager: Use uv for all dependency management and virtual environments.

Lockfile: Always commit uv.lock to ensure deterministic builds.

Scripts: Define common tasks (dev, lint, migrate) in pyproject.toml under [tool.uv.scripts].

# Example usage
uv add fastapi sqlmodel alembic pydantic-settings
uv run uvicorn app.main:app --reload


2. Project Structure (Layered Architecture)

We follow a strict Layered Architecture to separate concerns:

/app:

/api: Presentation layer (Routes & Dependencies).

/models: SQLModel definitions (Table models + API schemas).

/services: Business logic (Interacts with DB and external APIs).

/core: Global config, security (JWT), and DB engine setup.

/migrations: Alembic migration scripts.

/tests: Pytest suite.

3. Data Models & Validation (SQLModel + Pydantic v2)

SQLModel allows us to share models between the database and API.

Class Naming:

UserBase: Common fields (Pydantic only).

User: The actual database table (table=True).

UserCreate / UserUpdate: Specialized DTOs for input validation.

UserPublic: Outbound data (hiding sensitive fields like hashed_password).

from sqlmodel import SQLModel, Field

class UserBase(SQLModel):
    email: str = Field(unique=True, index=True)
    full_name: str | None = None

class User(UserBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    hashed_password: str

class UserCreate(UserBase):
    password: str


4. Database & Migrations (SQLModel + Alembic)

Migrations: Never use SQLModel.metadata.create_all(). Always use Alembic.

Naming: Migration names must be descriptive (e.g., alembic revision --autogenerate -m "add_user_profile_fields").

Driver: Use psycopg (v3) for high-performance PostgreSQL connectivity.

Session Management: Use a dependency (get_session) with a context manager or yield for automatic cleanup.

# app/core/db.py
async def get_session():
    async with Session(engine) as session:
        yield session


5. API Design & Authentication

Versioning: Use prefix /api/v1 for all routes.

Auth: * Managed Auth (Clerk/PropelAuth) is preferred for rapid scaling.

Use FastAPI Dependencies to inject the current user into routes.

Error Handling: Use custom exceptions that map to specific HTTP status codes.

@router.get("/me", response_model=UserPublic)
async def read_user_me(current_user: User = Depends(get_current_user)):
    return current_user


6. Frontend Synchronization (OpenAPI)

To keep the React frontend in sync with the FastAPI backend:

Generate Spec: FastAPI automatically generates openapi.json at /openapi.json.

Generate Client: Use @hey-api/openapi-ts or similar in the frontend to generate TypeScript types and TanStack Query hooks.

Workflow:

Update Python models.

Run npx openapi-ts in the frontend.

Frontend types update automatically.

7. Performance & Optimization

Async First: Use async def for all I/O-bound operations (DB queries, API calls).

Background Tasks: Use FastAPI's BackgroundTasks for non-blocking operations like sending emails.

Query Optimization: * Use .selectinload() or .joinedload() for relationships to avoid N+1 problems.

Keep DB indexes focused on high-traffic WHERE and JOIN columns.

8. Development Standards (Linter/Formatter)

Ruff: Use ruff for both linting and formatting (faster than Flake8/Black).

Type Checking: Use mypy or pyright for strict type enforcement.

Logging:

Production: Structured JSON logging.

Development: Use a wrapper to limit console output.

import logging
import os

logger = logging.getLogger(__name__)
if os.getenv("ENV") != "production":
    logger.setLevel(logging.DEBUG)


9. Pre-Deployment Checklist

[ ] All migrations are applied (alembic upgrade head).

[ ] Pydantic models have no any types.

[ ] openapi.json is verified and synced with frontend.

[ ] Environment variables are validated via pydantic-settings.

[ ] CORS is configured strictly for the production frontend domain.