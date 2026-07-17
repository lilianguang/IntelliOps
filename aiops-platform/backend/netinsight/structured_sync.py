"""网络洞察 - 结构化配置增量同步服务

职责：
1. 记录已处理到的 Git commit
2. 通过 git diff 检测变更文件
3. 调用厂商解析器把配置解析成结构化数据
4. 增量写入/更新数据库

触发时机：
- 每日定时扫描完成并提交 Git 后
- 用户上传配置后
- 手动点击"重新解析"
"""

import os
import hashlib
from datetime import datetime
from typing import List, Dict, Optional

from sqlalchemy import select, delete
from core.db import async_session_factory
from models.netinsight import (
    NetConfig, NetConfigSyncState,
    NetConfigInterface, NetConfigIP, NetConfigVLAN,
    NetConfigRoute, NetConfigNAT, NetConfigACL,
    NetConfigBGPPeer, NetConfigOSPF, NetConfigVRRP, NetConfigMLAG,
    NetConfigLBServerFarm, NetConfigLBRealServer, NetConfigLBVirtualServer,
)
from netinsight.parser import get_parser
from netinsight.version import _run_git


# ========================================================================
#  Git 变更检测
# ========================================================================

def get_changed_files(base_path: str, old_commit: str, new_commit: str) -> List[Dict]:
    """获取两次 commit 之间变更的文件列表

    Returns:
        [{"action": "M"|"A"|"D"|"R", "filename": str, "old_filename": str?}]
    """
    if not old_commit or not new_commit or old_commit == new_commit:
        return []

    r = _run_git(base_path, ["diff", "--name-status", old_commit, new_commit])
    if r.returncode != 0 or not r.stdout.strip():
        return []

    changes = []
    for line in r.stdout.strip().split("\n"):
        parts = line.split("\t")
        if not parts:
            continue
        action = parts[0][0].upper() if parts[0] else ""

        if action == "R" and len(parts) >= 3:
            changes.append({
                "action": "R",
                "old_filename": parts[1],
                "filename": parts[2],
            })
        elif action in ("M", "A", "D") and len(parts) >= 2:
            changes.append({
                "action": action,
                "filename": parts[1],
            })

    return changes


def get_all_files_in_commit(base_path: str, commit: str) -> List[str]:
    """获取某次 commit 中的所有 .cfg 文件（用于首次全量解析）"""
    r = _run_git(base_path, ["ls-tree", "-r", "--name-only", commit])
    if r.returncode != 0 or not r.stdout.strip():
        return []
    return [f for f in r.stdout.strip().split("\n") if f.lower().endswith(".cfg")]


# ========================================================================
#  同步状态管理
# ========================================================================

async def get_sync_state() -> Optional[NetConfigSyncState]:
    """读取当前同步状态"""
    async with async_session_factory() as session:
        result = await session.execute(select(NetConfigSyncState))
        return result.scalars().first()


async def save_sync_state(commit: str, total_commits: int = 0):
    """保存同步状态"""
    async with async_session_factory() as session:
        result = await session.execute(select(NetConfigSyncState))
        state = result.scalars().first()
        if state:
            state.last_processed_commit = commit
            state.last_processed_at = datetime.now()
            if total_commits:
                state.total_commits_processed += total_commits
        else:
            session.add(NetConfigSyncState(
                last_processed_commit=commit,
                last_processed_at=datetime.now(),
                total_commits_processed=total_commits or 1,
            ))
        await session.commit()


# ========================================================================
#  解析数据写入
# ========================================================================

async def delete_parsed_data(net_config_id: int):
    """删除某份配置的所有结构化解析数据"""
    async with async_session_factory() as session:
        for model in (
            NetConfigInterface, NetConfigIP, NetConfigVLAN,
            NetConfigRoute, NetConfigNAT, NetConfigACL,
            NetConfigBGPPeer, NetConfigOSPF, NetConfigVRRP, NetConfigMLAG,
            NetConfigLBServerFarm, NetConfigLBRealServer, NetConfigLBVirtualServer,
        ):
            await session.execute(
                delete(model).where(model.net_config_id == net_config_id)
            )
        await session.commit()


async def save_parsed_data(net_config_id: int, device_ip: str, vendor: str, result):
    """把 ParsingResult 写入数据库"""
    async with async_session_factory() as session:
        # 接口
        for iface in result.interfaces:
            session.add(NetConfigInterface(
                net_config_id=net_config_id,
                device_ip=device_ip,
                vendor=vendor,
                interface_name=iface.interface_name,
                interface_type=iface.interface_type,
                description=iface.description,
                shutdown=iface.shutdown,
                link_type=iface.link_type,
                access_vlan=iface.access_vlan,
                trunk_vlans=iface.trunk_vlans,
                pvid=iface.pvid,
                lacp_group=iface.lacp_group,
                raw_config=iface.raw_config,
            ))

        # IP
        for ip in result.ips:
            session.add(NetConfigIP(
                net_config_id=net_config_id,
                device_ip=device_ip,
                vendor=vendor,
                ip_address=ip.ip_address,
                mask=ip.mask,
                ip_type=ip.ip_type,
                interface_name=ip.interface_name,
                vrf=ip.vrf,
                description=ip.description,
                raw_line=ip.raw_line,
            ))

        # VLAN
        for vlan in result.vlans:
            session.add(NetConfigVLAN(
                net_config_id=net_config_id,
                device_ip=device_ip,
                vlan_id=vlan.vlan_id,
                vlan_name=vlan.vlan_name,
                description=vlan.description,
                raw_config=vlan.raw_config,
            ))

        # 路由
        for route in result.routes:
            session.add(NetConfigRoute(
                net_config_id=net_config_id,
                device_ip=device_ip,
                route_type=route.route_type,
                destination=route.destination,
                mask=route.mask,
                next_hop=route.next_hop,
                preference=route.preference,
                cost=route.cost,
                vrf=route.vrf,
                raw_line=route.raw_line,
            ))

        # NAT
        for nat in result.nats:
            session.add(NetConfigNAT(
                net_config_id=net_config_id,
                device_ip=device_ip,
                nat_type=nat.nat_type,
                global_ip=nat.global_ip,
                global_port=nat.global_port,
                local_ip=nat.local_ip,
                local_port=nat.local_port,
                protocol=nat.protocol,
                interface_name=nat.interface_name,
                acl_name=nat.acl_name,
                raw_line=nat.raw_line,
            ))

        # ACL
        for acl in result.acls:
            session.add(NetConfigACL(
                net_config_id=net_config_id,
                device_ip=device_ip,
                acl_name=acl.acl_name,
                rule_id=acl.rule_id,
                action=acl.action,
                protocol=acl.protocol,
                source_ip=acl.source_ip,
                source_port=acl.source_port,
                dest_ip=acl.dest_ip,
                dest_port=acl.dest_port,
                rule_text=acl.rule_text,
                raw_line=acl.raw_line,
            ))

        # BGP
        for peer in result.bgp_peers:
            session.add(NetConfigBGPPeer(
                net_config_id=net_config_id,
                device_ip=device_ip,
                as_number=peer.as_number,
                peer_ip=peer.peer_ip,
                peer_as=peer.peer_as,
                description=peer.description,
                raw_line=peer.raw_line,
            ))

        # OSPF
        for ospf in result.ospf:
            session.add(NetConfigOSPF(
                net_config_id=net_config_id,
                device_ip=device_ip,
                process_id=ospf.process_id,
                area_id=ospf.area_id,
                network=ospf.network,
                wildcard=ospf.wildcard,
                raw_line=ospf.raw_line,
            ))

        # VRRP
        for vrrp in result.vrrp:
            session.add(NetConfigVRRP(
                net_config_id=net_config_id,
                device_ip=device_ip,
                interface_name=vrrp.interface_name,
                vrid=vrrp.vrid,
                virtual_ip=vrrp.virtual_ip,
                priority=vrrp.priority,
                raw_line=vrrp.raw_line,
            ))

        # M-LAG
        for mlag in result.mlag:
            session.add(NetConfigMLAG(
                net_config_id=net_config_id,
                device_ip=device_ip,
                mlag_id=mlag.mlag_id,
                peer_link=mlag.peer_link,
                virtual_ip=mlag.virtual_ip,
                interface_name=mlag.interface_name,
                raw_line=mlag.raw_line,
            ))

        # LB Server Farm
        for sf in result.lb_server_farms:
            session.add(NetConfigLBServerFarm(
                net_config_id=net_config_id,
                device_ip=device_ip,
                farm_id=sf.farm_id,
                description=sf.description,
                fail_action=sf.fail_action,
                snat_pool=sf.snat_pool,
                probe=sf.probe,
                raw_config=sf.raw_config,
            ))

        # LB Real Server
        for rs in result.lb_real_servers:
            session.add(NetConfigLBRealServer(
                net_config_id=net_config_id,
                device_ip=device_ip,
                server_id=rs.server_id,
                ip_address=rs.ip_address,
                port=rs.port,
                server_farm_id=rs.server_farm_id,
                weight=rs.weight,
                raw_config=rs.raw_config,
            ))

        # LB Virtual Server
        for vs in result.lb_virtual_servers:
            session.add(NetConfigLBVirtualServer(
                net_config_id=net_config_id,
                device_ip=device_ip,
                server_id=vs.server_id,
                server_type=vs.server_type,
                description=vs.description,
                vpn_instance=vs.vpn_instance,
                port=vs.port,
                virtual_ip=vs.virtual_ip,
                default_server_farm=vs.default_server_farm,
                route_advertisement=vs.route_advertisement,
                sticky=vs.sticky,
                vrrp_vrid=vs.vrrp_vrid,
                service=vs.service,
                raw_config=vs.raw_config,
            ))

        await session.commit()


async def update_config_meta(net_config_id: int, content_hash: str, status: int, error: str = ""):
    """更新 net_configs 的解析元数据"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(NetConfig).where(NetConfig.id == net_config_id)
        )
        config = result.scalar_one_or_none()
        if config:
            config.content_hash = content_hash
            config.parsed_at = datetime.now()
            config.parse_status = status
            config.parse_error = error
            await session.commit()


# ========================================================================
#  单文件解析入口
# ========================================================================

async def parse_single_config(config: NetConfig, content: str):
    """解析单个配置文件并写入结构化库"""
    new_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    # 如果 hash 没变且之前解析成功，跳过
    if config.content_hash == new_hash and config.parse_status == 1:
        return

    # 删除旧数据
    await delete_parsed_data(config.id)

    try:
        parser = get_parser(config.vendor)
        result = parser.parse(content)

        if result.errors:
            await update_config_meta(
                config.id, new_hash, 2, "; ".join(result.errors)
            )
            return

        await save_parsed_data(config.id, config.ip_address, config.vendor, result)
        await update_config_meta(config.id, new_hash, 1, "")

    except Exception as e:
        await update_config_meta(config.id, new_hash, 2, str(e)[:500])


# ========================================================================
#  增量 / 全量解析入口
# ========================================================================

async def get_config_by_filename(filename: str) -> Optional[NetConfig]:
    """根据文件名查找 net_configs 记录"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(NetConfig).where(NetConfig.file_name == filename)
        )
        return result.scalar_one_or_none()


async def incremental_parse(base_path: str, current_commit: Optional[str]):
    """基于 Git commit 做增量解析

    Args:
        base_path: Git 仓库根目录（工作区）
        current_commit: 当前最新 commit hash；None 表示未提交
    """
    if not current_commit:
        print("[结构化同步] 当前没有新的 Git commit，跳过")
        return

    state = await get_sync_state()
    last_commit = state.last_processed_commit if state else None

    if last_commit == current_commit:
        print("[结构化同步] 已是最新版本，无需解析")
        return

    if not last_commit:
        print("[结构化同步] 首次运行，执行全量解析 ...")
        await full_parse_all(base_path)
        await save_sync_state(current_commit)
        return

    print(f"[结构化同步] 增量解析: {last_commit[:8]} -> {current_commit[:8]}")
    changes = get_changed_files(base_path, last_commit, current_commit)
    if not changes:
        print("[结构化同步] 无文件变更")
        await save_sync_state(current_commit)
        return

    for change in changes:
        action = change["action"]
        filename = change["filename"]

        if action == "D":
            config = await get_config_by_filename(filename)
            if config:
                await delete_parsed_data(config.id)
                await update_config_meta(config.id, "", 0, "文件已删除")
            continue

        if action == "R":
            old_filename = change.get("old_filename")
            if old_filename:
                old_config = await get_config_by_filename(old_filename)
                if old_config:
                    await delete_parsed_data(old_config.id)

        # A / M / R 都需要解析当前文件
        config = await get_config_by_filename(filename)
        if not config:
            print(f"[结构化同步] 跳过：数据库中无 {filename}")
            continue

        full_path = os.path.join(base_path, filename)
        if not os.path.isfile(full_path):
            print(f"[结构化同步] 文件不存在：{full_path}")
            continue

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            await update_config_meta(config.id, "", 2, f"读取失败: {e}")
            continue

        await parse_single_config(config, content)

    await save_sync_state(current_commit)
    print(f"[结构化同步] 完成，处理了 {len(changes)} 个文件变更")


async def full_parse_all(base_path: str):
    """全量解析工作区中所有已索引的配置文件"""
    async with async_session_factory() as session:
        result = await session.execute(select(NetConfig))
        configs = result.scalars().all()

    for config in configs:
        full_path = os.path.join(base_path, config.file_path)
        if not os.path.isfile(full_path):
            await update_config_meta(config.id, "", 2, "文件不存在")
            continue

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            await update_config_meta(config.id, "", 2, f"读取失败: {e}")
            continue

        await parse_single_config(config, content)

    print(f"[结构化同步] 全量解析完成，共 {len(configs)} 个文件")
