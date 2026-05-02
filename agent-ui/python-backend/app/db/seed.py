"""
Database seed script — populates default roles, policies and users.
Run once on first startup, or call seed_database() from the lifespan handler.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import Role, RolePolicy, User
from app.core.auth import hash_password
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Seed data definitions
# ---------------------------------------------------------------------------

ROLES = [
    {"name": "admin",        "description": "Platform administrator with full access", "is_admin": True},
    {"name": "engineering",  "description": "Software engineering team",               "is_admin": False},
    {"name": "hr",           "description": "Human resources team",                    "is_admin": False},
    {"name": "finance",      "description": "Finance and accounting team",             "is_admin": False},
]

ROLE_POLICIES = {
    "admin": {
        "security_level": "low",
        "max_prompt_length": 10000,
        "max_requests_per_day": 1000,
        "system_prompt": (
            "You are a helpful enterprise AI assistant. "
            "You have full access and can assist with any topic."
        ),
        "allowed_topics": [],
        "blocked_topics": [],
    },
    "engineering": {
        "security_level": "medium",
        "max_prompt_length": 4000,
        "max_requests_per_day": 200,
        "system_prompt": (
            "You are a helpful AI assistant for software engineering tasks. "
            "Assist with coding, architecture, code review, debugging, DevOps, "
            "and technical design. Keep answers concise and technically accurate."
        ),
        "allowed_topics": ["coding", "architecture", "debugging", "devops", "technical", "software"],
        "blocked_topics": ["payroll", "salary negotiation", "personal hr matters"],
    },
    "hr": {
        "security_level": "high",
        "max_prompt_length": 2000,
        "max_requests_per_day": 100,
        "system_prompt": (
            "You are a helpful AI assistant for HR professionals. "
            "Assist with HR policies, recruitment, onboarding, employee relations, "
            "performance management, and workplace matters. "
            "Do not assist with software engineering or technical infrastructure topics."
        ),
        "allowed_topics": ["hr", "recruitment", "policies", "employee", "benefits", "onboarding", "performance"],
        "blocked_topics": ["code", "programming", "sql injection", "hacking", "exploit"],
    },
    "finance": {
        "security_level": "high",
        "max_prompt_length": 2000,
        "max_requests_per_day": 100,
        "system_prompt": (
            "You are a helpful AI assistant for finance professionals. "
            "Assist with financial analysis, budgeting, forecasting, accounting, "
            "and financial reporting. Do not assist with software engineering topics."
        ),
        "allowed_topics": ["finance", "budgeting", "accounting", "reporting", "forecasting", "investment"],
        "blocked_topics": ["code", "programming", "exploit", "hacking"],
    },
}

# Default seed users — passwords should be changed after first login
SEED_USERS = [
    {
        "username": "admin",
        "email": "admin@company.com",
        "password": "Admin@SecureMCP1",
        "role": "admin",
        "department": "IT",
    },
    {
        "username": "engineer1",
        "email": "engineer@company.com",
        "password": "Engineer@SecureMCP1",
        "role": "engineering",
        "department": "Engineering",
    },
    {
        "username": "hr_manager",
        "email": "hr@company.com",
        "password": "HR@SecureMCP1",
        "role": "hr",
        "department": "Human Resources",
    },
    {
        "username": "finance_analyst",
        "email": "finance@company.com",
        "password": "Finance@SecureMCP1",
        "role": "finance",
        "department": "Finance",
    },
]


# ---------------------------------------------------------------------------
# Seeding logic
# ---------------------------------------------------------------------------

async def seed_database(db: AsyncSession) -> None:
    """
    Idempotent seed — only inserts rows that do not already exist.
    Safe to call on every startup.
    """
    await _seed_roles(db)
    await _seed_users(db)
    logger.info("Database seeding complete")


async def _seed_roles(db: AsyncSession) -> None:
    for role_data in ROLES:
        result = await db.execute(select(Role).where(Role.name == role_data["name"]))
        existing = result.scalar_one_or_none()

        if existing is None:
            role = Role(**role_data)
            db.add(role)
            await db.flush()  # get role.id without committing

            policy_data = ROLE_POLICIES.get(role_data["name"], {})
            policy = RolePolicy(role_id=role.id, **policy_data)
            db.add(policy)
            logger.info(f"Seeded role: {role_data['name']}")
        else:
            logger.debug(f"Role already exists, skipping: {role_data['name']}")

    await db.commit()


async def _seed_users(db: AsyncSession) -> None:
    for user_data in SEED_USERS:
        result = await db.execute(select(User).where(User.username == user_data["username"]))
        existing = result.scalar_one_or_none()

        if existing is None:
            role_result = await db.execute(select(Role).where(Role.name == user_data["role"]))
            role = role_result.scalar_one_or_none()

            if role is None:
                logger.warning(f"Role '{user_data['role']}' not found, skipping user: {user_data['username']}")
                continue

            user = User(
                username=user_data["username"],
                email=user_data["email"],
                hashed_password=hash_password(user_data["password"]),
                role_id=role.id,
                department=user_data.get("department"),
            )
            db.add(user)
            logger.info(f"Seeded user: {user_data['username']} ({user_data['role']})")
        else:
            logger.debug(f"User already exists, skipping: {user_data['username']}")

    await db.commit()
