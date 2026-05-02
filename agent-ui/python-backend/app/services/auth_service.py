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
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


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
    )
    refresh_token = create_refresh_token(user_id=user.id)

    logger.info(f"User logged in: {user.username} (role: {user.role.name})")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role.name,
            "department": user.department,
            "is_admin": user.role.is_admin,
        },
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

    policy = user.role.policy if user.role else None
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No policy configured for role '{user.role.name}'",
        )

    return user, policy


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
