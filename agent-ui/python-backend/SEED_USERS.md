# Seed Users

These users are automatically created on first server startup via `app/db/seed.py`.
The seeding is **idempotent** — running the server multiple times will not duplicate records.

> **Important:** Change all passwords after first login in any non-development environment.

---

## Default Users

| Username | Email | Password | Role | Department |
|---|---|---|---|---|
| `admin` | admin@company.com | `Admin@SecureMCP1` | admin | IT |
| `engineer1` | engineer@company.com | `Engineer@SecureMCP1` | engineering | Engineering |
| `hr_manager` | hr@company.com | `HR@SecureMCP1` | hr | Human Resources |
| `finance_analyst` | finance@company.com | `Finance@SecureMCP1` | finance | Finance |

---

## Role Policies

### admin
- **Security level:** low
- **Max prompt length:** 10,000 characters
- **Max requests/day:** 1,000
- **System prompt:** Full access, no topic restrictions
- **Allowed topics:** (all)
- **Blocked topics:** (none)

### engineering
- **Security level:** medium
- **Max prompt length:** 4,000 characters
- **Max requests/day:** 200
- **System prompt:** Software engineering tasks (coding, architecture, debugging, DevOps)
- **Allowed topics:** coding, architecture, debugging, devops, technical, software
- **Blocked topics:** payroll, salary negotiation, personal hr matters

### hr
- **Security level:** high
- **Max prompt length:** 2,000 characters
- **Max requests/day:** 100
- **System prompt:** HR policies, recruitment, onboarding, employee relations, performance
- **Allowed topics:** hr, recruitment, policies, employee, benefits, onboarding, performance
- **Blocked topics:** code, programming, sql injection, hacking, exploit

### finance
- **Security level:** high
- **Max prompt length:** 2,000 characters
- **Max requests/day:** 100
- **System prompt:** Financial analysis, budgeting, forecasting, accounting, reporting
- **Allowed topics:** finance, budgeting, accounting, reporting, forecasting, investment
- **Blocked topics:** code, programming, exploit, hacking

---

## Adding New Users (Admin API)

Once the server is running, use the admin endpoint to create additional users:

```bash
# 1. Login as admin to get a token
curl -X POST http://localhost:8003/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "Admin@SecureMCP1"}'

# 2. Create a new user (requires Bearer token)
curl -X POST http://localhost:8003/api/admin/users \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "newengineer",
    "email": "newengineer@company.com",
    "password": "StrongPass@123",
    "role": "engineering",
    "department": "Engineering"
  }'
```

---

## Updating Role Policies (Admin API)

```bash
# Update the HR role policy (e.g. increase daily limit)
curl -X PUT http://localhost:8003/api/admin/policies/<hr_role_id> \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "max_requests_per_day": 150,
    "security_level": "high"
  }'
```

---

## Environment Variables

Set these in `agent-ui/python-backend/.env` before starting:

```env
# Required
GEMINI_API_KEY=your-gemini-key-here

# JWT — change in production!
JWT_SECRET=use-a-long-random-string-here

# Database (defaults to local SQLite)
DATABASE_URL=sqlite+aiosqlite:///./securemcp.db

# Optional: store raw prompt text in audit log (default: false)
STORE_RAW_PROMPTS=false
```
