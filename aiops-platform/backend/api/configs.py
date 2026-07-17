"""配置中心 API - 规则/数据源/大模型/告警渠道 CRUD"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
from core.db import async_session_factory
from models.rule import Rule, AlertStormConfig, AIAnalysisConfig
from models.datasource import Datasource
from models.llm_config import LLMConfig
from models.alert_channel import AlertChannel
from rule_engine.loader import rule_loader
from sqlalchemy import select

router = APIRouter()


# ===== 规则配置 CRUD =====

class RuleUpdate(BaseModel):
    """规则更新（所有字段可选）"""
    rule_name: Optional[str] = None
    skill_id: Optional[int] = None
    rule_type: Optional[str] = None
    match_condition: Optional[dict] = None
    exclude_condition: Optional[dict] = None
    risk_level: Optional[str] = None
    action_config: Optional[dict] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None


class RuleCreate(BaseModel):
    rule_name: str
    skill_id: int
    rule_type: str
    match_condition: dict
    exclude_condition: Optional[dict] = None
    risk_level: str = "medium"
    action_config: dict
    priority: int = 0
    enabled: bool = True


class RuleResponse(BaseModel):
    id: int
    rule_name: str
    skill_id: Optional[int] = None
    rule_type: str
    match_condition: Optional[dict] = None
    exclude_condition: Optional[dict] = None
    risk_level: str
    action_config: Optional[dict] = None
    priority: int
    enabled: int

    class Config:
        from_attributes = True


@router.get("/rules", response_model=list[RuleResponse])
async def list_rules(skill_id: Optional[int] = None):
    """获取规则列表"""
    async with async_session_factory() as session:
        query = select(Rule)
        if skill_id:
            query = query.where(Rule.skill_id == skill_id)
        query = query.order_by(Rule.priority)
        result = await session.execute(query)
        return result.scalars().all()


@router.post("/rules", response_model=RuleResponse)
async def create_rule(rule: RuleCreate):
    """创建规则"""
    async with async_session_factory() as session:
        new_rule = Rule(
            rule_name=rule.rule_name,
            skill_id=rule.skill_id,
            rule_type=rule.rule_type,
            match_condition=rule.match_condition,
            exclude_condition=rule.exclude_condition,
            risk_level=rule.risk_level,
            action_config=rule.action_config,
            priority=rule.priority,
            enabled=1 if rule.enabled else 0,
        )
        session.add(new_rule)
        await session.commit()
        await session.refresh(new_rule)

    # 刷新缓存
    await rule_loader.refresh_cache(rule.skill_id)
    return new_rule


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: int, rule: RuleUpdate):
    """更新规则"""
    async with async_session_factory() as session:
        result = await session.execute(select(Rule).where(Rule.id == rule_id))
        existing = result.scalar_one_or_none()
        if not existing:
            raise HTTPException(status_code=404, detail="规则不存在")

        update_data = rule.dict(exclude_unset=True)
        for key, value in update_data.items():
            if key == "enabled" and value is not None:
                value = 1 if value else 0
            if hasattr(existing, key):
                setattr(existing, key, value)
        await session.commit()

    await rule_loader.refresh_cache(rule.skill_id)
    return {"message": "更新成功"}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int):
    """删除规则"""
    async with async_session_factory() as session:
        result = await session.execute(select(Rule).where(Rule.id == rule_id))
        rule = result.scalar_one_or_none()
        if not rule:
            raise HTTPException(status_code=404, detail="规则不存在")
        skill_id = rule.skill_id
        await session.delete(rule)
        await session.commit()

    await rule_loader.refresh_cache(skill_id)
    return {"message": "删除成功"}


@router.post("/rules/refresh-cache")
async def refresh_rules_cache():
    """手动刷新规则缓存"""
    await rule_loader.refresh_cache()
    return {"message": "规则缓存已刷新"}


# ===== 通用序列化 =====

def _serialize(obj) -> dict:
    """将 ORM 对象转为可 JSON 序列化的字典"""
    if obj is None:
        return {}
    data = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    for k, v in list(data.items()):
        if hasattr(v, "isoformat"):
            data[k] = v.isoformat()
        # 枚举值
        if hasattr(v, "value"):
            data[k] = v.value
    return data


# ===== 数据源配置 CRUD =====

class DatasourceUpdate(BaseModel):
    name: Optional[str] = None
    ds_type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    extra_config: Optional[dict] = None
    enabled: Optional[bool] = None


@router.get("/datasources")
async def list_datasources():
    async with async_session_factory() as session:
        result = await session.execute(select(Datasource))
        return [_serialize(d) for d in result.scalars().all()]


@router.post("/datasources")
async def create_datasource(data: dict):
    async with async_session_factory() as session:
        ds = Datasource(**data)
        session.add(ds)
        await session.commit()
        await session.refresh(ds)
        return _serialize(ds)


@router.put("/datasources/{ds_id}")
async def update_datasource(ds_id: int, data: DatasourceUpdate):
    """更新数据源"""
    async with async_session_factory() as session:
        result = await session.execute(select(Datasource).where(Datasource.id == ds_id))
        existing = result.scalar_one_or_none()
        if not existing:
            raise HTTPException(status_code=404, detail="数据源不存在")
        for key, value in data.dict(exclude_unset=True).items():
            if key == "enabled" and value is not None:
                value = 1 if value else 0
            if hasattr(existing, key):
                setattr(existing, key, value)
        await session.commit()
        await session.refresh(existing)
        return _serialize(existing)


@router.delete("/datasources/{ds_id}")
async def delete_datasource(ds_id: int):
    """删除数据源"""
    async with async_session_factory() as session:
        result = await session.execute(select(Datasource).where(Datasource.id == ds_id))
        ds = result.scalar_one_or_none()
        if not ds:
            raise HTTPException(status_code=404, detail="数据源不存在")
        await session.delete(ds)
        await session.commit()
    return {"message": "删除成功"}


@router.post("/datasources/test")
async def test_datasource(data: dict):
    """连通性测试 - 使用传入参数（无需先保存）"""
    return await _do_datasource_test(data)


@router.post("/datasources/{ds_id}/test")
async def test_datasource_by_id(ds_id: int):
    """连通性测试 - 测试已保存的数据源"""
    async with async_session_factory() as session:
        result = await session.execute(select(Datasource).where(Datasource.id == ds_id))
        ds = result.scalar_one_or_none()
        if not ds:
            raise HTTPException(status_code=404, detail="数据源不存在")
        return await _do_datasource_test(_serialize(ds))


async def _do_datasource_test(data: dict) -> dict:
    """执行数据源连通性测试"""
    from core import connectivity

    ds_type = (data.get("ds_type") or "").lower()
    host = data.get("host", "")
    port = int(data.get("port") or 0)
    username = data.get("username")
    password = data.get("password")
    extra = data.get("extra_config") or {}

    if ds_type == "es":
        use_ssl = bool(extra.get("use_ssl", False))
        return await connectivity.test_elasticsearch(
            host, port, username, password, use_ssl
        )
    elif ds_type == "mysql":
        db = extra.get("database", "aiops")
        return await connectivity.test_mysql(host, port, username, password, db)
    elif ds_type == "redis":
        rdb = int(extra.get("db", 0))
        return await connectivity.test_redis(host, port, password, rdb)
    elif ds_type == "prometheus":
        use_ssl = bool(extra.get("use_ssl", False))
        return await connectivity.test_prometheus(host, port, username, password, use_ssl)
    raise HTTPException(status_code=400, detail=f"不支持的数据源类型: {ds_type}")


# ===== 大模型配置 CRUD =====

class LLMConfigUpdate(BaseModel):
    name: Optional[str] = None
    model_name: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    temperature: Optional[float] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None


@router.get("/llms")
async def list_llm_configs():
    async with async_session_factory() as session:
        result = await session.execute(select(LLMConfig))
        return [_serialize(c) for c in result.scalars().all()]


@router.post("/llms")
async def create_llm_config(data: dict):
    async with async_session_factory() as session:
        cfg = LLMConfig(**data)
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
        return _serialize(cfg)


@router.put("/llms/{llm_id}")
async def update_llm_config(llm_id: int, data: LLMConfigUpdate):
    """更新大模型配置"""
    async with async_session_factory() as session:
        result = await session.execute(select(LLMConfig).where(LLMConfig.id == llm_id))
        existing = result.scalar_one_or_none()
        if not existing:
            raise HTTPException(status_code=404, detail="大模型配置不存在")
        for key, value in data.dict(exclude_unset=True).items():
            if key == "enabled" and value is not None:
                value = 1 if value else 0
            if hasattr(existing, key):
                setattr(existing, key, value)
        await session.commit()
        await session.refresh(existing)
        return _serialize(existing)


@router.delete("/llms/{llm_id}")
async def delete_llm_config(llm_id: int):
    """删除大模型配置"""
    async with async_session_factory() as session:
        result = await session.execute(select(LLMConfig).where(LLMConfig.id == llm_id))
        cfg = result.scalar_one_or_none()
        if not cfg:
            raise HTTPException(status_code=404, detail="大模型配置不存在")
        await session.delete(cfg)
        await session.commit()
    return {"message": "删除成功"}


@router.post("/llms/test")
async def test_llm_config(data: dict):
    """连通性测试 - 使用传入参数"""
    from core import connectivity
    return await connectivity.test_llm(
        data.get("api_base", ""),
        data.get("api_key", ""),
        data.get("model_name", "qwen3"),
    )


@router.post("/llms/{llm_id}/test")
async def test_llm_config_by_id(llm_id: int):
    """连通性测试 - 测试已保存的配置"""
    from core import connectivity
    async with async_session_factory() as session:
        result = await session.execute(select(LLMConfig).where(LLMConfig.id == llm_id))
        cfg = result.scalar_one_or_none()
        if not cfg:
            raise HTTPException(status_code=404, detail="大模型配置不存在")
        return await connectivity.test_llm(cfg.api_base, cfg.api_key, cfg.model_name)


# ===== 告警渠道 CRUD =====

class AlertChannelUpdate(BaseModel):
    name: Optional[str] = None
    channel_type: Optional[str] = None
    config: Optional[dict] = None
    enabled: Optional[bool] = None


@router.get("/alerts")
async def list_alert_channels():
    async with async_session_factory() as session:
        result = await session.execute(select(AlertChannel))
        return [_serialize(c) for c in result.scalars().all()]


@router.post("/alerts")
async def create_alert_channel(data: dict):
    async with async_session_factory() as session:
        channel = AlertChannel(**data)
        session.add(channel)
        await session.commit()
        await session.refresh(channel)
        return _serialize(channel)


@router.put("/alerts/{channel_id}")
async def update_alert_channel(channel_id: int, data: AlertChannelUpdate):
    """更新告警渠道"""
    async with async_session_factory() as session:
        result = await session.execute(select(AlertChannel).where(AlertChannel.id == channel_id))
        existing = result.scalar_one_or_none()
        if not existing:
            raise HTTPException(status_code=404, detail="告警渠道不存在")
        for key, value in data.dict(exclude_unset=True).items():
            if key == "enabled" and value is not None:
                value = 1 if value else 0
            if hasattr(existing, key):
                setattr(existing, key, value)
        await session.commit()
        await session.refresh(existing)
        return _serialize(existing)


@router.delete("/alerts/{channel_id}")
async def delete_alert_channel(channel_id: int):
    """删除告警渠道"""
    async with async_session_factory() as session:
        result = await session.execute(select(AlertChannel).where(AlertChannel.id == channel_id))
        channel = result.scalar_one_or_none()
        if not channel:
            raise HTTPException(status_code=404, detail="告警渠道不存在")
        await session.delete(channel)
        await session.commit()
    return {"message": "删除成功"}


@router.post("/alerts/test")
async def test_alert_channel(data: dict):
    """连通性测试 - 使用传入参数"""
    return await _do_alert_test(data.get("channel_type", ""), data.get("config") or {})


@router.post("/alerts/{channel_id}/test")
async def test_alert_channel_by_id(channel_id: int):
    """连通性测试 - 测试已保存的渠道"""
    async with async_session_factory() as session:
        result = await session.execute(select(AlertChannel).where(AlertChannel.id == channel_id))
        channel = result.scalar_one_or_none()
        if not channel:
            raise HTTPException(status_code=404, detail="告警渠道不存在")
        ctype = channel.channel_type.value if hasattr(channel.channel_type, "value") else channel.channel_type
        cfg = channel.config or {}
        return await _do_alert_test(ctype, cfg)


async def _do_alert_test(channel_type: str, config: dict) -> dict:
    """执行告警渠道连通性测试"""
    from core import connectivity

    channel_type = (channel_type or "").lower()
    if channel_type == "dingtalk":
        return await connectivity.test_dingtalk(
            config.get("webhook_url", ""), config.get("secret")
        )
    elif channel_type == "email":
        return await connectivity.test_email(
            smtp_host=config.get("smtp_host", ""),
            smtp_port=int(config.get("smtp_port", 465)),
            smtp_user=config.get("smtp_user"),
            smtp_pass=config.get("smtp_pass"),
            from_addr=config.get("from_addr") or config.get("smtp_user"),
            to_addrs=config.get("to_addrs"),
            use_ssl=bool(config.get("use_ssl", True)),
        )
    elif channel_type == "webhook":
        return await connectivity.test_webhook(
            config.get("url", ""),
            config.get("method", "POST"),
            config.get("headers") or {},
        )
    raise HTTPException(status_code=400, detail=f"不支持的渠道类型: {channel_type}")