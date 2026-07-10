"""
Authentication service — login, registration, token refresh.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    verify_password, hash_password,
    create_access_token, create_refresh_token,
    decode_token,
)
from app.core.database import get_db
from app.db.models import User, Role, RolePolicy
from app.repositories.user_repository import UserRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.audit_repository import AuditRepository
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def build_user_profile(user: User, requests_today: int | None = None) -> dict:
    """Serialize user + role policy flags for the frontend."""
    policy = user.role.policy if user.role else None
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.name,
        "department": user.department,
        "is_admin": user.role.is_admin,
        "is_active": user.is_active,
        "allow_file_uploads": bool(policy.allow_file_uploads) if policy else False,
        "time_restriction_start": policy.time_restriction_start if policy else None,
        "time_restriction_end": policy.time_restriction_end if policy else None,
        "session_timeout_minutes": policy.session_timeout_minutes if policy else 60,
        "max_conversation_turns": policy.max_conversation_turns if policy else 50,
        "security_level": policy.security_level if policy else "medium",
        "max_prompt_length": policy.max_prompt_length if policy else 4000,
        "max_requests_per_day": policy.max_requests_per_day if policy else 100,
        "requests_today": requests_today if requests_today is not None else 0,
    }


async def login(username: str, password: str, db: AsyncSession) -> dict:
    user_repo = UserRepository(db)
    user = await user_repo.get_by_username(username)

    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    access_token = create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role.name,
        is_admin=user.role.is_admin,
        token_version=getattr(user, "token_version", 0),
    )
    refresh_token = create_refresh_token(user_id=user.id)

    logger.info(f"User logged in: {user.username} (role: {user.role.name})")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": build_user_profile(user),
    }


async def refresh_access_token(refresh_token: str, db: AsyncSession) -> dict:
    payload = decode_token(refresh_token, expected_type="refresh")
    user_id = int(payload["sub"])

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id_with_role(user_id)

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    new_access_token = create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role.name,
        is_admin=user.role.is_admin,
        token_version=getattr(user, "token_version", 0),
    )
    return {"access_token": new_access_token, "token_type": "bearer"}


async def register_user(
    username: str, email: str, password: str, role_name: str,
    department: str | None, db: AsyncSession
) -> User:
    user_repo = UserRepository(db)
    role_repo = RoleRepository(db)

    if await user_repo.get_by_username(username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    if await user_repo.get_by_email(email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    role = await role_repo.get_by_name(role_name)
    if not role:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Role '{role_name}' not found")

    new_user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        role_id=role.id,
        department=department,
    )
    return await user_repo.create(new_user)


# ---------------------------------------------------------------------------
# FastAPI dependency — resolves the current authenticated user from the token
# ---------------------------------------------------------------------------

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, RolePolicy]:
    """
    Dependency injected into protected endpoints.
    Returns (user, policy) so controllers can enforce role limits.
    """
    payload = decode_token(token, expected_type="access")
    user_id = int(payload["sub"])

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id_with_role(user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    token_version = getattr(user, "token_version", 0)
    if payload.get("tv", 0) != token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )

    policy = user.role.policy if user.role else None
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No policy configured for role '{user.role.name}'",
        )

    return user, policy


async def invalidate_user_session(user: User, db: AsyncSession) -> None:
    """Bump token_version so existing access tokens are rejected."""
    user_repo = UserRepository(db)
    user.token_version = getattr(user, "token_version", 0) + 1
    await user_repo.update(user)
    logger.info("Session invalidated for user: %s (tv=%d)", user.username, user.token_version)


async def require_admin(
    current: tuple = Depends(get_current_user),
) -> tuple[User, RolePolicy]:
    user, policy = current
    if not user.role.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user, policy
