"""迁移脚本：逻辑资源层重构
1. 重建 ip_mapping_relations 表（新字段）
2. 创建 lb_mapping_relations 表
3. 清理 logical_table_columns（移除8张表元数据）
4. 初始化 ip_mapping / lb_mapping 列元数据
"""

import asyncio
import pymysql
import re
from config.settings import settings


def parse_dsn(dsn: str):
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


# 保留的通用表列元数据
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
    "ip_mapping": [
        ("external_ip", "外网IP", "ip", 130),
        ("external_port", "外网端口", "number", 90),
        ("protocol", "协议", "tag", 80),
        ("vpn_instance", "VPN实例", "text", 120),
        ("internal_ip", "内网IP", "ip", 130),
        ("internal_port", "内网端口", "number", 90),
        ("business", "业务", "text", 150),
        ("remarks", "备注", "text", 150),
    ],
    "lb_mapping": [
        ("vip", "VIP", "ip", 130),
        ("vip_port", "VIP端口", "number", 90),
        ("protocol", "协议", "tag", 80),
        ("vpn_instance", "VPN实例", "text", 120),
        ("backend_ip", "后端IP", "text", 200),
        ("backend_port", "后端IP端口", "text", 120),
        ("business", "业务", "text", 150),
        ("remarks", "备注", "text", 150),
    ],
}

# 需要移除列元数据的8张表
REMOVED_TABLES = ["vlans", "routes", "nat", "acls", "bgp", "ospf", "vrrp", "mlag",
                  "lb_server_farms", "lb_real_servers", "lb_virtual_servers"]


async def run_migration():
    dsn = parse_dsn(settings.MYSQL_DSN)
    conn = pymysql.connect(**dsn, charset="utf8mb4")
    cur = conn.cursor()

    # 1. 重建 ip_mapping_relations
    print("[迁移] 重建 ip_mapping_relations 表...")
    cur.execute("DROP TABLE IF EXISTS ip_mapping_relations")
    cur.execute("""
    CREATE TABLE ip_mapping_relations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        external_ip VARCHAR(64) COMMENT '外网IP',
        external_port INT COMMENT '外网端口',
        protocol VARCHAR(16) COMMENT '协议',
        vpn_instance VARCHAR(128) COMMENT 'VPN实例',
        internal_ip VARCHAR(64) COMMENT '内网IP',
        internal_port INT COMMENT '内网端口',
        business VARCHAR(256) COMMENT '业务',
        remarks TEXT COMMENT '备注',
        source VARCHAR(32) DEFAULT 'manual' COMMENT 'auto=自动解析/manual=手动',
        source_key VARCHAR(128) COMMENT '去重键(external_ip:external_port:protocol)',
        device_ip VARCHAR(64) COMMENT '来源设备IP(参考)',
        created_at DATETIME DEFAULT NOW(),
        updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
        INDEX idx_imr_external_ip (external_ip),
        INDEX idx_imr_internal_ip (internal_ip),
        INDEX idx_imr_source_key (source_key),
        UNIQUE KEY uk_imr_source_key (source_key)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='地址映射';
    """)

    # 2. 重建 lb_mapping_relations（去重键已改为 vip:vip_port:protocol）
    print("[迁移] 重建 lb_mapping_relations 表...")
    cur.execute("DROP TABLE IF EXISTS lb_mapping_relations")
    cur.execute("""
    CREATE TABLE lb_mapping_relations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        vip VARCHAR(64) COMMENT 'VIP',
        vip_port INT COMMENT 'VIP端口',
        protocol VARCHAR(16) COMMENT '协议',
        vpn_instance VARCHAR(128) COMMENT 'VPN实例',
        backend_ip TEXT COMMENT '后端IP(逗号分隔)',
        backend_port TEXT COMMENT '后端IP端口(逗号分隔)',
        business VARCHAR(256) COMMENT '业务',
        remarks TEXT COMMENT '备注',
        source VARCHAR(32) DEFAULT 'manual' COMMENT 'auto=自动解析/manual=手动',
        source_key VARCHAR(128) COMMENT '去重键(vip:vip_port:protocol)',
        device_ip VARCHAR(64) COMMENT '来源设备IP(参考)',
        created_at DATETIME DEFAULT NOW(),
        updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
        INDEX idx_lbm_vip (vip),
        INDEX idx_lbm_backend_ip (backend_ip(64)),
        INDEX idx_lbm_source_key (source_key),
        UNIQUE KEY uk_lbm_source_key (source_key)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='负载均衡';
    """)

    # 3. 清理已移除表的列元数据
    print("[迁移] 清理已移除表的列元数据...")
    placeholders = ",".join(["%s"] * len(REMOVED_TABLES))
    cur.execute(f"DELETE FROM logical_table_columns WHERE table_name IN ({placeholders})", REMOVED_TABLES)
    deleted = cur.rowcount
    print(f"  删除 {deleted} 条旧列元数据")

    # 4. 确保保留的表元数据存在（upsert）
    print("[迁移] 初始化列元数据（interfaces, ips, ip_mapping, lb_mapping）...")
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

    # 5. 同步已有列元数据的新字段（如果 ip_mapping 旧字段存在，更新为新字段）
    # 先删除 ip_mapping 可能的旧字段（如果之前有初始化过）
    cur.execute("DELETE FROM logical_table_columns WHERE table_name = 'ip_mapping'")
    cur.execute("DELETE FROM logical_table_columns WHERE table_name = 'lb_mapping'")
    # 重新插入
    for table_name in ["ip_mapping", "lb_mapping"]:
        columns = TABLE_META[table_name]
        for order, (field_name, label, col_type, width) in enumerate(columns):
            cur.execute("""
                INSERT INTO logical_table_columns
                (table_name, field_name, label, column_type, width, visible, sort_order, is_custom)
                VALUES (%s, %s, %s, %s, %s, 1, %s, 0)
            """, (table_name, field_name, label, col_type, width, order))
            total_inserted += 1

    conn.commit()
    print(f"[迁移] 完成！新增列元数据 {total_inserted} 条")

    cur.close()
    conn.close()


if __name__ == "__main__":
    asyncio.run(run_migration())
