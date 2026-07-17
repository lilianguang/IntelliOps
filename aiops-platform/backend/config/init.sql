-- AIOps 智能运维平台 - 数据库初始化脚本
-- 适用版本: v3.0

-- 创建数据库
CREATE DATABASE IF NOT EXISTS aiops DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE aiops;

-- ============================================================
-- V2.0 原有表
-- ============================================================

-- 技能配置表
CREATE TABLE IF NOT EXISTS skills (
    id INT AUTO_INCREMENT PRIMARY KEY,
    datasource_id INT COMMENT '关联数据源ID',
    ds_type VARCHAR(32) DEFAULT 'es' COMMENT '数据源类型: es/prometheus/...',
    skill_name VARCHAR(64) NOT NULL UNIQUE COMMENT '技能标识',
    display_name VARCHAR(64) NOT NULL COMMENT '展示名称',
    description VARCHAR(255) COMMENT '功能描述',
    index_pattern VARCHAR(128) COMMENT 'ES索引模式(兼容旧版)',
    field_schema TEXT COMMENT 'ES字段说明JSON：[{name,type,desc,example}]',
    query_filter TEXT COMMENT 'ES查询过滤条件JSON：{logic:AND/OR,conditions:[{field,operator,value}]}',
    query_config JSON COMMENT '查询配置(按ds_type动态结构)',
    prompt_template VARCHAR(64) NOT NULL COMMENT 'Prompt模板文件名',
    model VARCHAR(32) DEFAULT 'qwen3' COMMENT '默认模型',
    scan_interval_sec INT DEFAULT 300 COMMENT '扫描间隔(秒)',
    keyword_matching TINYINT(1) DEFAULT 1 COMMENT '启用关键字匹配',
    anomaly_detection TINYINT(1) DEFAULT 0 COMMENT '启用AI异常检测',
    enabled TINYINT(1) DEFAULT 1 COMMENT '是否启用',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    INDEX idx_enabled (enabled),
    INDEX idx_pattern (index_pattern),
    INDEX idx_datasource (datasource_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='技能配置';

-- 数据源配置表
CREATE TABLE IF NOT EXISTS datasources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL COMMENT '数据源名称',
    ds_type VARCHAR(32) NOT NULL COMMENT '类型: es/mysql/redis',
    host VARCHAR(256) NOT NULL,
    port INT NOT NULL,
    username VARCHAR(128),
    password VARCHAR(256),
    extra_config JSON COMMENT '额外配置',
    enabled TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据源配置';

-- 大模型配置表
CREATE TABLE IF NOT EXISTS llm_configs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL COMMENT '配置名称',
    model_name VARCHAR(64) NOT NULL COMMENT '模型名称',
    api_base VARCHAR(256) NOT NULL COMMENT 'API地址',
    api_key VARCHAR(256) NOT NULL COMMENT 'API密钥',
    temperature FLOAT DEFAULT 0.7,
    priority INT DEFAULT 0 COMMENT '优先级: 0=主, 1=备',
    enabled TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='大模型配置';

-- 告警渠道配置表
CREATE TABLE IF NOT EXISTS alert_channels (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL COMMENT '渠道名称',
    channel_type VARCHAR(32) NOT NULL COMMENT '类型: dingtalk/email/webhook',
    config JSON NOT NULL COMMENT '渠道配置',
    enabled TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='告警渠道配置';

-- 事件关键字表 (v3.0 可废弃，合并到 rules 表)
CREATE TABLE IF NOT EXISTS event_keywords (
    id INT AUTO_INCREMENT PRIMARY KEY,
    skill_id INT NOT NULL COMMENT '关联技能ID',
    keyword VARCHAR(128) NOT NULL COMMENT '关键字',
    match_type ENUM('exact','contains','regex') DEFAULT 'contains',
    risk_level ENUM('low','medium','high','critical') DEFAULT 'medium',
    enabled TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='事件关键字';

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,
    display_name VARCHAR(64),
    role ENUM('admin','config','audit','user') NOT NULL DEFAULT 'user',
    email VARCHAR(128),
    phone VARCHAR(32),
    enabled TINYINT(1) DEFAULT 1,
    last_login DATETIME,
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    INDEX idx_role (role),
    INDEX idx_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户';

-- 对话记录表
CREATE TABLE IF NOT EXISTS conversations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conversation_id VARCHAR(36) NOT NULL UNIQUE COMMENT '对话UUID',
    tenant VARCHAR(64) COMMENT '租户',
    user VARCHAR(64) COMMENT '用户',
    skill VARCHAR(64) COMMENT '技能标识',
    title VARCHAR(128) COMMENT '会话标题',
    query TEXT COMMENT '用户问题',
    summary TEXT COMMENT 'AI摘要',
    risk_level ENUM('low','medium','high','critical') DEFAULT 'low',
    full_report JSON COMMENT '完整报告',
    archived TINYINT(1) DEFAULT 0 COMMENT '是否归档: 0=否, 1=是',
    messages JSON COMMENT '多轮消息数组: [{role,content,risk_level,created_at}]',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    INDEX idx_archived (archived),
    INDEX idx_created (created_at),
    INDEX idx_user (user)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话记录';

-- 分析报告表
CREATE TABLE IF NOT EXISTS reports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conversation_id VARCHAR(36) NOT NULL COMMENT '关联对话ID',
    report_content JSON NOT NULL COMMENT '报告内容',
    created_at DATETIME DEFAULT NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='分析报告';

-- 事件主表
CREATE TABLE IF NOT EXISTS events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(36) NOT NULL UNIQUE COMMENT '事件UUID',
    skill_id INT NOT NULL COMMENT '关联技能',
    event_type VARCHAR(64) NOT NULL COMMENT '事件类型',
    risk_level ENUM('low','medium','high','critical') NOT NULL,
    summary TEXT COMMENT '事件摘要',
    source_device VARCHAR(128) COMMENT '源设备',
    source_ip VARCHAR(64) COMMENT '源IP',
    raw_log TEXT COMMENT '原始日志',
    ai_report JSON COMMENT 'AI分析报告',
    status ENUM('new','acknowledged','resolved','ignored') DEFAULT 'new',
    occurrence_count INT DEFAULT 1 COMMENT '发生次数',
    first_seen DATETIME NOT NULL COMMENT '首次发现',
    last_seen DATETIME NOT NULL COMMENT '最近发现',
    created_at DATETIME DEFAULT NOW(),
    INDEX idx_skill (skill_id),
    INDEX idx_risk (risk_level),
    INDEX idx_status (status),
    INDEX idx_last_seen (last_seen),
    INDEX idx_device (source_ip)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='事件主表';

-- 事件去重指纹表
CREATE TABLE IF NOT EXISTS event_fingerprints (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    fingerprint VARCHAR(64) NOT NULL UNIQUE COMMENT 'MD5指纹',
    event_id VARCHAR(36) NOT NULL COMMENT '关联事件',
    first_seen DATETIME NOT NULL,
    last_seen DATETIME NOT NULL,
    count INT DEFAULT 1,
    suppressed TINYINT(1) DEFAULT 0 COMMENT '是否被风暴抑制',
    created_at DATETIME DEFAULT NOW(),
    INDEX idx_fingerprint (fingerprint),
    INDEX idx_suppressed (suppressed)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='事件去重指纹';

-- 告警日志表
CREATE TABLE IF NOT EXISTS alert_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(36) NOT NULL,
    channel_id INT NOT NULL,
    status VARCHAR(32) COMMENT 'success/failed',
    result TEXT,
    error_msg TEXT,
    created_at DATETIME DEFAULT NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='告警日志';

-- 审计日志表
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    username VARCHAR(64) NOT NULL,
    action VARCHAR(64) NOT NULL COMMENT '操作类型',
    target VARCHAR(128) COMMENT '操作对象',
    detail JSON COMMENT '操作详情',
    ip_address VARCHAR(64),
    created_at DATETIME DEFAULT NOW(),
    INDEX idx_user (user_id),
    INDEX idx_action (action),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='审计日志';

-- ============================================================
-- V3.0 新增表
-- ============================================================

-- 规则配置表
CREATE TABLE IF NOT EXISTS rules (
    id INT AUTO_INCREMENT PRIMARY KEY,
    rule_name VARCHAR(64) NOT NULL COMMENT '规则名称',
    skill_id INT NOT NULL COMMENT '关联技能ID',
    rule_type ENUM(
        'severity_filter',
        'command_monitor',
        'dangerous_command',
        'http_status_alert',
        'response_time_alert',
        'keyword_match',
        'ai_analysis_trigger',
        'ignore_rule',
        'metric_threshold'
    ) NOT NULL COMMENT '规则类型',
    match_condition JSON NOT NULL COMMENT '匹配条件',
    exclude_condition JSON COMMENT '排除条件',
    risk_level ENUM('low','medium','high','critical') DEFAULT 'medium',
    action_config JSON NOT NULL COMMENT '动作配置',
    priority INT DEFAULT 0 COMMENT '优先级(越小越优先)',
    enabled TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    INDEX idx_skill (skill_id),
    INDEX idx_type (rule_type),
    INDEX idx_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='规则配置(v3.0)';

-- 告警风暴配置表
CREATE TABLE IF NOT EXISTS alert_storm_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    skill_id INT NOT NULL,
    rule_id INT COMMENT '关联规则(NULL=全局)',
    window_minutes INT DEFAULT 5 COMMENT '时间窗口(分钟)',
    max_count INT DEFAULT 10 COMMENT '窗口内最大告警次数',
    action_on_storm ENUM('digest','suppress','escalate') DEFAULT 'digest',
    enabled TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT NOW(),
    INDEX idx_skill (skill_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='告警风暴配置(v3.0)';

-- AI分析配置表
CREATE TABLE IF NOT EXISTS ai_analysis_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    skill_id INT NOT NULL,
    trigger_type ENUM('periodic','on_alert','severity_match','command_match','manual') NOT NULL,
    cron_expression VARCHAR(32) COMMENT 'cron表达式',
    analysis_type VARCHAR(32) NOT NULL COMMENT '分析类型',
    analysis_params JSON COMMENT '分析参数',
    prompt_template VARCHAR(64) COMMENT 'Prompt模板',
    enabled TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT NOW(),
    INDEX idx_skill (skill_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI分析配置(v3.0)';

-- 风暴事件记录表
CREATE TABLE IF NOT EXISTS alert_storm_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    rule_id INT NOT NULL,
    fingerprint VARCHAR(64) NOT NULL COMMENT '风暴指纹',
    first_seen DATETIME NOT NULL,
    last_seen DATETIME NOT NULL,
    count INT DEFAULT 1,
    suppressed TINYINT(1) DEFAULT 0,
    digest_sent TINYINT(1) DEFAULT 0,
    created_at DATETIME DEFAULT NOW(),
    INDEX idx_fingerprint (fingerprint),
    INDEX idx_suppressed (suppressed)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风暴事件记录(v3.0)';

-- ============================================================
-- 默认数据
-- ============================================================

-- (管理员由 main.py 启动时自动创建)

-- 默认技能配置
INSERT INTO skills (skill_name, display_name, description, index_pattern, prompt_template, model, scan_interval_sec, keyword_matching, anomaly_detection) VALUES
('h3c-net-analysis', '网络设备日志分析', '分析H3C交换机、路由器等网络设备日志', 'h3c-net-logs-*', 'h3c_net_analysis.tpl', 'qwen3', 300, 1, 0),
('nginx-access-analysis', 'Nginx访问日志分析', '分析互联网/政务外网Nginx访问日志', '*-nginx-access-*', 'nginx_access_analysis.tpl', 'qwen3', 300, 1, 0),
('storage-analysis', '存储日志分析', '分析存储设备及光纤交换机日志', 'ops-storage-logs-*', 'storage_analysis.tpl', 'qwen3', 300, 1, 0),
('security-analysis', '安全日志分析', '分析WAF/IPS/微步等安全设备日志', 'ops-*-logs-*', 'security_analysis.tpl', 'qwen3', 300, 1, 0),
('incident-analysis', '故障事件分析', '综合故障事件根因分析', '*', 'incident_analysis.tpl', 'qwen3', 300, 1, 0);

-- 默认危险命令规则 (v3.0)
INSERT INTO rules (rule_name, skill_id, rule_type, match_condition, exclude_condition, risk_level, action_config, priority) VALUES
(
    '危险命令实时告警',
    1,
    'dangerous_command',
    '{"es_query": {"bool": {"must": [{"bool": {"should": [{"wildcard": {"command": "*undo*"}},{"wildcard": {"command": "*reset*"}},{"wildcard": {"command": "*reboot*"}},{"wildcard": {"command": "*shutdown*"}},{"wildcard": {"command": "*delete*"}},{"wildcard": {"command": "*format*"}},{"wildcard": {"command": "*erase*"}},{"wildcard": {"command": "*password*"}}]}}],"filter": [{"bool": {"must_not": [{"term": {"src_ip": "192.168.167.242"}},{"term": {"command": "undo debugging all"}},{"wildcard": {"command": "*unreserved iccrunning.cfg*"}}]}}]}}}',
    NULL,
    'critical',
    '{"alert": true, "alert_type": "immediate", "call_ai": true, "ai_analysis": "root_cause", "alert_fields": ["device_ip", "hostname", "user", "src_ip", "command", "timestamp"]}',
    1
),
(
    '0-3级日志AI分析',
    1,
    'severity_filter',
    '{"field": "severity", "operator": "<=", "value": 3}',
    NULL,
    'medium',
    '{"call_ai": true, "ai_analysis": "emotion_scan"}',
    20
),
(
    '命令执行监控',
    1,
    'command_monitor',
    '{"field": "event_name", "contains": "command"}',
    NULL,
    'high',
    '{"call_ai": true, "ai_analysis": "command_analysis"}',
    15
),
(
    '5XX状态码告警',
    2,
    'http_status_alert',
    '{"field": "status", "operator": ">=", "value": 500}',
    NULL,
    'high',
    '{"alert": true, "alert_type": "immediate", "alert_fields": ["domain", "request", "timestamp", "client", "status"]}',
    10
),
(
    '响应超时告警',
    2,
    'response_time_alert',
    '{"field": "responsetime", "operator": ">", "value": 10.0}',
    NULL,
    'medium',
    '{"alert": true, "alert_type": "immediate", "alert_fields": ["domain", "request", "timestamp", "client", "responsetime"]}',
    10
);

-- 默认告警风暴配置
INSERT INTO alert_storm_config (skill_id, rule_id, window_minutes, max_count, action_on_storm) VALUES
(1, 1, 5, 10, 'digest');

-- 默认AI分析配置：Nginx定期业务报告
INSERT INTO ai_analysis_config (skill_id, trigger_type, cron_expression, analysis_type, analysis_params, prompt_template) VALUES
(2, 'periodic', '0 0 8 * * ?', 'business_report', '{"dimensions": ["status", "responsetime", "url", "domain", "log_type"], "time_range": "24h"}', 'nginx_business_report.tpl');

-- ============================================================
-- V3.2 新增：CMDB IT资源管理表
-- ============================================================

CREATE TABLE IF NOT EXISTS cmdb_assets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    asset_code VARCHAR(64) NOT NULL UNIQUE COMMENT '资产编号',
    name VARCHAR(128) NOT NULL COMMENT '名称',
    asset_type VARCHAR(64) COMMENT '类型: server/network/storage/security/software/other',
    model VARCHAR(128) COMMENT '型号',
    serial_number VARCHAR(128) COMMENT '序列号',
    ip_address VARCHAR(64) COMMENT 'IP地址',
    status ENUM('online','offline','maintenance','decommissioned') DEFAULT 'online' COMMENT '状态',
    environment VARCHAR(64) COMMENT '环境: production/test/development/dr',
    region VARCHAR(128) COMMENT '区域',
    datacenter VARCHAR(256) COMMENT '机房信息',
    rack_info VARCHAR(256) COMMENT '机柜信息',
    organization VARCHAR(128) COMMENT '组织归属',
    owner VARCHAR(64) COMMENT '负责人',
    warranty_info TEXT COMMENT '维保信息',
    remarks TEXT COMMENT '备注',
    source VARCHAR(64) DEFAULT 'manual' COMMENT '来源: manual/excel/api_sync',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    INDEX idx_asset_code (asset_code),
    INDEX idx_asset_type (asset_type),
    INDEX idx_status (status),
    INDEX idx_ip (ip_address),
    INDEX idx_owner (owner)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='CMDB IT资源管理';

-- ============================================================
-- V3.1 升级：对话归档 / 会话标题（幂等迁移，兼容已有数据库）
-- ============================================================
DROP PROCEDURE IF EXISTS aiops_upgrade_conversations_v31;
DELIMITER //
CREATE PROCEDURE aiops_upgrade_conversations_v31()
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = DATABASE() AND table_name = 'conversations' AND column_name = 'title') THEN
        ALTER TABLE conversations ADD COLUMN title VARCHAR(128) COMMENT '会话标题' AFTER skill;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = DATABASE() AND table_name = 'conversations' AND column_name = 'archived') THEN
        ALTER TABLE conversations ADD COLUMN archived TINYINT(1) DEFAULT 0 COMMENT '是否归档: 0=否, 1=是' AFTER full_report;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.statistics
                   WHERE table_schema = DATABASE() AND table_name = 'conversations' AND index_name = 'idx_archived') THEN
        ALTER TABLE conversations ADD INDEX idx_archived (archived);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.statistics
                   WHERE table_schema = DATABASE() AND table_name = 'conversations' AND index_name = 'idx_created') THEN
        ALTER TABLE conversations ADD INDEX idx_created (created_at);
    END IF;
END //
DELIMITER ;
CALL aiops_upgrade_conversations_v31();
DROP PROCEDURE IF EXISTS aiops_upgrade_conversations_v31;

-- ============================================================
-- V3.3 新增：网络洞察 - 配置索引 & 系统设置
-- ============================================================

CREATE TABLE IF NOT EXISTS net_configs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vendor VARCHAR(64) NOT NULL COMMENT '厂商: h3c/nsfocus/huawei/cisco等',
    ip_address VARCHAR(64) NOT NULL COMMENT '设备IP地址',
    file_name VARCHAR(256) NOT NULL COMMENT '文件名',
    file_path VARCHAR(512) NOT NULL COMMENT '相对路径(vendor/filename)',
    file_size BIGINT DEFAULT 0 COMMENT '文件大小(字节)',
    file_date VARCHAR(32) COMMENT '配置日期(从文件名解析)',
    config_summary TEXT COMMENT '结构化摘要(预留)',
    content_hash VARCHAR(64) COMMENT '文件内容SHA256',
    parsed_at DATETIME COMMENT '最近一次解析完成时间',
    parse_status INT DEFAULT 0 COMMENT '0未解析 1成功 2失败',
    parse_error TEXT COMMENT '解析错误信息',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    UNIQUE KEY uk_vendor_ip_file (vendor, ip_address, file_name),
    INDEX idx_vendor (vendor),
    INDEX idx_ip (ip_address),
    INDEX idx_parse_status (parse_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='网络设备配置索引';

CREATE TABLE IF NOT EXISTS net_config_sync_state (
    id INT AUTO_INCREMENT PRIMARY KEY,
    last_processed_commit VARCHAR(64) COMMENT '上次处理完的 Git commit hash',
    last_processed_at DATETIME COMMENT '上次处理时间',
    total_commits_processed INT DEFAULT 0 COMMENT '累计处理提交数',
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='网络洞察配置同步状态';

CREATE TABLE IF NOT EXISTS system_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    setting_key VARCHAR(128) NOT NULL UNIQUE,
    setting_value LONGTEXT COMMENT '设置值（支持 base64 图片等大文本）',
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统设置';

INSERT INTO system_settings (setting_key, setting_value) VALUES
('net_config_base_path', '')
ON DUPLICATE KEY UPDATE setting_key = setting_key;

-- ============================================================
-- V3.4 新增：网络洞察 - 结构化配置知识库
-- ============================================================

CREATE TABLE IF NOT EXISTS net_config_interfaces (
    id INT AUTO_INCREMENT PRIMARY KEY,
    net_config_id INT NOT NULL COMMENT '关联配置ID',
    device_ip VARCHAR(64) COMMENT '设备IP',
    vendor VARCHAR(64) COMMENT '厂商',
    interface_name VARCHAR(128) NOT NULL COMMENT '接口名',
    interface_type VARCHAR(64) COMMENT '类型: physical/loopback/vlan/bagg/bridge-aggregation',
    description VARCHAR(512) DEFAULT NULL COMMENT '接口描述，可为空',
    shutdown TINYINT(1) DEFAULT 0 COMMENT '是否shutdown',
    link_type VARCHAR(32) COMMENT '链路类型: access/trunk/hybrid/route',
    access_vlan INT COMMENT 'Access VLAN',
    trunk_vlans VARCHAR(256) COMMENT 'Trunk允许VLAN列表',
    pvid INT COMMENT 'PVID',
    lacp_group INT COMMENT '聚合组ID',
    raw_config TEXT COMMENT '该接口原始配置块',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    INDEX idx_nci_net_config_id (net_config_id),
    INDEX idx_nci_device_ip (device_ip),
    INDEX idx_nci_interface_name (interface_name),
    INDEX idx_nci_access_vlan (access_vlan)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='网络设备接口信息';

CREATE TABLE IF NOT EXISTS net_config_ips (
    id INT AUTO_INCREMENT PRIMARY KEY,
    net_config_id INT NOT NULL COMMENT '关联配置ID',
    device_ip VARCHAR(64) COMMENT '所属设备IP',
    vendor VARCHAR(64) COMMENT '厂商',
    ip_address VARCHAR(64) NOT NULL COMMENT 'IP地址',
    mask VARCHAR(64) COMMENT '子网掩码',
    ip_type VARCHAR(64) COMMENT '类型: interface/secondary/loopback/virtual/vrrp/mlag/ospf/bgp/nat_static/nat_server',
    interface_name VARCHAR(128) COMMENT '关联接口名',
    vrf VARCHAR(64) COMMENT 'VRF',
    description VARCHAR(512) COMMENT '描述',
    raw_line TEXT COMMENT '原始配置行',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    INDEX idx_ncip_net_config_id (net_config_id),
    INDEX idx_ncip_device_ip (device_ip),
    INDEX idx_ncip_ip_address (ip_address),
    INDEX idx_ncip_ip_type (ip_type),
    INDEX idx_ncip_interface_name (interface_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='配置中所有IP地址';

CREATE TABLE IF NOT EXISTS net_config_vlans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    net_config_id INT NOT NULL COMMENT '关联配置ID',
    device_ip VARCHAR(64) COMMENT '设备IP',
    vlan_id INT NOT NULL COMMENT 'VLAN ID',
    vlan_name VARCHAR(128) COMMENT 'VLAN名称',
    description VARCHAR(512) COMMENT '描述',
    raw_config TEXT COMMENT '原始配置块',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    INDEX idx_ncv_net_config_id (net_config_id),
    INDEX idx_ncv_device_ip (device_ip),
    INDEX idx_ncv_vlan_id (vlan_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='VLAN信息';

CREATE TABLE IF NOT EXISTS net_config_routes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    net_config_id INT NOT NULL COMMENT '关联配置ID',
    device_ip VARCHAR(64) COMMENT '设备IP',
    route_type VARCHAR(32) COMMENT 'static/ospf/bgp/isis/direct',
    destination VARCHAR(128) COMMENT '目的网段',
    mask VARCHAR(64) COMMENT '掩码',
    next_hop VARCHAR(128) COMMENT '下一跳IP或接口',
    preference INT COMMENT '优先级',
    cost INT COMMENT '开销',
    vrf VARCHAR(64) COMMENT 'VRF',
    raw_line TEXT COMMENT '原始配置行',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    INDEX idx_ncr_net_config_id (net_config_id),
    INDEX idx_ncr_device_ip (device_ip),
    INDEX idx_ncr_destination (destination),
    INDEX idx_ncr_next_hop (next_hop)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='路由信息';

CREATE TABLE IF NOT EXISTS net_config_nat (
    id INT AUTO_INCREMENT PRIMARY KEY,
    net_config_id INT NOT NULL COMMENT '关联配置ID',
    device_ip VARCHAR(64) COMMENT '设备IP',
    nat_type VARCHAR(64) COMMENT 'server/static/dynamic/addressgroup',
    global_ip VARCHAR(64) COMMENT '公网/全局IP',
    global_port INT COMMENT '全局端口',
    local_ip VARCHAR(64) COMMENT '内网IP',
    local_port INT COMMENT '内网端口',
    protocol VARCHAR(16) COMMENT 'tcp/udp/icmp',
    interface_name VARCHAR(128) COMMENT '关联接口',
    acl_name VARCHAR(128) COMMENT '关联ACL',
    raw_line TEXT COMMENT '原始配置行',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    INDEX idx_ncn_net_config_id (net_config_id),
    INDEX idx_ncn_device_ip (device_ip),
    INDEX idx_ncn_global_ip (global_ip),
    INDEX idx_ncn_local_ip (local_ip)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='NAT映射信息';

CREATE TABLE IF NOT EXISTS net_config_acls (
    id INT AUTO_INCREMENT PRIMARY KEY,
    net_config_id INT NOT NULL COMMENT '关联配置ID',
    device_ip VARCHAR(64) COMMENT '设备IP',
    acl_name VARCHAR(128) COMMENT 'ACL名称或编号',
    rule_id VARCHAR(64) COMMENT '规则序号',
    action VARCHAR(32) COMMENT 'permit/deny',
    protocol VARCHAR(32) COMMENT '协议',
    source_ip VARCHAR(128) COMMENT '源IP',
    source_port VARCHAR(64) COMMENT '源端口',
    dest_ip VARCHAR(128) COMMENT '目的IP',
    dest_port VARCHAR(64) COMMENT '目的端口',
    rule_text TEXT COMMENT '完整规则文本',
    raw_line TEXT COMMENT '原始配置行',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    INDEX idx_nca_net_config_id (net_config_id),
    INDEX idx_nca_device_ip (device_ip),
    INDEX idx_nca_acl_name (acl_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ACL规则';

CREATE TABLE IF NOT EXISTS net_config_bgp_peers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    net_config_id INT NOT NULL COMMENT '关联配置ID',
    device_ip VARCHAR(64) COMMENT '设备IP',
    as_number VARCHAR(32) COMMENT '本地AS号',
    peer_ip VARCHAR(64) COMMENT '邻居IP',
    peer_as VARCHAR(32) COMMENT '邻居AS号',
    description VARCHAR(512) COMMENT '描述',
    raw_line TEXT COMMENT '原始配置行',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    INDEX idx_ncbp_net_config_id (net_config_id),
    INDEX idx_ncbp_device_ip (device_ip),
    INDEX idx_ncbp_peer_ip (peer_ip)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='BGP邻居';

CREATE TABLE IF NOT EXISTS net_config_ospf (
    id INT AUTO_INCREMENT PRIMARY KEY,
    net_config_id INT NOT NULL COMMENT '关联配置ID',
    device_ip VARCHAR(64) COMMENT '设备IP',
    process_id VARCHAR(32) COMMENT '进程ID',
    area_id VARCHAR(32) COMMENT '区域ID',
    network VARCHAR(128) COMMENT '宣告网段',
    wildcard VARCHAR(64) COMMENT '反掩码',
    raw_line TEXT COMMENT '原始配置行',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    INDEX idx_nco_net_config_id (net_config_id),
    INDEX idx_nco_device_ip (device_ip),
    INDEX idx_nco_network (network)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='OSPF配置';

CREATE TABLE IF NOT EXISTS net_config_vrrp (
    id INT AUTO_INCREMENT PRIMARY KEY,
    net_config_id INT NOT NULL COMMENT '关联配置ID',
    device_ip VARCHAR(64) COMMENT '设备IP',
    interface_name VARCHAR(128) COMMENT '关联接口',
    vrid INT COMMENT 'VRID',
    virtual_ip VARCHAR(64) COMMENT '虚拟IP',
    priority INT COMMENT '优先级',
    raw_line TEXT COMMENT '原始配置行',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    INDEX idx_ncvrrp_net_config_id (net_config_id),
    INDEX idx_ncvrrp_device_ip (device_ip),
    INDEX idx_ncvrrp_virtual_ip (virtual_ip)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='VRRP/HSRP信息';

CREATE TABLE IF NOT EXISTS net_config_mlag (
    id INT AUTO_INCREMENT PRIMARY KEY,
    net_config_id INT NOT NULL COMMENT '关联配置ID',
    device_ip VARCHAR(64) COMMENT '设备IP',
    mlag_id INT COMMENT 'M-LAG ID',
    peer_link VARCHAR(128) COMMENT 'Peer-link接口',
    virtual_ip VARCHAR(64) COMMENT '虚拟IP',
    interface_name VARCHAR(128) COMMENT '关联接口',
    raw_line TEXT COMMENT '原始配置行',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    INDEX idx_ncm_net_config_id (net_config_id),
    INDEX idx_ncm_device_ip (device_ip),
    INDEX idx_ncm_virtual_ip (virtual_ip)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='M-LAG信息';

-- ========================================================================
-- 负载均衡配置表
-- ========================================================================

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='负载均衡 Server Farm';

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='负载均衡 Real Server';

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='负载均衡 Virtual Server';

-- ============================================================
-- V3.5 新增：逻辑资源层
-- ============================================================

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

CREATE TABLE IF NOT EXISTS logical_table_custom_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    table_name VARCHAR(64) NOT NULL COMMENT '表标识',
    record_id INT NOT NULL COMMENT '原始表的记录ID',
    custom_fields JSON COMMENT '自定义列数据',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    UNIQUE KEY uk_table_record (table_name, record_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='逻辑资源层自定义列数据';

CREATE TABLE IF NOT EXISTS ip_mapping_relations (
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

CREATE TABLE IF NOT EXISTS lb_mapping_relations (
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

-- 逻辑资源层：默认列元数据（interfaces / ips / ip_mapping / lb_mapping）
INSERT IGNORE INTO logical_table_columns (table_name, field_name, label, column_type, width, visible, sort_order, is_custom) VALUES
('interfaces', 'device_ip',      '设备IP',      'ip',     130, 1, 0, 0),
('interfaces', 'interface_name', '接口名',      'text',   180, 1, 1, 0),
('interfaces', 'interface_type', '接口类型',    'text',   100, 1, 2, 0),
('interfaces', 'description',    '描述',        'text',   200, 1, 3, 0),
('interfaces', 'shutdown',       '是否关闭',    'tag',     80, 1, 4, 0),
('interfaces', 'link_type',      '链路类型',    'text',    90, 1, 5, 0),
('interfaces', 'access_vlan',    'Access VLAN', 'number', 110, 1, 6, 0),
('interfaces', 'trunk_vlans',    'Trunk VLANs', 'text',   150, 1, 7, 0),
('interfaces', 'pvid',           'PVID',        'number',  80, 1, 8, 0),
('interfaces', 'lacp_group',     '聚合组',      'number',  90, 1, 9, 0),
('ips', 'device_ip',      '设备IP',  'ip',   130, 1, 0, 0),
('ips', 'ip_address',     'IP地址',  'ip',   140, 1, 1, 0),
('ips', 'mask',           '子网掩码', 'text', 130, 1, 2, 0),
('ips', 'ip_type',        'IP类型',  'tag',  100, 1, 3, 0),
('ips', 'interface_name', '接口名',  'text', 180, 1, 4, 0),
('ips', 'vrf',            'VRF',     'text', 100, 1, 5, 0),
('ips', 'description',    '描述',    'text', 200, 1, 6, 0),
('ip_mapping', 'external_ip',   '外网IP',   'ip',     130, 1, 0, 0),
('ip_mapping', 'external_port', '外网端口', 'number',  90, 1, 1, 0),
('ip_mapping', 'protocol',      '协议',     'tag',     80, 1, 2, 0),
('ip_mapping', 'vpn_instance',  'VPN实例',  'text',   120, 1, 3, 0),
('ip_mapping', 'internal_ip',   '内网IP',   'ip',     130, 1, 4, 0),
('ip_mapping', 'internal_port', '内网端口', 'number',  90, 1, 5, 0),
('ip_mapping', 'business',      '业务',     'text',   150, 1, 6, 0),
('ip_mapping', 'remarks',       '备注',     'text',   150, 1, 7, 0),
('lb_mapping', 'vip',          'VIP',       'ip',     130, 1, 0, 0),
('lb_mapping', 'vip_port',     'VIP端口',   'number',  90, 1, 1, 0),
('lb_mapping', 'protocol',     '协议',      'tag',     80, 1, 2, 0),
('lb_mapping', 'vpn_instance', 'VPN实例',   'text',   120, 1, 3, 0),
('lb_mapping', 'backend_ip',   '后端IP',    'text',   200, 1, 4, 0),
('lb_mapping', 'backend_port', '后端IP端口', 'text',  120, 1, 5, 0),
('lb_mapping', 'business',     '业务',      'text',   150, 1, 6, 0),
('lb_mapping', 'remarks',      '备注',      'text',   150, 1, 7, 0);
