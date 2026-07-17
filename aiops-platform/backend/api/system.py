"""系统管理 API - 站点/主题等通用设置"""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config.settings import settings
from models.netinsight import SystemSetting

router = APIRouter()


DEFAULT_SITE = {
    "name": settings.APP_NAME,
    "logo": "",
    "favicon": "",
}

DEFAULT_THEME = {
    "primaryColor": "#409eff",
    "backgroundColor": "#f0f2f5",
    "sidebarColor": "#304156",
}


class SiteConfig(BaseModel):
    name: Optional[str] = None
    logo: Optional[str] = None
    favicon: Optional[str] = None


class ThemeConfig(BaseModel):
    primaryColor: Optional[str] = None
    backgroundColor: Optional[str] = None
    sidebarColor: Optional[str] = None


class SystemSettingsBody(BaseModel):
    site: Optional[SiteConfig] = None
    theme: Optional[ThemeConfig] = None


def _merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if v is not None:
            result[k] = v
    return result


@router.get("/system/settings")
async def get_system_settings():
    """读取系统站点与主题配置"""
    site_raw = await SystemSetting.get_value("site", "")
    theme_raw = await SystemSetting.get_value("theme", "")

    try:
        site = _merge(DEFAULT_SITE, json.loads(site_raw or "{}"))
    except Exception:
        site = dict(DEFAULT_SITE)

    try:
        theme = _merge(DEFAULT_THEME, json.loads(theme_raw or "{}"))
    except Exception:
        theme = dict(DEFAULT_THEME)

    return {"site": site, "theme": theme}


@router.put("/system/settings")
async def update_system_settings(body: SystemSettingsBody):
    """更新系统站点与主题配置"""
    if body.site is None and body.theme is None:
        raise HTTPException(status_code=400, detail="至少需要提供 site 或 theme 配置")

    if body.site is not None:
        current_raw = await SystemSetting.get_value("site", "")
        try:
            current = json.loads(current_raw or "{}")
        except Exception:
            current = {}
        updated = _merge(_merge(DEFAULT_SITE, current), body.site.dict(exclude_unset=True))
        await SystemSetting.set_value("site", json.dumps(updated, ensure_ascii=False))

    if body.theme is not None:
        current_raw = await SystemSetting.get_value("theme", "")
        try:
            current = json.loads(current_raw or "{}")
        except Exception:
            current = {}
        updated = _merge(_merge(DEFAULT_THEME, current), body.theme.dict(exclude_unset=True))
        await SystemSetting.set_value("theme", json.dumps(updated, ensure_ascii=False))

    return await get_system_settings()
