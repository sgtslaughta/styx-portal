from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import ServiceTemplate, User
from app.schemas import TemplateCreate, TemplateUpdate
from app.security.deps import get_current_user, require_owner_or_admin
from app.services.docker_args import validate_extra_args, DockerArgError

router = APIRouter()

# Risk fields that non-admins must NOT be able to set.
_RISK_FIELDS = (
    "devices", "entrypoint", "command", "privileged",
    "extra_docker_args", "dind", "cap_add", "security_opt"
)


def _enforce_risk_gate(body, user) -> None:
    """Raise 403 if non-admin tries to set a risk field."""
    if user.role == "admin":
        return
    # Special handling for cap_add/security_opt to maintain backward compatibility
    if (body.cap_add or body.security_opt) and user.role != "admin":
        raise HTTPException(403, "cap_add/security_opt overrides require admin")
    # General risk field gate for other fields
    for f in _RISK_FIELDS:
        if f in ("cap_add", "security_opt"):
            continue  # Already handled above
        if getattr(body, f, None):  # truthy: non-empty list/dict/str or True
            raise HTTPException(403, f"'{f}' requires admin")

# Field allowlist for template updates. Only these fields can be modified via PUT.
_TEMPLATE_UPDATE_FIELDS = {
    "display_name", "image", "icon", "description", "env_vars",
    "gpu_enabled", "gpu_count", "memory_limit", "cpu_limit", "shm_size",
    "dind", "volumes", "internal_port", "internal_protocol",
    "category", "tags", "session_config",
    "cap_add", "security_opt", "tls_skip_verify",
    "shared", "restart_policy", "read_only_rootfs", "tmpfs", "extra_hosts",
    "ulimits", "extra_ports", "entrypoint", "command", "devices",
    "privileged", "extra_docker_args",
}


@router.get("", response_model=list[ServiceTemplate])
async def list_templates(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    stmt = select(ServiceTemplate)
    if user.role != "admin":
        stmt = stmt.where(
            (ServiceTemplate.owner_id == user.id) | (ServiceTemplate.owner_id == None) | (ServiceTemplate.shared == True)  # noqa: E711, E712
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

    # Enforce risk field gate
    _enforce_risk_gate(body, user)

    # Validate extra_docker_args
    try:
        validate_extra_args(body.extra_docker_args or {}, is_admin=(user.role == "admin"))
    except DockerArgError as e:
        raise HTTPException(400, str(e))

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

    # Enforce risk field gate on patch — only for fields present in the patch
    _enforce_risk_gate(body, user)

    # Validate extra_docker_args if present in patch
    if body.extra_docker_args is not None:
        try:
            validate_extra_args(body.extra_docker_args, is_admin=(user.role == "admin"))
        except DockerArgError as e:
            raise HTTPException(400, str(e))

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
