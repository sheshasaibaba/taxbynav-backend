# TaxByNav Backend

FastAPI backend with JWT auth, refresh tokens, Google SSO, and appointment booking (30-min slots, one per user per day).

## Tech stack

- **FastAPI** – API
- **SQLModel + SQLAlchemy (async)** – ORM with PostgreSQL (Neon)
- **Alembic** – migrations
- **uv** – package manager (or pip)
- **JWT** – access + refresh tokens; passwords hashed with **bcrypt**

## Quick start

1. **Install dependencies** (from repo root `taxbynav-backend/`):

   ```bash
   # With uv (recommended)
   uv sync

   # Or with pip
   pip install -e ".[dev]"
   ```

2. **Environment**

   Copy `.env.example` to `.env` and set:

   - `DATABASE_URL` – PostgreSQL URL (e.g. Neon)
   - `SECRET_KEY` – e.g. `openssl rand -hex 32`
   - `CORS_ORIGINS` – e.g. `http://localhost:3000`
   - `APPOINTMENT_RETENTION_DAYS` – (optional, default `3`) delete appointments this many days after booking so no excess data remains; cleanup runs on startup and every 24h.
   - For **appointment confirmation emails** (Gmail SMTP), see [docs/EMAIL_SETUP.md](docs/EMAIL_SETUP.md).

3. **Migrations**

   ```bash
   uv run alembic upgrade head
   # or: alembic upgrade head
   ```

4. **Run**

   ```bash
   uv run uvicorn app.main:app --reload
   # or: uvicorn app.main:app --reload
   ```

   - API: http://localhost:8000  
   - Docs: http://localhost:8000/docs  

## Docker & Google Cloud Run

The app runs in a container the same way as locally: **uvicorn** serves the API; **migrations** run on startup when `DATABASE_URL` is set. Cloud Run sets `PORT` (default 8080); the image uses it automatically.

### Build and run locally with Docker

From `taxbynav-backend/`:

```bash
docker build -t taxbynav-backend .
docker run --rm -p 8080:8080 \
  -e DATABASE_URL="postgresql://user:pass@host/db?sslmode=require" \
  -e SECRET_KEY="your-secret-key" \
  -e CORS_ORIGINS="http://localhost:3000" \
  taxbynav-backend
```

- API: http://localhost:8080  
- Add any other env vars (e.g. `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, SMTP vars) as needed.

### Deploy to Google Cloud Run

1. **Build and push** (use your project ID and region):

   ```bash
   gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/taxbynav-backend
   ```

   Or with Artifact Registry:

   ```bash
   gcloud builds submit --tag REGION-docker.pkg.dev/YOUR_PROJECT_ID/REPO/taxbynav-backend
   ```

2. **Create or update the service** with required env vars (no `.env` file in the image; set them in Cloud Run):

   - `DATABASE_URL` – PostgreSQL URL (e.g. Neon)
   - `SECRET_KEY`
   - `CORS_ORIGINS` – your frontend origin(s), e.g. `https://yourdomain.com`
   - For Google SSO: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` (use your Cloud Run URL, e.g. `https://your-service-xxx.run.app/api/v1/auth/google/callback`)
   - Optional: SMTP vars, `APPOINTMENT_RETENTION_DAYS`, etc.

   Example:

   ```bash
   gcloud run deploy taxbynav-backend \
     --image gcr.io/YOUR_PROJECT_ID/taxbynav-backend \
     --platform managed \
     --region us-central1 \
     --allow-unauthenticated \
     --set-env-vars "DATABASE_URL=postgresql://...,SECRET_KEY=...,CORS_ORIGINS=https://yourdomain.com,GOOGLE_CLIENT_ID=...,GOOGLE_CLIENT_SECRET=...,GOOGLE_REDIRECT_URI=https://your-service-xxx.run.app/api/v1/auth/google/callback"
   ```

   For secrets (e.g. `SECRET_KEY`, `DATABASE_URL`), prefer [Secret Manager](https://cloud.google.com/run/docs/configuring/secrets) and reference them in the service.

3. **Migrations** run automatically when the container starts (entrypoint runs `alembic upgrade head` before uvicorn). Ensure the database is reachable from Cloud Run (e.g. Neon allows public access with SSL).

## Google SSO – what you need

To enable “Sign in with Google” you need a **Google OAuth 2.0 Client** and to point the backend at it.

### 1. Create OAuth credentials

1. Open [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
2. Select (or create) a project.
3. **Credentials** → **Create credentials** → **OAuth client ID**.
4. If asked, configure the **OAuth consent screen** (e.g. External, app name, support email).
5. Application type: **Web application**.
6. **Authorized redirect URIs**: add the exact URL your backend uses for the callback, for example:
   - Local: `http://localhost:8000/api/v1/auth/google/callback`
   - Production: `https://api.yourdomain.com/api/v1/auth/google/callback`
7. Create. You get:
   - **Client ID** (e.g. `xxx.apps.googleusercontent.com`)
   - **Client secret**

### 2. Backend env vars

In `.env`:

```env
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
```

`GOOGLE_REDIRECT_URI` must match exactly one of the “Authorized redirect URIs” in the Google client (including path and no trailing slash).

### 3. No extra API keys

You do **not** need a separate “API key” for Google SSO. The **Client ID** and **Client secret** are the only credentials. Keep the secret in `.env` and never in the frontend.

### 4. Frontend flow (high level)

- **Login with Google**: open `GET /api/v1/auth/google` → use the returned `authorization_url` to redirect the user to Google.
- After the user signs in, Google redirects to your `GOOGLE_REDIRECT_URI` (backend) with a `code`.
- Backend exchanges `code` for tokens and returns **your** JWT access + refresh tokens (same as email/password login).
- Frontend stores those and uses them like normal (e.g. `Authorization: Bearer <access_token>`, refresh via `X-Refresh-Token` or body).

For a pure SPA, you can use a popup: open the auth URL in a popup; when the backend callback loads, have it send the tokens to the opener (e.g. `postMessage`) and then close.

## API overview

- **Prefix**: `/api/v1`.

### Auth

| Method | Path | Description |
|--------|------|-------------|
| POST   | `/auth/login` | Email + password → `access_token`, `refresh_token`, `expires_in` |
| POST   | `/auth/signup` | Register → same token pair |
| POST   | `/auth/refresh` | Body `refresh_token` or header `X-Refresh-Token` → new token pair |
| POST   | `/auth/logout` | Optional body/header refresh token → revoke it |
| GET    | `/auth/me` | **Auth required.** Current user (Bearer) |
| GET    | `/auth/google` | Returns `authorization_url` for Google SSO |
| GET    | `/auth/google/callback?code=...` | OAuth callback; returns token pair |

**Headers**

- **Access token**: `Authorization: Bearer <access_token>`.
- **Refresh token** (for `/auth/refresh` and `/auth/logout`): `X-Refresh-Token: <refresh_token>` or body `{"refresh_token": "..."}`.

### Slots

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/slots/available?date=YYYY-MM-DD` | List slots for that day with `start_utc`, `end_utc`, `available` (no auth) |

### Appointments

| Method | Path | Description |
|--------|------|-------------|
| POST   | `/appointments` | **Auth required.** Book slot: `{"slot_start_utc": "ISO8601", "message": "optional"}`. One 30-min session per user per day; no overlapping slots. |
| GET    | `/appointments?from_date=YYYY-MM-DD` | **Auth required.** List current user’s appointments. |
| DELETE | `/appointments/{id}` | **Auth required.** Cancel own appointment. |

## Business rules

- **Slots**: 30 minutes; business hours configurable (default 9:00–17:00 UTC).
- **One appointment per user per day** (configurable via `max_slots_per_user_per_day`).
- **No overlapping**: each `slot_start_utc` is unique across all appointments.
- Passwords are **salted and hashed** (bcrypt). JWT access tokens short-lived; refresh tokens stored and revocable.

## CORS

Allowed origins come from `CORS_ORIGINS` (comma-separated). Allowed headers include `Authorization`, `Content-Type`, `X-Refresh-Token`.

## Project layout

```
app/
  api/          # Routes, schemas, deps
  core/         # Config, DB, security
  models/       # SQLModel tables + DTOs
  services/     # Business logic
migrations/     # Alembic
```

See `backend-standards.md` for full conventions.
