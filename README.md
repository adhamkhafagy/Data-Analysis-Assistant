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

## Phase 2 — database discovery and business context

The authenticated workspace page now includes a **Data sources** section. It supports creating, listing, editing, connection-testing, discovering metadata, refreshing, and removing PostgreSQL, MySQL, and Microsoft SQL Server sources. Creation stores settings only; a database is contacted only after the explicit Test connection, Discover schema, or Refresh action.

The connector interface is in `backend/app/services/connectors/`. Discovery uses SQLAlchemy inspection for schemas, tables, columns, primary keys, and foreign keys. It excludes common system schemas, caps the inspected table and column counts, stores catalog-only approximate table row estimates where available, and never selects customer rows. Catalog estimates may be absent or stale; column-level distributions and value samples are intentionally not collected. Discovery runs synchronously with process-local concurrency limits, so it is intended for small and medium schemas; a durable job queue is not included.

An optional Groq provider receives only bounded schema names, column names/types, key relationships, and safe metadata. It never receives credentials or customer records. Profiles are validated suggestions with confidence/uncertainty fields; they are never executed as SQL. Missing Groq configuration leaves schema discovery available and reports that a profile could not be generated.

### Phase 2 configuration and run steps (Windows PowerShell)

Prepare ignored local configuration files and generate the two independent secrets:

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env.local
py -3.12 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
py -3.12 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Put the first generated value in `DATA_SOURCE_ENCRYPTION_KEY` and the second in `SESSION_SECRET` in `backend\.env`. Never use the session secret as the Fernet key. Set `GROQ_API_KEY` in this backend-only file if AI profiles are wanted; `AI_PROVIDER=groq` and `GROQ_MODEL` select the provider and model. Secrets must not be placed in `NEXT_PUBLIC_*` variables. The backend fails at startup if its Fernet key is missing or invalid.

Run the services with Docker Desktop:

```powershell
$env:POSTGRES_PASSWORD = "use-a-private-local-password"
# Use the same password in DATABASE_URL in backend\.env if you change the Compose default.
docker compose up --build
```

PostgreSQL is only on the internal Compose network and is not published to the host. The persistent named volume is preserved across normal restarts. Existing migrations run in order; no reset or automatic schema creation is performed.

For individual development, run PostgreSQL 16 and configure `DATABASE_URL`, then in one terminal:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

For the bundled Docker Compose database, set the data source host to `db`, port `5432`, and database name `bi_platform` (or the database configured for that service). Compose configures `DATA_SOURCE_COMPOSE_DB_CIDR` for a development-only exception limited to that resolved service address and the Compose bridge subnet; the default `172.16.0.0/12` covers Docker's common default bridge allocations. For a customized Compose network, set this variable to that network's CIDR, obtainable with `docker network inspect <project>_default`, then recreate the backend with `docker compose up -d --force-recreate backend`. Keep `DATA_SOURCE_ALLOW_PRIVATE_NETWORKS=false`. The exception applies only to the exact hostname `db` and is ignored in production. Do not use `localhost` from the backend container: it refers to the backend itself. A database on the Windows host may use `host.docker.internal` only when reachable and explicitly permitted by the local policy. Do not expose a database port publicly. A hosted SaaS backend cannot reach an arbitrary customer's computer-local database; a customer-controlled agent or secure tunnel is future work.

For hosted deployment, set `APP_ENV=production`, `COOKIE_SECURE=true`, HTTPS, a strict `FRONTEND_ORIGIN`, and administrator-managed `DATA_SOURCE_ALLOWED_HOSTS`/`DATA_SOURCE_ALLOWED_CIDRS`. Hosted connection destinations must be literal IP addresses and match the administrator allowlist; hostnames are rejected in hosted mode to avoid DNS rebinding between validation and connection. Loopback, link-local, metadata, multicast, reserved and unspecified addresses are blocked. Network policy at the application layer does not replace outbound firewall or cloud egress rules. Use least-privilege read-only database accounts, TLS certificates matching the approved IP, firewall restrictions, and platform-level egress controls. Production requires `DATA_SOURCE_TLS_MODE=verify-full`; development may choose `require` or `disable` only for isolated local testing. The SQL Server adapter uses Microsoft ODBC Driver 18; the backend container installs it. On Windows, install that driver separately.

Important backend settings:

- `DATABASE_URL`, `SESSION_SECRET`, `DATA_SOURCE_ENCRYPTION_KEY`, `FRONTEND_ORIGIN`, `APP_ENV`, `COOKIE_SECURE`
- `DATA_SOURCE_ALLOWED_HOSTS`, `DATA_SOURCE_ALLOWED_CIDRS`, `DATA_SOURCE_COMPOSE_DB_CIDR` (Compose local development only), `DATA_SOURCE_ALLOW_PRIVATE_NETWORKS`, `DATA_SOURCE_ALLOW_LOCALHOST`
- `DATA_SOURCE_CONNECT_TIMEOUT_SECONDS`, `DATA_SOURCE_QUERY_TIMEOUT_SECONDS`, `DATA_SOURCE_TLS_MODE`, `DATA_SOURCE_MAX_TABLES`, `DATA_SOURCE_MAX_COLUMNS`, `DATA_SOURCE_MAX_CONCURRENT_JOBS`
- `AI_PROVIDER`, `GROQ_API_KEY`, `GROQ_MODEL`

Generate a new encryption key with the Fernet command above. Credentials encrypted with an old key cannot be decrypted after replacing it. Rotation is not implemented: before rotating, export a protected backup, run a controlled one-off migration that decrypts each credential using the old key and re-encrypts it with the new key, verify counts and sample round trips, then atomically deploy the new key. Keep old-key backups in a secure secret store until verification and rollback windows close; never put keys or plaintext passwords in logs or source control.

Create a source from an owned workspace page, test it, then explicitly discover the schema. Inspect the discovered inventory and optional profile there. If a connection fails, check host reachability from the backend, inbound firewall rules, read-only permissions, TLS certificate trust, the Windows ODBC Driver 18 for SQL Server, and the sanitized API status. The backend does not expose driver messages or credential-bearing URLs.

Phase 2 endpoints are `POST /api/v1/workspaces/{workspace_id}/data-sources`, `GET /api/v1/workspaces/{workspace_id}/data-sources`, `GET|PATCH|DELETE /api/v1/data-sources/{id}`, `POST /api/v1/data-sources/{id}/test-connection`, `POST /api/v1/data-sources/{id}/discover`, `GET /api/v1/data-sources/{id}/schema`, `GET /api/v1/data-sources/{id}/business-profile`, and `POST /api/v1/data-sources/{id}/refresh`. All require the existing browser session and ownership is checked against the source's workspace.

The additional migration `0002_data_sources` follows the Phase 1 baseline `0001_initial`, adds sources and discovered metadata, and cascades only when an owning workspace/source is deliberately deleted. Never edit applied migrations or reset the platform database to install this phase.

Phase 2 tests use temporary SQLite databases and a mock connector. The metadata discovery unit test uses SQLite inspection and proves that it does not fetch inserted row contents. They do not require a live PostgreSQL, MySQL, SQL Server, or Groq account. Run:

```powershell
cd backend
$env:SESSION_SECRET = "test-session-secret-long-enough-for-tests"
$env:DATA_SOURCE_ENCRYPTION_KEY = (py -3.12 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
pytest -p no:cacheprovider
```

Frontend checks are `npm run lint`, `npx tsc --noEmit`, and `npm run build` from `frontend`. Phase 3 dashboards and Phase 4 persistent AI chat/dashboard editing remain deferred.

## Phase 1 scope and security notes

Dashboards, data-source connections, and the AI analyst are labeled placeholders. No customer database is contacted and no analytics are fabricated. Production deployment still requires HTTPS, a real secret manager, auth rate limiting, monitoring, backup/restore, a reviewed CSRF strategy for the chosen domain topology, and security review. Social login, email verification, password reset, billing, database discovery, NL-to-SQL, persistent AI chat, and dynamic dashboards are later-phase work.
