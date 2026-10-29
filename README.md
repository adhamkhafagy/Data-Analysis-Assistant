# Data Analysis Assistant and AI Business Intelligence Platform

This repository now contains two independent applications. The existing Streamlit multi-agent assistant remains the root-level application (`main_app.py` and its existing modules). The new Phase 1 web platform lives in `frontend/` and `backend/`; backend services do not import Streamlit. The Streamlit agents are currently coupled to UI/session state, so they are preserved intact rather than pulled into API services. Reuse can be extracted later from pure data-quality helpers after defining stable service contracts.

## Legacy Streamlit application

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Put GROQ_API_KEY in the ignored root .env file for LLM/report features.
streamlit run main_app.py
```

## New web platform

### Requirements

- Python 3.12
- Node.js 20 or newer and npm
- Docker Desktop with Compose (recommended for PostgreSQL)

### Docker setup (Windows PowerShell)

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env.local
# Generate and set a private SESSION_SECRET in backend\.env (32+ characters).
# Set POSTGRES_PASSWORD in your PowerShell environment before Compose for a non-default local database password.
docker compose up --build
```

Compose starts PostgreSQL with a health check, applies Alembic migrations, then serves FastAPI and Next.js. Local URLs: frontend http://localhost:3000, API http://localhost:8000, OpenAPI docs http://localhost:8000/docs, health http://localhost:8000/health. PostgreSQL has no host port mapping. The default database password is for local development only; set `POSTGRES_PASSWORD` and the matching password in `backend/.env` for a private local value. The named volume persists data; do not remove it to reset data.

### Run services individually

Start a PostgreSQL 16 database and configure `backend/.env` using `backend/.env.example`. In separate PowerShell terminals:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

To upgrade schema after future changes, run `alembic upgrade head` from `backend/`. The API never creates tables automatically at startup.

### Configuration

`backend/.env` supports `APP_ENV`, `DATABASE_URL`, `SESSION_SECRET`, `FRONTEND_ORIGIN`, `COOKIE_SECURE`, and `SESSION_TTL_HOURS`. Use a cryptographically random secret of at least 32 characters, such as `(py -c "import secrets; print(secrets.token_urlsafe(48))")`. The browser session is a signed, HTTP-only, SameSite=Lax cookie. For production, set `APP_ENV=production`, `COOKIE_SECURE=true`, use HTTPS, set a strict frontend origin, and use a managed secret store. Cookie authentication is protected against cross-site form posts by SameSite=Lax and strict credentialed CORS; deploy frontend and API on the same site, validate origins at any reverse proxy, and consider a synchronizer-token CSRF defense before enabling cross-site deployments. Authentication throttling should be added at a trusted gateway or with a shared Redis-backed limiter before production.

`frontend/.env.local` uses `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). Only public URLs belong in `NEXT_PUBLIC_*` variables. Never commit real `.env` files.

### Authentication and workspaces

Open http://localhost:3000/register to create the first user. Registration signs the user in. The overview page supports workspace creation, opening, renaming, and deletion. Refreshing retains the session. Logout is in the profile menu. To verify via API, register and save cookies in a browser or HTTP client, then call `/api/v1/auth/me`; the UI performs this flow directly. Passwords are hashed with Argon2id. Workspace records are always queried by both ID and authenticated owner ID; cross-user access returns 404.

### API

- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`
- `GET|POST /api/v1/workspaces`, `GET|PATCH|DELETE /api/v1/workspaces/{workspace_id}`
- `GET /health`

Pydantic validation errors use FastAPI's 422 response. Expected auth/conflict/not-found errors use 401/409/404. Unexpected server errors return a generic message. OpenAPI is available at `/docs` outside production.

### Checks

Backend tests use a fresh temporary SQLite database per test and never touch application databases:

```powershell
cd backend
pip install -r requirements.txt
pytest
```

Frontend checks:

```powershell
cd frontend
npm install
npm run build
```

## Phase 1 scope and security notes

Dashboards, data-source connections, and the AI analyst are labeled placeholders. No customer database is contacted and no analytics are fabricated. Production deployment still requires HTTPS, a real secret manager, auth rate limiting, monitoring, backup/restore, a reviewed CSRF strategy for the chosen domain topology, and security review. Social login, email verification, password reset, billing, database discovery, NL-to-SQL, persistent AI chat, and dynamic dashboards are later-phase work.
