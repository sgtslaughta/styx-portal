from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import ServiceTemplate, User
from app.schemas import TemplateCreate, TemplateUpdate
from app.security.deps import get_current_user, require_owner_or_admin

router = APIRouter()

# Field allowlist for template updates. Only these fields can be modified via PUT.
_TEMPLATE_UPDATE_FIELDS = {
    "display_name", "image", "icon", "description", "env_vars",
    "gpu_enabled", "gpu_count", "memory_limit", "cpu_limit", "shm_size",
    "dind", "volumes", "internal_port", "internal_protocol",
    "category", "tags", "session_config",
    "cap_add", "security_opt", "tls_skip_verify",
}


@router.get("", response_model=list[ServiceTemplate])
async def list_templates(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    stmt = select(ServiceTemplate)
    if user.role != "admin":
        stmt = stmt.where(
            (ServiceTemplate.owner_id == user.id) | (ServiceTemplate.owner_id == None)  # noqa: E711
        )
    result = await session.exec(stmt)
    return result.all()


@router.post("", response_model=ServiceTemplate, status_code=201)
async def create_template(
    body: TemplateCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if not body.image or not body.image.strip():
        raise HTTPException(422, "Docker image is required")

    if body.dind and user.role != "admin":
        raise HTTPException(403, "DinD templates require admin")

    result = await session.exec(
        select(ServiceTemplate).where(ServiceTemplate.name == body.name)
    )
    existing = result.first()
    if existing:
        raise HTTPException(409, f"Template '{body.name}' already exists")

    template = ServiceTemplate(**body.model_dump(), owner_id=user.id)
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


@router.get("/{template_id}", response_model=ServiceTemplate)
async def get_template(
    template_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    template = await session.get(ServiceTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    if template.owner_id is not None:
        require_owner_or_admin(template.owner_id, user)
    return template


@router.put("/{template_id}", response_model=ServiceTemplate)
async def update_template(
    template_id: str,
    body: TemplateUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    template = await session.get(ServiceTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")

    # Explicit authorization: shared templates (owner_id=None) require admin role
    if template.owner_id is None:
        if user.role != "admin":
            raise HTTPException(403, "Shared templates can only be modified by admins")
    else:
        require_owner_or_admin(template.owner_id, user)

    if body.dind and user.role != "admin":
        raise HTTPException(403, "DinD templates require admin")

    # Apply only allowlisted fields
    for field, value in body.model_dump(exclude_unset=True).items():
        if field in _TEMPLATE_UPDATE_FIELDS:
            setattr(template, field, value)

    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    template = await session.get(ServiceTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")

    # Explicit authorization: shared templates (owner_id=None) require admin role
    if template.owner_id is None:
        if user.role != "admin":
            raise HTTPException(403, "Shared templates can only be modified by admins")
    else:
        require_owner_or_admin(template.owner_id, user)

    await session.delete(template)
    await session.commit()
    return Response(status_code=204)
