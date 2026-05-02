"""
Auth controller — handles /api/auth/* endpoints.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    LoginRequest, RegisterRequest, RefreshRequest,
    TokenResponse, UserProfileResponse,
)
from app.core.database import get_db
from app.services.auth_service import (
    login, refresh_access_token, register_user, get_current_user,
)
from app.db.models import User, RolePolicy

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login_endpoint(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    return await login(request.username, request.password, db)


@router.post("/register", response_model=UserProfileResponse, status_code=201)
async def register_endpoint(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    current: tuple = Depends(get_current_user),
):
    """Admin-only registration endpoint."""
    user, _ = current
    if not user.role.is_admin:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    new_user = await register_user(
        username=request.username,
        email=request.email,
        password=request.password,
        role_name=request.role,
        department=request.department,
        db=db,
    )
    return UserProfileResponse(
        id=new_user.id,
        username=new_user.username,
        email=new_user.email,
        role=request.role,
        department=new_user.department,
        is_admin=False,
        is_active=new_user.is_active,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_endpoint(request: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await refresh_access_token(request.refresh_token, db)


@router.get("/me", response_model=UserProfileResponse)
async def me_endpoint(current: tuple[User, RolePolicy] = Depends(get_current_user)):
    user, _ = current
    return UserProfileResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role.name,
        department=user.department,
        is_admin=user.role.is_admin,
        is_active=user.is_active,
    )
