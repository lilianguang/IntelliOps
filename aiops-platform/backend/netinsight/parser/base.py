"""配置解析器基类与结果数据结构"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class InterfaceInfo:
    interface_name: str
    interface_type: str = "physical"
    description: Optional[str] = None
    shutdown: bool = False
    link_type: Optional[str] = None
    access_vlan: Optional[int] = None
    trunk_vlans: Optional[str] = None
    pvid: Optional[int] = None
    lacp_group: Optional[int] = None
    raw_config: str = ""


@dataclass
class IPInfo:
    ip_address: str
    mask: Optional[str] = None
    ip_type: str = "interface"
    interface_name: Optional[str] = None
    vrf: Optional[str] = None
    description: Optional[str] = None
    raw_line: str = ""


@dataclass
class VLANInfo:
    vlan_id: int
    vlan_name: Optional[str] = None
    description: Optional[str] = None
    raw_config: str = ""


@dataclass
class RouteInfo:
    route_type: str = "static"
    destination: Optional[str] = None
    mask: Optional[str] = None
    next_hop: Optional[str] = None
    preference: Optional[int] = None
    cost: Optional[int] = None
    vrf: Optional[str] = None
    raw_line: str = ""


@dataclass
class NATInfo:
    nat_type: str = "server"
    global_ip: Optional[str] = None
    global_port: Optional[int] = None
    local_ip: Optional[str] = None
    local_port: Optional[int] = None
    protocol: Optional[str] = None
    interface_name: Optional[str] = None
    acl_name: Optional[str] = None
    raw_line: str = ""


@dataclass
class ACLInfo:
    acl_name: str
    rule_id: Optional[str] = None
    action: Optional[str] = None
    protocol: Optional[str] = None
    source_ip: Optional[str] = None
    source_port: Optional[str] = None
    dest_ip: Optional[str] = None
    dest_port: Optional[str] = None
    rule_text: str = ""
    raw_line: str = ""


@dataclass
class BGPPeerInfo:
    peer_ip: str
    as_number: Optional[str] = None
    peer_as: Optional[str] = None
    description: Optional[str] = None
    raw_line: str = ""


@dataclass
class OSPFInfo:
    process_id: Optional[str] = None
    area_id: Optional[str] = None
    network: Optional[str] = None
    wildcard: Optional[str] = None
    raw_line: str = ""


@dataclass
class VRRPInfo:
    interface_name: Optional[str] = None
    vrid: Optional[int] = None
    virtual_ip: Optional[str] = None
    priority: Optional[int] = None
    raw_line: str = ""


@dataclass
class MLAGInfo:
    mlag_id: Optional[int] = None
    peer_link: Optional[str] = None
    virtual_ip: Optional[str] = None
    interface_name: Optional[str] = None
    raw_line: str = ""


@dataclass
class LBServerFarmInfo:
    """负载均衡 Server Farm"""
    farm_id: str = ""
    description: Optional[str] = None
    fail_action: Optional[str] = None
    snat_pool: Optional[str] = None
    probe: Optional[str] = None
    raw_config: str = ""


@dataclass
class LBRealServerInfo:
    """负载均衡 Real Server"""
    server_id: str = ""
    ip_address: Optional[str] = None
    port: Optional[int] = None
    server_farm_id: Optional[str] = None
    weight: Optional[int] = None
    raw_config: str = ""


@dataclass
class LBVirtualServerInfo:
    """负载均衡 Virtual Server"""
    server_id: str = ""
    server_type: Optional[str] = None
    description: Optional[str] = None
    vpn_instance: Optional[str] = None
    port: Optional[int] = None
    virtual_ip: Optional[str] = None
    default_server_farm: Optional[str] = None
    route_advertisement: Optional[str] = None
    sticky: Optional[str] = None
    vrrp_vrid: Optional[int] = None
    service: Optional[str] = None
    raw_config: str = ""


@dataclass
class ParsingResult:
    hostname: Optional[str] = None
    interfaces: List[InterfaceInfo] = field(default_factory=list)
    ips: List[IPInfo] = field(default_factory=list)
    vlans: List[VLANInfo] = field(default_factory=list)
    routes: List[RouteInfo] = field(default_factory=list)
    nats: List[NATInfo] = field(default_factory=list)
    acls: List[ACLInfo] = field(default_factory=list)
    bgp_peers: List[BGPPeerInfo] = field(default_factory=list)
    ospf: List[OSPFInfo] = field(default_factory=list)
    vrrp: List[VRRPInfo] = field(default_factory=list)
    mlag: List[MLAGInfo] = field(default_factory=list)
    lb_server_farms: List[LBServerFarmInfo] = field(default_factory=list)
    lb_real_servers: List[LBRealServerInfo] = field(default_factory=list)
    lb_virtual_servers: List[LBVirtualServerInfo] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class BaseConfigParser:
    """配置解析器基类"""

    vendor: str = "unknown"

    def parse(self, content: str) -> ParsingResult:
        """解析配置文本，返回结构化结果

        Args:
            content: 配置文件完整内容

        Returns:
            ParsingResult: 结构化解析结果
        """
        raise NotImplementedError

    @staticmethod
    def _split_blocks(content: str) -> List[str]:
        """把配置按空行切分成段落块"""
        blocks = []
        current = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped == "":
                if current:
                    blocks.append("\n".join(current))
                    current = []
            else:
                current.append(line)
        if current:
            blocks.append("\n".join(current))
        return blocks

    @staticmethod
    def _extract_hostname(content: str) -> Optional[str]:
        """从配置中提取主机名，子类可重写"""
        return None
