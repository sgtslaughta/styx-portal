from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import PulledImage, Instance, ServiceTemplate, User
from app.security.deps import get_current_user, require_admin
from app.services.docker_manager import DockerManager

router = APIRouter()
_settings = Settings()


def get_docker_manager() -> DockerManager:
    return DockerManager(network_name=_settings.DOCKER_NETWORK)


@router.get("", response_model=list[PulledImage])
async def list_images(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    result = await session.exec(select(PulledImage))
    return result.all()


@router.delete("/{image_id}", status_code=204)
async def delete_image(
    image_id: str,
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
    admin: User = Depends(require_admin),
):
    pulled = await session.get(PulledImage, image_id)
    if not pulled:
        raise HTTPException(404, "Image not found")

    # Check if any instances still use this image
    result = await session.exec(select(Instance).join(ServiceTemplate, Instance.template_id == ServiceTemplate.id).where(ServiceTemplate.image == pulled.image))
    instances = result.all()
    if instances:
        raise HTTPException(409, f"Image still used by {len(instances)} instance(s)")

    try:
        docker.remove_image(pulled.image)
    except Exception:
        pass  # Image may already be gone from Docker

    await session.delete(pulled)
    await session.commit()
    return Response(status_code=204)


@router.delete("", status_code=204)
async def purge_images(
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
    admin: User = Depends(require_admin),
):
    """Remove all tracked images that have no active instances."""
    result = await session.exec(select(PulledImage))
    all_images = result.all()

    for pulled in all_images:
        inst_result = await session.exec(
            select(Instance).join(
                ServiceTemplate, Instance.template_id == ServiceTemplate.id
            ).where(ServiceTemplate.image == pulled.image)
        )
        if inst_result.first():
            continue
        try:
            docker.remove_image(pulled.image)
        except Exception:
            pass
        await session.delete(pulled)

    await session.commit()
    return Response(status_code=204)
