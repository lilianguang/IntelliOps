"""迁移脚本：添加负载均衡表到数据库

新增三张表：
- net_config_lb_server_farms: Server Farm 配置
- net_config_lb_real_servers: Real Server 配置
- net_config_lb_virtual_servers: Virtual Server 配置

用法：
  python migrate_lb_tables.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pymysql

# 从环境变量或默认值读取数据库连接
MYSQL_DSN = os.getenv("MYSQL_DSN", "mysql+pymysql://aiops:password@localhost:3306/aiops")

# 解析 DSN
# mysql+aiomysql://aiops:password@mysql:3306/aiops?charset=utf8mb4
parts = MYSQL_DSN.split("://")[1]  # aiops:password@mysql:3306/aiops?charset=utf8mb4
# 去掉查询字符串
if "?" in parts:
    parts = parts.split("?")[0]
user_pass, rest = parts.split("@")
user, password = user_pass.split(":")
host_port, db = rest.split("/")
if ":" in host_port:
    host, port = host_port.split(":")
    port = int(port)
else:
    host, port = host_port, 3306

print(f"连接数据库: {host}:{port}/{db} ...")
conn = pymysql.connect(host=host, port=port, user=user, password=password, database=db)
cursor = conn.cursor()

tables = [
    """
    CREATE TABLE IF NOT EXISTS net_config_lb_server_farms (
        id INT AUTO_INCREMENT PRIMARY KEY,
        net_config_id INT NOT NULL COMMENT '关联配置ID',
        device_ip VARCHAR(64) COMMENT '设备IP',
        farm_id VARCHAR(256) NOT NULL COMMENT 'Server Farm ID',
        description VARCHAR(512) COMMENT '描述',
        fail_action VARCHAR(64) COMMENT 'fail-action: reset/reassign',
        snat_pool VARCHAR(256) COMMENT 'SNAT池ID',
        probe VARCHAR(256) COMMENT '健康检查 Probe ID',
        raw_config TEXT COMMENT '原始配置块',
        created_at DATETIME DEFAULT NOW(),
        updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
        INDEX idx_nclbsf_net_config_id (net_config_id),
        INDEX idx_nclbsf_device_ip (device_ip),
        INDEX idx_nclbsf_farm_id (farm_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='负载均衡 Server Farm'
    """,
    """
    CREATE TABLE IF NOT EXISTS net_config_lb_real_servers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        net_config_id INT NOT NULL COMMENT '关联配置ID',
        device_ip VARCHAR(64) COMMENT '设备IP',
        server_id VARCHAR(256) NOT NULL COMMENT 'Real Server ID',
        ip_address VARCHAR(64) COMMENT '后端服务器IP',
        port INT COMMENT '后端服务端口',
        server_farm_id VARCHAR(256) COMMENT '关联 Server Farm ID',
        weight INT COMMENT '权重',
        raw_config TEXT COMMENT '原始配置块',
        created_at DATETIME DEFAULT NOW(),
        updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
        INDEX idx_nclbrs_net_config_id (net_config_id),
        INDEX idx_nclbrs_device_ip (device_ip),
        INDEX idx_nclbrs_ip_address (ip_address),
        INDEX idx_nclbrs_server_farm_id (server_farm_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='负载均衡 Real Server'
    """,
    """
    CREATE TABLE IF NOT EXISTS net_config_lb_virtual_servers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        net_config_id INT NOT NULL COMMENT '关联配置ID',
        device_ip VARCHAR(64) COMMENT '设备IP',
        server_id VARCHAR(256) NOT NULL COMMENT 'Virtual Server ID',
        server_type VARCHAR(32) COMMENT '类型: tcp/udp',
        description VARCHAR(512) COMMENT '描述',
        vpn_instance VARCHAR(128) COMMENT 'VPN实例',
        port INT COMMENT '监听端口',
        virtual_ip VARCHAR(64) COMMENT '虚拟IP (VIP)',
        default_server_farm VARCHAR(256) COMMENT '默认 Server Farm ID',
        route_advertisement VARCHAR(64) COMMENT 'route-advertisement: enable/disable',
        sticky VARCHAR(256) COMMENT '会话保持: enable/disable/global',
        vrrp_vrid INT COMMENT 'VRRP VRID',
        service VARCHAR(64) COMMENT 'service: enable/disable',
        raw_config TEXT COMMENT '原始配置块',
        created_at DATETIME DEFAULT NOW(),
        updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
        INDEX idx_nclbvs_net_config_id (net_config_id),
        INDEX idx_nclbvs_device_ip (device_ip),
        INDEX idx_nclbvs_virtual_ip (virtual_ip),
        INDEX idx_nclbvs_default_server_farm (default_server_farm)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='负载均衡 Virtual Server'
    """,
]

for sql in tables:
    cursor.execute(sql)
    table_name = sql.split("TABLE IF NOT EXISTS ")[1].split(" (")[0].strip()
    print(f"  ✅ 表 {table_name} 已就绪")

conn.commit()
cursor.close()
conn.close()
print("迁移完成！")
