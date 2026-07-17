"""网络洞察模型 - 配置索引、系统设置、结构化配置知识库

数据库表：
- net_configs: 配置文件索引
- net_config_sync_state: 已处理的 Git commit 状态
- net_config_interfaces: 接口信息
- net_config_ips: IP 地址（含接口 IP、VRRP、M-LAG、NAT 等）
- net_config_vlans: VLAN 信息
- net_config_routes: 路由信息
- net_config_nat: NAT 映射
- net_config_acls: ACL 规则
- net_config_bgp_peers: BGP 邻居
- net_config_ospf: OSPF 配置
- net_config_vrrp: VRRP/HSRP 信息
- net_config_mlag: M-LAG 信息
- net_config_lb_server_farms: 负载均衡 Server Farm
- net_config_lb_real_servers: 负载均衡 Real Server
- net_config_lb_virtual_servers: 负载均衡 Virtual Server
"""

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, Boolean,
    func, Index, UniqueConstraint, ForeignKey,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from core.db import Base, async_session_factory
from sqlalchemy import select, update


class NetConfig(Base):
    """网络设备配置备份索引"""
    __tablename__ = "net_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor = Column(String(64), nullable=False, comment="厂商: h3c/nsfocus/huawei/cisco等")
    ip_address = Column(String(64), nullable=False, comment="设备IP地址")
    file_name = Column(String(256), nullable=False, comment="文件名")
    file_path = Column(String(512), nullable=False, comment="相对路径(vendor/filename)")
    file_size = Column(BigInteger, default=0, comment="文件大小(字节)")
    file_date = Column(String(32), comment="配置日期(从文件名解析)")
    config_summary = Column(Text, comment="结构化摘要(预留)")

    # 结构化解析相关字段
    content_hash = Column(String(64), comment="文件内容SHA256")
    parsed_at = Column(DateTime, comment="最近一次解析完成时间")
    parse_status = Column(Integer, default=0, comment="0未解析 1成功 2失败")
    parse_error = Column(Text, comment="解析错误信息")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("vendor", "ip_address", "file_name", name="uk_vendor_ip_file"),
        Index("idx_vendor", "vendor"),
        Index("idx_ip", "ip_address"),
        Index("idx_parse_status", "parse_status"),
    )


class NetConfigSyncState(Base):
    """配置同步状态：记录已处理到哪个 Git commit"""
    __tablename__ = "net_config_sync_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    last_processed_commit = Column(String(64), comment="上次处理完的 Git commit hash")
    last_processed_at = Column(DateTime, comment="上次处理时间")
    total_commits_processed = Column(Integer, default=0, comment="累计处理提交数")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SystemSetting(Base):
    """通用系统键值设置"""
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    setting_key = Column(String(128), nullable=False, unique=True)
    setting_value = Column(Text().with_variant(LONGTEXT, "mysql"), comment="设置值（支持 base64 图片等大文本）")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    @staticmethod
    async def get_value(key: str, default: str = "") -> str:
        """读取设置值，不存在返回 default"""
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(SystemSetting.setting_value).where(
                        SystemSetting.setting_key == key
                    )
                )
                row = result.scalar_one_or_none()
                return row if row else default
        except Exception:
            return default

    @staticmethod
    async def set_value(key: str, value: str) -> None:
        """写入或更新设置值（upsert）"""
        async with async_session_factory() as session:
            existing = await session.execute(
                select(SystemSetting).where(SystemSetting.setting_key == key)
            )
            row = existing.scalar_one_or_none()
            if row:
                row.setting_value = value
            else:
                session.add(SystemSetting(setting_key=key, setting_value=value))
            await session.commit()


# ========================================================================
# 结构化配置知识表
# ========================================================================

class NetConfigInterface(Base):
    """网络设备接口信息"""
    __tablename__ = "net_config_interfaces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    net_config_id = Column(Integer, ForeignKey("net_configs.id", ondelete="CASCADE"), nullable=False)
    device_ip = Column(String(64), comment="设备IP")
    vendor = Column(String(64), comment="厂商")
    interface_name = Column(String(128), nullable=False, comment="接口名")
    interface_type = Column(String(64), comment="类型: physical/loopback/vlan/bagg/bridge-aggregation")
    description = Column(String(512), nullable=True, comment="接口描述，可为空")
    shutdown = Column(Boolean, default=False, comment="是否shutdown")
    link_type = Column(String(32), comment="链路类型: access/trunk/hybrid/route")
    access_vlan = Column(Integer, comment="Access VLAN")
    trunk_vlans = Column(String(256), comment="Trunk允许VLAN列表")
    pvid = Column(Integer, comment="PVID")
    lacp_group = Column(Integer, comment="聚合组ID")
    raw_config = Column(Text, comment="该接口原始配置块")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_nci_net_config_id", "net_config_id"),
        Index("idx_nci_device_ip", "device_ip"),
        Index("idx_nci_interface_name", "interface_name"),
        Index("idx_nci_access_vlan", "access_vlan"),
    )


class NetConfigIP(Base):
    """配置中所有 IP 地址"""
    __tablename__ = "net_config_ips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    net_config_id = Column(Integer, ForeignKey("net_configs.id", ondelete="CASCADE"), nullable=False)
    device_ip = Column(String(64), comment="所属设备IP")
    vendor = Column(String(64), comment="厂商")
    ip_address = Column(String(64), nullable=False, comment="IP地址")
    mask = Column(String(64), comment="子网掩码")
    ip_type = Column(String(64), comment="类型: interface/secondary/loopback/virtual/vrrp/mlag/ospf/bgp/nat_static/nat_server")
    interface_name = Column(String(128), comment="关联接口名")
    vrf = Column(String(64), comment="VRF")
    description = Column(String(512), comment="描述")
    raw_line = Column(Text, comment="原始配置行")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_ncip_net_config_id", "net_config_id"),
        Index("idx_ncip_device_ip", "device_ip"),
        Index("idx_ncip_ip_address", "ip_address"),
        Index("idx_ncip_ip_type", "ip_type"),
        Index("idx_ncip_interface_name", "interface_name"),
    )


class NetConfigVLAN(Base):
    """VLAN 信息"""
    __tablename__ = "net_config_vlans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    net_config_id = Column(Integer, ForeignKey("net_configs.id", ondelete="CASCADE"), nullable=False)
    device_ip = Column(String(64), comment="设备IP")
    vlan_id = Column(Integer, nullable=False, comment="VLAN ID")
    vlan_name = Column(String(128), comment="VLAN名称")
    description = Column(String(512), comment="描述")
    raw_config = Column(Text, comment="原始配置块")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_ncv_net_config_id", "net_config_id"),
        Index("idx_ncv_device_ip", "device_ip"),
        Index("idx_ncv_vlan_id", "vlan_id"),
    )


class NetConfigRoute(Base):
    """路由信息"""
    __tablename__ = "net_config_routes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    net_config_id = Column(Integer, ForeignKey("net_configs.id", ondelete="CASCADE"), nullable=False)
    device_ip = Column(String(64), comment="设备IP")
    route_type = Column(String(32), comment="static/ospf/bgp/isis/direct")
    destination = Column(String(128), comment="目的网段")
    mask = Column(String(64), comment="掩码")
    next_hop = Column(String(128), comment="下一跳IP或接口")
    preference = Column(Integer, comment="优先级")
    cost = Column(Integer, comment="开销")
    vrf = Column(String(64), comment="VRF")
    raw_line = Column(Text, comment="原始配置行")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_ncr_net_config_id", "net_config_id"),
        Index("idx_ncr_device_ip", "device_ip"),
        Index("idx_ncr_destination", "destination"),
        Index("idx_ncr_next_hop", "next_hop"),
    )


class NetConfigNAT(Base):
    """NAT 映射信息"""
    __tablename__ = "net_config_nat"

    id = Column(Integer, primary_key=True, autoincrement=True)
    net_config_id = Column(Integer, ForeignKey("net_configs.id", ondelete="CASCADE"), nullable=False)
    device_ip = Column(String(64), comment="设备IP")
    nat_type = Column(String(64), comment="server/static/dynamic/addressgroup")
    global_ip = Column(String(64), comment="公网/全局IP")
    global_port = Column(Integer, comment="全局端口")
    local_ip = Column(String(64), comment="内网IP")
    local_port = Column(Integer, comment="内网端口")
    protocol = Column(String(16), comment="tcp/udp/icmp")
    interface_name = Column(String(128), comment="关联接口")
    acl_name = Column(String(128), comment="关联ACL")
    raw_line = Column(Text, comment="原始配置行")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_ncn_net_config_id", "net_config_id"),
        Index("idx_ncn_device_ip", "device_ip"),
        Index("idx_ncn_global_ip", "global_ip"),
        Index("idx_ncn_local_ip", "local_ip"),
    )


class NetConfigACL(Base):
    """ACL 规则"""
    __tablename__ = "net_config_acls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    net_config_id = Column(Integer, ForeignKey("net_configs.id", ondelete="CASCADE"), nullable=False)
    device_ip = Column(String(64), comment="设备IP")
    acl_name = Column(String(128), comment="ACL名称或编号")
    rule_id = Column(String(64), comment="规则序号")
    action = Column(String(32), comment="permit/deny")
    protocol = Column(String(32), comment="协议")
    source_ip = Column(String(128), comment="源IP")
    source_port = Column(String(64), comment="源端口")
    dest_ip = Column(String(128), comment="目的IP")
    dest_port = Column(String(64), comment="目的端口")
    rule_text = Column(Text, comment="完整规则文本")
    raw_line = Column(Text, comment="原始配置行")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_nca_net_config_id", "net_config_id"),
        Index("idx_nca_device_ip", "device_ip"),
        Index("idx_nca_acl_name", "acl_name"),
    )


class NetConfigBGPPeer(Base):
    """BGP 邻居"""
    __tablename__ = "net_config_bgp_peers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    net_config_id = Column(Integer, ForeignKey("net_configs.id", ondelete="CASCADE"), nullable=False)
    device_ip = Column(String(64), comment="设备IP")
    as_number = Column(String(32), comment="本地AS号")
    peer_ip = Column(String(64), comment="邻居IP")
    peer_as = Column(String(32), comment="邻居AS号")
    description = Column(String(512), comment="描述")
    raw_line = Column(Text, comment="原始配置行")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_ncbp_net_config_id", "net_config_id"),
        Index("idx_ncbp_device_ip", "device_ip"),
        Index("idx_ncbp_peer_ip", "peer_ip"),
    )


class NetConfigOSPF(Base):
    """OSPF 配置"""
    __tablename__ = "net_config_ospf"

    id = Column(Integer, primary_key=True, autoincrement=True)
    net_config_id = Column(Integer, ForeignKey("net_configs.id", ondelete="CASCADE"), nullable=False)
    device_ip = Column(String(64), comment="设备IP")
    process_id = Column(String(32), comment="进程ID")
    area_id = Column(String(32), comment="区域ID")
    network = Column(String(128), comment="宣告网段")
    wildcard = Column(String(64), comment="反掩码")
    raw_line = Column(Text, comment="原始配置行")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_nco_net_config_id", "net_config_id"),
        Index("idx_nco_device_ip", "device_ip"),
        Index("idx_nco_network", "network"),
    )


class NetConfigVRRP(Base):
    """VRRP/HSRP 信息"""
    __tablename__ = "net_config_vrrp"

    id = Column(Integer, primary_key=True, autoincrement=True)
    net_config_id = Column(Integer, ForeignKey("net_configs.id", ondelete="CASCADE"), nullable=False)
    device_ip = Column(String(64), comment="设备IP")
    interface_name = Column(String(128), comment="关联接口")
    vrid = Column(Integer, comment="VRID")
    virtual_ip = Column(String(64), comment="虚拟IP")
    priority = Column(Integer, comment="优先级")
    raw_line = Column(Text, comment="原始配置行")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_ncvrrp_net_config_id", "net_config_id"),
        Index("idx_ncvrrp_device_ip", "device_ip"),
        Index("idx_ncvrrp_virtual_ip", "virtual_ip"),
    )


class NetConfigMLAG(Base):
    """M-LAG 信息"""
    __tablename__ = "net_config_mlag"

    id = Column(Integer, primary_key=True, autoincrement=True)
    net_config_id = Column(Integer, ForeignKey("net_configs.id", ondelete="CASCADE"), nullable=False)
    device_ip = Column(String(64), comment="设备IP")
    mlag_id = Column(Integer, comment="M-LAG ID")
    peer_link = Column(String(128), comment="Peer-link接口")
    virtual_ip = Column(String(64), comment="虚拟IP")
    interface_name = Column(String(128), comment="关联接口")
    raw_line = Column(Text, comment="原始配置行")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_ncm_net_config_id", "net_config_id"),
        Index("idx_ncm_device_ip", "device_ip"),
        Index("idx_ncm_virtual_ip", "virtual_ip"),
    )


# ========================================================================
# 负载均衡配置表
# ========================================================================

class NetConfigLBServerFarm(Base):
    """负载均衡 Server Farm"""
    __tablename__ = "net_config_lb_server_farms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    net_config_id = Column(Integer, ForeignKey("net_configs.id", ondelete="CASCADE"), nullable=False)
    device_ip = Column(String(64), comment="设备IP")
    farm_id = Column(String(256), nullable=False, comment="Server Farm ID")
    description = Column(String(512), comment="描述")
    fail_action = Column(String(64), comment="fail-action: reset/reassign")
    snat_pool = Column(String(256), comment="SNAT池ID")
    probe = Column(String(256), comment="健康检查 Probe ID")
    raw_config = Column(Text, comment="原始配置块")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_nclbsf_net_config_id", "net_config_id"),
        Index("idx_nclbsf_device_ip", "device_ip"),
        Index("idx_nclbsf_farm_id", "farm_id"),
    )


class NetConfigLBRealServer(Base):
    """负载均衡 Real Server"""
    __tablename__ = "net_config_lb_real_servers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    net_config_id = Column(Integer, ForeignKey("net_configs.id", ondelete="CASCADE"), nullable=False)
    device_ip = Column(String(64), comment="设备IP")
    server_id = Column(String(256), nullable=False, comment="Real Server ID")
    ip_address = Column(String(64), comment="后端服务器IP")
    port = Column(Integer, comment="后端服务端口")
    server_farm_id = Column(String(256), comment="关联 Server Farm ID")
    weight = Column(Integer, comment="权重")
    raw_config = Column(Text, comment="原始配置块")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_nclbrs_net_config_id", "net_config_id"),
        Index("idx_nclbrs_device_ip", "device_ip"),
        Index("idx_nclbrs_ip_address", "ip_address"),
        Index("idx_nclbrs_server_farm_id", "server_farm_id"),
    )


class NetConfigLBVirtualServer(Base):
    """负载均衡 Virtual Server"""
    __tablename__ = "net_config_lb_virtual_servers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    net_config_id = Column(Integer, ForeignKey("net_configs.id", ondelete="CASCADE"), nullable=False)
    device_ip = Column(String(64), comment="设备IP")
    server_id = Column(String(256), nullable=False, comment="Virtual Server ID")
    server_type = Column(String(32), comment="类型: tcp/udp")
    description = Column(String(512), comment="描述")
    vpn_instance = Column(String(128), comment="VPN实例")
    port = Column(Integer, comment="监听端口")
    virtual_ip = Column(String(64), comment="虚拟IP (VIP)")
    default_server_farm = Column(String(256), comment="默认 Server Farm ID")
    route_advertisement = Column(String(64), comment="route-advertisement: enable/disable")
    sticky = Column(String(256), comment="会话保持: enable/disable/global")
    vrrp_vrid = Column(Integer, comment="VRRP VRID")
    service = Column(String(64), comment="service: enable/disable")
    raw_config = Column(Text, comment="原始配置块")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_nclbvs_net_config_id", "net_config_id"),
        Index("idx_nclbvs_device_ip", "device_ip"),
        Index("idx_nclbvs_virtual_ip", "virtual_ip"),
        Index("idx_nclbvs_default_server_farm", "default_server_farm"),
    )


# ========================================================================
# 逻辑资源层 - 表列元数据 & 自定义列数据 & 业务IP对应关系
# ========================================================================

from sqlalchemy import JSON


class LogicalTableColumn(Base):
    """逻辑资源层表列元数据"""
    __tablename__ = "logical_table_columns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_name = Column(String(64), nullable=False, comment="表标识")
    field_name = Column(String(128), nullable=False, comment="字段名")
    label = Column(String(64), nullable=False, comment="显示名称")
    column_type = Column(String(32), default="text", comment="text/number/ip/select/tag")
    width = Column(Integer, default=120, comment="列宽(px)")
    visible = Column(Boolean, default=True, comment="是否显示")
    sort_order = Column(Integer, default=0, comment="排序序号")
    is_custom = Column(Boolean, default=False, comment="是否自定义列")
    select_options = Column(Text, comment="下拉选项JSON")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_ltc_table_name", "table_name"),
        UniqueConstraint("table_name", "field_name", name="uk_table_field"),
    )


class LogicalTableCustomData(Base):
    """逻辑资源层自定义列数据"""
    __tablename__ = "logical_table_custom_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_name = Column(String(64), nullable=False, comment="表标识")
    record_id = Column(Integer, nullable=False, comment="原始表的记录ID")
    custom_fields = Column(JSON, comment="自定义列数据")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("table_name", "record_id", name="uk_table_record"),
    )


class IpMappingRelation(Base):
    """业务IP对应关系"""
    __tablename__ = "ip_mapping_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_ip = Column(String(64), comment="外网IP")
    external_port = Column(Integer, comment="外网端口")
    protocol = Column(String(16), comment="协议")
    vpn_instance = Column(String(128), comment="VPN实例")
    internal_ip = Column(String(64), comment="内网IP")
    internal_port = Column(Integer, comment="内网端口")
    business = Column(String(256), comment="业务")
    remarks = Column(Text, comment="备注")
    source = Column(String(32), default="manual", comment="auto=自动解析/manual=手动")
    source_key = Column(String(128), comment="去重键(external_ip:external_port)")
    device_ip = Column(String(64), comment="来源设备IP(参考)")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_imr_external_ip", "external_ip"),
        Index("idx_imr_internal_ip", "internal_ip"),
        Index("idx_imr_source_key", "source_key"),
    )


class LbMappingRelation(Base):
    """负载均衡对应关系"""
    __tablename__ = "lb_mapping_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vip = Column(String(64), comment="VIP")
    vip_port = Column(Integer, comment="VIP端口")
    protocol = Column(String(16), comment="协议")
    vpn_instance = Column(String(128), comment="VPN实例")
    backend_ip = Column(Text, comment="后端IP(逗号分隔)")
    backend_port = Column(Text, comment="后端IP端口(逗号分隔)")
    business = Column(String(256), comment="业务")
    remarks = Column(Text, comment="备注")
    source = Column(String(32), default="manual", comment="auto=自动解析/manual=手动")
    source_key = Column(String(128), comment="去重键(vip:vip_port)")
    device_ip = Column(String(64), comment="来源设备IP(参考)")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_lbm_vip", "vip"),
        Index("idx_lbm_backend_ip", "backend_ip"),
        Index("idx_lbm_source_key", "source_key"),
    )
