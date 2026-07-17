"""应用配置 - 从环境变量读取，支持docker-compose注入"""

import os
from typing import Optional


class Settings:
    # 应用
    APP_NAME: str = "AIOPS 智能运维平台"
    APP_VERSION: str = "3.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # MySQL
    MYSQL_DSN: str = os.getenv(
        "MYSQL_DSN",
        "mysql+aiomysql://aiops:password@localhost:3306/aiops?charset=utf8mb4"
    )
    MYSQL_POOL_SIZE: int = int(os.getenv("MYSQL_POOL_SIZE", "10"))

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Elasticsearch
    ES_HOSTS: str = os.getenv("ES_HOSTS", "192.67.0.230:9200")
    ES_USERNAME: Optional[str] = os.getenv("ES_USERNAME")
    ES_PASSWORD: Optional[str] = os.getenv("ES_PASSWORD")
    ES_VERIFY_CERTS: bool = os.getenv("ES_VERIFY_CERTS", "false").lower() == "true"

    # LLM (默认模型，可通过配置中心修改)
    LLM_DEFAULT_MODEL: str = os.getenv("LLM_DEFAULT_MODEL", "qwen3")
    LLM_API_BASE: str = os.getenv("LLM_API_BASE", "")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "300"))

    # JWT认证
    JWT_SECRET: str = os.getenv("JWT_SECRET", "aiops-jwt-secret-key-change-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

    # 规则缓存刷新间隔(秒)
    RULE_CACHE_TTL: int = int(os.getenv("RULE_CACHE_TTL", "300"))

    # 扫描默认间隔
    DEFAULT_SCAN_INTERVAL: int = int(os.getenv("DEFAULT_SCAN_INTERVAL", "300"))

    # 网络洞察：只读源目录（每日备份）与可写工作区（上传/AI分析/Git版本）
    NET_CONFIG_SOURCE_PATH: str = os.getenv("NET_CONFIG_SOURCE_PATH", "/data/net_configs_source")
    NET_CONFIG_WORKSPACE_PATH: str = os.getenv("NET_CONFIG_WORKSPACE_PATH", "/data/net_workspace")
    NET_CONFIG_SCAN_INTERVAL: int = int(os.getenv("NET_CONFIG_SCAN_INTERVAL", "86400"))  # 默认每天同步一次


settings = Settings()