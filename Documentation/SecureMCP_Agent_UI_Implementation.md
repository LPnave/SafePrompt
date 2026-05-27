# SecureMCP — Agent-UI Enterprise Implementation
## Full Technical Documentation

**Version:** 2.0  
**Last Updated:** May 2026  
**Scope:** `agent-ui/` directory — Python FastAPI backend + Next.js frontend

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Python Backend](#2-python-backend)
   - 2.1 [Entry Point & Lifespan](#21-entry-point--lifespan)
   - 2.2 [Configuration](#22-configuration)
   - 2.3 [Database Layer](#23-database-layer)
   - 2.4 [ORM Models](#24-orm-models)
   - 2.5 [Alembic Migrations](#25-alembic-migrations)
   - 2.6 [Database Seed](#26-database-seed)
   - 2.7 [Repository Layer](#27-repository-layer)
   - 2.8 [Authentication (JWT + bcrypt)](#28-authentication-jwt--bcrypt)
   - 2.9 [Service Layer](#29-service-layer)
   - 2.10 [API Controllers](#210-api-controllers)
   - 2.11 [Pydantic Schemas](#211-pydantic-schemas)
   - 2.12 [Audit System](#212-audit-system)
3. [The Enterprise Prompt Pipeline](#3-the-enterprise-prompt-pipeline)
4. [Security Validator (ML Core)](#4-security-validator-ml-core)
5. [Next.js Frontend](#5-nextjs-frontend)
   - 5.1 [Project Structure](#51-project-structure)
   - 5.2 [Auth Library](#52-auth-library)
   - 5.3 [Next.js Middleware (Route Protection)](#53-nextjs-middleware-route-protection)
   - 5.4 [Chat Proxy Route](#54-chat-proxy-route)
   - 5.5 [Login Page](#55-login-page)
   - 5.6 [Admin Panel — Dashboard](#56-admin-panel--dashboard)
   - 5.7 [Admin Panel — Reports](#57-admin-panel--reports)
   - 5.8 [Admin Panel — Roles & Policies](#58-admin-panel--roles--policies)
   - 5.9 [Admin Panel — Users](#59-admin-panel--users)
   - 5.10 [Admin API Client](#510-admin-api-client)
6. [API Reference](#6-api-reference)
7. [Database Schema](#7-database-schema)
8. [Dependency List](#8-dependency-list)
9. [Startup & Development](#9-startup--development)
10. [Known Design Decisions & Fixes](#10-known-design-decisions--fixes)

---

## 1. Architecture Overview

SecureMCP Agent-UI is a full-stack enterprise AI assistant with a **6-stage prompt security pipeline**. It consists of:

- A **Python FastAPI backend** (`agent-ui/python-backend/`) following clean architecture (Controller → Service → Repository)
- A **Next.js 15 frontend** (`agent-ui/secure_agent/`) providing the chat UI, admin panel, and reporting dashboard
- A **PostgreSQL database** managed by Alembic migrations
- A local **Ollama/Llama 3.2** LLM for generating AI responses
- A set of **Hugging Face transformer models** for ML-based prompt vetting and sanitization

```
┌─────────────────────────────────────────────────────────────────┐
│                     Next.js Frontend (port 3000)                 │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │  Chat UI    │  │ Admin Panel  │  │   Reports Dashboard    │  │
│  │ (assistant- │  │ (Roles,      │  │  (Charts, Blocked Log) │  │
│  │   ui SDK)   │  │  Users)      │  │                        │  │
│  └──────┬──────┘  └──────┬───────┘  └──────────┬─────────────┘  │
│         │   Next.js Middleware (cookie auth gate)                 │
│         │   /app/api/chat/route.ts (proxy)                       │
└─────────┼──────────────────────────────────────────────────────-─┘
          │ HTTP (Bearer JWT)
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                 FastAPI Backend (port 8003)                       │
│                                                                  │
│  Controllers: /api/auth  /api/chat  /api/sanitize                │
│               /api/admin  /api/reports                           │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │           6-Stage Enterprise Prompt Pipeline              │   │
│  │  1. Time restriction   2. Rate limit   3. Prompt length   │   │
│  │  4. Topic enforcement  5. ML vetting   6. LLM call        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Async Audit Worker ──► PostgreSQL (audit_events table)          │
└────────────────────────────┬─────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
    PostgreSQL Database            Ollama (port 11434)
    (roles, role_policies,         Llama 3.2 model
     users, audit_events)
```

---

## 2. Python Backend

### 2.1 Entry Point & Lifespan

**File:** `app/main.py`

The application is a `FastAPI` instance with a `asynccontextmanager` lifespan that executes 4 startup steps in order:

1. **Database connection check** — calls `check_db_connection()`. Schema management is left to Alembic (run before startup via `start.bat`).
2. **Database seeding** — calls `seed_database(db)` which idempotently inserts default roles, policies, and users if they don't already exist.
3. **ML model loading** — instantiates `ZeroShotSecurityValidator` at the configured security level. The validator is injected into `chat_service` via `set_validator()`.
4. **Background audit worker** — starts `audit_worker()` as an `asyncio.Task`. It drains an `asyncio.Queue` and batch-writes audit events to PostgreSQL.

On shutdown the audit task is cancelled gracefully.

```
CORS origins are configurable via CORS_ORIGINS in .env (comma-separated).

Registered routers:
  auth_router      →  /api/auth/*
  chat_router      →  /api/chat
  sanitize_router  →  /api/sanitize, /api/health, /api/stats, /api/security/level
  admin_router     →  /api/admin/*
  reporting_router →  /api/reports/*
```

---

### 2.2 Configuration

**File:** `app/core/config.py`

Uses `pydantic-settings` `BaseSettings` which reads from the `.env` file and environment variables. `extra = "ignore"` is set so stale system-level environment variables (e.g. left-over `GEMINI_*` vars) don't cause validation errors.

| Setting | Default | Description |
|---|---|---|
| `PORT` | `8003` | Uvicorn port |
| `HOST` | `0.0.0.0` | Uvicorn host |
| `CORS_ORIGINS` | `http://localhost:3000,...` | Comma-separated allowed origins |
| `DEFAULT_SECURITY_LEVEL` | `medium` | Global ML validator level |
| `MODEL_CACHE_DIR` | `./models` | HuggingFace cache directory |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API base URL |
| `OLLAMA_MODEL` | `llama3.2` | Model name sent to Ollama |
| `DATABASE_URL` | SQLite fallback | Full SQLAlchemy async URL |
| `JWT_SECRET` | (must override) | HMAC secret for JWT signing |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRY_MINUTES` | `60` | Access token lifetime |
| `JWT_REFRESH_EXPIRY_DAYS` | `7` | Refresh token lifetime |
| `STORE_RAW_PROMPTS` | `False` | Whether to store raw prompt text in audit log |

A `SecurityLevel` enum (`LOW`, `MEDIUM`, `HIGH`) is used throughout the codebase via the `settings.security_level` property.

---

### 2.3 Database Layer

**File:** `app/core/database.py`

- Async SQLAlchemy engine created from `settings.DATABASE_URL` using `create_async_engine`.
- Session factory: `AsyncSessionLocal` (via `async_sessionmaker`).
- `check_db_connection()` — runs `SELECT 1` to verify the database is reachable. It does NOT create or alter tables; that is Alembic's responsibility.
- `get_db()` — FastAPI dependency that provides a scoped `AsyncSession` per request, with automatic rollback on error and close on finish.
- `Base` — `DeclarativeBase` from which all ORM models inherit.

The database is PostgreSQL in production/development, accessed via the `asyncpg` driver (`postgresql+asyncpg://...`).

---

### 2.4 ORM Models

**File:** `app/db/models.py`

Four tables are defined using SQLAlchemy 2.0 `Mapped[]` / `mapped_column()` style:

#### `roles`
| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | Auto-increment |
| `name` | String(50) | Unique |
| `description` | String(255) | Optional |
| `is_admin` | Boolean | Whether role grants admin access |
| `created_at` | DateTime | Server default `now()` |

Relationships: `policy` (one-to-one → `RolePolicy`), `users` (one-to-many → `User`).

#### `role_policies`
| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `role_id` | Integer FK → roles | Unique (one policy per role) |
| `security_level` | String(10) | `low`, `medium`, or `high` |
| `max_prompt_length` | Integer | Character limit per prompt |
| `max_requests_per_day` | Integer | Daily rate limit |
| `system_prompt` | Text | Injected before every LLM call |
| `allowed_topics` | JSON | List of strings; zero-shot classification labels |
| `blocked_topics` | JSON | List of keyword phrases; always enforced |
| `enforce_topic_restrictions` | Boolean | Enables ML allowed-topic check |
| `response_filter_enabled` | Boolean | Flag (reserved for future use) |
| `max_conversation_turns` | Integer | Max turns per session |
| `session_timeout_minutes` | Integer | Session idle timeout |
| `allow_file_uploads` | Boolean | Feature flag |
| `time_restriction_start` | String(5) | `HH:MM` UTC — start of allowed window |
| `time_restriction_end` | String(5) | `HH:MM` UTC — end of allowed window |
| `updated_at` | DateTime | Auto-updated on write |

#### `users`
| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `username` | String(100) | Unique |
| `email` | String(255) | Unique |
| `hashed_password` | String(255) | bcrypt hash |
| `role_id` | Integer FK → roles | |
| `department` | String(100) | Optional |
| `is_active` | Boolean | Soft-delete flag |
| `created_at` | DateTime | |

#### `audit_events`
| Column | Type | Notes |
|---|---|---|
| `id` | String(36) PK | UUID v4 |
| `timestamp` | DateTime | Naive UTC (`TIMESTAMP WITHOUT TIME ZONE`) |
| `user_id` | Integer FK → users | Nullable |
| `user_role` | String(50) | Denormalised for reporting |
| `department` | String(100) | Denormalised |
| `session_id` | String(100) | From frontend |
| `prompt_hash` | String(64) | SHA-256 hex of original prompt |
| `raw_prompt` | Text | Only stored if `STORE_RAW_PROMPTS=True` |
| `sanitized_prompt` | Text | Prompt after sanitization |
| `prompt_length` | Integer | Character count |
| `threats_detected` | JSON | List of detected threat patterns |
| `sanitization_applied` | Boolean | Was the prompt modified? |
| `blocked` | Boolean | Was the request blocked? |
| `block_reason` | String(255) | Human-readable block reason |
| `security_level_used` | String(10) | Level at time of request |
| `confidence_score` | Float | ML confidence from validator |
| `processing_time_ms` | Float | Total pipeline time |
| `vetting_time_ms` | Float | ML vetting time only |
| `llm_time_ms` | Float | Ollama call time only |
| `model_used` | String(100) | `llama3.2` |
| `tokens_used` | Integer | Character count of LLM response |
| `action` | String(20) | `passed`, `sanitized`, or `blocked` |

Indexes: `user_id`, `timestamp`, `blocked`, `user_role`.

---

### 2.5 Alembic Migrations

**Files:** `alembic.ini`, `alembic/env.py`, `alembic/versions/20260501_0001_initial_schema.py`

Alembic is configured for **async migrations** using `async_engine_from_config` and `asyncpg`. The `DATABASE_URL` is injected into Alembic's config from `app.core.config.settings` at runtime, so a single `.env` file controls both the app and migrations.

The single initial migration (`revision: 0001`) creates all four tables and the four indexes on `audit_events`.

**Running migrations:**
```bash
alembic upgrade head   # apply all pending migrations
alembic downgrade -1   # revert one migration
```

Migrations are run automatically by `start.bat` before Uvicorn starts. If migrations fail (e.g. database is unreachable), the startup script aborts with a clear error message.

---

### 2.6 Database Seed

**File:** `app/db/seed.py`

`seed_database(db)` is idempotent — it uses `SELECT` checks before inserting. It seeds:

**Roles + policies:**
| Role | Security | Max Prompt | Max/Day | Key Blocked Topics |
|---|---|---|---|---|
| `admin` | low | 10,000 chars | 1,000 | — |
| `engineering` | medium | 4,000 chars | 200 | payroll, salary negotiation, personal hr matters |
| `hr` | high | 2,000 chars | 100 | code, programming, sql injection, hacking |
| `finance` | high | 2,000 chars | 100 | code, programming, exploit, hacking |

**Seed users (development only — change passwords in production):**
| Username | Password | Role | Department |
|---|---|---|---|
| `admin` | `Admin@SecureMCP1` | admin | IT |
| `engineer1` | `Engineer@SecureMCP1` | engineering | Engineering |
| `hr_manager` | `HR@SecureMCP1` | hr | Human Resources |
| `finance_analyst` | `Finance@SecureMCP1` | finance | Finance |

---

### 2.7 Repository Layer

**Files:** `app/repositories/`

A generic `BaseRepository[T]` provides `get_by_id`, `get_all`, `create`, `update`, `delete` using async SQLAlchemy.

#### `UserRepository(BaseRepository[User])`
- `get_by_username(username)` — loads user with `role → policy` via `selectinload`
- `get_by_email(email)`
- `get_by_id_with_role(user_id)` — used by auth dependency; loads full role+policy graph
- `get_all_with_roles()` — used by admin user list
- `get_by_role_id(role_id)` — used by `delete_role` to guard against deletion when users are assigned

#### `RoleRepository(BaseRepository[Role])`
- `get_by_name(name)` — loads with policy
- `get_all_with_policies()` — used by admin role list

#### `RolePolicyRepository(BaseRepository[RolePolicy])`
- `get_by_role_id(role_id)`

#### `AuditRepository(BaseRepository[AuditEvent])`
- `count_today_for_user(user_id)` — counts today's events for rate limiting; uses `cast(timestamp, Date) == date.today()` (Python `date` object, not a string, to avoid PostgreSQL `DATE = VARCHAR` type error)
- `get_usage_summary(start, end)` — prompts per day grouped by role; uses `func.count().filter()` for boolean aggregation (not `SUM(CAST(...))` which fails on PostgreSQL booleans)
- `get_threat_breakdown(start, end)` — threat counts grouped by role and action
- `get_user_activity(start, end)` — per-user prompt statistics
- `get_blocked_events(limit, start, end)` — recent blocked prompts for audit log

---

### 2.8 Authentication (JWT + bcrypt)

**File:** `app/core/auth.py`

Password hashing uses the `bcrypt` library directly (not `passlib`, which has an incompatibility with `bcrypt>=4.0.0`).

```python
hash_password(plain: str) → str        # bcrypt.hashpw with gensalt
verify_password(plain, hashed) → bool  # bcrypt.checkpw
```

JWT operations use `python-jose`:

```python
create_access_token(user_id, username, role, is_admin) → str
# Payload: { sub, username, role, is_admin, type="access", exp }
# Expiry: JWT_EXPIRY_MINUTES (default 60 min)

create_refresh_token(user_id) → str
# Payload: { sub, type="refresh", exp }
# Expiry: JWT_REFRESH_EXPIRY_DAYS (default 7 days)

decode_token(token, expected_type) → dict
# Raises HTTP 401 on any JWTError or type mismatch
```

**Auth service** (`app/services/auth_service.py`):
- `login(username, password, db)` — verifies credentials, returns access + refresh tokens with user profile
- `refresh_access_token(refresh_token, db)` — validates refresh token, returns new access token
- `register_user(...)` — admin-only; checks for duplicate username/email before creation
- `get_current_user(token, db)` — FastAPI dependency; decodes JWT, loads `(User, RolePolicy)` tuple
- `require_admin(current)` — FastAPI dependency that wraps `get_current_user` and checks `role.is_admin`

---

### 2.9 Service Layer

#### Chat Service — `app/services/chat_service.py`

The main entry point is `run_chat_pipeline()`. It:
1. Accepts `(messages, user, policy, session_id, audit_repo)`
2. Runs the 6-stage pipeline (see Section 3)
3. Returns an `AsyncGenerator` of data-stream lines in Vercel AI SDK format

Helper functions:
- `_extract_text(content)` — normalises `str | list | dict` message content to plain string
- `_hash_prompt(prompt)` — SHA-256 hex digest for audit privacy
- `_check_rate_limit(user, policy, audit_repo)` — async, queries today's count
- `_check_prompt_length(prompt, policy)` — synchronous character count check
- `_check_time_restriction(policy)` — compares current UTC `HH:MM` against policy window; handles midnight-wrapping windows
- `_check_topic_restrictions(prompt, policy, validator)` — two-stage enforcement (see Section 3)
- `_build_ollama_messages(messages, sanitized_content, last_message, system_prompt)` — converts message history to Ollama's OpenAI-compatible format, prepending the role system prompt
- `_call_ollama(messages)` — async HTTP POST to `OLLAMA_BASE_URL/api/chat` via `httpx`; handles timeouts and connection errors
- `_enqueue_audit(...)` — creates an `AuditEvent` ORM instance and puts it on `audit_queue` (non-blocking `put_nowait`)

**Important timestamp note:** The audit event timestamp is created as `datetime.now(timezone.utc).replace(tzinfo=None)`. The `.replace(tzinfo=None)` strips timezone awareness to produce a naive UTC datetime, which is required by PostgreSQL's `TIMESTAMP WITHOUT TIME ZONE` column. asyncpg rejects timezone-aware datetimes for such columns.

#### Admin Service — `app/services/admin_service.py`

CRUD operations for users and roles:
- `list_users`, `create_user`, `update_user`, `deactivate_user`
- `list_roles`, `create_role`, `update_role`, `delete_role`
- `update_role_policy` — applies an allowlisted set of field updates to a `RolePolicy`
- `create_policy_for_role` — idempotent; returns existing policy or creates with safe defaults
- `delete_role` — guarded: refuses if any active users are still assigned to the role; also deletes the associated policy first

#### Auth Service — `app/services/auth_service.py`
(Covered in 2.8 above)

#### Sanitize Service — `app/services/sanitize_service.py`
- `sanitize_single(prompt, security_level)` — validates a single prompt and returns a structured dict
- `sanitize_batch(prompts, security_level)` — batch version; used by `/api/sanitize/batch`

---

### 2.10 API Controllers

All controllers use FastAPI `APIRouter` with a prefix. Admin endpoints gate on `require_admin` dependency.

#### Auth Controller — `/api/auth`
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/login` | None | Username/password → tokens + user profile |
| POST | `/api/auth/register` | Admin JWT | Create a new user (admin-only) |
| POST | `/api/auth/refresh` | None | Refresh token → new access token |
| GET | `/api/auth/me` | JWT | Returns current user profile |

#### Chat Controller — `/api/chat`
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/chat` | JWT | Runs the full 6-stage pipeline; returns streaming response |

The controller normalises `parts`-format messages from assistant-ui before passing to the service.

#### Sanitize Controller — `/api/sanitize`, `/api/health`, `/api/stats`, `/api/security/level`
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/sanitize` | JWT | Sanitize a single prompt |
| POST | `/api/sanitize/batch` | JWT | Sanitize multiple prompts |
| GET | `/api/health` | None | Health check + model loaded status |
| GET | `/api/stats` | JWT | Model info and request statistics |
| GET | `/api/security/level` | JWT | Current global security level |
| PUT | `/api/security/level` | Admin JWT | Update global security level |

#### Admin Controller — `/api/admin`
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/admin/users` | Admin JWT | List all users |
| POST | `/api/admin/users` | Admin JWT | Create user |
| PUT | `/api/admin/users/{id}` | Admin JWT | Update user role/dept/status |
| DELETE | `/api/admin/users/{id}` | Admin JWT | Deactivate user |
| GET | `/api/admin/roles` | Admin JWT | List all roles with policies |
| POST | `/api/admin/roles` | Admin JWT | Create new role (auto-creates default policy) |
| PUT | `/api/admin/roles/{id}` | Admin JWT | Update role metadata |
| DELETE | `/api/admin/roles/{id}` | Admin JWT | Delete role (fails if users assigned) |
| PUT | `/api/admin/policies/{role_id}` | Admin JWT | Update role policy fields |
| POST | `/api/admin/policies/{role_id}` | Admin JWT | Create policy for existing role |

#### Reporting Controller — `/api/reports`
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/reports/usage` | Admin JWT | Prompts per day grouped by role |
| GET | `/api/reports/threats` | Admin JWT | Threat action counts by role |
| GET | `/api/reports/users` | Admin JWT | Per-user activity summary |
| GET | `/api/reports/blocked` | Admin JWT | Recent blocked events (audit log) |

All reporting endpoints accept optional `start` and `end` ISO datetime query parameters for date filtering.

---

### 2.11 Pydantic Schemas

**File:** `app/api/schemas.py`

All request and response shapes are defined here:

- **Auth:** `LoginRequest`, `RegisterRequest`, `RefreshRequest`, `TokenResponse`, `UserProfileResponse`
- **Sanitize:** `SanitizeRequest` / `SanitizeResponse`, `BatchSanitizeRequest` / `BatchSanitizeResponse`
- **Chat:** `ChatMessage`, `ChatRequest`
- **Admin — Users:** `CreateUserRequest`, `UpdateUserRequest`, `UserResponse`
- **Admin — Roles:** `CreateRoleRequest` (name regex `^[a-z0-9_-]+$`), `UpdateRoleRequest`, `RoleResponse`, `RolePolicyResponse`, `UpdatePolicyRequest`
- **Reports:** `UsageSummaryItem`, `ThreatBreakdownItem`, `UserActivityItem`, `BlockedEventResponse`

`UpdatePolicyRequest` validates:
- `max_conversation_turns`: 1–500
- `session_timeout_minutes`: 1–1440
- `time_restriction_start` / `time_restriction_end`: must match `^\d{2}:\d{2}$`

---

### 2.12 Audit System

**File:** `app/core/audit.py`

The audit system is fully non-blocking. The chat service calls `audit_queue.put_nowait(event)` which never blocks the HTTP response.

A single `asyncio.Task` runs `audit_worker(session_factory)` for the lifetime of the application:

```
Loop:
  1. Wait up to 1s for an event on the queue (asyncio.wait_for)
  2. Drain any additional events already in the queue (up to batch size 50)
  3. Attempt DB write (session.add_all + commit) up to 3 times
     with exponential backoff: 1s → 2s → 4s
  4. If all attempts fail: write the batch to audit_fallback.jsonl
  5. Clear batch, repeat
```

The fallback JSONL file ensures no events are permanently lost even during database outages.

---

## 3. The Enterprise Prompt Pipeline

`run_chat_pipeline()` in `chat_service.py` executes these stages in order for every chat request:

### Stage 1 — Time Restriction
```python
_check_time_restriction(policy)
```
Reads `policy.time_restriction_start` and `policy.time_restriction_end` (both `HH:MM` UTC strings). If either is unset the check is skipped. Handles windows that wrap midnight (e.g. `22:00`–`06:00`): if `start > end` the logic uses `OR` instead of `AND`.  
**Raises:** HTTP 403 if current UTC time is outside the window.

### Stage 2 — Rate Limiting
```python
await _check_rate_limit(user, policy, audit_repo)
```
Counts `audit_events` rows for `user_id` where `CAST(timestamp AS DATE) = today`. Compares against `policy.max_requests_per_day`.  
**Raises:** HTTP 429 if limit reached.

### Stage 3 — Prompt Length
```python
_check_prompt_length(original_content, policy)
```
Simple `len(prompt) > policy.max_prompt_length` check.  
**Raises:** HTTP 400 if exceeded.

### Stage 4 — Topic Enforcement (Two-Stage)
```python
_check_topic_restrictions(original_content, policy, validator)
```

**Sub-stage 4a — Blocked Keyword Matching (always active):**
Iterates over `policy.blocked_topics` (a list of keyword phrases). Checks if any keyword appears as a case-insensitive substring of the prompt. This runs regardless of the `enforce_topic_restrictions` toggle.  
**Raises:** HTTP 400 with the matched keyword.

**Sub-stage 4b — Allowed-Topic ML Classification (toggle-gated):**
Only runs if `policy.enforce_topic_restrictions is True`. Uses the BART-MNLI zero-shot classifier with `policy.allowed_topics` as candidate labels. If the best classification score is below `0.30`, the topic is considered outside the role's allowed domain.  
**Raises:** HTTP 400 listing allowed topics.

### Stage 5 — ML Vetting & Sanitization
```python
validation_result = validator.validate_for_role(original_content, policy.security_level)
```
The `ZeroShotSecurityValidator` runs the full multi-model analysis:
- DeBERTa prompt injection detector
- BERT PII detector
- CodeBERT malicious code detector
- BART-MNLI general classifier

Returns a `ValidationResult` with `is_safe`, `modified_prompt`, `warnings`, `blocked_patterns`, `confidence`.

If the validator is in **block mode** (HIGH security level) and the prompt is unsafe with detected patterns, the request is blocked here. The audit event is enqueued with `action="blocked"` and HTTP 400 is raised.

Otherwise, `sanitized_content = validation_result.modified_prompt` (potentially modified).

### Stage 6 — LLM Call (Ollama)
```python
ollama_messages = _build_ollama_messages(messages, sanitized_content, last_message, policy.system_prompt)
ai_text = await _call_ollama(ollama_messages)
```
The role's `system_prompt` is prepended as the first message with `role: "system"`. All previous messages in the conversation are included for context. The sanitized version of the latest prompt replaces the original.

The Ollama API is called at `OLLAMA_BASE_URL/api/chat` with `stream: false`. Response text is extracted from `response["message"]["content"]`.

### Response Streaming
The pipeline returns an `AsyncGenerator` that yields lines in Vercel AI SDK data-stream format:
- `8:...` — sanitization metadata (if prompt was modified)
- `0:"chunk"` — text deltas (chunked at 5 characters)
- `d:{finishReason, usage}` — completion signal

### Audit Enqueue (non-blocking)
After the LLM call, an `AuditEvent` is put on the queue. The action is determined as:
- `"blocked"` — if `validation_result.is_safe` is False (should not reach here in normal flow)
- `"sanitized"` — if the prompt was modified but safe
- `"passed"` — if the prompt was unchanged and safe

---

## 4. Security Validator (ML Core)

**File:** `app/core/security.py`

The `ZeroShotSecurityValidator` is the heart of the security system. It loads four Hugging Face transformer models at startup:

| Model | HuggingFace ID | Purpose |
|---|---|---|
| Injection detector | `protectai/deberta-v3-base-prompt-injection` | Detects prompt injection attempts |
| PII detector | `SoelMgd/bert-pii-detection` | Detects personally identifiable information |
| Code detector | `microsoft/codebert-base` | Detects malicious code patterns |
| General classifier | BART-MNLI (`facebook/bart-large-mnli`) | Zero-shot classification for jailbreaks, credentials, etc. |

The validator supports three security levels:
- **LOW** — minimal detection, no blocking, sanitize and pass
- **MEDIUM** — moderate detection, sanitize and pass
- **HIGH** — strict detection, block on threats (`block_mode = True`)

`validate_for_role(prompt, role_security_level)` temporarily sets the security level to the role's configured level before running validation, then restores the global level. A `threading.Lock` protects this operation for thread safety.

`validate_prompt(prompt)` runs the full pipeline at the current global security level.

Both return a `ValidationResult` with:
```python
is_safe: bool
modified_prompt: str       # sanitized version
warnings: list[str]        # human-readable descriptions
blocked_patterns: list[str]  # matched threat categories
confidence: float
processing_time_ms: float
```

---

## 5. Next.js Frontend

### 5.1 Project Structure

```
secure_agent/
├── app/
│   ├── layout.tsx              # Root layout (Geist font, global CSS)
│   ├── page.tsx                # Chat UI (assistant-ui SDK)
│   ├── assistant.tsx           # Assistant configuration
│   ├── login/
│   │   └── page.tsx            # Login form (Suspense-wrapped)
│   ├── admin/
│   │   ├── layout.tsx          # Admin shell with sidebar navigation
│   │   ├── page.tsx            # Dashboard with stat cards + charts
│   │   ├── reports/
│   │   │   └── page.tsx        # Full reports page
│   │   ├── roles/
│   │   │   └── page.tsx        # Role & policy management
│   │   └── users/
│   │       └── page.tsx        # User management
│   └── api/
│       └── chat/
│           └── route.ts        # Next.js Route Handler (chat proxy)
├── components/
│   ├── admin/
│   │   └── TagInput.tsx        # Reusable tag input for topic lists
│   ├── assistant-ui/           # assistant-ui component overrides
│   └── ui/                     # shadcn/ui components
├── lib/
│   ├── auth.ts                 # JWT storage, login/logout, refresh
│   ├── admin-api.ts            # Typed fetch wrappers for all API endpoints
│   ├── sanitizer-client.ts     # Sanitize API client
│   └── utils.ts                # cn() Tailwind utility
├── hooks/
│   └── use-mobile.ts           # Mobile breakpoint hook
├── middleware.ts               # Next.js edge middleware (route protection)
└── next.config.ts              # Standalone output, webpack polling
```

---

### 5.2 Auth Library

**File:** `lib/auth.ts`

Tokens are stored in two places simultaneously:
- `localStorage` — for client-side JS access (API calls from components)
- A cookie named `auth_token` — readable by Next.js Edge Middleware for server-side route protection without JavaScript

```typescript
saveTokens(accessToken, refreshToken, user)
  → localStorage.setItem(ACCESS_TOKEN_KEY, ...)
  → localStorage.setItem(REFRESH_TOKEN_KEY, ...)
  → localStorage.setItem(USER_KEY, JSON.stringify(user))
  → setCookie("auth_token", accessToken, 1)  // 1-day cookie, SameSite=Strict

clearTokens()
  → removes all localStorage keys and deletes cookie

login(username, password)
  → POST /api/auth/login
  → calls saveTokens()
  → returns AuthUser

logout()
  → calls clearTokens()

refreshIfExpired()
  → decodes JWT locally (no verification) to check exp
  → if < 5 min remaining: POST /api/auth/refresh
  → updates access token in localStorage + cookie
  → returns true on success, false on failure
```

---

### 5.3 Next.js Middleware (Route Protection)

**File:** `middleware.ts`

Runs on every request via the Next.js Edge Runtime. Checks for the `auth_token` cookie.

```
Public paths: /login, /api/auth, /_next, /favicon
All other paths: require auth_token cookie → redirect to /login?redirect=<original-path>
```

The middleware uses a cookie (not localStorage) because Edge Middleware runs before JavaScript is available. On login, the frontend sets both the cookie and localStorage so both the middleware and client-side code can read the token.

---

### 5.4 Chat Proxy Route

**File:** `app/api/chat/route.ts`

A Next.js Route Handler that proxies chat requests to the Python backend. This indirection is needed because:
1. The browser cannot send requests directly to the Python backend with proper auth headers in some configurations
2. Docker deployments need the proxy to resolve the backend via Docker's internal service name (`BACKEND_INTERNAL_URL`) rather than `localhost`

The proxy:
1. Forwards the `Authorization: Bearer <token>` header from the browser
2. Streams the Python backend's response back to the browser
3. Translates the `d:` (finish) frames from the Python format to `e:` frames expected by assistant-ui
4. Intercepts `8:` (sanitization metadata) frames — logs them, does not forward (avoids `[object Object]` display issues)

---

### 5.5 Login Page

**File:** `app/login/page.tsx`

A full-page centered login form built with Tailwind CSS. Features:
- Password visibility toggle
- Loading spinner during authentication
- Error display for bad credentials
- Redirect to the originally requested page after login (via `?redirect=` query param)
- Dev-only seed account hints block (hidden in production via `process.env.NODE_ENV`)

The `LoginForm` component is wrapped in `<Suspense>` because it calls `useSearchParams()`, which requires a Suspense boundary in Next.js App Router.

---

### 5.6 Admin Panel — Dashboard

**File:** `app/admin/page.tsx`

Stat cards + charts overview:

**Stat cards:**
- Total Prompts (all time)
- Blocked (with block rate %)
- Sanitized
- Manage Users (link shortcut)

**Charts (Recharts):**
- Bar chart: prompt volume for last 14 days (total vs blocked)
- Pie chart: actions taken distribution (passed / sanitized / blocked)

Data is aggregated client-side from the `/api/reports/usage` and `/api/reports/threats` endpoints.

---

### 5.7 Admin Panel — Reports

**File:** `app/admin/reports/page.tsx`

Full reporting dashboard with refresh button. Four sections:

1. **Prompt Volume (last 30 days)** — `LineChart` with three lines: Total, Blocked, Sanitized
2. **Volume by Role** — `PieChart` showing which role generates the most prompts
3. **Security Actions** — `BarChart` grouped by action type (passed/sanitized/blocked)
4. **User Activity Summary** — table showing per-user: total prompts, blocked count, average latency
5. **Recent Blocked Prompts** — table showing timestamp, user, role, department, prompt length, detected threats, block reason, security level

---

### 5.8 Admin Panel — Roles & Policies

**File:** `app/admin/roles/page.tsx`

Full role and policy management interface. Features:

**Role management:**
- Create new roles (name, description, is_admin flag)
- Edit role metadata (rename, change description)
- Delete roles (UI warns if users are still assigned)

**Policy editor (per role, expanded inline):**
| Field | UI Control |
|---|---|
| Security Level | `<select>` (low/medium/high) |
| Max Prompt Length | Number input |
| Max Requests/Day | Number input |
| Max Conversation Turns | Number input |
| Session Timeout (min) | Number input |
| Enforce Topic Restrictions | Toggle switch |
| Response Filtering | Toggle switch |
| Allow File Uploads | Toggle switch |
| Time-of-Day Restrictions | Toggle + HH:MM start/end inputs |
| Allowed Topics | `<TagInput>` |
| Blocked Topics/Keywords | `<TagInput>` |
| System Prompt | `<textarea>` |

Uses `adminApi.roles.updatePolicy()` on save. Creates a new policy via `adminApi.roles.createPolicy()` if the role has no policy.

---

### 5.9 Admin Panel — Users

**File:** `app/admin/users/page.tsx`

User management table with:
- List all users with role, department, status
- Create new user (username, email, password, role, department)
- Update user role or department
- Deactivate (soft-delete) user

---

### 5.10 Admin API Client

**File:** `lib/admin-api.ts`

A typed fetch wrapper client. All requests include `Authorization: Bearer <token>` from localStorage.

```typescript
adminApi.users.list()
adminApi.users.create({ username, email, password, role, department? })
adminApi.users.update(id, { role_name?, department?, is_active? })
adminApi.users.deactivate(id)

adminApi.roles.list()
adminApi.roles.create({ name, description?, is_admin? })
adminApi.roles.update(id, { name?, description?, is_admin? })
adminApi.roles.delete(id)
adminApi.roles.updatePolicy(roleId, Partial<RolePolicyRecord>)
adminApi.roles.createPolicy(roleId)

adminApi.reports.usage(start?, end?)
adminApi.reports.threats(start?, end?)
adminApi.reports.userActivity(start?, end?)
adminApi.reports.blocked(limit?)
```

All TypeScript interfaces exactly mirror the Pydantic response schemas from the backend.

---

## 6. API Reference

### Authentication Flow
```
POST /api/auth/login
Body:  { "username": "admin", "password": "Admin@SecureMCP1" }
Response: {
  "access_token": "<JWT>",
  "refresh_token": "<JWT>",
  "token_type": "bearer",
  "user": { "id": 1, "username": "admin", "role": "admin", "is_admin": true, ... }
}

POST /api/auth/refresh
Body:  { "refresh_token": "<JWT>" }
Response: { "access_token": "<new JWT>", "token_type": "bearer" }

GET /api/auth/me
Headers: Authorization: Bearer <access_token>
Response: UserProfileResponse
```

### Chat
```
POST /api/chat
Headers: Authorization: Bearer <access_token>
Body: {
  "messages": [{ "role": "user", "content": "..." }],
  "session_id": "optional-uuid"
}
Response: text/plain stream (Vercel AI SDK data-stream format)
  → 0:"text chunk"\n   (text deltas)
  → e:{finishReason}\n (completion)
  → Error responses also use data-stream format with finishReason: "error"
```

### Policy Update
```
PUT /api/admin/policies/{role_id}
Headers: Authorization: Bearer <admin_access_token>
Body: {
  "security_level": "medium",
  "max_prompt_length": 4000,
  "max_requests_per_day": 200,
  "system_prompt": "You are...",
  "allowed_topics": ["coding", "devops"],
  "blocked_topics": ["payroll", "salary"],
  "enforce_topic_restrictions": true,
  "response_filter_enabled": false,
  "max_conversation_turns": 50,
  "session_timeout_minutes": 60,
  "allow_file_uploads": false,
  "time_restriction_start": "08:00",
  "time_restriction_end": "18:00"
}
Response: RolePolicyResponse
```

---

## 7. Database Schema

```sql
-- Roles
CREATE TABLE roles (
  id          SERIAL PRIMARY KEY,
  name        VARCHAR(50)  UNIQUE NOT NULL,
  description VARCHAR(255),
  is_admin    BOOLEAN NOT NULL DEFAULT false,
  created_at  TIMESTAMP NOT NULL DEFAULT now()
);

-- Per-role security and behavioural policy
CREATE TABLE role_policies (
  id                        SERIAL PRIMARY KEY,
  role_id                   INTEGER UNIQUE NOT NULL REFERENCES roles(id),
  security_level            VARCHAR(10) NOT NULL DEFAULT 'medium',
  max_prompt_length         INTEGER NOT NULL DEFAULT 4000,
  max_requests_per_day      INTEGER NOT NULL DEFAULT 100,
  system_prompt             TEXT,
  allowed_topics            JSON,
  blocked_topics            JSON,
  enforce_topic_restrictions BOOLEAN NOT NULL DEFAULT false,
  response_filter_enabled   BOOLEAN NOT NULL DEFAULT false,
  max_conversation_turns    INTEGER NOT NULL DEFAULT 50,
  session_timeout_minutes   INTEGER NOT NULL DEFAULT 60,
  allow_file_uploads        BOOLEAN NOT NULL DEFAULT false,
  time_restriction_start    VARCHAR(5),
  time_restriction_end      VARCHAR(5),
  updated_at                TIMESTAMP NOT NULL DEFAULT now()
);

-- Users
CREATE TABLE users (
  id              SERIAL PRIMARY KEY,
  username        VARCHAR(100) UNIQUE NOT NULL,
  email           VARCHAR(255) UNIQUE NOT NULL,
  hashed_password VARCHAR(255) NOT NULL,
  role_id         INTEGER NOT NULL REFERENCES roles(id),
  department      VARCHAR(100),
  is_active       BOOLEAN NOT NULL DEFAULT true,
  created_at      TIMESTAMP NOT NULL DEFAULT now()
);

-- Immutable audit trail
CREATE TABLE audit_events (
  id                   VARCHAR(36) PRIMARY KEY,
  timestamp            TIMESTAMP NOT NULL DEFAULT now(),
  user_id              INTEGER REFERENCES users(id),
  user_role            VARCHAR(50),
  department           VARCHAR(100),
  session_id           VARCHAR(100),
  prompt_hash          VARCHAR(64),
  raw_prompt           TEXT,
  sanitized_prompt     TEXT,
  prompt_length        INTEGER NOT NULL DEFAULT 0,
  threats_detected     JSON,
  sanitization_applied BOOLEAN NOT NULL DEFAULT false,
  blocked              BOOLEAN NOT NULL DEFAULT false,
  block_reason         VARCHAR(255),
  security_level_used  VARCHAR(10),
  confidence_score     FLOAT,
  processing_time_ms   FLOAT NOT NULL DEFAULT 0.0,
  vetting_time_ms      FLOAT NOT NULL DEFAULT 0.0,
  llm_time_ms          FLOAT NOT NULL DEFAULT 0.0,
  model_used           VARCHAR(100),
  tokens_used          INTEGER NOT NULL DEFAULT 0,
  action               VARCHAR(20) NOT NULL DEFAULT 'passed'
);

CREATE INDEX ix_audit_events_user_id    ON audit_events(user_id);
CREATE INDEX ix_audit_events_timestamp  ON audit_events(timestamp);
CREATE INDEX ix_audit_events_blocked    ON audit_events(blocked);
CREATE INDEX ix_audit_events_user_role  ON audit_events(user_role);
```

---

## 8. Dependency List

### Backend (`requirements.txt`)
```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
pydantic[email]>=2.9.0
pydantic-settings>=2.6.0
transformers>=4.36.2
torch>=2.6.0
spacy>=3.7.2
sentence-transformers>=2.2.0
python-dotenv>=1.0.0
python-multipart>=0.0.6
aiofiles>=23.2.1
httpx>=0.27.0
sqlalchemy[asyncio]>=2.0.0
aiosqlite>=0.20.0
asyncpg>=0.29.0
alembic>=1.13.0
python-jose[cryptography]>=3.3.0
bcrypt>=4.0.0
```

### Frontend key dependencies (`package.json`)
```
next (15.x)
react, react-dom
@assistant-ui/react
ai (Vercel AI SDK)
recharts
lucide-react
tailwindcss
shadcn/ui components (button, dialog, input, etc.)
```

---

## 9. Startup & Development

### Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL running (local or Docker)
- Ollama running with `llama3.2` model pulled: `ollama pull llama3.2`

### Backend
```bash
cd agent-ui/python-backend

# 1. Configure .env
#    Set DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/securemcp
#    Set JWT_SECRET=<long random string>

# 2. Start (creates venv, installs deps, runs migrations, starts server)
.\start.bat

# Manual migration commands:
alembic upgrade head      # apply all migrations
alembic downgrade -1      # revert last migration
alembic revision --autogenerate -m "description"  # generate new migration
```

### Frontend
```bash
cd agent-ui/secure_agent
npm install
npm run dev    # starts on http://localhost:3000
```

### Environment Variables (`.env` — backend)
```env
PORT=8003
HOST=0.0.0.0
CORS_ORIGINS=http://localhost:3000

DATABASE_URL=postgresql+asyncpg://securemcp:securemcp_dev_pass@localhost:5432/securemcp

JWT_SECRET=<long-random-string>
JWT_EXPIRY_MINUTES=60
JWT_REFRESH_EXPIRY_DAYS=7

DEFAULT_SECURITY_LEVEL=medium
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

STORE_RAW_PROMPTS=False
```

### Environment Variables (`.env.local` — frontend)
```env
NEXT_PUBLIC_SANITIZER_API_URL=http://localhost:8003
# For Docker only:
# BACKEND_INTERNAL_URL=http://python-backend:8003
```

---

## 10. Known Design Decisions & Fixes

### Topic Enforcement — Two-Stage Design
The `enforce_topic_restrictions` toggle controls only the ML zero-shot classification check. Blocked keywords are **always enforced** regardless of the toggle state. This is intentional — keywords represent an explicit security boundary (e.g. "don't discuss payroll"), while the topic classification is a best-effort ML-based filter for broader control.

Note: Keyword matching is a case-insensitive substring check. A blocked keyword of `"salary negotiation"` will NOT block a prompt containing only the word `"salary"`. Admins should add specific terms they want blocked.

### PostgreSQL Type Compatibility
Two PostgreSQL-specific type issues were resolved:
1. **DATE = VARCHAR**: `audit_repository.count_today_for_user` passes `date.today()` (a Python `date` object) instead of `date.today().isoformat()` (a string). SQLAlchemy binds a `date` object to `DATE`; a string is bound as `VARCHAR`, causing a PostgreSQL operator error.
2. **Timezone-aware datetime**: `AuditEvent.timestamp` is stored in a `TIMESTAMP WITHOUT TIME ZONE` column. The Python code uses `datetime.now(timezone.utc).replace(tzinfo=None)` to create a naive UTC datetime. asyncpg rejects timezone-aware datetimes for naive-timestamp columns.
3. **Boolean aggregation**: `get_usage_summary` and `get_user_activity` use `func.count().filter(col.is_(True))` instead of `SUM(CAST(bool AS INTEGER))`. The `func.cast()` pattern does not exist in SQLAlchemy; the filter approach is idiomatic and correct on PostgreSQL.

### Password Hashing — bcrypt Directly
`passlib[bcrypt]` was removed because `passlib` has an incompatibility with `bcrypt>=4.0.0` that causes `AttributeError: module 'bcrypt' has no attribute '__about__'`. The backend now uses `bcrypt` directly.

### Pydantic `extra = "ignore"`
`Settings.Config` sets `extra = "ignore"` to silently ignore any system-level environment variables not defined in the `Settings` model. This prevents `ValidationError` when stale environment variables (e.g. legacy `GEMINI_API_KEY`) remain in the system environment after an LLM migration.

### LLM — Ollama (Local Llama 3.2)
The application originally used Google Gemini. It was migrated to Ollama running `llama3.2` locally. The Ollama `/api/chat` endpoint uses the same OpenAI-compatible message format. The system prompt (from the role policy) is prepended as `{"role": "system", "content": "..."}`. Temperature is fixed at `0.7`.

### Audit Worker — Fallback JSONL
If PostgreSQL is unavailable during the audit worker's write attempts, events are written to `audit_fallback.jsonl` in the backend working directory. These can be replayed manually into the database after connectivity is restored.

### Next.js `useSearchParams()` + Suspense
The login page uses `useSearchParams()` to read the `?redirect=` parameter. In Next.js App Router (Next.js 15), `useSearchParams()` must be used inside a component wrapped by `<Suspense>`. The page exports a wrapper `LoginPage` component that renders `<Suspense><LoginForm /></Suspense>`.

### Timestamp Column — `TIMESTAMP WITHOUT TIME ZONE`
The `audit_events.timestamp` column is `TIMESTAMP WITHOUT TIME ZONE` (i.e. no timezone stored). All timestamps are UTC by convention. The Python code enforces this by stripping timezone info before inserting. For a future migration, consider changing to `TIMESTAMP WITH TIME ZONE` for explicit timezone safety.
