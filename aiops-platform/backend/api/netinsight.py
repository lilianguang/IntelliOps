"""网络洞察 API - 配置管理 + AI 配置问答

端点列表:
  GET  /netinsight/configs          - 配置索引列表
  POST /netinsight/configs/scan     - 触发目录扫描
  POST /netinsight/configs/upload   - 上传配置文件
  GET  /netinsight/settings         - 获取系统设置
  PUT  /netinsight/settings         - 更新系统设置
  POST /netinsight/chat             - AI 配置问答（SSE 流式）
"""

import os
import json
import shutil
import re
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict

from api.auth import get_current_user
from netinsight.scanner import (
    scan_configs, list_configs, get_vendors, load_configs,
    get_source_path, get_workspace_path, parse_filename, VENDOR_DIR_MAP,
    get_config_content, delete_config,
)
from netinsight.version import commit_changes, list_file_versions, get_version_content
from netinsight.structured_sync import full_parse_all, parse_single_config, get_config_by_filename
from netinsight.structured_query import (
    search_ip, search_device_interfaces, search_device_config, search_vlan,
    search_route, search_nat, search_acl, search_bgp_peer,
    search_lb_by_ip, get_parsing_stats,
)
from models.netinsight import SystemSetting, NetConfig, IpMappingRelation, LbMappingRelation
from sqlalchemy import or_, select
from gateway.model_scheduler import model_scheduler
from core.llm_client import llm_client
from core.db import async_session_factory
from api.chat import _detect_intent

router = APIRouter()


# ====================================================================
#  工具函数
# ====================================================================

def _sse_frame(data: dict) -> str:
    """构建一帧 SSE 数据（与 chat.py 保持一致的协议）"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _human_filesize(size: int) -> str:
    """字节数 → 可读文件大小"""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.1f} MB"


# ====================================================================
#  配置管理端点
# ====================================================================

@router.get("/netinsight/configs")
async def api_list_configs(
    vendor: Optional[str] = None,
    region: Optional[str] = None,
    name: Optional[str] = None,
    auth=Depends(get_current_user),
):
    """获取配置索引列表（支持 vendor/region/name 筛选）"""
    configs = await list_configs(vendor=vendor, region=region, name=name)
    vendors = await get_vendors()
    return {
        "configs": configs,
        "vendors": vendors,
        "total": len(configs),
    }


@router.delete("/netinsight/configs/{config_id}")
async def api_delete_config(config_id: int, auth=Depends(get_current_user)):
    """删除配置备份记录及本地文件"""
    success = await delete_config(config_id)
    if not success:
        raise HTTPException(status_code=404, detail="配置不存在")
    return {"message": "已删除"}


@router.post("/netinsight/configs/scan")
async def api_scan_configs(auth=Depends(get_current_user)):
    """触发目录扫描，返回扫描统计"""
    result = await scan_configs()
    return result


class UploadConfigResponse(BaseModel):
    vendor: str
    ip: Optional[str] = None
    filename: Optional[str] = None


@router.post("/netinsight/configs/upload")
async def api_upload_config(
    file: UploadFile = File(...),
    vendor: str = Form(...),
    ip: Optional[str] = Form(None),
    auth=Depends(get_current_user),
):
    """上传单个配置文件到指定厂商目录（保存到可写工作区）

    文件名规范：优先使用传入的 ip 参数，其次尝试从原始文件名解析 IP。
    最终保存为 {ip}_running_YYYYMMDD_HHMMSS.cfg，确保扫描索引能正确识别。
    """
    workspace_path = await get_workspace_path()
    if not workspace_path:
        raise HTTPException(status_code=400, detail="未配置工作区路径")

    # 确定设备 IP
    original_name = file.filename or "uploaded.cfg"
    parsed = parse_filename(original_name)
    device_ip = (ip or "").strip()
    if not device_ip and parsed:
        device_ip = parsed["ip"]
    if not device_ip:
        raise HTTPException(
            status_code=400,
            detail="无法从文件名解析设备 IP，请在上传时填写 IP 地址，或按 'IP.cfg' / 'IP_running_日期.cfg' 格式命名文件"
        )

    # 确保厂商目录存在
    vendor_dir = os.path.join(workspace_path, vendor)
    os.makedirs(vendor_dir, exist_ok=True)

    # 统一命名为标准格式
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{device_ip}_running_{timestamp}.cfg"
    target = os.path.join(vendor_dir, filename)
    try:
        with open(target, "wb") as f:
            shutil.copyfileobj(file.file, f)
    finally:
        await file.close()

    # 触发重新扫描以更新索引（扫描内部会提交 Git 版本）
    scan_stats = await scan_configs()

    return {
        "message": "上传成功",
        "path": f"{vendor}/{filename}",
        "ip": device_ip,
        "scan": scan_stats,
    }


# ====================================================================
#  系统设置端点
# ====================================================================

@router.get("/netinsight/settings")
async def api_get_settings(auth=Depends(get_current_user)):
    """获取网络洞察相关设置"""
    return {
        "net_config_source_path": await get_source_path(),
        "net_config_workspace_path": await get_workspace_path(),
    }


class SettingsUpdate(BaseModel):
    net_config_base_path: Optional[str] = None
    net_config_workspace_path: Optional[str] = None


@router.put("/netinsight/settings")
async def api_update_settings(req: SettingsUpdate, auth=Depends(get_current_user)):
    """更新网络洞察设置"""
    if req.net_config_base_path is not None:
        await SystemSetting.set_value("net_config_base_path", req.net_config_base_path)
    if req.net_config_workspace_path is not None:
        await SystemSetting.set_value("net_config_workspace_path", req.net_config_workspace_path)
    return {"message": "设置已更新"}


# ====================================================================
#  配置内容 & 版本管理端点
# ====================================================================

@router.get("/netinsight/configs/{config_id}/content")
async def api_get_config_content(config_id: int, auth=Depends(get_current_user)):
    """获取单个配置文件的完整内容"""
    data = await get_config_content(config_id)
    if not data:
        raise HTTPException(status_code=404, detail="配置不存在")
    return data


@router.get("/netinsight/configs/{config_id}/versions")
async def api_get_config_versions(config_id: int, auth=Depends(get_current_user)):
    """获取单个配置文件的历史版本列表（最近 10 个）"""
    data = await get_config_content(config_id)
    if not data:
        raise HTTPException(status_code=404, detail="配置不存在")

    base_path = await get_workspace_path()
    versions = list_file_versions(base_path, data["file_path"], keep=10)
    return {"file_path": data["file_path"], "versions": versions}


@router.get("/netinsight/configs/{config_id}/versions/{commit_hash}")
async def api_get_version_content(
    config_id: int,
    commit_hash: str,
    auth=Depends(get_current_user),
):
    """获取配置文件在指定 Git 提交版本中的内容"""
    data = await get_config_content(config_id)
    if not data:
        raise HTTPException(status_code=404, detail="配置不存在")

    base_path = await get_workspace_path()
    content = get_version_content(base_path, data["file_path"], commit_hash)
    if content is None:
        raise HTTPException(status_code=404, detail="指定版本不存在")
    return {"commit": commit_hash, "content": content}


# ====================================================================
#  结构化配置查询端点
# ====================================================================

@router.get("/netinsight/search/ip")
async def api_search_ip(ip: str, auth=Depends(get_current_user)):
    """查询某个 IP 地址在所有配置中的出现位置"""
    return await search_ip(ip)


@router.get("/netinsight/search/interface")
async def api_search_interface(device_ip: str, auth=Depends(get_current_user)):
    """查询某台设备的所有接口信息"""
    return {"device_ip": device_ip, "interfaces": await search_device_interfaces(device_ip)}


@router.get("/netinsight/search/vlan")
async def api_search_vlan(vlan_id: int, auth=Depends(get_current_user)):
    """查询某个 VLAN 在哪些设备上存在"""
    return {"vlan_id": vlan_id, "devices": await search_vlan(vlan_id)}


@router.get("/netinsight/search/route")
async def api_search_route(
    destination: Optional[str] = None,
    next_hop: Optional[str] = None,
    auth=Depends(get_current_user),
):
    """查询路由（按目的网段或下一跳）"""
    return {"routes": await search_route(destination=destination, next_hop=next_hop)}


@router.get("/netinsight/search/nat")
async def api_search_nat(ip: Optional[str] = None, auth=Depends(get_current_user)):
    """查询 NAT 映射（按全局 IP 或内网 IP）"""
    return {"nat": await search_nat(ip=ip)}


@router.get("/netinsight/search/acl")
async def api_search_acl(
    name: Optional[str] = None,
    ip: Optional[str] = None,
    auth=Depends(get_current_user),
):
    """查询 ACL 规则"""
    return {"acls": await search_acl(acl_name=name, ip=ip)}


@router.get("/netinsight/search/bgp")
async def api_search_bgp(peer_ip: Optional[str] = None, auth=Depends(get_current_user)):
    """查询 BGP 邻居"""
    return {"bgp_peers": await search_bgp_peer(peer_ip=peer_ip)}


@router.get("/netinsight/stats/parsing")
async def api_parsing_stats(auth=Depends(get_current_user)):
    """获取结构化解析统计"""
    return await get_parsing_stats()


@router.post("/netinsight/configs/reparse")
async def api_reparse_all(auth=Depends(get_current_user)):
    """手动触发全量重新解析"""
    workspace_path = await get_workspace_path()
    await full_parse_all(workspace_path)
    return {"message": "全量重新解析已触发"}


@router.post("/netinsight/configs/{config_id}/reparse")
async def api_reparse_single(config_id: int, auth=Depends(get_current_user)):
    """手动重新解析单个配置文件"""
    data = await get_config_content(config_id)
    if not data:
        raise HTTPException(status_code=404, detail="配置不存在")

    config = await get_config_by_filename(data["file_name"])
    if not config:
        raise HTTPException(status_code=404, detail="配置记录不存在")

    workspace_path = await get_workspace_path()
    full_path = os.path.join(workspace_path, config.file_path)
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="配置文件不存在")

    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    await parse_single_config(config, content)
    return {"message": "重新解析完成"}


# ====================================================================
#  AI 配置问答端点（SSE 流式）
# ====================================================================

class NetChatRequest(BaseModel):
    question: str
    vendor: Optional[str] = None
    ip: Optional[str] = None
    config_ids: Optional[List[int]] = None
    filters: Optional[Dict] = None
    max_tokens: int = 8192


# 结构化查询结果格式化工具

def _format_ip_result(ip: str, result: dict) -> str:
    lines = [f"## IP {ip} 查询结果", ""]
    if not result["found"]:
        lines.append(f"在已解析的全部配置中未找到 IP {ip} 的相关配置。")
        return "\n".join(lines)

    lines.append(f"共在 **{result['total']}** 处发现该 IP：")
    lines.append("")
    for r in result["results"]:
        lines.append(f"- **设备 {r['device_ip']}**（{r['vendor']}）")
        lines.append(f"  - 类型：{r['ip_type']}")
        if r['interface_name']:
            lines.append(f"  - 接口：{r['interface_name']}")
        if r['mask']:
            lines.append(f"  - 地址：{r['ip_address']} / {r['mask']}")
        lines.append(f"  - 配置行：`{r['raw_line']}`")
        lines.append("")
    return "\n".join(lines)


def _format_ip_and_nat_result(ip: str, device_configs: list, ip_result: dict, nat_result: list) -> str:
    """合并格式化设备配置、IP 查询结果与 NAT 映射结果"""
    lines = [f"## IP {ip} 查询结果", ""]

    # 设备配置索引（管理 IP）
    if device_configs:
        lines.append(f"### 匹配到的设备配置（共 {len(device_configs)} 份）")
        lines.append("")
        for c in device_configs:
            lines.append(f"- **设备 {c['device_ip']}**（{c['vendor']}）")
            lines.append(f"  - 配置文件：{c['file_name']}")
            lines.append(f"  - 解析状态：{'成功' if c['parse_status'] == 1 else ('失败' if c['parse_status'] == 2 else '未解析')}")
            lines.append("")

    # IP/VRRP/M-LAG 等接口级 IP
    if ip_result.get("found"):
        lines.append(f"### 接口/VRRP/M-LAG 等配置（共 {ip_result['total']} 处）")
        lines.append("")
        for r in ip_result["results"]:
            lines.append(f"- **设备 {r['device_ip']}**（{r['vendor']}）")
            lines.append(f"  - 类型：{r['ip_type']}")
            if r['interface_name']:
                lines.append(f"  - 接口：{r['interface_name']}")
            if r['mask']:
                lines.append(f"  - 地址：{r['ip_address']} / {r['mask']}")
            lines.append(f"  - 配置行：`{r['raw_line']}`")
            lines.append("")

    # NAT 映射
    if nat_result:
        lines.append(f"### NAT 映射（共 {len(nat_result)} 条）")
        lines.append("")
        for n in nat_result:
            lines.append(f"- **设备 {n['device_ip']}** | {n['nat_type']}")
            lines.append(f"  - 全局：{n['global_ip']}:{n['global_port'] or 'any'} → 内网：{n['local_ip']}:{n['local_port'] or 'any'}")
            if n['protocol']:
                lines.append(f"  - 协议：{n['protocol']}")
            if n['interface_name']:
                lines.append(f"  - 接口：{n['interface_name']}")
            lines.append(f"  - 原始配置：`{n['raw_line']}`")
            lines.append("")

    return "\n".join(lines)


def _format_vlan_result(vlan_id: int, devices: list) -> str:
    lines = [f"## VLAN {vlan_id} 查询结果", ""]
    if not devices:
        lines.append(f"在已解析的配置中未找到 VLAN {vlan_id}。")
        return "\n".join(lines)
    lines.append(f"VLAN {vlan_id} 出现在以下设备：")
    for d in devices:
        name = f"（{d['vlan_name']}）" if d['vlan_name'] else ""
        lines.append(f"- {d['device_ip']}{name}")
    return "\n".join(lines)


def _format_interface_result(device_ip: str, interfaces: list) -> str:
    lines = [f"## 设备 {device_ip} 接口信息", ""]
    if not interfaces:
        lines.append("未找到该设备的接口信息。")
        return "\n".join(lines)
    lines.append(f"共 **{len(interfaces)}** 个接口：")
    lines.append("")
    for i in interfaces:
        desc = f" - {i['description']}" if i['description'] else ""
        shutdown = " [shutdown]" if i['shutdown'] else ""
        vlan_info = ""
        if i['access_vlan']:
            vlan_info = f" | VLAN: {i['access_vlan']}"
        elif i['trunk_vlans']:
            vlan_info = f" | Trunk: {i['trunk_vlans']}"
        lines.append(f"- **{i['interface_name']}** ({i['interface_type']}){desc}{shutdown}{vlan_info}")
    return "\n".join(lines)


def _format_route_result(routes: list) -> str:
    lines = ["## 路由查询结果", ""]
    if not routes:
        lines.append("未找到匹配的路由。")
        return "\n".join(lines)
    for r in routes:
        lines.append(f"- **{r['device_ip']}** | 目的：{r['destination']}/{r['mask']} | 下一跳：{r['next_hop']} | 类型：{r['route_type']}")
        lines.append(f"  - 原始配置：`{r['raw_line']}`")
    return "\n".join(lines)


def _format_nat_result(nat: list) -> str:
    lines = ["## NAT 查询结果", ""]
    if not nat:
        lines.append("未找到匹配的 NAT 映射。")
        return "\n".join(lines)
    for n in nat:
        lines.append(f"- **{n['device_ip']}** | {n['nat_type']}")
        lines.append(f"  - 全局：{n['global_ip']}:{n['global_port'] or 'any'} → 内网：{n['local_ip']}:{n['local_port'] or 'any'}")
        lines.append(f"  - 原始配置：`{n['raw_line']}`")
    return "\n".join(lines)


def _format_acl_result(acls: list) -> str:
    lines = ["## ACL 查询结果", ""]
    if not acls:
        lines.append("未找到匹配的 ACL 规则。")
        return "\n".join(lines)
    for a in acls:
        lines.append(f"- **{a['device_ip']}** | ACL: {a['acl_name']} | 规则 {a['rule_id']} | {a['action']} {a['protocol']}")
        lines.append(f"  - 源：{a['source_ip']}:{a['source_port'] or 'any'} → 目的：{a['dest_ip']}:{a['dest_port'] or 'any'}")
        lines.append(f"  - 规则文本：`{a['rule_text']}`")
    return "\n".join(lines)


def _format_bgp_result(peers: list) -> str:
    lines = ["## BGP 邻居查询结果", ""]
    if not peers:
        lines.append("未找到 BGP 邻居。")
        return "\n".join(lines)
    for p in peers:
        lines.append(f"- **{p['device_ip']}** | 本地 AS: {p['as_number']} | 邻居: {p['peer_ip']} | 邻居 AS: {p['peer_as']}")
        if p['description']:
            lines.append(f"  - 描述：{p['description']}")
    return "\n".join(lines)


def _format_lb_result(ip: str, lb_data: dict) -> str:
    """格式化负载均衡查询结果"""
    lines = [f"## 负载均衡查询结果（IP: {ip}）", ""]

    # 完整服务信息
    for svc in lb_data.get("full_services", []):
        lines.append(f"### Virtual Server: {svc['server_id']}")
        lines.append(f"- **设备**：{svc['device_ip']}")
        lines.append(f"- **类型**：{svc.get('server_type', 'tcp')}")
        if svc.get('description'):
            lines.append(f"- **描述**：{svc['description']}")
        if svc.get('vpn_instance'):
            lines.append(f"- **VPN 实例**：{svc['vpn_instance']}")
        if svc.get('port'):
            lines.append(f"- **监听端口**：{svc['port']}")
        if svc.get('virtual_ip'):
            lines.append(f"- **虚拟 IP (VIP)**：{svc['virtual_ip']}")
        if svc.get('service'):
            lines.append(f"- **服务状态**：{svc['service']}")
        lines.append("")

        # Server Farm
        sf = svc.get("server_farm")
        if sf:
            lines.append(f"#### Server Farm: {sf['farm_id']}")
            if sf.get('description'):
                lines.append(f"- 描述：{sf['description']}")
            if sf.get('fail_action'):
                lines.append(f"- Fail-action：{sf['fail_action']}")
            if sf.get('probe'):
                lines.append(f"- 健康检查：{sf['probe']}")
            lines.append("")

        # Real Servers
        rs_list = svc.get("real_servers", [])
        if rs_list:
            lines.append(f"#### 后端服务器（共 {len(rs_list)} 台）")
            for rs in rs_list:
                port_str = f":{rs['port']}" if rs.get('port') else ""
                weight_str = f" 权重:{rs['weight']}" if rs.get('weight') else ""
                lines.append(f"- {rs['ip_address']}{port_str}{weight_str}")
            lines.append("")

    # 单独的 real server 匹配（IP 是后端服务器而非 VIP）
    rs_only = lb_data.get("real_servers", [])
    vs_count = len(lb_data.get("virtual_servers", []))
    if rs_only and vs_count == 0:
        lines.append("### 该 IP 作为后端服务器")
        for rs in rs_only:
            lines.append(f"- **设备** {rs['device_ip']} | Server ID: {rs['server_id']}")
            lines.append(f"  - IP：{rs['ip_address']}, 端口：{rs.get('port', 'any')}")
            lines.append(f"  - 关联 Server Farm：{rs.get('server_farm_id', 'N/A')}")
        lines.append("")

    return "\n".join(lines)


def _model_to_dict(obj):
    """将 SQLAlchemy 模型实例转为 dict"""
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


async def _query_logical_resource_by_ip(ip: str, visited: set = None) -> dict:
    """根据 IP 查询 IT资源管理-逻辑资源层（地址映射 + 负载均衡），并做一层关联扩展"""
    if visited is None:
        visited = set()
    if ip in visited:
        return {"ip_mappings": [], "lb_mappings": []}
    visited.add(ip)

    async with async_session_factory() as session:
        # 地址映射：外网IP 或 内网IP 匹配
        ip_result = await session.execute(
            select(IpMappingRelation).where(
                or_(IpMappingRelation.external_ip == ip, IpMappingRelation.internal_ip == ip)
            )
        )
        ip_mappings = [_model_to_dict(m) for m in ip_result.scalars().all()]

        # 负载均衡：VIP 或 后端IP 包含
        lb_result = await session.execute(
            select(LbMappingRelation).where(
                or_(LbMappingRelation.vip == ip, LbMappingRelation.backend_ip.like(f"%{ip}%"))
            )
        )
        lb_mappings = [_model_to_dict(m) for m in lb_result.scalars().all()]

        # 关联扩展：地址映射中的内网IP可能作为LB后端
        related_ips = set()
        for m in ip_mappings:
            internal = m.get("internal_ip")
            if internal and internal != ip:
                related_ips.add(internal)
        for related_ip in related_ips:
            related_result = await session.execute(
                select(LbMappingRelation).where(LbMappingRelation.backend_ip.like(f"%{related_ip}%"))
            )
            for row in related_result.scalars().all():
                mapped = _model_to_dict(row)
                if mapped not in lb_mappings:
                    lb_mappings.append(mapped)

        return {"ip_mappings": ip_mappings, "lb_mappings": lb_mappings}


def _format_logical_resource_tables(ip: str, data: dict) -> str:
    """将逻辑资源层查询结果格式化为 Markdown 表格"""
    lines = [f"## {ip} 的逻辑资源层查询结果", ""]
    ip_mappings = data.get("ip_mappings", [])
    lb_mappings = data.get("lb_mappings", [])

    if ip_mappings:
        lines.append("### 地址映射")
        lines.append("| 外网IP | 外网端口 | 协议 | VPN实例 | 内网IP | 内网端口 | 业务 | 备注 |")
        lines.append("|--------|----------|------|---------|--------|----------|------|------|")
        for m in ip_mappings:
            lines.append(
                f"| {m.get('external_ip', '')} | {m.get('external_port', '')} | {m.get('protocol', '')} | "
                f"{m.get('vpn_instance', '')} | {m.get('internal_ip', '')} | {m.get('internal_port', '')} | "
                f"{m.get('business', '')} | {m.get('remarks', '')} |"
            )
        lines.append("")

    if lb_mappings:
        lines.append("### 负载均衡")
        lines.append("| VIP | VIP端口 | 协议 | VPN实例 | 后端IP | 后端端口 | 业务 | 备注 |")
        lines.append("|-----|---------|------|---------|--------|----------|------|------|")
        for m in lb_mappings:
            lines.append(
                f"| {m.get('vip', '')} | {m.get('vip_port', '')} | {m.get('protocol', '')} | "
                f"{m.get('vpn_instance', '')} | {m.get('backend_ip', '')} | {m.get('backend_port', '')} | "
                f"{m.get('business', '')} | {m.get('remarks', '')} |"
            )
        lines.append("")

    if not ip_mappings and not lb_mappings:
        lines.append("在 IT资源管理-逻辑资源层 中未找到相关记录。")

    return "\n".join(lines)


async def try_structured_answer(question: str, filters: dict = None) -> Optional[str]:
    """尝试从结构化配置库中直接给出答案

    流程：
    1. 分析类问题（report 意图）返回 None，交给 LLM 做配置分析
    2. 查询类问题优先查 IT资源管理-逻辑资源层（地址映射+负载均衡）
    3. 逻辑资源层未命中时，继续走原有结构化库查询或 LLM 兜底

    返回格式化后的 Markdown 字符串；如果无法结构化回答，返回 None（走 LLM 兜底）。
    """
    q = question.strip()

    # 0. 意图识别：复用 AI对话 的 _detect_intent
    #    report 意图表示用户要求分析/报告，交给 LLM 读取完整配置做分析
    intent = _detect_intent(q)
    if intent == "report":
        return None

    # 1. 查询类问题：优先查询 IT资源管理-逻辑资源层（地址映射 + 负载均衡）
    ips = re.findall(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?!\d)", q)
    if ips:
        logical_parts = []
        for ip in ips:
            logical_data = await _query_logical_resource_by_ip(ip)
            if logical_data["ip_mappings"] or logical_data["lb_mappings"]:
                logical_parts.append(_format_logical_resource_tables(ip, logical_data))
        if logical_parts:
            return (
                "\n\n".join(logical_parts)
                + "\n\n---\n\n"
                + "如需查看相关设备的完整原始配置，请告诉我具体设备 IP 或点击上方配置备份概览中的「查看」按钮。"
            )

    # 2. 负载均衡查询（关键词触发）
    if any(kw in q.lower() for kw in ("负载均衡", "server-farm", "real-server", "virtual-server")):
        ips = re.findall(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?!\d)", q)
        if ips:
            lb_data = await search_lb_by_ip(ips[0])
            if lb_data["virtual_servers"] or lb_data["real_servers"]:
                return _format_lb_result(ips[0], lb_data)

    # 1. IP 查询（最高优先级）：同时查设备配置索引、接口/IP/VRRP/M-LAG 表、NAT 映射表、负载均衡表
    ips = re.findall(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?!\d)", q)
    if ips:
        for ip in ips:
            device_configs = await search_device_config(ip)
            ip_result = await search_ip(ip)
            nat_result = await search_nat(ip)
            lb_data = await search_lb_by_ip(ip)
            has_lb = bool(lb_data["virtual_servers"] or lb_data["real_servers"])
            has_structured_data = ip_result["found"] or nat_result or has_lb
            has_device_index = bool(device_configs)

            # 如果只命中设备配置索引，且用户明确说"看看配置/分析配置"，则走 LLM 读取完整配置
            if has_device_index and not has_structured_data:
                if any(kw in q for kw in ("配置", "看看", "分析", "总结", "概要")):
                    return None

            if has_device_index or has_structured_data:
                parts = []
                parts.append(_format_ip_and_nat_result(ip, device_configs, ip_result, nat_result))
                if has_lb:
                    parts.append(_format_lb_result(ip, lb_data))
                return "\n\n".join(parts)
        # 结构化库中完全找不到该 IP 时，返回 None 走 LLM 兜底（读取完整配置）
        return None

    # 2. VLAN 查询
    vlan_match = re.search(r"(?:vlan|VLAN)\s*(\d+)", q)
    if vlan_match:
        vlan_id = int(vlan_match.group(1))
        devices = await search_vlan(vlan_id)
        return _format_vlan_result(vlan_id, devices)

    # 3. 接口查询：包含"接口"且能提取到设备 IP
    if "接口" in q or "interface" in q.lower():
        device_ips = re.findall(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?!\d)", q)
        if device_ips:
            interfaces = await search_device_interfaces(device_ips[0])
            return _format_interface_result(device_ips[0], interfaces)

    # 4. 路由查询
    if "路由" in q or "route" in q.lower():
        ips = re.findall(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?!\d)", q)
        destination = None
        next_hop = None
        # 简单规则：如果提到"下一跳"，第二个 IP 是下一跳
        if "下一跳" in q and len(ips) >= 2:
            destination = ips[0]
            next_hop = ips[1]
        elif ips:
            destination = ips[0]
        routes = await search_route(destination=destination, next_hop=next_hop)
        return _format_route_result(routes)

    # 5. NAT 查询
    if "nat" in q.lower() or "映射" in q:
        ips = re.findall(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?!\d)", q)
        nat = await search_nat(ip=ips[0] if ips else None)
        return _format_nat_result(nat)

    # 6. ACL 查询
    if "acl" in q.lower() or "访问控制" in q:
        acl_match = re.search(r"acl\s+(\S+)", q, re.IGNORECASE)
        ips = re.findall(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?!\d)", q)
        acls = await search_acl(
            acl_name=acl_match.group(1) if acl_match else None,
            ip=ips[0] if ips else None,
        )
        return _format_acl_result(acls)

    # 7. BGP 查询
    if "bgp" in q.lower():
        ips = re.findall(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?!\d)", q)
        peers = await search_bgp_peer(peer_ip=ips[0] if ips else None)
        return _format_bgp_result(peers)

    return None


# 系统 Prompt：引导 AI 基于配置内容回答网络相关问题
SYSTEM_PROMPT = """你是一位资深网络工程师和 AI 运维助手。你的任务是基于用户提供的网络设备配置备份文件，准确回答用户的网络相关问题。

## 回答原则
1. **只能基于提供的配置内容回答**，不要编造或假设配置中不存在的信息
2. 如果配置中找不到相关信息，必须明确说明"在全部 X 台设备配置中均未找到"或"在已提供的配置片段中未找到"，不能谎称搜索了全部配置
3. 回答要准确、专业，引用配置中的具体命令和参数
4. 对于 NAT 映射、ACL 规则、路由策略等查询，给出具体的配置行和解释
5. 对于配置合理性问题，指出具体风险并给出改进建议
6. 使用 Markdown 格式组织回答，命令和配置片段用代码块展示

## 关于配置范围
- 你可能只会收到部分设备的完整配置，以及其余设备的配置片段或仅设备列表
- 如果收到"[以下 N 台设备仅列出标题，未展开配置]"，说明这些设备的内容未放入当前上下文，你不能基于它们的完整配置下结论
- 如果问题涉及具体 IP、接口名、VLAN 等，优先使用"搜索结果"中的汇总信息作答

## 网络知识背景
- 你熟悉 H3C (Comware)、华为 (VRP)、Cisco (IOS/IOS-XE/NX-OS)、绿盟、启明星辰等厂商配置语法
- 你理解 VXLAN、VRF、BGP EVPN、OSPF、NAT、ACL、策略路由等网络技术
- 对于 SDN 场景，你能分析 underlay 和 overlay 配置的关系
"""


@router.post("/netinsight/chat")
async def api_net_chat(req: NetChatRequest, auth=Depends(get_current_user)):
    """AI 配置问答 - SSE 流式响应

    流式协议（与 chat.py 保持一致）：
      data: {"type":"meta","config_count":5,"vendors":["h3c"]}\n\n
      data: {"type":"content","content":"逐段文本"}\n\n
      data: {"type":"finish"}\n\n
      data: {"type":"error","content":"错误信息"}\n\n
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    async def _stream_generator():
        # 0. 优先尝试结构化库直接回答（省 token、速度快）
        structured_answer = await try_structured_answer(req.question, filters=req.filters)
        if structured_answer:
            yield _sse_frame({
                "type": "meta",
                "config_count": 0,
                "vendors": [],
                "ips": [],
                "source": "structured_db",
            })
            # 把完整答案一次性返回（按 200 字左右分段，保持 SSE 协议一致）
            chunk_size = 200
            for i in range(0, len(structured_answer), chunk_size):
                yield _sse_frame({
                    "type": "content",
                    "content": structured_answer[i:i + chunk_size],
                })
            yield _sse_frame({"type": "finish"})
            return

        # 1. 识别问题中是否包含"查看/分析某设备完整配置"的意图
        question_ips = re.findall(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?!\d)", req.question)
        target_ip = req.ip
        view_config_intent = any(kw in req.question for kw in ("配置", "看看", "分析", "总结", "概要"))
        if not target_ip and view_config_intent and question_ips:
            for ip in question_ips:
                device_cfgs = await search_device_config(ip)
                if device_cfgs:
                    target_ip = ip
                    break

        # 2. 加载配置（合并用户传入的 vendor/config_ids 与 filters 中的筛选条件）
        filters = req.filters or {}
        try:
            configs = await load_configs(
                vendor=req.vendor or filters.get("vendor"),
                ip=target_ip,
                ids=req.config_ids or filters.get("config_ids"),
            )
        except Exception as e:
            yield _sse_frame({"type": "error", "content": f"配置加载失败: {str(e)[:300]}"})
            return

        if not configs:
            yield _sse_frame({"type": "error", "content": "未找到匹配的配置记录，请先扫描或上传配置文件"})
            return

        # 检查是否有配置内容（可能文件不存在）
        valid_configs = [c for c in configs if c["content"] and not c["content"].startswith("[读取失败")]
        if not valid_configs:
            yield _sse_frame({"type": "error", "content": "配置文件读取失败，请检查存储路径是否正确"})
            return

        # 帧 1: meta
        vendors_used = list(set(c["vendor"] for c in valid_configs))
        yield _sse_frame({
            "type": "meta",
            "config_count": len(valid_configs),
            "vendors": vendors_used,
            "ips": [c["ip"] for c in valid_configs],
            "source": "llm",
        })

        # 2. 针对问题中的 IP/关键词进行预搜索，避免 LLM 漏看
        question_ips = re.findall(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?!\d)", req.question)
        search_results: List[str] = []
        matched_device_ips: set = set()
        if question_ips:
            for ip in question_ips:
                matched = []
                snippets = []
                for c in valid_configs:
                    if ip in c["content"]:
                        matched_device_ips.add(c["ip"])
                        matched.append(f"{c['ip']} ({c['vendor']})")
                        # 提取 IP 所在行及其上下文（前后各 2 行）
                        lines = c["content"].splitlines()
                        for idx, line in enumerate(lines):
                            if ip in line:
                                start = max(0, idx - 2)
                                end = min(len(lines), idx + 3)
                                snippet = "\n".join(
                                    f"    {l}" for l in lines[start:end]
                                )
                                snippets.append(
                                    f"设备 {c['ip']} ({c['vendor']}) 第 {idx + 1} 行:\n{snippet}"
                                )
                                break  # 每份配置只取第一处出现
                if matched:
                    search_results.append(
                        f"IP {ip} 在以下 {len(matched)} 台设备配置中出现：{', '.join(matched)}"
                    )
                    search_results.extend(snippets)
                else:
                    if view_config_intent and target_ip == ip:
                        search_results.append(
                            f"IP {ip} 是设备管理地址，未在配置内容中作为接口/NAT/路由等出现。请基于完整配置内容给出该设备的配置摘要。"
                        )
                    else:
                        search_results.append(
                            f"IP {ip} 在全部 {len(valid_configs)} 台设备配置中均未找到"
                        )

        # 把匹配到 IP 的设备排在前面，确保它们进入上下文
        if matched_device_ips:
            valid_configs = sorted(
                valid_configs,
                key=lambda c: (c["ip"] not in matched_device_ips, c["vendor"], c["ip"]),
            )

        # 3. 构建配置上下文（限制总长度，避免超出 LLM 上下文窗口）
        # 每份配置最大占用字符数，保证至少能看到 N 台设备的头
        MAX_CONFIG_CONTEXT = 100000  # 100K 字符，预留给 prompt + response
        PER_CONFIG_MAX = 12000       # 单份配置最大展示长度
        config_parts = []
        total_chars = 0
        shown_full = 0
        shown_header_only = 0

        for idx, c in enumerate(valid_configs):
            header = f"\n## 设备 {c['ip']} ({c['vendor']}) - {c['filename']}\n"
            content = c["content"]

            # 先按单份上限截断
            if len(content) > PER_CONFIG_MAX:
                content = content[:PER_CONFIG_MAX] + "\n... [该设备配置已按单份上限截断] ..."

            available = MAX_CONFIG_CONTEXT - total_chars - len(header) - len(content)
            if available < 0:
                # 当前这份放不下完整内容了，改为只放标题
                if MAX_CONFIG_CONTEXT - total_chars - len(header) >= 0:
                    config_parts.append(header + "[配置未展开，仅列出设备]\n")
                    shown_header_only += 1
                    total_chars += len(header) + len("[配置未展开，仅列出设备]\n")
                else:
                    # 连标题都放不下，直接记录剩余数量
                    remaining = len(valid_configs) - idx
                    sample_devices = valid_configs[idx:idx + 5]
                    sample_text = ", ".join(
                        f"{x['ip']} ({x['vendor']})" for x in sample_devices
                    )
                    suffix = " 等" if remaining > 5 else ""
                    config_parts.append(
                        f"\n## [还有 {remaining} 台设备未列出：{sample_text}{suffix}]\n"
                    )
                break

            config_parts.append(header + content + "\n")
            total_chars += len(header) + len(content)
            shown_full += 1

        truncation_note = ""
        if shown_header_only > 0 or shown_full < len(valid_configs):
            truncation_note = (
                f"\n[说明：当前上下文共包含 {len(valid_configs)} 台设备，"
                f"其中 {shown_full} 台展示了完整/截断配置，"
                f"{shown_header_only} 台仅列出标题，"
                f"其余设备未列出。请基于已展示内容作答，不要假设未展示设备包含该信息。]\n"
            )

        search_context = ""
        if search_results:
            search_context = "\n## 搜索结果（按问题中的 IP/关键词预检索）\n" + "\n".join(search_results) + "\n"

        config_context = "\n".join(config_parts) + truncation_note

        # 4. 构建消息
        if view_config_intent and target_ip:
            user_message = (
                f"用户想查看设备 {target_ip} 的配置内容，请基于下方该设备的完整配置生成摘要或回答用户问题。\n"
                f"注意：{target_ip} 是设备管理地址，配置内容中可能不直接出现该 IP，请从接口、VLAN、路由、NAT、ACL、BGP、OSPF、VRRP、M-LAG、系统参数等维度进行总结。\n\n"
                f"{search_context}"
                f"--- 配置开始 ---\n{config_context}\n--- 配置结束 ---\n\n"
                f"**我的问题**: {req.question}"
            )
        else:
            user_message = (
                f"以下是当前网络设备的配置备份内容，请基于这些配置回答我的问题。\n"
                f"如果问题涉及具体 IP/关键词，我已预先在所有设备配置中做了检索，结果见\"搜索结果\"部分。\n\n"
                f"{search_context}"
                f"--- 配置开始 ---\n{config_context}\n--- 配置结束 ---\n\n"
                f"**我的问题**: {req.question}"
            )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        # 4. 获取 LLM 配置并流式调用
        try:
            model_cfg = await model_scheduler.get_model()
            if not model_cfg:
                yield _sse_frame({"type": "error", "content": "未配置大模型，请先在配置中心→大模型中添加并启用"})
                return
        except Exception as e:
            yield _sse_frame({"type": "error", "content": f"加载模型配置失败: {str(e)[:200]}"})
            return

        try:
            async for chunk in llm_client.stream_chat(
                messages=messages,
                model=model_cfg["model_name"],
                temperature=0.3,
                max_tokens=req.max_tokens,
                api_base=model_cfg.get("api_base"),
                api_key=model_cfg.get("api_key"),
            ):
                content = chunk.get("content", "") if isinstance(chunk, dict) else str(chunk)
                if content:
                    yield _sse_frame({"type": "content", "content": content})
        except Exception as e:
            err_msg = f"大模型调用失败: {str(e)[:300]}"
            print(f"[AIOPS] 网络洞察问答异常: {err_msg}")
            yield _sse_frame({"type": "error", "content": err_msg})
            return

        # 帧: finish
        yield _sse_frame({"type": "finish"})

    return StreamingResponse(
        _stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
