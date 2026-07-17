"""健康检查 API"""

from fastapi import APIRouter
from config.settings import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "app": settings.APP_NAME,
    }