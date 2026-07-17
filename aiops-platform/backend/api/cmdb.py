"""CMDB IT资源管理 API — CRUD + Excel导入 + 同步接口"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from core.db import async_session_factory
from models.cmdb import CMDBAsset
from sqlalchemy import select, func, or_
import io

router = APIRouter()


# ========== Pydantic Models ==========

class AssetCreate(BaseModel):
    asset_code: str
    name: str
    asset_type: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    ip_address: Optional[str] = None
    status: Optional[str] = "online"
    environment: Optional[str] = None
    region: Optional[str] = None
    datacenter: Optional[str] = None
    rack_info: Optional[str] = None
    organization: Optional[str] = None
    owner: Optional[str] = None
    warranty_info: Optional[str] = None
    remarks: Optional[str] = None


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    asset_type: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    ip_address: Optional[str] = None
    status: Optional[str] = None
    environment: Optional[str] = None
    region: Optional[str] = None
    datacenter: Optional[str] = None
    rack_info: Optional[str] = None
    organization: Optional[str] = None
    owner: Optional[str] = None
    warranty_info: Optional[str] = None
    remarks: Optional[str] = None


class AssetSync(BaseModel):
    """外部平台同步接口（预留）—— 支持批量 upsert"""
    assets: List[AssetCreate]
    source: str = "api_sync"


class AssetSyncResponse(BaseModel):
    created: int = 0
    updated: int = 0
    failed: int = 0
    errors: List[str] = []


# ========== Helper ==========

def _asset_to_dict(a: CMDBAsset) -> dict:
    return {
        "id": a.id,
        "asset_code": a.asset_code,
        "name": a.name,
        "asset_type": a.asset_type,
        "model": a.model,
        "serial_number": a.serial_number,
        "ip_address": a.ip_address,
        "status": a.status if a.status else "online",
        "environment": a.environment,
        "region": a.region,
        "datacenter": a.datacenter,
        "rack_info": a.rack_info,
        "organization": a.organization,
        "owner": a.owner,
        "warranty_info": a.warranty_info,
        "remarks": a.remarks,
        "source": a.source,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


# ========== CRUD ==========

@router.get("/cmdb/assets")
async def list_assets(
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    asset_type: Optional[str] = None,
    status: Optional[str] = None,
    environment: Optional[str] = None,
):
    """资产列表（分页+筛选+搜索）"""
    async with async_session_factory() as session:
        query = select(CMDBAsset)

        if keyword:
            kw = f"%{keyword}%"
            query = query.where(
                or_(
                    CMDBAsset.asset_code.like(kw),
                    CMDBAsset.name.like(kw),
                    CMDBAsset.ip_address.like(kw),
                    CMDBAsset.owner.like(kw),
                    CMDBAsset.serial_number.like(kw),
                )
            )
        if asset_type:
            query = query.where(CMDBAsset.asset_type == asset_type)
        if status:
            query = query.where(CMDBAsset.status == status)
        if environment:
            query = query.where(CMDBAsset.environment == environment)

        count_q = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_q)).scalar()

        query = query.order_by(CMDBAsset.id.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(query)
        items = result.scalars().all()

        return {"total": total, "page": page, "page_size": page_size, "items": [_asset_to_dict(a) for a in items]}


@router.post("/cmdb/assets")
async def create_asset(body: AssetCreate):
    """新增资产"""
    async with async_session_factory() as session:
        existing = await session.execute(
            select(CMDBAsset).where(CMDBAsset.asset_code == body.asset_code)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"资产编号 {body.asset_code} 已存在")

        asset = CMDBAsset(**body.model_dump(), source="manual")
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        return _asset_to_dict(asset)


@router.put("/cmdb/assets/{asset_id}")
async def update_asset(asset_id: int, body: AssetUpdate):
    """更新资产"""
    async with async_session_factory() as session:
        result = await session.execute(select(CMDBAsset).where(CMDBAsset.id == asset_id))
        asset = result.scalar_one_or_none()
        if not asset:
            raise HTTPException(status_code=404, detail="资产不存在")

        update_data = body.model_dump(exclude_unset=True)
        for k, v in update_data.items():
            setattr(asset, k, v)
        await session.commit()
        await session.refresh(asset)
        return _asset_to_dict(asset)


@router.delete("/cmdb/assets/{asset_id}")
async def delete_asset(asset_id: int):
    """删除资产"""
    async with async_session_factory() as session:
        result = await session.execute(select(CMDBAsset).where(CMDBAsset.id == asset_id))
        asset = result.scalar_one_or_none()
        if not asset:
            raise HTTPException(status_code=404, detail="资产不存在")
        await session.delete(asset)
        await session.commit()
        return {"message": "已删除"}


@router.get("/cmdb/assets/{asset_id}")
async def get_asset(asset_id: int):
    """获取单个资产详情"""
    async with async_session_factory() as session:
        result = await session.execute(select(CMDBAsset).where(CMDBAsset.id == asset_id))
        asset = result.scalar_one_or_none()
        if not asset:
            raise HTTPException(status_code=404, detail="资产不存在")
        return _asset_to_dict(asset)


# ========== Excel 导入 ==========

# Excel 表头映射（中文名 → 数据库字段名）
EXCEL_HEADER_MAP = {
    "编号": "asset_code",
    "名称": "name",
    "类型": "asset_type",
    "型号": "model",
    "序列号": "serial_number",
    "IP地址": "ip_address",
    "状态": "status",
    "环境": "environment",
    "区域": "region",
    "机房信息": "datacenter",
    "机柜信息": "rack_info",
    "组织归属": "organization",
    "负责人": "owner",
    "维保信息": "warranty_info",
    "备注": "remarks",
}

# 状态值映射
STATUS_MAP = {
    "在线": "online", "正常": "online", "online": "online",
    "离线": "offline", "offline": "offline",
    "维护中": "maintenance", "maintenance": "maintenance",
    "已报废": "decommissioned", "报废": "decommissioned", "decommissioned": "decommissioned",
}


@router.post("/cmdb/assets/import")
async def import_excel(file: UploadFile = File(...)):
    """Excel批量导入资产"""
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls 格式")

    try:
        from openpyxl import load_workbook
        content = await file.read()
        wb = load_workbook(io.BytesIO(content), read_only=True)
        ws = wb.active
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Excel解析失败: {str(e)}")

    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="Excel为空或仅有表头")

    # 解析表头
    header_row = [str(c).strip() if c else "" for c in rows[0]]
    field_indices = {}
    for idx, h in enumerate(header_row):
        if h in EXCEL_HEADER_MAP:
            field_indices[EXCEL_HEADER_MAP[h]] = idx

    if "asset_code" not in field_indices or "name" not in field_indices:
        raise HTTPException(status_code=400, detail="Excel表头必须包含「编号」和「名称」列")

    created = 0
    updated = 0
    failed = 0
    errors = []

    async with async_session_factory() as session:
        for row_idx, row in enumerate(rows[1:], start=2):
            try:
                data = {}
                for field, col_idx in field_indices.items():
                    val = row[col_idx] if col_idx < len(row) else None
                    data[field] = str(val).strip() if val is not None and str(val).strip() != "" else None

                if not data.get("asset_code") or not data.get("name"):
                    errors.append(f"第{row_idx}行: 编号和名称不能为空，已跳过")
                    failed += 1
                    continue

                # 状态映射
                if data.get("status"):
                    data["status"] = STATUS_MAP.get(data["status"], data["status"].lower())

                # Upsert: 按编号查找
                result = await session.execute(
                    select(CMDBAsset).where(CMDBAsset.asset_code == data["asset_code"])
                )
                existing = result.scalar_one_or_none()

                if existing:
                    for k, v in data.items():
                        if v is not None:
                            setattr(existing, k, v)
                    existing.source = "excel"
                    updated += 1
                else:
                    asset = CMDBAsset(**{k: v for k, v in data.items() if v is not None}, source="excel")
                    session.add(asset)
                    created += 1

            except Exception as e:
                errors.append(f"第{row_idx}行: {str(e)}")
                failed += 1

        await session.commit()

    return {"created": created, "updated": updated, "failed": failed, "errors": errors}


# ========== 同步接口（预留，供外部平台联动） ==========

@router.post("/cmdb/assets/sync", response_model=AssetSyncResponse)
async def sync_assets(body: AssetSync):
    """外部平台批量同步资产（upsert by asset_code）

    预留接口：后续其他CMDB平台、ITSM系统可通过此接口动态联动更新数据。
    - 按 asset_code 做 upsert
    - 已存在则更新，不存在则创建
    """
    created = 0
    updated = 0
    failed = 0
    errors = []

    async with async_session_factory() as session:
        for item in body.assets:
            try:
                result = await session.execute(
                    select(CMDBAsset).where(CMDBAsset.asset_code == item.asset_code)
                )
                existing = result.scalar_one_or_none()

                if existing:
                    update_data = item.model_dump(exclude={"asset_code"})
                    for k, v in update_data.items():
                        if v is not None:
                            setattr(existing, k, v)
                    existing.source = body.source
                    updated += 1
                else:
                    asset = CMDBAsset(**item.model_dump(), source=body.source)
                    session.add(asset)
                    created += 1
            except Exception as e:
                errors.append(f"编号 {item.asset_code}: {str(e)}")
                failed += 1

        await session.commit()

    return AssetSyncResponse(created=created, updated=updated, failed=failed, errors=errors)


# ========== 统计 ==========

@router.get("/cmdb/stats")
async def cmdb_stats():
    """资产统计概览"""
    async with async_session_factory() as session:
        total = (await session.execute(select(func.count(CMDBAsset.id)))).scalar()

        # 按类型统计
        type_stats = (await session.execute(
            select(CMDBAsset.asset_type, func.count(CMDBAsset.id)).group_by(CMDBAsset.asset_type)
        )).all()

        # 按状态统计
        status_stats = (await session.execute(
            select(CMDBAsset.status, func.count(CMDBAsset.id)).group_by(CMDBAsset.status)
        )).all()

        # 按环境统计
        env_stats = (await session.execute(
            select(CMDBAsset.environment, func.count(CMDBAsset.id)).group_by(CMDBAsset.environment)
        )).all()

        return {
            "total": total,
            "by_type": {r[0] or "未分类": r[1] for r in type_stats},
            "by_status": {r[0] or "未知": r[1] for r in status_stats},
            "by_environment": {r[0] or "未分类": r[1] for r in env_stats},
        }
