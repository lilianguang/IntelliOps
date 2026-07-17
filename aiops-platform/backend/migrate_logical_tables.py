"""迁移脚本：创建逻辑资源层3张新表 + 初始化13张表的列元数据"""

import asyncio
import pymysql
import re
from config.settings import settings


def parse_dsn(dsn: str):
    """从 SQLAlchemy DSN 解析 pymysql 连接参数"""
    # mysql+aiomysql://user:pass@host:port/db?charset=utf8mb4
    m = re.match(r"mysql\+\w+://([^:]+):([^@]+)@([^:/]+):?(\d+)?/([^?]+)", dsn)
    if not m:
        raise ValueError(f"无法解析 DSN: {dsn}")
    return {
        "user": m.group(1),
        "password": m.group(2),
        "host": m.group(3),
        "port": int(m.group(4) or 3306),
        "database": m.group(5),
    }


# 13张表的列元数据定义
TABLE_META = {
    "interfaces": [
        ("device_ip", "设备IP", "ip", 130),
        ("interface_name", "接口名", "text", 180),
        ("interface_type", "接口类型", "text", 100),
        ("description", "描述", "text", 200),
        ("shutdown", "是否关闭", "tag", 80),
        ("link_type", "链路类型", "text", 90),
        ("access_vlan", "Access VLAN", "number", 110),
        ("trunk_vlans", "Trunk VLANs", "text", 150),
        ("pvid", "PVID", "number", 80),
        ("lacp_group", "聚合组", "number", 90),
    ],
    "ips": [
        ("device_ip", "设备IP", "ip", 130),
        ("ip_address", "IP地址", "ip", 140),
        ("mask", "子网掩码", "text", 130),
        ("ip_type", "IP类型", "tag", 100),
        ("interface_name", "接口名", "text", 180),
        ("vrf", "VRF", "text", 100),
        ("description", "描述", "text", 200),
    ],
    "vlans": [
        ("device_ip", "设备IP", "ip", 130),
        ("vlan_id", "VLAN ID", "number", 90),
        ("vlan_name", "VLAN名称", "text", 150),
        ("description", "描述", "text", 200),
    ],
    "routes": [
        ("device_ip", "设备IP", "ip", 130),
        ("route_type", "路由类型", "tag", 90),
        ("destination", "目的网段", "text", 140),
        ("mask", "掩码", "text", 130),
        ("next_hop", "下一跳", "ip", 140),
        ("preference", "优先级", "number", 80),
        ("cost", "开销", "number", 80),
        ("vrf", "VRF", "text", 100),
    ],
    "nat": [
        ("device_ip", "设备IP", "ip", 130),
        ("nat_type", "NAT类型", "tag", 90),
        ("global_ip", "公网IP", "ip", 130),
        ("global_port", "公网端口", "number", 90),
        ("local_ip", "内网IP", "ip", 130),
        ("local_port", "内网端口", "number", 90),
        ("protocol", "协议", "tag", 80),
        ("interface_name", "接口", "text", 150),
        ("acl_name", "ACL", "text", 100),
    ],
    "acls": [
        ("device_ip", "设备IP", "ip", 130),
        ("acl_name", "ACL名称", "text", 130),
        ("rule_id", "规则序号", "text", 80),
        ("action", "动作", "tag", 80),
        ("protocol", "协议", "tag", 80),
        ("source_ip", "源IP", "ip", 130),
        ("source_port", "源端口", "text", 80),
        ("dest_ip", "目的IP", "ip", 130),
        ("dest_port", "目的端口", "text", 80),
    ],
    "bgp": [
        ("device_ip", "设备IP", "ip", 130),
        ("as_number", "本地AS", "text", 90),
        ("peer_ip", "邻居IP", "ip", 130),
        ("peer_as", "邻居AS", "text", 90),
        ("description", "描述", "text", 200),
    ],
    "ospf": [
        ("device_ip", "设备IP", "ip", 130),
        ("process_id", "进程ID", "text", 80),
        ("area_id", "区域ID", "text", 100),
        ("network", "宣告网段", "text", 140),
        ("wildcard", "反掩码", "text", 130),
    ],
    "vrrp": [
        ("device_ip", "设备IP", "ip", 130),
        ("interface_name", "接口", "text", 180),
        ("vrid", "VRID", "number", 80),
        ("virtual_ip", "虚拟IP", "ip", 130),
        ("priority", "优先级", "number", 80),
    ],
    "mlag": [
        ("device_ip", "设备IP", "ip", 130),
        ("mlag_id", "M-LAG ID", "number", 90),
        ("peer_link", "Peer-link", "text", 150),
        ("virtual_ip", "虚拟IP", "ip", 130),
        ("interface_name", "接口", "text", 180),
    ],
    "lb_server_farms": [
        ("device_ip", "设备IP", "ip", 130),
        ("farm_id", "Farm ID", "text", 250),
        ("description", "描述", "text", 200),
        ("fail_action", "Fail Action", "tag", 100),
        ("probe", "健康检查", "text", 150),
    ],
    "lb_real_servers": [
        ("device_ip", "设备IP", "ip", 130),
        ("server_id", "Server ID", "text", 250),
        ("ip_address", "后端IP", "ip", 130),
        ("port", "端口", "number", 80),
        ("server_farm_id", "Server Farm", "text", 250),
        ("weight", "权重", "number", 80),
    ],
    "lb_virtual_servers": [
        ("device_ip", "设备IP", "ip", 130),
        ("server_id", "Server ID", "text", 250),
        ("server_type", "类型", "tag", 80),
        ("description", "描述", "text", 150),
        ("vpn_instance", "VPN实例", "text", 100),
        ("port", "监听端口", "number", 90),
        ("virtual_ip", "VIP", "ip", 130),
        ("default_server_farm", "Server Farm", "text", 250),
        ("service", "服务状态", "tag", 90),
    ],
}


async def run_migration():
    dsn = parse_dsn(settings.MYSQL_DSN)
    conn = pymysql.connect(**dsn, charset="utf8mb4")
    cur = conn.cursor()

    print("[迁移] 创建 3 张新表...")

    # 1. logical_table_columns
    cur.execute("""
    CREATE TABLE IF NOT EXISTS logical_table_columns (
        id INT AUTO_INCREMENT PRIMARY KEY,
        table_name VARCHAR(64) NOT NULL COMMENT '表标识',
        field_name VARCHAR(128) NOT NULL COMMENT '字段名',
        label VARCHAR(64) NOT NULL COMMENT '显示名称',
        column_type VARCHAR(32) DEFAULT 'text' COMMENT 'text/number/ip/select/tag',
        width INT DEFAULT 120 COMMENT '列宽(px)',
        visible TINYINT(1) DEFAULT 1 COMMENT '是否显示',
        sort_order INT DEFAULT 0 COMMENT '排序序号',
        is_custom TINYINT(1) DEFAULT 0 COMMENT '是否自定义列',
        select_options TEXT COMMENT '下拉选项JSON',
        created_at DATETIME DEFAULT NOW(),
        updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
        UNIQUE KEY uk_table_field (table_name, field_name),
        INDEX idx_ltc_table_name (table_name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='逻辑资源层表列元数据';
    """)

    # 2. logical_table_custom_data
    cur.execute("""
    CREATE TABLE IF NOT EXISTS logical_table_custom_data (
        id INT AUTO_INCREMENT PRIMARY KEY,
        table_name VARCHAR(64) NOT NULL COMMENT '表标识',
        record_id INT NOT NULL COMMENT '原始表的记录ID',
        custom_fields JSON COMMENT '自定义列数据',
        created_at DATETIME DEFAULT NOW(),
        updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
        UNIQUE KEY uk_table_record (table_name, record_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='逻辑资源层自定义列数据';
    """)

    # 3. ip_mapping_relations
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ip_mapping_relations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        external_ip VARCHAR(64) COMMENT '外网IP',
        external_port INT COMMENT '外网端口',
        protocol VARCHAR(16) COMMENT 'tcp/udp',
        vip_ip VARCHAR(64) COMMENT 'VIP',
        vip_port INT COMMENT 'VIP端口',
        service_name VARCHAR(256) COMMENT '业务名称',
        server_farm VARCHAR(256) COMMENT 'Server Farm',
        backend_ips TEXT COMMENT '后端服务器IP列表(JSON)',
        internal_ip VARCHAR(64) COMMENT '内网IP',
        internal_port INT COMMENT '内网端口',
        device_ip VARCHAR(64) COMMENT '所属设备',
        source VARCHAR(32) DEFAULT 'manual' COMMENT 'auto=解析/manual=手动',
        remarks TEXT COMMENT '备注',
        created_at DATETIME DEFAULT NOW(),
        updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
        INDEX idx_imr_external_ip (external_ip),
        INDEX idx_imr_vip_ip (vip_ip),
        INDEX idx_imr_internal_ip (internal_ip)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='业务IP对应关系（手动维护）';
    """)

    # 4. 初始化列元数据
    print("[迁移] 初始化 13 张表的列元数据...")
    total_inserted = 0
    for table_name, columns in TABLE_META.items():
        for order, (field_name, label, col_type, width) in enumerate(columns):
            cur.execute("""
                INSERT IGNORE INTO logical_table_columns
                (table_name, field_name, label, column_type, width, visible, sort_order, is_custom)
                VALUES (%s, %s, %s, %s, %s, 1, %s, 0)
            """, (table_name, field_name, label, col_type, width, order))
            if cur.rowcount > 0:
                total_inserted += 1

    conn.commit()
    print(f"[迁移] 完成！新增列元数据 {total_inserted} 条")

    cur.close()
    conn.close()


if __name__ == "__main__":
    asyncio.run(run_migration())
