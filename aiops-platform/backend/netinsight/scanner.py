"""网络洞察 - 配置扫描与加载服务

架构：
- 源目录（NET_CONFIG_SOURCE_PATH）: 只读，挂载用户本地每日备份目录
- 工作区（NET_CONFIG_WORKSPACE_PATH）: 可写，存放同步后的配置、用户上传文件、Git 版本

负责：
1. 将源目录配置同步到工作区
2. 扫描工作区，解析文件名，upsert 到数据库索引
3. 从工作区读取配置内容，供 AI 分析使用
"""

import os
import re
import shutil
from pathlib import Path
from typing import Optional, List, Dict

from sqlalchemy import select
from core.db import async_session_factory
from models.netinsight import NetConfig, SystemSetting
from models.cmdb import CMDBAsset
from config.settings import settings
from netinsight.version import commit_changes
from netinsight.structured_sync import incremental_parse

# 配置文件名正则（按优先级匹配）
_FILENAME_PATTERNS = [
    re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3})_running_(.+)\.cfg$", re.IGNORECASE),
    re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3})[-_](.+)\.cfg$", re.IGNORECASE),
    re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3})\.cfg$", re.IGNORECASE),
]

# 已知厂商目录名映射（子目录名 → 标准化厂商名）
VENDOR_DIR_MAP = {
    "h3c": "h3c",
    "huawei": "huawei",
    "cisco": "cisco",
    "nsfocus": "nsfocus",
    "venustech": "venustech",
    "topsec": "topsec",
    "sangfor": "sangfor",
    "hillstone": "hillstone",
    "juniper": "juniper",
    "arista": "arista",
    "fortinet": "fortinet",
    "paloalto": "paloalto",
    "ruijie": "ruijie",
    "zte": "zte",
}

# 配置文件内容关键词 → 厂商识别（用于根目录文件自动检测）
_VENDOR_CONTENT_SIGNATURES = [
    (["irf ", "Comware", "version 7"], "h3c"),
    (["sysname", "interface Vlanif"], "huawei"),
    (["hostname", "interface GigabitEthernet", "no shutdown"], "cisco"),
    (["nsfocus", "ips-policy"], "nsfocus"),
    (["venustech", "vss"], "venustech"),
    (["ruijie", "RGOS"], "ruijie"),
]


def detect_vendor_from_content(content: str) -> str:
    """通过配置文件内容关键词识别厂商"""
    if not content:
        return "unknown"
    # 只取前 2000 字符做识别
    head = content[:2000]
    for keywords, vendor in _VENDOR_CONTENT_SIGNATURES:
        if any(kw in head for kw in keywords):
            return vendor
    return "unknown"


async def get_source_path() -> str:
    """获取只读源目录路径（每日备份源）"""
    db_path = await SystemSetting.get_value("net_config_base_path", "")
    if db_path and db_path.strip():
        return db_path.strip()
    return settings.NET_CONFIG_SOURCE_PATH


async def get_workspace_path() -> str:
    """获取可写工作区路径（AI分析/上传/Git版本）"""
    return settings.NET_CONFIG_WORKSPACE_PATH


def sync_source_to_workspace(source_path: str, workspace_path: str) -> Dict:
    """将只读源目录中的 .cfg 文件同步到可写工作区根目录

    只新增/覆盖，不删除工作区中已有文件（保留用户上传）。
    返回同步统计。
    """
    stats = {"synced": 0, "errors": []}
    if not source_path or not os.path.isdir(source_path):
        return stats

    os.makedirs(workspace_path, exist_ok=True)

    for root, dirs, files in os.walk(source_path):
        # 跳过 .git 目录
        dirs[:] = [d for d in dirs if d != ".git"]
        for filename in files:
            if not filename.lower().endswith(".cfg"):
                continue
            src = os.path.join(root, filename)
            # 源目录中的文件统一放到工作区根目录
            dst = os.path.join(workspace_path, filename)
            try:
                shutil.copy2(src, dst)
                stats["synced"] += 1
            except Exception as e:
                stats["errors"].append(f"{src}: {str(e)[:200]}")

    return stats


def parse_filename(filename: str) -> Optional[Dict]:
    """解析配置文件名，提取 IP 和日期

    支持格式:
      - IP_running_日期.cfg
      - IP_任意描述.cfg
      - IP.cfg
    返回: {"ip": "10.0.0.1", "date": "2026-07-03"} 或 None
    """
    for pattern in _FILENAME_PATTERNS:
        m = pattern.match(filename)
        if m:
            ip = m.group(1)
            date = m.group(2) if pattern.groups >= 2 else ""
            # 简单验证 IP 合法性
            parts = ip.split(".")
            if all(0 <= int(p) <= 255 for p in parts):
                return {"ip": ip, "date": date}
    return None


async def scan_configs() -> Dict:
    """扫描配置目录，解析文件名，upsert 到数据库

    流程：
    1. 将只读源目录同步到可写工作区
    2. 扫描工作区（支持子目录和根目录文件，自动识别厂商）
    3. 提交 Git 版本记录
    返回: {"synced": N, "scanned": N, "created": N, "updated": N, "skipped": N, "errors": [...]}
    """
    source_path = await get_source_path()
    workspace_path = await get_workspace_path()

    os.makedirs(workspace_path, exist_ok=True)

    # 1. 同步源目录到工作区（源目录可选；不存在时跳过同步，继续扫描工作区已有文件）
    sync_stats = {"synced": 0, "errors": []}
    if source_path and os.path.isdir(source_path):
        sync_stats = sync_source_to_workspace(source_path, workspace_path)
    elif source_path:
        sync_stats["errors"].append(f"源配置目录不存在: {source_path}")

    # 2. 扫描工作区
    stats = {"synced": sync_stats["synced"], "scanned": 0, "created": 0, "updated": 0, "skipped": 0, "errors": sync_stats["errors"]}

    async def _scan_dir(dir_path: str, vendor: str, rel_prefix: str):
        """扫描单个目录中的所有 .cfg 文件"""
        for filename in os.listdir(dir_path):
            if not filename.lower().endswith(".cfg"):
                continue

            parsed = parse_filename(filename)
            if not parsed:
                stats["skipped"] += 1
                continue

            stats["scanned"] += 1
            file_full = os.path.join(dir_path, filename)
            file_rel = f"{rel_prefix}{filename}" if rel_prefix else filename
            try:
                file_size = os.path.getsize(file_full)
            except OSError:
                file_size = 0

            # 根目录文件需自动识别厂商
            actual_vendor = vendor
            if not actual_vendor or actual_vendor == "unknown":
                try:
                    with open(file_full, "r", encoding="utf-8", errors="replace") as f:
                        head = f.read(2000)
                    actual_vendor = detect_vendor_from_content(head)
                except Exception:
                    actual_vendor = "unknown"

            # upsert 到数据库
            try:
                async with async_session_factory() as session:
                    result = await session.execute(
                        select(NetConfig).where(
                            NetConfig.vendor == actual_vendor,
                            NetConfig.ip_address == parsed["ip"],
                            NetConfig.file_name == filename,
                        )
                    )
                    existing = result.scalar_one_or_none()
                    if existing:
                        existing.file_path = file_rel
                        existing.file_size = file_size
                        existing.file_date = parsed["date"]
                        stats["updated"] += 1
                    else:
                        session.add(NetConfig(
                            vendor=actual_vendor,
                            ip_address=parsed["ip"],
                            file_name=filename,
                            file_path=file_rel,
                            file_size=file_size,
                            file_date=parsed["date"],
                        ))
                        stats["created"] += 1
                    await session.commit()
            except Exception as e:
                stats["errors"].append(f"{file_rel}: {str(e)[:200]}")

    # 2a. 扫描子目录（子目录名 = 厂商）
    for vendor_dir in sorted(os.listdir(workspace_path)):
        vendor_full = os.path.join(workspace_path, vendor_dir)
        if not os.path.isdir(vendor_full):
            continue
        vendor = VENDOR_DIR_MAP.get(vendor_dir.lower(), vendor_dir.lower())
        await _scan_dir(vendor_full, vendor, f"{vendor_dir}/")

    # 2b. 扫描根目录文件（自动识别厂商）
    await _scan_dir(workspace_path, "", "")

    # 3. 提交到 Git 版本记录（保留最近 10 个版本）
    new_commit = None
    try:
        new_commit = commit_changes(workspace_path, f"扫描网络配置: {stats['scanned']} 个文件", keep=10)
    except Exception as e:
        print(f"[AIOPS] Git 版本提交失败: {e}")

    # 4. 增量解析变更配置到结构化知识库
    try:
        await incremental_parse(workspace_path, new_commit)
    except Exception as e:
        print(f"[AIOPS] 结构化配置同步失败: {e}")

    print(f"[AIOPS] 网络配置扫描完成: {stats}")
    return stats


async def _enrich_with_cmdb(configs: list) -> List[Dict]:
    """根据 IP 关联 CMDB，注入名称和区域信息"""
    if not configs:
        return []
    ip_map = {}
    ips = list(set(c.ip_address for c in configs if c.ip_address))
    if ips:
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(CMDBAsset).where(CMDBAsset.ip_address.in_(ips))
                )
                for asset in result.scalars().all():
                    ip_map[asset.ip_address] = {
                        "name": asset.name,
                        "region": asset.region,
                    }
        except Exception as e:
            print(f"[AIOPS] CMDB 关联失败: {e}")

    return [
        {
            "id": c.id,
            "vendor": c.vendor,
            "ip_address": c.ip_address,
            "file_name": c.file_name,
            "file_path": c.file_path,
            "file_size": c.file_size,
            "file_date": c.file_date,
            "config_summary": c.config_summary,
            "name": ip_map.get(c.ip_address, {}).get("name", ""),
            "region": ip_map.get(c.ip_address, {}).get("region", ""),
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in configs
    ]


async def list_configs(vendor: Optional[str] = None, region: Optional[str] = None, name: Optional[str] = None) -> List[Dict]:
    """获取配置索引列表（从数据库读取，并关联 CMDB 注入名称/区域，支持 vendor/region/name 筛选）"""
    async with async_session_factory() as session:
        query = select(NetConfig)
        if vendor:
            query = query.where(NetConfig.vendor == vendor)

        # region/name 字段来自 CMDB，先按条件查 CMDB 拿到 IP 列表
        if region or name:
            cmdb_query = select(CMDBAsset.ip_address)
            if region:
                cmdb_query = cmdb_query.where(CMDBAsset.region == region)
            if name:
                cmdb_query = cmdb_query.where(CMDBAsset.name.like(f"%{name}%"))
            cmdb_result = await session.execute(cmdb_query)
            cmdb_ips = [row[0] for row in cmdb_result.all() if row[0]]
            if not cmdb_ips:
                return []
            query = query.where(NetConfig.ip_address.in_(cmdb_ips))

        query = query.order_by(NetConfig.vendor, NetConfig.ip_address)
        result = await session.execute(query)
        configs = result.scalars().all()
        return await _enrich_with_cmdb(list(configs))


async def get_vendors() -> List[str]:
    """获取所有已扫描到的厂商列表"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(NetConfig.vendor).distinct().order_by(NetConfig.vendor)
        )
        return [row[0] for row in result.all()]


async def get_config_content(config_id: int) -> Optional[Dict]:
    """获取单个配置的完整内容"""
    workspace_path = await get_workspace_path()
    async with async_session_factory() as session:
        result = await session.execute(
            select(NetConfig).where(NetConfig.id == config_id)
        )
        c = result.scalar_one_or_none()
        if not c:
            return None

        full_path = os.path.join(workspace_path, c.file_path)
        content = ""
        try:
            if os.path.isfile(full_path):
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
        except Exception as e:
            content = f"[读取失败: {str(e)[:200]}]"

        return {
            "id": c.id,
            "vendor": c.vendor,
            "ip_address": c.ip_address,
            "file_name": c.file_name,
            "file_path": c.file_path,
            "file_size": c.file_size,
            "content": content,
        }


async def load_configs(
    vendor: Optional[str] = None,
    ip: Optional[str] = None,
    ids: Optional[List[int]] = None,
) -> List[Dict]:
    """加载配置内容（从 DB 索引 + 本地文件读取）

    支持三种筛选方式：
    - ids: 指定配置记录 ID
    - vendor: 按厂商筛选
    - ip: 按 IP 筛选
    都不传则加载全部
    """
    workspace_path = await get_workspace_path()

    async with async_session_factory() as session:
        query = select(NetConfig)
        if ids:
            query = query.where(NetConfig.id.in_(ids))
        elif vendor and ip:
            query = query.where(NetConfig.vendor == vendor, NetConfig.ip_address == ip)
        elif vendor:
            query = query.where(NetConfig.vendor == vendor)
        elif ip:
            query = query.where(NetConfig.ip_address == ip)

        query = query.order_by(NetConfig.vendor, NetConfig.ip_address)
        result = await session.execute(query)
        configs = result.scalars().all()

        loaded = []
        for c in configs:
            full_path = os.path.join(workspace_path, c.file_path)
            content = ""
            try:
                if os.path.isfile(full_path):
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
            except Exception as e:
                content = f"[读取失败: {str(e)[:200]}]"

            loaded.append({
                "id": c.id,
                "vendor": c.vendor,
                "ip": c.ip_address,
                "filename": c.file_name,
                "file_date": c.file_date,
                "content": content,
            })

        return loaded


async def delete_config(config_id: int) -> bool:
    """删除配置索引及对应的本地文件"""
    workspace_path = await get_workspace_path()
    async with async_session_factory() as session:
        result = await session.execute(select(NetConfig).where(NetConfig.id == config_id))
        config = result.scalar_one_or_none()
        if not config:
            return False

        # 删除本地文件
        full_path = os.path.join(workspace_path, config.file_path)
        try:
            if os.path.isfile(full_path):
                os.remove(full_path)
        except Exception as e:
            print(f"[AIOPS] 删除配置文件失败: {e}")

        await session.delete(config)
        await session.commit()
        return True
