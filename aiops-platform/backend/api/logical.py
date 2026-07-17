"""逻辑资源层 API — 重构版

端点列表:
  # 业务IP对应关系
  GET    /logical/ip-mapping              - 列表（自动解析+手动，精确/模糊搜索）
  POST   /logical/ip-mapping              - 新增
  PUT    /logical/ip-mapping/{id}         - 更新
  DELETE /logical/ip-mapping/{id}         - 删除
  POST   /logical/ip-mapping/sync         - 从NAT自动同步（去重upsert）
  GET    /logical/ip-mapping/export        - 导出Excel
  POST   /logical/ip-mapping/import        - 导入Excel

  # 负载均衡对应关系
  GET    /logical/lb-mapping               - 列表
  POST   /logical/lb-mapping               - 新增
  PUT    /logical/lb-mapping/{id}          - 更新
  DELETE /logical/lb-mapping/{id}          - 删除
  POST   /logical/lb-mapping/sync          - 从LB表自动同步
  GET    /logical/lb-mapping/export         - 导出Excel
  POST   /logical/lb-mapping/import         - 导入Excel

  # 通用CRUD (interfaces, ips)
  GET    /logical/{table_name}             - 列表
  POST   /logical/{table_name}             - 新增
  PUT    /logical/{table_name}/{id}        - 更新
  DELETE /logical/{table_name}/{id}        - 删除
  GET    /logical/{table_name}/export       - 导出Excel
  POST   /logical/{table_name}/import       - 导入Excel

  # 列元数据
  GET    /logical/meta/{table_name}        - 获取列定义
  POST   /logical/meta/{table_name}        - 新增自定义列
  PUT    /logical/meta/{table_name}/{id}   - 修改列配置
  DELETE /logical/meta/{table_name}/{id}   - 删除自定义列
"""

import io
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy import select, func, or_, text
from sqlalchemy import inspect as sa_inspect

from api.auth import get_current_user
from core.db import async_session_factory
from models.netinsight import (
    NetConfigInterface, NetConfigIP,
    NetConfigNAT,
    NetConfigLBServerFarm, NetConfigLBRealServer, NetConfigLBVirtualServer,
    LogicalTableColumn, LogicalTableCustomData,
    IpMappingRelation, LbMappingRelation,
)

router = APIRouter()

# ========================================================================
#  表名白名单（仅保留 interfaces + ips）
# ========================================================================

TABLE_REGISTRY = {
    "interfaces": NetConfigInterface,
    "ips": NetConfigIP,
}

SEARCH_FIELDS = {
    "interfaces": ["interface_name", "description", "device_ip", "interface_type"],
    "ips": ["ip_address", "device_ip", "interface_name", "ip_type", "vrf"],
}

# IP映射/负载均衡 搜索字段
IP_MAPPING_SEARCH_FIELDS = ["external_ip", "internal_ip", "protocol", "vpn_instance", "business"]
LB_MAPPING_SEARCH_FIELDS = ["vip", "backend_ip", "protocol", "vpn_instance", "business"]


def _get_model(table_name: str):
    model = TABLE_REGISTRY.get(table_name)
    if not model:
        raise HTTPException(status_code=400, detail=f"不支持的表: {table_name}")
    return model


def _model_to_dict(obj) -> dict:
    d = {}
    for c in obj.__table__.columns:
        val = getattr(obj, c.name, None)
        if hasattr(val, "isoformat"):
            val = val.isoformat()
        d[c.name] = val
    return d


def _apply_search(query, model, fields, keyword, search_type="fuzzy"):
    """通用搜索：fuzzy=LIKE, exact=精确匹配"""
    if not keyword:
        return query
    if search_type == "exact":
        filters = []
        for f in fields:
            col = getattr(model, f, None)
            if col is not None:
                filters.append(col == keyword)
        return query.where(or_(*filters)) if filters else query
    else:
        kw = f"%{keyword}%"
        filters = []
        for f in fields:
            col = getattr(model, f, None)
            if col is not None:
                filters.append(col.like(kw))
        return query.where(or_(*filters)) if filters else query


# ========================================================================
#  Excel 导出/导入 工具函数
# ========================================================================

async def _get_columns_for_export(table_name: str) -> list:
    """获取表的可见列定义"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(LogicalTableColumn)
            .where(LogicalTableColumn.table_name == table_name, LogicalTableColumn.visible == True)
            .order_by(LogicalTableColumn.sort_order, LogicalTableColumn.id)
        )
        return result.scalars().all()


def _export_excel(records: list, columns: list, sheet_name: str = "Sheet1"):
    """生成 Excel 文件并返回 StreamingResponse"""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    # 表头：序号 + 各字段
    headers = ["序号"] + [c.label for c in columns]
    ws.append(headers)

    # 数据行
    for idx, record in enumerate(records, 1):
        row = [idx]
        for col in columns:
            val = record.get(col.field_name) if isinstance(record, dict) else getattr(record, col.field_name, None)
            if val is None:
                val = ""
            row.append(val)
        ws.append(row)

    # 列宽
    ws.column_dimensions["A"].width = 6
    for i, col in enumerate(columns, 2):
        ws.column_dimensions[chr(64 + i) if i <= 26 else "A"].width = max(12, min(40, (col.width or 120) // 5))

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    from urllib.parse import quote
    filename = quote(sheet_name)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}.xlsx"},
    )


# ========================================================================
#  地址映射 API（必须在 /logical/{table_name} 前定义）
# ========================================================================

IP_MAPPING_COLUMNS = [
    ("external_ip", "外网IP"),
    ("external_port", "外网端口"),
    ("protocol", "协议"),
    ("vpn_instance", "VPN实例"),
    ("internal_ip", "内网IP"),
    ("internal_port", "内网端口"),
    ("business", "业务"),
    ("remarks", "备注"),
]

IP_MAPPING_HEADER_MAP = {v: k for k, v in IP_MAPPING_COLUMNS}


@router.get("/logical/ip-mapping")
async def list_ip_mapping(
    page: int = 1,
    page_size: int = 50,
    keyword: Optional[str] = None,
    search_type: str = "fuzzy",
    source: Optional[str] = None,
    auth=Depends(get_current_user),
):
    """地址映射列表"""
    async with async_session_factory() as session:
        query = select(IpMappingRelation)

        if source:
            query = query.where(IpMappingRelation.source == source)

        if keyword:
            query = _apply_search(query, IpMappingRelation, IP_MAPPING_SEARCH_FIELDS, keyword, search_type)

        count_q = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_q)).scalar()

        query = query.order_by(IpMappingRelation.id.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(query)
        items = [_model_to_dict(m) for m in result.scalars().all()]

        return {"total": total, "page": page, "page_size": page_size, "items": items}


class IpMappingCreate(BaseModel):
    external_ip: Optional[str] = None
    external_port: Optional[int] = None
    protocol: Optional[str] = None
    vpn_instance: Optional[str] = None
    internal_ip: Optional[str] = None
    internal_port: Optional[int] = None
    business: Optional[str] = None
    remarks: Optional[str] = None


@router.post("/logical/ip-mapping")
async def create_ip_mapping(body: IpMappingCreate, auth=Depends(get_current_user)):
    """新增IP映射（手动）"""
    async with async_session_factory() as session:
        data = body.model_dump(exclude_unset=True)
        data["source"] = "manual"
        if data.get("external_ip"):
            proto = data.get("protocol") or ""
            port = data.get("external_port") if data.get("external_port") is not None else ""
            data["source_key"] = f"{data['external_ip']}:{port}:{proto}"
        record = IpMappingRelation(**data)
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return _model_to_dict(record)


@router.put("/logical/ip-mapping/{record_id}")
async def update_ip_mapping(record_id: int, body: IpMappingCreate, auth=Depends(get_current_user)):
    """更新IP映射（可编辑业务/备注等）"""
    async with async_session_factory() as session:
        result = await session.execute(select(IpMappingRelation).where(IpMappingRelation.id == record_id))
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="记录不存在")

        update_data = body.model_dump(exclude_unset=True)
        if "external_ip" in update_data:
            proto = update_data.get("protocol") or ""
            port = update_data.get("external_port") if update_data.get("external_port") is not None else ""
            update_data["source_key"] = f"{update_data['external_ip']}:{port}:{proto}"
        for k, v in update_data.items():
            setattr(record, k, v)
        await session.commit()
        await session.refresh(record)
        return _model_to_dict(record)


@router.delete("/logical/ip-mapping/{record_id}")
async def delete_ip_mapping(record_id: int, auth=Depends(get_current_user)):
    async with async_session_factory() as session:
        result = await session.execute(select(IpMappingRelation).where(IpMappingRelation.id == record_id))
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="记录不存在")
        await session.delete(record)
        await session.commit()
        return {"message": "已删除"}


@router.post("/logical/ip-mapping/sync")
async def sync_ip_mapping(auth=Depends(get_current_user)):
    """从NAT表自动同步（去重upsert，保留已编辑的business/remarks）"""
    async with async_session_factory() as session:
        sql = text("""
            INSERT INTO ip_mapping_relations
                (external_ip, external_port, protocol, vpn_instance, internal_ip, internal_port,
                 business, remarks, source, source_key, device_ip)
            SELECT
                dedup.global_ip, dedup.global_port, dedup.protocol,
                NULL as vpn_instance,
                dedup.local_ip, dedup.local_port,
                '' as business, '' as remarks,
                'auto' as source,
                CONCAT(dedup.global_ip, ':', IFNULL(dedup.global_port, ''), ':', IFNULL(dedup.protocol, '')) as source_key,
                dedup.device_ip
            FROM (
                SELECT DISTINCT global_ip, global_port, protocol, local_ip, local_port, device_ip
                FROM net_config_nat
                WHERE global_ip IS NOT NULL
            ) dedup
            ON DUPLICATE KEY UPDATE
                protocol = VALUES(protocol),
                internal_ip = VALUES(internal_ip),
                internal_port = VALUES(internal_port),
                device_ip = VALUES(device_ip),
                source = 'auto'
        """)
        await session.execute(sql)
        await session.commit()

        count_q = select(func.count()).select_from(IpMappingRelation)
        total = (await session.execute(count_q)).scalar()
        return {"message": "同步完成", "total": total}


@router.get("/logical/ip-mapping/export")
async def export_ip_mapping(auth=Depends(get_current_user)):
    """导出Excel"""
    async with async_session_factory() as session:
        result = await session.execute(select(IpMappingRelation).order_by(IpMappingRelation.id))
        records = [_model_to_dict(m) for m in result.scalars().all()]
        columns = await _get_columns_for_export("ip_mapping")
        if not columns:
            from types import SimpleNamespace
            columns = [SimpleNamespace(field_name=f, label=l, width=120) for f, l in IP_MAPPING_COLUMNS]
        return _export_excel(records, columns, "地址映射")


@router.post("/logical/ip-mapping/import")
async def import_ip_mapping(file: UploadFile = File(...), auth=Depends(get_current_user)):
    """导入Excel"""
    from openpyxl import load_workbook

    content = await file.read()
    wb = load_workbook(io.BytesIO(content), read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="Excel为空或仅有表头")

    header_row = [str(c).strip() if c else "" for c in rows[0]]
    field_indices = {}
    for idx, h in enumerate(header_row):
        if h in IP_MAPPING_HEADER_MAP:
            field_indices[IP_MAPPING_HEADER_MAP[h]] = idx

    if not field_indices:
        raise HTTPException(status_code=400, detail="未找到匹配的表头列")

    created, updated, failed = 0, 0, 0
    async with async_session_factory() as session:
        for row in rows[1:]:
            try:
                data = {}
                for field, col_idx in field_indices.items():
                    val = row[col_idx] if col_idx < len(row) else None
                    if val is not None and str(val).strip() != "":
                        data[field] = str(val).strip() if not isinstance(val, (int, float)) else int(val)

                if not data.get("external_ip"):
                    failed += 1
                    continue

                data["source"] = "manual"
                port = data.get("external_port")
                proto = data.get("protocol") or ""
                data["source_key"] = f"{data['external_ip']}:{port if port is not None else ''}:{proto}"

                existing = await session.execute(
                    select(IpMappingRelation).where(IpMappingRelation.source_key == data["source_key"])
                )
                record = existing.scalar_one_or_none()

                if record:
                    for k, v in data.items():
                        setattr(record, k, v)
                    updated += 1
                else:
                    session.add(IpMappingRelation(**data))
                    created += 1
            except Exception:
                failed += 1

        await session.commit()

    return {"created": created, "updated": updated, "failed": failed}


# ========================================================================
#  负载均衡对应关系 API
# ========================================================================

LB_MAPPING_COLUMNS = [
    ("vip", "VIP"),
    ("vip_port", "VIP端口"),
    ("protocol", "协议"),
    ("vpn_instance", "VPN实例"),
    ("backend_ip", "后端IP"),
    ("backend_port", "后端IP端口"),
    ("business", "业务"),
    ("remarks", "备注"),
]

LB_MAPPING_HEADER_MAP = {v: k for k, v in LB_MAPPING_COLUMNS}


@router.get("/logical/lb-mapping")
async def list_lb_mapping(
    page: int = 1,
    page_size: int = 50,
    keyword: Optional[str] = None,
    search_type: str = "fuzzy",
    source: Optional[str] = None,
    auth=Depends(get_current_user),
):
    """负载均衡对应关系列表"""
    async with async_session_factory() as session:
        query = select(LbMappingRelation)

        if source:
            query = query.where(LbMappingRelation.source == source)

        if keyword:
            query = _apply_search(query, LbMappingRelation, LB_MAPPING_SEARCH_FIELDS, keyword, search_type)

        count_q = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_q)).scalar()

        query = query.order_by(LbMappingRelation.id.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(query)
        items = [_model_to_dict(m) for m in result.scalars().all()]

        return {"total": total, "page": page, "page_size": page_size, "items": items}


class LbMappingCreate(BaseModel):
    vip: Optional[str] = None
    vip_port: Optional[int] = None
    protocol: Optional[str] = None
    vpn_instance: Optional[str] = None
    backend_ip: Optional[str] = None
    backend_port: Optional[str] = None
    business: Optional[str] = None
    remarks: Optional[str] = None


@router.post("/logical/lb-mapping")
async def create_lb_mapping(body: LbMappingCreate, auth=Depends(get_current_user)):
    async with async_session_factory() as session:
        data = body.model_dump(exclude_unset=True)
        data["source"] = "manual"
        if data.get("vip"):
            proto = data.get("protocol") or ""
            port = data.get("vip_port") if data.get("vip_port") is not None else ""
            data["source_key"] = f"{data['vip']}:{port}:{proto}"
        record = LbMappingRelation(**data)
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return _model_to_dict(record)


@router.put("/logical/lb-mapping/{record_id}")
async def update_lb_mapping(record_id: int, body: LbMappingCreate, auth=Depends(get_current_user)):
    async with async_session_factory() as session:
        result = await session.execute(select(LbMappingRelation).where(LbMappingRelation.id == record_id))
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="记录不存在")

        update_data = body.model_dump(exclude_unset=True)
        if "vip" in update_data:
            proto = update_data.get("protocol") or ""
            port = update_data.get("vip_port") if update_data.get("vip_port") is not None else ""
            update_data["source_key"] = f"{update_data['vip']}:{port}:{proto}"
        for k, v in update_data.items():
            setattr(record, k, v)
        await session.commit()
        await session.refresh(record)
        return _model_to_dict(record)


@router.delete("/logical/lb-mapping/{record_id}")
async def delete_lb_mapping(record_id: int, auth=Depends(get_current_user)):
    async with async_session_factory() as session:
        result = await session.execute(select(LbMappingRelation).where(LbMappingRelation.id == record_id))
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="记录不存在")
        await session.delete(record)
        await session.commit()
        return {"message": "已删除"}


@router.post("/logical/lb-mapping/sync")
async def sync_lb_mapping(auth=Depends(get_current_user)):
    """从LB三表自动同步（去重upsert，保留已编辑的business/remarks）"""
    async with async_session_factory() as session:
        sql = text("""
            INSERT INTO lb_mapping_relations
                (vip, vip_port, protocol, vpn_instance, backend_ip, backend_port,
                 business, remarks, source, source_key, device_ip)
            SELECT
                vs_dedup.virtual_ip, vs_dedup.port,
                vs_dedup.server_type as protocol,
                MIN(vs_dedup.vpn_instance) as vpn_instance,
                GROUP_CONCAT(DISTINCT rs.ip_address) as backend_ip,
                GROUP_CONCAT(DISTINCT rs.port) as backend_port,
                '' as business, '' as remarks,
                'auto' as source,
                CONCAT(vs_dedup.virtual_ip, ':', IFNULL(vs_dedup.port, ''), ':', IFNULL(vs_dedup.server_type, '')) as source_key,
                MIN(vs_dedup.device_ip) as device_ip
            FROM (
                SELECT DISTINCT virtual_ip, port, server_type, vpn_instance, default_server_farm, device_ip
                FROM net_config_lb_virtual_servers
                WHERE virtual_ip IS NOT NULL
            ) vs_dedup
            LEFT JOIN net_config_lb_server_farms sf
                ON sf.farm_id = vs_dedup.default_server_farm AND sf.device_ip = vs_dedup.device_ip
            LEFT JOIN net_config_lb_real_servers rs
                ON rs.server_farm_id = sf.farm_id AND rs.device_ip = sf.device_ip
            GROUP BY vs_dedup.virtual_ip, vs_dedup.port, vs_dedup.server_type
            ON DUPLICATE KEY UPDATE
                protocol = VALUES(protocol),
                vpn_instance = VALUES(vpn_instance),
                backend_ip = VALUES(backend_ip),
                backend_port = VALUES(backend_port),
                device_ip = VALUES(device_ip),
                source = 'auto'
        """)
        await session.execute(sql)
        await session.commit()

        count_q = select(func.count()).select_from(LbMappingRelation)
        total = (await session.execute(count_q)).scalar()
        return {"message": "同步完成", "total": total}


@router.get("/logical/lb-mapping/export")
async def export_lb_mapping(auth=Depends(get_current_user)):
    async with async_session_factory() as session:
        result = await session.execute(select(LbMappingRelation).order_by(LbMappingRelation.id))
        records = [_model_to_dict(m) for m in result.scalars().all()]
        columns = await _get_columns_for_export("lb_mapping")
        if not columns:
            from types import SimpleNamespace
            columns = [SimpleNamespace(field_name=f, label=l, width=120) for f, l in LB_MAPPING_COLUMNS]
        return _export_excel(records, columns, "负载均衡")


@router.post("/logical/lb-mapping/import")
async def import_lb_mapping(file: UploadFile = File(...), auth=Depends(get_current_user)):
    from openpyxl import load_workbook

    content = await file.read()
    wb = load_workbook(io.BytesIO(content), read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="Excel为空或仅有表头")

    header_row = [str(c).strip() if c else "" for c in rows[0]]
    field_indices = {}
    for idx, h in enumerate(header_row):
        if h in LB_MAPPING_HEADER_MAP:
            field_indices[LB_MAPPING_HEADER_MAP[h]] = idx

    if not field_indices:
        raise HTTPException(status_code=400, detail="未找到匹配的表头列")

    created, updated, failed = 0, 0, 0
    async with async_session_factory() as session:
        for row in rows[1:]:
            try:
                data = {}
                for field, col_idx in field_indices.items():
                    val = row[col_idx] if col_idx < len(row) else None
                    if val is not None and str(val).strip() != "":
                        data[field] = str(val).strip() if not isinstance(val, (int, float)) else int(val)

                if not data.get("vip"):
                    failed += 1
                    continue

                data["source"] = "manual"
                port = data.get("vip_port")
                proto = data.get("protocol") or ""
                data["source_key"] = f"{data['vip']}:{port if port is not None else ''}:{proto}"

                existing = await session.execute(
                    select(LbMappingRelation).where(LbMappingRelation.source_key == data["source_key"])
                )
                record = existing.scalar_one_or_none()

                if record:
                    for k, v in data.items():
                        setattr(record, k, v)
                    updated += 1
                else:
                    session.add(LbMappingRelation(**data))
                    created += 1
            except Exception:
                failed += 1

        await session.commit()

    return {"created": created, "updated": updated, "failed": failed}


# ========================================================================
#  通用 CRUD（interfaces, ips）
# ========================================================================

@router.get("/logical/{table_name}")
async def list_records(
    table_name: str,
    page: int = 1,
    page_size: int = 50,
    keyword: Optional[str] = None,
    search_type: str = "fuzzy",
    device_ip: Optional[str] = None,
    auth=Depends(get_current_user),
):
    """分页列表 + 搜索"""
    Model = _get_model(table_name)
    async with async_session_factory() as session:
        query = select(Model)

        if keyword:
            fields = SEARCH_FIELDS.get(table_name, [])
            query = _apply_search(query, Model, fields, keyword, search_type)

        if device_ip and hasattr(Model, "device_ip"):
            query = query.where(Model.device_ip == device_ip)

        count_q = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_q)).scalar()

        query = query.order_by(Model.id.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(query)
        items = result.scalars().all()

        records = []
        if items:
            record_ids = [item.id for item in items]
            custom_q = select(LogicalTableCustomData).where(
                LogicalTableCustomData.table_name == table_name,
                LogicalTableCustomData.record_id.in_(record_ids),
            )
            custom_result = await session.execute(custom_q)
            custom_map = {c.record_id: c.custom_fields for c in custom_result.scalars().all()}

            for item in items:
                d = _model_to_dict(item)
                custom = custom_map.get(item.id)
                if custom:
                    d["_custom_fields"] = custom
                records.append(d)

        return {"total": total, "page": page, "page_size": page_size, "items": records}


class DynamicRecordCreate(BaseModel):
    data: dict


@router.post("/logical/{table_name}")
async def create_record(table_name: str, body: DynamicRecordCreate, auth=Depends(get_current_user)):
    Model = _get_model(table_name)
    async with async_session_factory() as session:
        model_columns = {c.name for c in Model.__table__.columns}
        builtin = {}
        custom = {}
        for k, v in body.data.items():
            if k in model_columns and k not in ("id", "created_at", "updated_at"):
                builtin[k] = v
            elif k not in ("id", "created_at", "updated_at"):
                custom[k] = v

        record = Model(**builtin)
        session.add(record)
        await session.flush()

        if custom:
            session.add(LogicalTableCustomData(table_name=table_name, record_id=record.id, custom_fields=custom))

        await session.commit()
        await session.refresh(record)
        return _model_to_dict(record)


@router.put("/logical/{table_name}/{record_id}")
async def update_record(table_name: str, record_id: int, body: DynamicRecordCreate, auth=Depends(get_current_user)):
    Model = _get_model(table_name)
    async with async_session_factory() as session:
        result = await session.execute(select(Model).where(Model.id == record_id))
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="记录不存在")

        model_columns = {c.name for c in Model.__table__.columns}
        custom = {}
        for k, v in body.data.items():
            if k in model_columns and k not in ("id", "created_at", "updated_at"):
                setattr(record, k, v)
            elif k not in ("id", "created_at", "updated_at"):
                custom[k] = v

        if custom:
            cd_result = await session.execute(
                select(LogicalTableCustomData).where(
                    LogicalTableCustomData.table_name == table_name,
                    LogicalTableCustomData.record_id == record_id,
                )
            )
            cd = cd_result.scalar_one_or_none()
            if cd:
                existing = cd.custom_fields or {}
                existing.update(custom)
                cd.custom_fields = existing
            else:
                session.add(LogicalTableCustomData(table_name=table_name, record_id=record_id, custom_fields=custom))

        await session.commit()
        await session.refresh(record)
        return _model_to_dict(record)


@router.delete("/logical/{table_name}/{record_id}")
async def delete_record(table_name: str, record_id: int, auth=Depends(get_current_user)):
    Model = _get_model(table_name)
    async with async_session_factory() as session:
        result = await session.execute(select(Model).where(Model.id == record_id))
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="记录不存在")

        await session.execute(
            text("DELETE FROM logical_table_custom_data WHERE table_name = :tn AND record_id = :rid"),
            {"tn": table_name, "rid": record_id},
        )
        await session.delete(record)
        await session.commit()
        return {"message": "已删除"}


@router.get("/logical/{table_name}/export")
async def export_generic(table_name: str, auth=Depends(get_current_user)):
    """通用导出Excel"""
    Model = _get_model(table_name)
    async with async_session_factory() as session:
        result = await session.execute(select(Model).order_by(Model.id))
        records = [_model_to_dict(m) for m in result.scalars().all()]
        columns = await _get_columns_for_export(table_name)
        if not columns:
            raise HTTPException(status_code=400, detail=f"表 {table_name} 无列元数据")
        labels = {"interfaces": "接口信息", "ips": "IP地址"}
        return _export_excel(records, columns, labels.get(table_name, table_name))


@router.post("/logical/{table_name}/import")
async def import_generic(table_name: str, file: UploadFile = File(...), auth=Depends(get_current_user)):
    """通用导入Excel"""
    Model = _get_model(table_name)
    from openpyxl import load_workbook

    content = await file.read()
    wb = load_workbook(io.BytesIO(content), read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="Excel为空或仅有表头")

    # 从列元数据获取 header→field 映射
    columns = await _get_columns_for_export(table_name)
    header_map = {c.label: c.field_name for c in columns}

    header_row = [str(c).strip() if c else "" for c in rows[0]]
    field_indices = {}
    for idx, h in enumerate(header_row):
        if h in header_map:
            field_indices[header_map[h]] = idx

    if not field_indices:
        raise HTTPException(status_code=400, detail="未找到匹配的表头列")

    model_columns = {c.name for c in Model.__table__.columns}
    created, updated, failed = 0, 0, 0
    async with async_session_factory() as session:
        for row in rows[1:]:
            try:
                data = {}
                for field, col_idx in field_indices.items():
                    val = row[col_idx] if col_idx < len(row) else None
                    if val is not None and str(val).strip() != "":
                        if field in model_columns:
                            col_type = next((c.column_type for c in columns if c.field_name == field), "text")
                            if col_type == "number":
                                try:
                                    data[field] = int(val)
                                except (ValueError, TypeError):
                                    data[field] = str(val)
                            else:
                                data[field] = str(val).strip()
                        else:
                            data[field] = str(val).strip()

                if not data:
                    failed += 1
                    continue

                # 按 device_ip + 第一个搜索字段 做简单 upsert
                search_fields = SEARCH_FIELDS.get(table_name, [])
                upsert_key_field = search_fields[0] if search_fields else None

                if upsert_key_field and data.get(upsert_key_field) and hasattr(Model, upsert_key_field):
                    col = getattr(Model, upsert_key_field)
                    existing = await session.execute(select(Model).where(col == data[upsert_key_field]))
                    record = existing.scalar_one_or_none()
                else:
                    record = None

                builtin = {k: v for k, v in data.items() if k in model_columns and k not in ("id", "created_at", "updated_at")}
                custom = {k: v for k, v in data.items() if k not in model_columns and k not in ("id", "created_at", "updated_at")}

                if record:
                    for k, v in builtin.items():
                        setattr(record, k, v)
                    updated += 1
                else:
                    record = Model(**builtin)
                    session.add(record)
                    await session.flush()
                    created += 1

                if custom:
                    cd_result = await session.execute(
                        select(LogicalTableCustomData).where(
                            LogicalTableCustomData.table_name == table_name,
                            LogicalTableCustomData.record_id == record.id,
                        )
                    )
                    cd = cd_result.scalar_one_or_none()
                    if cd:
                        existing_custom = cd.custom_fields or {}
                        existing_custom.update(custom)
                        cd.custom_fields = existing_custom
                    else:
                        session.add(LogicalTableCustomData(table_name=table_name, record_id=record.id, custom_fields=custom))

            except Exception:
                failed += 1

        await session.commit()

    return {"created": created, "updated": updated, "failed": failed}


# ========================================================================
#  表元数据 API（动态字段管理）
# ========================================================================

@router.get("/logical/meta/{table_name}")
async def get_table_meta(table_name: str, auth=Depends(get_current_user)):
    """获取表的列定义"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(LogicalTableColumn)
            .where(LogicalTableColumn.table_name == table_name)
            .order_by(LogicalTableColumn.sort_order, LogicalTableColumn.id)
        )
        columns = result.scalars().all()
        return {
            "table_name": table_name,
            "columns": [
                {
                    "id": c.id,
                    "field_name": c.field_name,
                    "label": c.label,
                    "column_type": c.column_type,
                    "width": c.width,
                    "visible": c.visible,
                    "sort_order": c.sort_order,
                    "is_custom": c.is_custom,
                    "select_options": c.select_options,
                }
                for c in columns
            ],
        }


class ColumnMetaCreate(BaseModel):
    field_name: str
    label: str
    column_type: str = "text"
    width: int = 120
    visible: bool = True
    select_options: Optional[str] = None


@router.post("/logical/meta/{table_name}")
async def create_column_meta(table_name: str, body: ColumnMetaCreate, auth=Depends(get_current_user)):
    async with async_session_factory() as session:
        existing = await session.execute(
            select(LogicalTableColumn).where(
                LogicalTableColumn.table_name == table_name,
                LogicalTableColumn.field_name == body.field_name,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"字段 {body.field_name} 已存在")

        max_order = await session.execute(
            select(func.max(LogicalTableColumn.sort_order)).where(LogicalTableColumn.table_name == table_name)
        )
        next_order = (max_order.scalar() or 0) + 1

        col = LogicalTableColumn(
            table_name=table_name,
            field_name=body.field_name,
            label=body.label,
            column_type=body.column_type,
            width=body.width,
            visible=body.visible,
            sort_order=next_order,
            is_custom=True,
            select_options=body.select_options,
        )
        session.add(col)
        await session.commit()
        await session.refresh(col)
        return {"id": col.id, "message": "自定义列已添加"}


class ColumnMetaUpdate(BaseModel):
    label: Optional[str] = None
    column_type: Optional[str] = None
    width: Optional[int] = None
    visible: Optional[bool] = None
    sort_order: Optional[int] = None
    select_options: Optional[str] = None


@router.put("/logical/meta/{table_name}/{col_id}")
async def update_column_meta(table_name: str, col_id: int, body: ColumnMetaUpdate, auth=Depends(get_current_user)):
    async with async_session_factory() as session:
        result = await session.execute(
            select(LogicalTableColumn).where(
                LogicalTableColumn.id == col_id,
                LogicalTableColumn.table_name == table_name,
            )
        )
        col = result.scalar_one_or_none()
        if not col:
            raise HTTPException(status_code=404, detail="列不存在")

        update_data = body.model_dump(exclude_unset=True)
        for k, v in update_data.items():
            setattr(col, k, v)
        await session.commit()
        return {"message": "已更新"}


@router.delete("/logical/meta/{table_name}/{col_id}")
async def delete_column_meta(table_name: str, col_id: int, auth=Depends(get_current_user)):
    async with async_session_factory() as session:
        result = await session.execute(
            select(LogicalTableColumn).where(
                LogicalTableColumn.id == col_id,
                LogicalTableColumn.table_name == table_name,
            )
        )
        col = result.scalar_one_or_none()
        if not col:
            raise HTTPException(status_code=404, detail="列不存在")
        if not col.is_custom:
            raise HTTPException(status_code=400, detail="内置列不能删除")

        await session.delete(col)
        await session.commit()
        return {"message": "已删除"}
