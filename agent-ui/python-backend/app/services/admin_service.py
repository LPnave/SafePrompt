"""
Admin service — user management and role policy CRUD.
"""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_password
from app.db.models import User, Role, RolePolicy
from app.repositories.user_repository import UserRepository
from app.repositories.role_repository import RoleRepository, RolePolicyRepository
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

async def list_users(db: AsyncSession) -> list[User]:
    repo = UserRepository(db)
    return await repo.get_all_with_roles()


async def create_user(
    username: str, email: str, password: str,
    role_name: str, department: str | None, db: AsyncSession
) -> User:
    user_repo = UserRepository(db)
    role_repo = RoleRepository(db)

    if await user_repo.get_by_username(username):
        raise HTTPException(status_code=409, detail="Username already exists")
    if await user_repo.get_by_email(email):
        raise HTTPException(status_code=409, detail="Email already registered")

    role = await role_repo.get_by_name(role_name)
    if not role:
        raise HTTPException(status_code=400, detail=f"Role '{role_name}' not found")

    user = User(
        username=username, email=email,
        hashed_password=hash_password(password),
        role_id=role.id, department=department,
    )
    return await user_repo.create(user)


async def update_user(user_id: int, updates: dict, db: AsyncSession) -> User:
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if "role_name" in updates:
        role_repo = RoleRepository(db)
        role = await role_repo.get_by_name(updates.pop("role_name"))
        if not role:
            raise HTTPException(status_code=400, detail="Role not found")
        user.role_id = role.id

    for key, value in updates.items():
        if hasattr(user, key):
            setattr(user, key, value)

    return await user_repo.update(user)


async def deactivate_user(user_id: int, db: AsyncSession) -> User:
    return await update_user(user_id, {"is_active": False}, db)


# ---------------------------------------------------------------------------
# Role management
# ---------------------------------------------------------------------------

async def list_roles(db: AsyncSession) -> list[Role]:
    repo = RoleRepository(db)
    return await repo.get_all_with_policies()


async def update_role_policy(role_id: int, updates: dict, db: AsyncSession) -> RolePolicy:
    policy_repo = RolePolicyRepository(db)
    policy = await policy_repo.get_by_role_id(role_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Role policy not found")

    allowed = {
        "security_level", "max_prompt_length", "max_requests_per_day",
        "system_prompt", "allowed_topics", "blocked_topics",
        "enforce_topic_restrictions", "response_filter_enabled",
        "max_conversation_turns", "session_timeout_minutes",
        "allow_file_uploads", "time_restriction_start", "time_restriction_end",
    }
    for key, value in updates.items():
        if key in allowed:
            setattr(policy, key, value)

    return await policy_repo.update(policy)


async def create_role(
    name: str, description: str | None, is_admin: bool, db: AsyncSession
) -> Role:
    role_repo = RoleRepository(db)
    policy_repo = RolePolicyRepository(db)

    existing = await role_repo.get_by_name(name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Role '{name}' already exists")

    role = Role(name=name, description=description, is_admin=is_admin)
    role = await role_repo.create(role)

    # Auto-create a default policy for the new role
    policy = RolePolicy(
        role_id=role.id,
        security_level="medium",
        max_prompt_length=2000,
        max_requests_per_day=100,
    )
    await policy_repo.create(policy)
    logger.info("Created role '%s' (id=%d) with default policy", name, role.id)
    return role


async def update_role(role_id: int, updates: dict, db: AsyncSession) -> Role:
    role_repo = RoleRepository(db)
    role = await role_repo.get_by_id(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if "name" in updates and updates["name"] != role.name:
        if await role_repo.get_by_name(updates["name"]):
            raise HTTPException(status_code=409, detail="Role name already in use")

    for key, value in updates.items():
        if hasattr(role, key):
            setattr(role, key, value)

    return await role_repo.update(role)


async def delete_role(role_id: int, db: AsyncSession) -> None:
    role_repo = RoleRepository(db)
    policy_repo = RolePolicyRepository(db)
    user_repo = UserRepository(db)

    role = await role_repo.get_by_id(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_admin:
        raise HTTPException(status_code=403, detail="Cannot delete the admin role")

    # Guard: reject if any active user is still assigned to this role
    users = await user_repo.get_by_role_id(role_id)
    if users:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete role: {len(users)} user(s) still assigned. Reassign them first.",
        )

    policy = await policy_repo.get_by_role_id(role_id)
    if policy:
        await policy_repo.delete(policy)

    await role_repo.delete(role)
    logger.info("Deleted role id=%d ('%s')", role_id, role.name)


async def create_policy_for_role(role_id: int, db: AsyncSession) -> RolePolicy:
    """Idempotent — returns existing policy or creates one with safe defaults."""
    role_repo = RoleRepository(db)
    policy_repo = RolePolicyRepository(db)

    role = await role_repo.get_by_id(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    existing = await policy_repo.get_by_role_id(role_id)
    if existing:
        return existing

    policy = RolePolicy(
        role_id=role_id,
        security_level="medium",
        max_prompt_length=2000,
        max_requests_per_day=100,
    )
    return await policy_repo.create(policy)
