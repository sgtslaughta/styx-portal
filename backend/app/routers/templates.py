from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import ServiceTemplate
from app.schemas import TemplateCreate, TemplateUpdate

router = APIRouter()


@router.get("", response_model=list[ServiceTemplate])
async def list_templates(session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(ServiceTemplate))
    return result.all()


@router.post("", response_model=ServiceTemplate, status_code=201)
async def create_template(body: TemplateCreate, session: AsyncSession = Depends(get_session)):
    if not body.image or not body.image.strip():
        raise HTTPException(422, "Docker image is required")

    result = await session.exec(
        select(ServiceTemplate).where(ServiceTemplate.name == body.name)
    )
    existing = result.first()
    if existing:
        raise HTTPException(409, f"Template '{body.name}' already exists")

    template = ServiceTemplate(**body.model_dump())
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


@router.get("/{template_id}", response_model=ServiceTemplate)
async def get_template(template_id: str, session: AsyncSession = Depends(get_session)):
    template = await session.get(ServiceTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    return template


@router.put("/{template_id}", response_model=ServiceTemplate)
async def update_template(
    template_id: str, body: TemplateUpdate, session: AsyncSession = Depends(get_session)
):
    template = await session.get(ServiceTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(template, field, value)

    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: str, session: AsyncSession = Depends(get_session)):
    template = await session.get(ServiceTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    await session.delete(template)
    await session.commit()
    return Response(status_code=204)
