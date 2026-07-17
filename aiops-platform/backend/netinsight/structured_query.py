"""网络洞察 - 结构化配置查询服务

基于已解析到数据库的结构化数据，提供快速查询能力，供 API 和 AI 问答使用。
"""

from typing import List, Dict, Optional
from sqlalchemy import select, or_
from core.db import async_session_factory
from models.netinsight import (
    NetConfig, NetConfigInterface, NetConfigIP, NetConfigVLAN,
    NetConfigRoute, NetConfigNAT, NetConfigACL,
    NetConfigBGPPeer, NetConfigOSPF, NetConfigVRRP, NetConfigMLAG,
    NetConfigLBServerFarm, NetConfigLBRealServer, NetConfigLBVirtualServer,
)


async def search_ip(ip: str) -> Dict:
    """查询某个 IP 在哪些设备、哪些位置出现

    Returns:
        {"found": bool, "total": int, "results": [...]}
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(NetConfigIP)
            .where(NetConfigIP.ip_address == ip)
            .order_by(NetConfigIP.device_ip, NetConfigIP.ip_type)
        )
        rows = result.scalars().all()

    results = []
    for r in rows:
        results.append({
            "device_ip": r.device_ip,
            "vendor": r.vendor,
            "ip_address": r.ip_address,
            "mask": r.mask,
            "ip_type": r.ip_type,
            "interface_name": r.interface_name,
            "vrf": r.vrf,
            "description": r.description,
            "raw_line": r.raw_line,
        })

    return {"found": len(results) > 0, "total": len(results), "results": results}


async def search_device_config(device_ip: str) -> List[Dict]:
    """按设备管理 IP 查找配置索引（用于用户问'某 IP 的配置'）"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(NetConfig)
            .where(NetConfig.ip_address == device_ip)
            .order_by(NetConfig.vendor, NetConfig.file_name)
        )
        rows = result.scalars().all()

    return [
        {
            "id": r.id,
            "device_ip": r.ip_address,
            "vendor": r.vendor,
            "file_name": r.file_name,
            "file_path": r.file_path,
            "file_size": r.file_size,
            "file_date": r.file_date,
            "parse_status": r.parse_status,
        }
        for r in rows
    ]


async def search_device_interfaces(device_ip: str) -> List[Dict]:
    """查询某台设备的所有接口"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(NetConfigInterface)
            .where(NetConfigInterface.device_ip == device_ip)
            .order_by(NetConfigInterface.interface_name)
        )
        rows = result.scalars().all()

    return [
        {
            "interface_name": r.interface_name,
            "interface_type": r.interface_type,
            "description": r.description,
            "shutdown": r.shutdown,
            "link_type": r.link_type,
            "access_vlan": r.access_vlan,
            "trunk_vlans": r.trunk_vlans,
            "pvid": r.pvid,
            "lacp_group": r.lacp_group,
        }
        for r in rows
    ]


async def search_vlan(vlan_id: int) -> List[Dict]:
    """查询某个 VLAN 在哪些设备上存在"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(NetConfigVLAN)
            .where(NetConfigVLAN.vlan_id == vlan_id)
            .order_by(NetConfigVLAN.device_ip)
        )
        rows = result.scalars().all()

    return [
        {
            "device_ip": r.device_ip,
            "vlan_id": r.vlan_id,
            "vlan_name": r.vlan_name,
            "description": r.description,
        }
        for r in rows
    ]


async def search_route(destination: Optional[str] = None, next_hop: Optional[str] = None) -> List[Dict]:
    """查询路由"""
    async with async_session_factory() as session:
        query = select(NetConfigRoute)
        filters = []
        if destination:
            filters.append(NetConfigRoute.destination == destination)
        if next_hop:
            filters.append(NetConfigRoute.next_hop == next_hop)
        if filters:
            query = query.where(or_(*filters))
        query = query.order_by(NetConfigRoute.device_ip)
        result = await session.execute(query)
        rows = result.scalars().all()

    return [
        {
            "device_ip": r.device_ip,
            "route_type": r.route_type,
            "destination": r.destination,
            "mask": r.mask,
            "next_hop": r.next_hop,
            "preference": r.preference,
            "cost": r.cost,
            "vrf": r.vrf,
            "raw_line": r.raw_line,
        }
        for r in rows
    ]


async def search_nat(ip: Optional[str] = None) -> List[Dict]:
    """查询 NAT 映射"""
    async with async_session_factory() as session:
        query = select(NetConfigNAT)
        if ip:
            query = query.where(
                or_(NetConfigNAT.global_ip == ip, NetConfigNAT.local_ip == ip)
            )
        query = query.order_by(NetConfigNAT.device_ip)
        result = await session.execute(query)
        rows = result.scalars().all()

    return [
        {
            "device_ip": r.device_ip,
            "nat_type": r.nat_type,
            "global_ip": r.global_ip,
            "global_port": r.global_port,
            "local_ip": r.local_ip,
            "local_port": r.local_port,
            "protocol": r.protocol,
            "interface_name": r.interface_name,
            "acl_name": r.acl_name,
            "raw_line": r.raw_line,
        }
        for r in rows
    ]


async def search_acl(acl_name: Optional[str] = None, ip: Optional[str] = None) -> List[Dict]:
    """查询 ACL 规则"""
    async with async_session_factory() as session:
        query = select(NetConfigACL)
        filters = []
        if acl_name:
            filters.append(NetConfigACL.acl_name == acl_name)
        if ip:
            filters.append(
                or_(
                    NetConfigACL.source_ip == ip,
                    NetConfigACL.dest_ip == ip,
                )
            )
        if filters:
            query = query.where(or_(*filters))
        query = query.order_by(NetConfigACL.device_ip, NetConfigACL.acl_name)
        result = await session.execute(query)
        rows = result.scalars().all()

    return [
        {
            "device_ip": r.device_ip,
            "acl_name": r.acl_name,
            "rule_id": r.rule_id,
            "action": r.action,
            "protocol": r.protocol,
            "source_ip": r.source_ip,
            "source_port": r.source_port,
            "dest_ip": r.dest_ip,
            "dest_port": r.dest_port,
            "rule_text": r.rule_text,
        }
        for r in rows
    ]


async def search_bgp_peer(peer_ip: Optional[str] = None) -> List[Dict]:
    """查询 BGP 邻居"""
    async with async_session_factory() as session:
        query = select(NetConfigBGPPeer)
        if peer_ip:
            query = query.where(NetConfigBGPPeer.peer_ip == peer_ip)
        query = query.order_by(NetConfigBGPPeer.device_ip)
        result = await session.execute(query)
        rows = result.scalars().all()

    return [
        {
            "device_ip": r.device_ip,
            "as_number": r.as_number,
            "peer_ip": r.peer_ip,
            "peer_as": r.peer_as,
            "description": r.description,
        }
        for r in rows
    ]


async def search_lb_by_ip(ip: str) -> Dict:
    """按 IP 查询负载均衡配置（VIP 或 Real Server IP）

    Returns:
        {
          "virtual_servers": [...],
          "server_farms": [...],
          "real_servers": [...],
          "full_services": [...]  # 聚合后的完整服务信息
        }
    """
    async with async_session_factory() as session:
        # 1. 查 Virtual Server (VIP)
        vs_rows = await session.execute(
            select(NetConfigLBVirtualServer)
            .where(NetConfigLBVirtualServer.virtual_ip == ip)
            .order_by(NetConfigLBVirtualServer.device_ip)
        )
        virtual_servers = vs_rows.scalars().all()

        # 2. 查 Real Server (后端IP)
        rs_rows = await session.execute(
            select(NetConfigLBRealServer)
            .where(NetConfigLBRealServer.ip_address == ip)
            .order_by(NetConfigLBRealServer.device_ip)
        )
        real_servers = rs_rows.scalars().all()

        # 3. 收集所有关联的 server_farm_id
        farm_ids = set()
        for vs in virtual_servers:
            if vs.default_server_farm:
                farm_ids.add(vs.default_server_farm)
        for rs in real_servers:
            if rs.server_farm_id:
                farm_ids.add(rs.server_farm_id)

        # 4. 查询 server farms
        server_farms = []
        if farm_ids:
            sf_rows = await session.execute(
                select(NetConfigLBServerFarm)
                .where(NetConfigLBServerFarm.farm_id.in_(farm_ids))
                .order_by(NetConfigLBServerFarm.device_ip)
            )
            server_farms = sf_rows.scalars().all()

        # 5. 查询这些 farm 下的所有 real servers
        farm_related_rs = []
        if farm_ids:
            rs_farm_rows = await session.execute(
                select(NetConfigLBRealServer)
                .where(NetConfigLBRealServer.server_farm_id.in_(farm_ids))
                .order_by(NetConfigLBRealServer.device_ip)
            )
            farm_related_rs = rs_farm_rows.scalars().all()

    # 聚合完整服务信息：VS + SF + RS
    full_services = []
    for vs in virtual_servers:
        service = {
            "device_ip": vs.device_ip,
            "server_id": vs.server_id,
            "server_type": vs.server_type,
            "description": vs.description,
            "vpn_instance": vs.vpn_instance,
            "port": vs.port,
            "virtual_ip": vs.virtual_ip,
            "default_server_farm": vs.default_server_farm,
            "service": vs.service,
        }
        # 关联 server farm
        for sf in server_farms:
            if sf.farm_id == vs.default_server_farm:
                service["server_farm"] = {
                    "farm_id": sf.farm_id,
                    "description": sf.description,
                    "fail_action": sf.fail_action,
                    "probe": sf.probe,
                }
                break
        # 关联 real servers
        service["real_servers"] = [
            {
                "server_id": rs.server_id,
                "ip_address": rs.ip_address,
                "port": rs.port,
                "weight": rs.weight,
            }
            for rs in farm_related_rs
            if rs.server_farm_id == vs.default_server_farm and rs.device_ip == vs.device_ip
        ]
        full_services.append(service)

    return {
        "virtual_servers": [
            {"device_ip": v.device_ip, "server_id": v.server_id, "server_type": v.server_type,
             "description": v.description, "vpn_instance": v.vpn_instance,
             "port": v.port, "virtual_ip": v.virtual_ip,
             "default_server_farm": v.default_server_farm, "service": v.service}
            for v in virtual_servers
        ],
        "server_farms": [
            {"device_ip": s.device_ip, "farm_id": s.farm_id, "description": s.description,
             "fail_action": s.fail_action, "snat_pool": s.snat_pool, "probe": s.probe}
            for s in server_farms
        ],
        "real_servers": [
            {"device_ip": r.device_ip, "server_id": r.server_id,
             "ip_address": r.ip_address, "port": r.port,
             "server_farm_id": r.server_farm_id, "weight": r.weight}
            for r in real_servers
        ],
        "full_services": full_services,
    }


async def get_parsing_stats() -> Dict:
    """获取结构化解析统计"""
    async with async_session_factory() as session:
        total = await session.execute(select(NetConfig))
        total_count = len(total.scalars().all())

        parsed = await session.execute(
            select(NetConfig).where(NetConfig.parse_status == 1)
        )
        parsed_count = len(parsed.scalars().all())

        failed = await session.execute(
            select(NetConfig).where(NetConfig.parse_status == 2)
        )
        failed_count = len(failed.scalars().all())

    return {
        "total_configs": total_count,
        "parsed": parsed_count,
        "failed": failed_count,
        "unparsed": total_count - parsed_count - failed_count,
    }
