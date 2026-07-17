"""H3C Comware 配置解析器"""

import re
from typing import List, Optional, Tuple

from netinsight.parser.base import (
    BaseConfigParser, ParsingResult,
    InterfaceInfo, IPInfo, VLANInfo, RouteInfo,
    NATInfo, ACLInfo, BGPPeerInfo, OSPFInfo,
    VRRPInfo, MLAGInfo,
    LBServerFarmInfo, LBRealServerInfo, LBVirtualServerInfo,
)


class H3CParser(BaseConfigParser):
    """H3C (Comware) 配置解析器

    支持提取：
    - sysname/hostname
    - 接口（物理口、Vlan-interface、LoopBack、Bridge-Aggregation 等）
    - 接口 IP / VRRP / M-LAG 虚拟 IP
    - VLAN
    - 静态路由
    - NAT（server/static）
    - ACL
    - BGP 邻居
    - OSPF 宣告
    """

    vendor = "h3c"

    # 接口名匹配：interface [type] [slot/]name
    _INTERFACE_RE = re.compile(
        r"^interface\s+(\S+)",
        re.IGNORECASE,
    )

    # IP 地址
    _IP_RE = re.compile(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?!\d)")

    # sysname
    _SYSNAME_RE = re.compile(r"^sysname\s+(\S+)", re.IGNORECASE | re.MULTILINE)

    # vlan
    _VLAN_RE = re.compile(r"^vlan\s+(\d+)(?:\s+name\s+(\S+))?", re.IGNORECASE | re.MULTILINE)
    _VLAN_RANGE_RE = re.compile(r"^vlan\s+(\d+)\s+to\s+(\d+)", re.IGNORECASE | re.MULTILINE)

    # ip address
    _IP_ADDRESS_RE = re.compile(
        r"ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)",
        re.IGNORECASE,
    )

    # 静态路由
    _ROUTE_STATIC_RE = re.compile(
        r"ip\s+route-static\s+(\S+)\s+(\S+)\s+(\S+)(?:\s+preference\s+(\d+))?(?:\s+.*)?",
        re.IGNORECASE,
    )

    # NAT server
    _NAT_SERVER_RE = re.compile(
        r"nat\s+server\s+(?:protocol\s+(tcp|udp|icmp)\s+)?"
        r"global\s+(\S+)(?:\s+(\d+))?\s+inside\s+(\S+)(?:\s+(\d+))?",
        re.IGNORECASE,
    )

    # NAT static
    _NAT_STATIC_RE = re.compile(
        r"nat\s+static\s+(inbound|outbound)\s+(\S+)\s+(\S+)(?:\s+(\S+))?",
        re.IGNORECASE,
    )

    # VRRP
    _VRRP_RE = re.compile(
        r"vrrp\s+vrid\s+(\d+)\s+virtual-ip\s+(\d+\.\d+\.\d+\.\d+)",
        re.IGNORECASE,
    )
    _VRRP_PRIORITY_RE = re.compile(
        r"vrrp\s+vrid\s+(\d+)\s+priority\s+(\d+)",
        re.IGNORECASE,
    )

    # M-LAG virtual-ip
    _MLAG_VIP_RE = re.compile(
        r"port\s+m-lag\s+virtual-ip\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)",
        re.IGNORECASE,
    )

    # BGP
    _BGP_RE = re.compile(r"^bgp\s+(\d+)", re.IGNORECASE | re.MULTILINE)
    _BGP_PEER_RE = re.compile(
        r"peer\s+(\d+\.\d+\.\d+\.\d+)\s+as-number\s+(\d+)",
        re.IGNORECASE,
    )
    _BGP_PEER_DESC_RE = re.compile(
        r"peer\s+(\d+\.\d+\.\d+\.\d+)\s+description\s+(.*)",
        re.IGNORECASE,
    )

    # OSPF
    _OSPF_RE = re.compile(r"^ospf\s+(\d+)", re.IGNORECASE | re.MULTILINE)
    _OSPF_AREA_NETWORK_RE = re.compile(
        r"area\s+(\S+)\s+network\s+(\S+)\s+(\S+)",
        re.IGNORECASE,
    )

    # ACL
    _ACL_HEADER_RE = re.compile(
        r"^acl\s+(?:number\s+)?(\S+)",
        re.IGNORECASE | re.MULTILINE,
    )
    _ACL_RULE_RE = re.compile(
        r"^\s*(rule\s+(\S+)\s+)?(permit|deny)\s+(\S+)(?:\s+source\s+(\S+)(?:\s+(\S+))?)?"
        r"(?:\s+destination\s+(\S+)(?:\s+(\S+))?)?(?:\s+source-port\s+(\S+))?"
        r"(?:\s+destination-port\s+(\S+))?",
        re.IGNORECASE,
    )

    def parse(self, content: str) -> ParsingResult:
        result = ParsingResult()
        result.hostname = self._extract_hostname(content)

        try:
            # 1. VLAN
            result.vlans = self._parse_vlans(content)

            # 2. 接口块
            interfaces, interface_ips, vrrps, mlags = self._parse_interfaces(content)
            result.interfaces = interfaces
            result.ips.extend(interface_ips)
            result.vrrp.extend(vrrps)
            result.mlag.extend(mlags)

            # 3. 全局 IP（LoopBack 等已在接口块中处理）
            # 4. 静态路由
            result.routes = self._parse_routes(content)

            # 5. NAT
            result.nats = self._parse_nat(content)

            # 6. ACL
            result.acls = self._parse_acls(content)

            # 7. BGP
            result.bgp_peers = self._parse_bgp(content)

            # 8. OSPF
            result.ospf = self._parse_ospf(content)

            # 9. 负载均衡
            lb_sf, lb_rs, lb_vs = self._parse_load_balancing(content)
            result.lb_server_farms = lb_sf
            result.lb_real_servers = lb_rs
            result.lb_virtual_servers = lb_vs

        except Exception as e:
            result.errors.append(f"解析异常: {str(e)[:200]}")

        return result

    def _extract_hostname(self, content: str) -> Optional[str]:
        m = self._SYSNAME_RE.search(content)
        return m.group(1).strip() if m else None

    def _parse_vlans(self, content: str) -> List[VLANInfo]:
        vlans = []
        seen = set()

        # 单 vlan
        for m in self._VLAN_RE.finditer(content):
            vid = int(m.group(1))
            name = m.group(2)
            if vid not in seen:
                seen.add(vid)
                vlans.append(VLANInfo(vlan_id=vid, vlan_name=name))

        # vlan range
        for m in self._VLAN_RANGE_RE.finditer(content):
            start, end = int(m.group(1)), int(m.group(2))
            for vid in range(start, end + 1):
                if vid not in seen:
                    seen.add(vid)
                    vlans.append(VLANInfo(vlan_id=vid))

        return vlans

    def _parse_interfaces(self, content: str) -> Tuple[List[InterfaceInfo], List[IPInfo], List[VRRPInfo], List[MLAGInfo]]:
        interfaces: List[InterfaceInfo] = []
        ips: List[IPInfo] = []
        vrrps: List[VRRPInfo] = []
        mlags: List[MLAGInfo] = []

        lines = content.splitlines()
        i = 0
        current_if: Optional[InterfaceInfo] = None

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # 检测接口块开始
            m = self._INTERFACE_RE.match(stripped)
            if m:
                if current_if:
                    interfaces.append(current_if)
                if_name = m.group(1)
                current_if = InterfaceInfo(
                    interface_name=if_name,
                    interface_type=self._classify_interface(if_name),
                    raw_config=line,
                )
                i += 1
                continue

            if current_if is not None:
                # 接口块结束：遇到非缩进行（且不是注释）
                if stripped and not line.startswith(" ") and not line.startswith("\t"):
                    interfaces.append(current_if)
                    current_if = None
                    continue

                current_if.raw_config += "\n" + line

                # description
                if stripped.lower().startswith("description "):
                    current_if.description = stripped[len("description "):].strip()

                # shutdown
                if stripped.lower() == "shutdown":
                    current_if.shutdown = True

                # link-type
                if "port link-type" in stripped.lower():
                    parts = stripped.split()
                    if len(parts) >= 3:
                        current_if.link_type = parts[-1].lower()

                # access vlan
                if "port access vlan" in stripped.lower():
                    parts = stripped.split()
                    if len(parts) >= 4:
                        try:
                            current_if.access_vlan = int(parts[-1])
                        except ValueError:
                            pass

                # trunk vlans
                if "port trunk permit vlan" in stripped.lower():
                    # port trunk permit vlan 403
                    # port trunk permit vlan 1 to 10
                    parts = stripped.split()
                    if len(parts) >= 5:
                        current_if.trunk_vlans = " ".join(parts[4:])

                # pvid
                if "port trunk pvid vlan" in stripped.lower():
                    parts = stripped.split()
                    if len(parts) >= 5:
                        try:
                            current_if.pvid = int(parts[-1])
                        except ValueError:
                            pass

                # lacp group
                if "port link-aggregation group" in stripped.lower():
                    parts = stripped.split()
                    if len(parts) >= 4:
                        try:
                            current_if.lacp_group = int(parts[-1])
                        except ValueError:
                            pass

                # ip address
                ip_m = self._IP_ADDRESS_RE.search(stripped)
                if ip_m:
                    ip_addr, mask = ip_m.group(1), ip_m.group(2)
                    ips.append(IPInfo(
                        ip_address=ip_addr,
                        mask=mask,
                        ip_type="interface",
                        interface_name=current_if.interface_name,
                        raw_line=stripped,
                    ))

                # VRRP
                vrrp_m = self._VRRP_RE.search(stripped)
                if vrrp_m:
                    vrid = int(vrrp_m.group(1))
                    vip = vrrp_m.group(2)
                    vrrps.append(VRRPInfo(
                        interface_name=current_if.interface_name,
                        vrid=vrid,
                        virtual_ip=vip,
                        raw_line=stripped,
                    ))
                    ips.append(IPInfo(
                        ip_address=vip,
                        ip_type="vrrp",
                        interface_name=current_if.interface_name,
                        raw_line=stripped,
                    ))

                # VRRP priority
                prio_m = self._VRRP_PRIORITY_RE.search(stripped)
                if prio_m:
                    vrid = int(prio_m.group(1))
                    priority = int(prio_m.group(2))
                    for v in vrrps:
                        if v.interface_name == current_if.interface_name and v.vrid == vrid:
                            v.priority = priority

                # M-LAG virtual-ip
                mlag_m = self._MLAG_VIP_RE.search(stripped)
                if mlag_m:
                    vip, mask = mlag_m.group(1), mlag_m.group(2)
                    mlags.append(MLAGInfo(
                        interface_name=current_if.interface_name,
                        virtual_ip=vip,
                        raw_line=stripped,
                    ))
                    ips.append(IPInfo(
                        ip_address=vip,
                        mask=mask,
                        ip_type="mlag",
                        interface_name=current_if.interface_name,
                        raw_line=stripped,
                    ))

            i += 1

        if current_if:
            interfaces.append(current_if)

        return interfaces, ips, vrrps, mlags

    def _classify_interface(self, name: str) -> str:
        lower = name.lower()
        if lower.startswith("loopback"):
            return "loopback"
        if lower.startswith("vlan-interface") or lower.startswith("vlanif"):
            return "vlan"
        if lower.startswith("bridge-aggregation") or lower.startswith("bagg"):
            return "bridge-aggregation"
        if lower.startswith("null"):
            return "null"
        if lower.startswith("m-gigabitethernet"):
            return "management"
        return "physical"

    def _parse_routes(self, content: str) -> List[RouteInfo]:
        routes = []
        for line in content.splitlines():
            stripped = line.strip()
            m = self._ROUTE_STATIC_RE.match(stripped)
            if m:
                dest, mask_or_nh, nh_or_pref, pref = m.group(1), m.group(2), m.group(3), m.group(4)
                # H3C: ip route-static dest mask next-hop [preference n]
                # dest could be 0.0.0.0, mask could be 0, next-hop is IP or interface
                routes.append(RouteInfo(
                    route_type="static",
                    destination=dest,
                    mask=mask_or_nh,
                    next_hop=nh_or_pref,
                    preference=int(pref) if pref else None,
                    raw_line=stripped,
                ))
        return routes

    def _parse_nat(self, content: str) -> List[NATInfo]:
        nats = []
        for line in content.splitlines():
            stripped = line.strip()

            # nat server protocol tcp global 1.1.1.1 80 inside 192.168.1.1 8080
            m = self._NAT_SERVER_RE.search(stripped)
            if m:
                proto, global_ip, global_port, local_ip, local_port = m.groups()
                nats.append(NATInfo(
                    nat_type="server",
                    protocol=proto.lower() if proto else None,
                    global_ip=global_ip,
                    global_port=int(global_port) if global_port else None,
                    local_ip=local_ip,
                    local_port=int(local_port) if local_port else None,
                    raw_line=stripped,
                ))

            # nat static inbound/outbound ...
            m2 = self._NAT_STATIC_RE.match(stripped)
            if m2:
                direction, ip1, ip2, maybe_acl = m2.groups()
                nats.append(NATInfo(
                    nat_type=f"static_{direction}",
                    global_ip=ip1,
                    local_ip=ip2,
                    acl_name=maybe_acl,
                    raw_line=stripped,
                ))

        return nats

    def _parse_acls(self, content: str) -> List[ACLInfo]:
        acls = []
        lines = content.splitlines()
        current_acl_name: Optional[str] = None

        for line in lines:
            stripped = line.strip()

            # ACL 头
            m = self._ACL_HEADER_RE.match(stripped)
            if m:
                current_acl_name = m.group(1)
                continue

            # ACL 规则
            if current_acl_name:
                m = self._ACL_RULE_RE.match(stripped)
                if m:
                    _, rule_id, action, protocol, src_ip, src_wc, dst_ip, dst_wc, src_port, dst_port = m.groups()
                    acls.append(ACLInfo(
                        acl_name=current_acl_name,
                        rule_id=rule_id,
                        action=action.lower() if action else None,
                        protocol=protocol.lower() if protocol else None,
                        source_ip=src_ip,
                        source_port=src_port,
                        dest_ip=dst_ip,
                        dest_port=dst_port,
                        rule_text=stripped,
                        raw_line=stripped,
                    ))
                elif not line.startswith(" ") and not stripped.startswith("rule"):
                    # ACL 块结束
                    current_acl_name = None

        return acls

    def _parse_bgp(self, content: str) -> List[BGPPeerInfo]:
        peers = []
        lines = content.splitlines()
        in_bgp = False
        local_as = None
        peer_desc_map = {}

        for line in lines:
            stripped = line.strip()

            m = self._BGP_RE.match(stripped)
            if m:
                in_bgp = True
                local_as = m.group(1)
                continue

            if in_bgp:
                if stripped and not line.startswith(" ") and not line.startswith("\t"):
                    in_bgp = False
                    continue

                pm = self._BGP_PEER_RE.search(stripped)
                if pm:
                    peer_ip, peer_as = pm.group(1), pm.group(2)
                    peers.append(BGPPeerInfo(
                        peer_ip=peer_ip,
                        as_number=local_as,
                        peer_as=peer_as,
                        raw_line=stripped,
                    ))

                dm = self._BGP_PEER_DESC_RE.search(stripped)
                if dm:
                    peer_ip, desc = dm.group(1), dm.group(2).strip()
                    peer_desc_map[peer_ip] = desc

        for p in peers:
            if p.peer_ip in peer_desc_map:
                p.description = peer_desc_map[p.peer_ip]

        return peers

    def _parse_ospf(self, content: str) -> List[OSPFInfo]:
        ospf_list = []
        lines = content.splitlines()
        in_ospf = False
        process_id = None

        for line in lines:
            stripped = line.strip()

            m = self._OSPF_RE.match(stripped)
            if m:
                in_ospf = True
                process_id = m.group(1)
                continue

            if in_ospf:
                if stripped and not line.startswith(" ") and not line.startswith("\t"):
                    in_ospf = False
                    continue

                m2 = self._OSPF_AREA_NETWORK_RE.search(stripped)
                if m2:
                    area_id, network, wildcard = m2.groups()
                    ospf_list.append(OSPFInfo(
                        process_id=process_id,
                        area_id=area_id,
                        network=network,
                        wildcard=wildcard,
                        raw_line=stripped,
                    ))

        return ospf_list

    # ================================================================
    #  负载均衡解析
    # ================================================================

    _SF_HEADER_RE = re.compile(
        r"^server-farm\s+(\S+)", re.IGNORECASE,
    )
    _RS_HEADER_RE = re.compile(
        r"^real-server\s+(\S+)", re.IGNORECASE,
    )
    _VS_HEADER_RE = re.compile(
        r"^virtual-server\s+(\S+)(?:\s+type\s+(tcp|udp))?", re.IGNORECASE,
    )

    def _extract_lb_blocks(self, content: str):
        """把配置拆分为 server-farm / real-server / virtual-server 块

        块规则：行首为关键字，缩进行为属性，以 # 或下一个非缩进行结束。
        """
        sf_blocks, rs_blocks, vs_blocks = [], [], []
        lines = content.splitlines()
        current_type = None
        current_lines = []

        for line in lines:
            stripped = line.strip()

            # 检查是否新块开始
            if self._SF_HEADER_RE.match(stripped) and not line.startswith(" ") and not line.startswith("\t"):
                if current_lines:
                    self._store_block(current_type, current_lines, sf_blocks, rs_blocks, vs_blocks)
                current_type = "sf"
                current_lines = [line]
                continue

            if self._RS_HEADER_RE.match(stripped) and not line.startswith(" ") and not line.startswith("\t"):
                if current_lines:
                    self._store_block(current_type, current_lines, sf_blocks, rs_blocks, vs_blocks)
                current_type = "rs"
                current_lines = [line]
                continue

            if self._VS_HEADER_RE.match(stripped) and not line.startswith(" ") and not line.startswith("\t"):
                if current_lines:
                    self._store_block(current_type, current_lines, sf_blocks, rs_blocks, vs_blocks)
                current_type = "vs"
                current_lines = [line]
                continue

            # # 单独一行表示块结束
            if stripped == "#":
                if current_lines:
                    self._store_block(current_type, current_lines, sf_blocks, rs_blocks, vs_blocks)
                current_type = None
                current_lines = []
                continue

            if current_type is not None:
                # 非缩进行且非块关键字 → 块结束
                if stripped and not line.startswith(" ") and not line.startswith("\t"):
                    # 检查是否是其他块类型的关键字
                    if not (self._SF_HEADER_RE.match(stripped) or
                            self._RS_HEADER_RE.match(stripped) or
                            self._VS_HEADER_RE.match(stripped)):
                        self._store_block(current_type, current_lines, sf_blocks, rs_blocks, vs_blocks)
                        current_type = None
                        current_lines = []
                        continue
                current_lines.append(line)

        if current_lines:
            self._store_block(current_type, current_lines, sf_blocks, rs_blocks, vs_blocks)

        return sf_blocks, rs_blocks, vs_blocks

    @staticmethod
    def _store_block(block_type, block_lines, sf_blocks, rs_blocks, vs_blocks):
        if not block_lines:
            return
        text = "\n".join(block_lines)
        if block_type == "sf":
            sf_blocks.append(text)
        elif block_type == "rs":
            rs_blocks.append(text)
        elif block_type == "vs":
            vs_blocks.append(text)

    def _parse_load_balancing(self, content: str):
        """解析负载均衡配置，返回 (server_farms, real_servers, virtual_servers)"""
        sf_blocks, rs_blocks, vs_blocks = self._extract_lb_blocks(content)

        server_farms = []
        for block in sf_blocks:
            first_line = block.splitlines()[0].strip()
            m = self._SF_HEADER_RE.match(first_line)
            if not m:
                continue
            farm_id = m.group(1)
            sf = LBServerFarmInfo(farm_id=farm_id, raw_config=block)
            for line in block.splitlines()[1:]:
                s = line.strip().lower()
                if s.startswith("description "):
                    sf.description = line.strip()[len("description "):].strip()
                elif s.startswith("fail-action "):
                    sf.fail_action = line.strip().split()[-1] if len(line.strip().split()) >= 2 else None
                elif s.startswith("snat-pool "):
                    sf.snat_pool = line.strip().split()[-1] if len(line.strip().split()) >= 2 else None
                elif s.startswith("probe "):
                    sf.probe = line.strip().split()[-1] if len(line.strip().split()) >= 2 else None
            server_farms.append(sf)

        real_servers = []
        for block in rs_blocks:
            first_line = block.splitlines()[0].strip()
            m = self._RS_HEADER_RE.match(first_line)
            if not m:
                continue
            server_id = m.group(1)
            rs = LBRealServerInfo(server_id=server_id, raw_config=block)
            for line in block.splitlines()[1:]:
                s = line.strip().lower()
                if s.startswith("ip address "):
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        rs.ip_address = parts[2]
                elif s.startswith("port "):
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        try:
                            rs.port = int(parts[1])
                        except ValueError:
                            pass
                elif s.startswith("server-farm "):
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        rs.server_farm_id = parts[1]
                elif s.startswith("weight "):
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        try:
                            rs.weight = int(parts[1])
                        except ValueError:
                            pass
            real_servers.append(rs)

        virtual_servers = []
        for block in vs_blocks:
            first_line = block.splitlines()[0].strip()
            m = self._VS_HEADER_RE.match(first_line)
            if not m:
                continue
            server_id, server_type = m.group(1), m.group(2)
            vs = LBVirtualServerInfo(server_id=server_id, server_type=server_type, raw_config=block)
            for line in block.splitlines()[1:]:
                s = line.strip().lower()
                if s.startswith("description "):
                    vs.description = line.strip()[len("description "):].strip()
                elif s.startswith("vpn-instance "):
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        vs.vpn_instance = parts[1]
                elif s.startswith("port "):
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        try:
                            vs.port = int(parts[1])
                        except ValueError:
                            pass
                elif s.startswith("virtual ip address "):
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        vs.virtual_ip = parts[3]
                elif s.startswith("default server-farm "):
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        vs.default_server_farm = parts[2]
                elif s.startswith("route-advertisement "):
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        vs.route_advertisement = parts[1]
                elif s.startswith("sticky "):
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        vs.sticky = parts[1]
                elif s.startswith("vrrp "):
                    parts = line.strip().split()
                    # vrrp vrid 6 interface Route-Aggregation64.501
                    if len(parts) >= 3 and parts[1].lower() == "vrid":
                        try:
                            vs.vrrp_vrid = int(parts[2])
                        except ValueError:
                            pass
                elif s.startswith("service "):
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        vs.service = parts[1]
            virtual_servers.append(vs)

        return server_farms, real_servers, virtual_servers
