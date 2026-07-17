"""技能管理 API - CRUD"""

import json
from fastapi import APIRouter, Depends, HTTPException
from api.auth import get_current_user
from pydantic import BaseModel
from typing import Optional, List
from core.db import async_session_factory
from models.skill import Skill
from models.datasource import Datasource
from sqlalchemy import select, delete

router = APIRouter()


class SkillCreate(BaseModel):
    skill_name: str
    display_name: str
    description: Optional[str] = ""
    datasource_id: Optional[int] = None
    ds_type: str = "es"
    index_pattern: Optional[str] = None
    field_schema: Optional[str] = None
    query_filter: Optional[str] = None
    query_config: Optional[dict] = None
    prompt_template: str
    model: str = "qwen3"
    scan_interval_sec: int = 300
    keyword_matching: bool = True
    anomaly_detection: bool = False


class SkillUpdate(BaseModel):
    """技能更新（部分字段可选）"""
    skill_name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    datasource_id: Optional[int] = None
    ds_type: Optional[str] = None
    index_pattern: Optional[str] = None
    field_schema: Optional[str] = None
    query_filter: Optional[str] = None
    query_config: Optional[dict] = None
    prompt_template: Optional[str] = None
    model: Optional[str] = None
    scan_interval_sec: Optional[int] = None
    keyword_matching: Optional[bool] = None
    anomaly_detection: Optional[bool] = None
    enabled: Optional[bool] = None


class SkillResponse(BaseModel):
    id: int
    skill_name: str
    display_name: str
    description: Optional[str]
    datasource_id: Optional[int] = None
    ds_type: str = "es"
    index_pattern: Optional[str] = None
    field_schema: Optional[str] = None
    query_filter: Optional[str] = None
    query_config: Optional[dict] = None
    prompt_template: Optional[str] = None
    model: str
    scan_interval_sec: int = 300
    keyword_matching: int = 1
    anomaly_detection: int = 0
    enabled: int
    datasource_name: Optional[str] = None  # 关联数据源名称

    class Config:
        from_attributes = True


@router.get("/skills", response_model=list[SkillResponse])
async def list_skills(auth=Depends(get_current_user)):
    """获取技能列表（含数据源名称）"""
    async with async_session_factory() as session:
        result = await session.execute(select(Skill))
        skills = result.scalars().all()

        # 批量查询关联数据源名称
        ds_ids = [s.datasource_id for s in skills if s.datasource_id]
        ds_map = {}
        if ds_ids:
            ds_result = await session.execute(
                select(Datasource).where(Datasource.id.in_(ds_ids))
            )
            for ds in ds_result.scalars().all():
                ds_map[ds.id] = ds.name

        # 构建响应
        resp = []
        for s in skills:
            data = SkillResponse.model_validate(s)
            data.datasource_name = ds_map.get(s.datasource_id, None)
            resp.append(data)
        return resp


@router.post("/skills/register", response_model=SkillResponse)
async def register_skill(skill: SkillCreate, auth=Depends(get_current_user)):
    """注册新技能"""
    async with async_session_factory() as session:
        # 检查是否已存在
        existing = await session.execute(
            select(Skill).where(Skill.skill_name == skill.skill_name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="技能名称已存在")

        # 验证数据源关联
        if skill.datasource_id:
            ds_result = await session.execute(
                select(Datasource).where(Datasource.id == skill.datasource_id)
            )
            ds = ds_result.scalar_one_or_none()
            if not ds:
                raise HTTPException(status_code=400, detail="关联的数据源不存在")

        new_skill = Skill(
            skill_name=skill.skill_name,
            display_name=skill.display_name,
            description=skill.description,
            datasource_id=skill.datasource_id,
            ds_type=skill.ds_type,
            index_pattern=skill.index_pattern,
            field_schema=skill.field_schema,
            query_filter=skill.query_filter,
            query_config=skill.query_config,
            prompt_template=skill.prompt_template,
            model=skill.model,
            scan_interval_sec=skill.scan_interval_sec,
            keyword_matching=1 if skill.keyword_matching else 0,
            anomaly_detection=1 if skill.anomaly_detection else 0,
        )
        session.add(new_skill)
        await session.commit()
        await session.refresh(new_skill)
        return new_skill


@router.get("/skills/{skill_id}", response_model=SkillResponse)
async def get_skill(skill_id: int, auth=Depends(get_current_user)):
    """获取技能详情"""
    async with async_session_factory() as session:
        result = await session.execute(select(Skill).where(Skill.id == skill_id))
        skill = result.scalar_one_or_none()
        if not skill:
            raise HTTPException(status_code=404, detail="技能不存在")
        return skill


@router.put("/skills/{skill_id}", response_model=SkillResponse)
async def update_skill(skill_id: int, skill: SkillUpdate, auth=Depends(get_current_user)):
    """更新技能配置"""
    async with async_session_factory() as session:
        result = await session.execute(select(Skill).where(Skill.id == skill_id))
        existing = result.scalar_one_or_none()
        if not existing:
            raise HTTPException(status_code=404, detail="技能不存在")
        update_data = skill.dict(exclude_unset=True)
        # bool → int 转换（DB列为Integer）
        if "keyword_matching" in update_data:
            update_data["keyword_matching"] = 1 if update_data["keyword_matching"] else 0
        if "anomaly_detection" in update_data:
            update_data["anomaly_detection"] = 1 if update_data["anomaly_detection"] else 0
        if "enabled" in update_data:
            update_data["enabled"] = 1 if update_data["enabled"] else 0
        for key, value in update_data.items():
            if hasattr(existing, key):
                setattr(existing, key, value)
        await session.commit()
        await session.refresh(existing)
        return existing


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: int, auth=Depends(get_current_user)):
    """删除技能"""
    async with async_session_factory() as session:
        result = await session.execute(select(Skill).where(Skill.id == skill_id))
        skill = result.scalar_one_or_none()
        if not skill:
            raise HTTPException(status_code=404, detail="技能不存在")
        await session.delete(skill)
        await session.commit()
        return {"message": "删除成功"}


# ============================================================
# ES 字段说明（field_schema）管理
# ============================================================

class FieldItem(BaseModel):
    """单个ES字段定义"""
    name: str
    type: str = ""
    desc: str = ""
    example: str = ""


class FieldSchemaUpdate(BaseModel):
    """字段说明更新请求"""
    fields: List[FieldItem] = []


@router.get("/skills/{skill_id}/fields")
async def get_skill_fields(skill_id: int, auth=Depends(get_current_user)):
    """获取技能的ES字段说明"""
    async with async_session_factory() as session:
        result = await session.execute(select(Skill).where(Skill.id == skill_id))
        skill = result.scalar_one_or_none()
        if not skill:
            raise HTTPException(status_code=404, detail="技能不存在")
        if skill.field_schema:
            try:
                return json.loads(skill.field_schema)
            except json.JSONDecodeError:
                return []
        return []


@router.put("/skills/{skill_id}/fields")
async def update_skill_fields(skill_id: int, body: FieldSchemaUpdate, auth=Depends(get_current_user)):
    """更新技能的ES字段说明"""
    async with async_session_factory() as session:
        result = await session.execute(select(Skill).where(Skill.id == skill_id))
        skill = result.scalar_one_or_none()
        if not skill:
            raise HTTPException(status_code=404, detail="技能不存在")
        skill.field_schema = json.dumps(
            [f.dict() for f in body.fields], ensure_ascii=False
        )
        await session.commit()
        return {"message": "字段说明已更新", "count": len(body.fields)}