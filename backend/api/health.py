import httpx
from fastapi import APIRouter

from backend.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    settings = get_settings()
    ollama = "unavailable"
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(f"{settings.ollama_url}/api/tags")
            if response.is_success:
                ollama = "available"
    except httpx.HTTPError:
        pass
    return {"status": "ok", "ollama": ollama, "model": settings.model}
