"""
Admin controller — user management and role policy CRUD.
All endpoints require admin role.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    CreateUserRequest, UpdateUserRequest, UserResponse,
    RoleResponse, RolePolicyResponse, UpdatePolicyRequest,
    CreateRoleRequest, UpdateRoleRequest,
)
from app.core.database import get_db
from app.services.auth_service import require_admin
from app.services import admin_service
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users", response_model=list[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    users = await admin_service.list_users(db)
    return [
        UserResponse(
            id=u.id, username=u.username, email=u.email,
            role=u.role.name if u.role else "unknown",
            department=u.department, is_active=u.is_active, created_at=u.created_at,
        )
        for u in users
    ]


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    request: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    user = await admin_service.create_user(
        username=request.username, email=request.email,
        password=request.password, role_name=request.role,
        department=request.department, db=db,
    )
    return UserResponse(
        id=user.id, username=user.username, email=user.email,
        role=request.role, department=user.department,
        is_active=user.is_active, created_at=user.created_at,
    )


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    request: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    updates = request.model_dump(exclude_none=True)
    user = await admin_service.update_user(user_id, updates, db)
    return UserResponse(
        id=user.id, username=user.username, email=user.email,
        role=user.role.name if user.role else "unknown",
        department=user.department, is_active=user.is_active, created_at=user.created_at,
    )


@router.delete("/users/{user_id}", status_code=204)
async def deactivate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    await admin_service.deactivate_user(user_id, db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _policy_response(p) -> RolePolicyResponse:
    return RolePolicyResponse(
        id=p.id, role_id=p.role_id,
        security_level=p.security_level,
        max_prompt_length=p.max_prompt_length,
        max_requests_per_day=p.max_requests_per_day,
        system_prompt=p.system_prompt,
        allowed_topics=p.allowed_topics,
        blocked_topics=p.blocked_topics,
        enforce_topic_restrictions=p.enforce_topic_restrictions,
        response_filter_enabled=p.response_filter_enabled,
        max_conversation_turns=p.max_conversation_turns,
        session_timeout_minutes=p.session_timeout_minutes,
        allow_file_uploads=p.allow_file_uploads,
        time_restriction_start=p.time_restriction_start,
        time_restriction_end=p.time_restriction_end,
        updated_at=p.updated_at,
    )


# ---------------------------------------------------------------------------
# Roles & policies
# ---------------------------------------------------------------------------

@router.get("/roles", response_model=list[RoleResponse])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    roles = await admin_service.list_roles(db)
    return [
        RoleResponse(
            id=r.id, name=r.name, description=r.description,
            is_admin=r.is_admin,
            policy=_policy_response(r.policy) if r.policy else None,
        )
        for r in roles
    ]


@router.post("/roles", response_model=RoleResponse, status_code=201)
async def create_role(
    request: CreateRoleRequest,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    role = await admin_service.create_role(
        name=request.name, description=request.description,
        is_admin=request.is_admin, db=db,
    )
    # Reload with policy
    roles = await admin_service.list_roles(db)
    created = next((r for r in roles if r.id == role.id), None)
    return RoleResponse(
        id=created.id, name=created.name, description=created.description,
        is_admin=created.is_admin,
        policy=_policy_response(created.policy) if created and created.policy else None,
    )


@router.put("/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    request: UpdateRoleRequest,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    updates = request.model_dump(exclude_none=True)
    await admin_service.update_role(role_id, updates, db)
    roles = await admin_service.list_roles(db)
    updated = next((r for r in roles if r.id == role_id), None)
    if not updated:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Role not found")
    return RoleResponse(
        id=updated.id, name=updated.name, description=updated.description,
        is_admin=updated.is_admin,
        policy=_policy_response(updated.policy) if updated.policy else None,
    )


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    await admin_service.delete_role(role_id, db)


@router.put("/policies/{role_id}", response_model=RolePolicyResponse)
async def update_policy(
    role_id: int,
    request: UpdatePolicyRequest,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    updates = request.model_dump(exclude_none=True)
    policy = await admin_service.update_role_policy(role_id, updates, db)
    return _policy_response(policy)


@router.post("/policies/{role_id}", response_model=RolePolicyResponse, status_code=201)
async def create_policy(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    policy = await admin_service.create_policy_for_role(role_id, db)
    return _policy_response(policy)
