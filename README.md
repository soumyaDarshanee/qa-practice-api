# qa-practice-api

A small **supply-chain compliance** backend to practise API and E2E testing against.
Organisations manage their **suppliers**, the suppliers' **certificates** (with expiry
dates) and **audits**. Built with Django REST Framework + PostgreSQL, running in Docker
and driven by `make` commands.

The web frontend lives in the sibling repo **qa-practice-web**.

## Quick start

You need **Docker Desktop**. `make` is optional (see the table below for plain commands).

```bash
make setup        # = make up + make migrate + make test-setup
make demo-data    # optional: sample suppliers to click around
```

| URL | What |
|---|---|
| http://localhost:8000/api/docs/ | Swagger UI (try every endpoint) |
| http://localhost:8000/api/schema/ | OpenAPI schema (import into Postman, or generate a client) |
| http://localhost:8000/api/health/ | Health check |
| http://localhost:8000/admin/ | Django admin (first run `docker compose exec api python manage.py createsuperuser`) |

### Test users

All use the password **`Password123!`**.

| Email | Role | Organisation |
|---|---|---|
| admin@qa.test | admin (read + write) | Green Valley Foods |
| viewer@qa.test | viewer (read only) | Green Valley Foods |
| other-admin@qa.test | admin | Blue River Trading (for tenant-isolation tests) |

### Commands

| make | Without make | What it does |
|---|---|---|
| `make up` | `docker compose up -d --build` | Start Postgres + API |
| `make down` | `docker compose down` | Stop (data is kept) |
| `make migrate` | `docker compose exec api python manage.py makemigrations compliance` then `... migrate` | Create + apply migrations |
| `make test-setup` | `docker compose exec api python manage.py seed` | Reference data + test users |
| `make demo-data` | `... python manage.py seed --sample-data` | Sample suppliers/certificates/audits |
| `make reset` | `... python manage.py reset_db` | Wipe everything, reload the baseline |
| `make schema` | `... python manage.py spectacular --file openapi.yaml` | Export the OpenAPI schema |
| `make test` | `... python manage.py test compliance` | Backend's own tests |
| `make logs` | `docker compose logs -f api` | Follow logs |
| `make clean` | `docker compose down -v` | Stop and delete the database |

Postgres is exposed on **localhost:5433** (user/password/db: `compliance`) if you want to
look at data with a DB client.

## Authentication

```http
POST /api/auth/login/
{"email": "admin@qa.test", "password": "Password123!"}
→ 200 {"token": "…", "user": {"id": 1, "email": "…", "role": "admin", "organisation": {…}}}
```

Send the token on every other request: `Authorization: Token <token>`.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| POST | `/api/auth/register/` | Creates a user + new organisation (role admin) |
| POST | `/api/auth/login/` | Returns a token. Wrong password → 401 |
| POST | `/api/auth/logout/` | Invalidates the token → 204 |
| GET | `/api/auth/me/` | Current user, role, organisation |
| GET | `/api/regions/`, `/api/countries/?region=EU` | Reference data (not paginated) |
| GET/POST | `/api/suppliers/` | Filters: `search`, `status`, `risk_level`, `country`, `ordering`, `page`, `page_size` |
| GET/PUT/PATCH/DELETE | `/api/suppliers/{id}/` | Deleting a supplier deletes its certificates + audits |
| GET/POST | `/api/certificates/` | Filters: `supplier`, `status` (valid/expiring/expired), `certificate_type` |
| GET/PUT/PATCH/DELETE | `/api/certificates/{id}/` | |
| GET/POST | `/api/audits/` | Filters: `supplier`, `result` (pass/fail) |
| GET/PUT/PATCH/DELETE | `/api/audits/{id}/` | |
| GET | `/api/dashboard/` | Counts for the dashboard |

Lists are paginated: `{"count", "next", "previous", "results"}`, 10 per page by default,
`page_size` up to 100.

### Business rules (good material for negative tests)

- **Tenancy:** you only ever see your own organisation's data. Another org's supplier id → **404**, not 403.
- **Roles:** viewers get **403** on POST/PUT/PATCH/DELETE.
- **No token / bad token:** **401**.
- **Supplier:** `name`, `email` and `country` (ISO code like `NL`) are required. Name is unique per organisation (case-insensitive). Invalid email / unknown country → 400.
- **Certificate:** `expiry_date` must be after `issue_date`. `certificate_number` is unique per supplier. You can't attach a certificate to another org's supplier (400).
- **Certificate status** is calculated: `expired` (before today), `expiring` (within 30 days), otherwise `valid`.
- **Audit:** `score` is 0–100. `result` is calculated: `pass` when score ≥ 70.
- **Register:** email must be unique; password at least 8 characters.

## Test-only endpoints (`E2E_MODE=true`)

Switched on by default in `docker-compose.yml`, like a backend "e2e mode" flag. Never enable it in a real environment.

| Method | Path | Use |
|---|---|---|
| POST | `/api/e2e/reset/` | Reset DB to baseline. Body `{"sample_data": true}` to add demo data |
| GET | `/api/e2e/seed-status/` | Fail-fast seed check for a setup project: 200 when OK, 503 with what's missing |
| POST | `/api/e2e/users/` | Create a unique user + token. Body: `{"role": "viewer", "organisation_id": 1}` or `{"organisation_name": "My Org"}` |

These let you build the same lifecycle as a real E2E suite: reset → seed check → auth
setup per role → specs creating their own data through the API.

## Ideas for what to practise

- **Postman / Newman:** import `/api/schema/`, build a collection with an environment (`baseUrl`, `token`), set the token in a login pre-request script, chain requests (create supplier → add certificate → check dashboard counts), run with Newman.
- **Playwright API tests:** `request` fixture, auth setup that saves tokens, factories that create data via the API, cleanup in `afterEach`.
- **Codegen:** generate a typed client from `openapi.yaml` (for example with Kubb or openapi-typescript) and build factories on top of it.
- **Negative + boundary tests:** score -1/0/69/70/100/101, expiry = issue date, duplicate names with different casing, page_size 0/101, viewer writes, cross-tenant ids.
