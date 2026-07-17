"""CMDB IT资源管理模型"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, func, Index
from core.db import Base


class CMDBAsset(Base):
    __tablename__ = "cmdb_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_code = Column(String(64), unique=True, nullable=False, comment="资产编号")
    name = Column(String(128), nullable=False, comment="名称")
    asset_type = Column(String(64), comment="类型: server/network/storage/security/software/other")
    model = Column(String(128), comment="型号")
    serial_number = Column(String(128), comment="序列号")
    ip_address = Column(String(64), comment="IP地址")
    status = Column(
        Enum("online", "offline", "maintenance", "decommissioned", name="cmdb_status"),
        default="online",
        comment="状态",
    )
    environment = Column(String(64), comment="环境: production/test/development/dr")
    region = Column(String(128), comment="区域")
    datacenter = Column(String(256), comment="机房信息")
    rack_info = Column(String(256), comment="机柜信息")
    organization = Column(String(128), comment="组织归属")
    owner = Column(String(64), comment="负责人")
    warranty_info = Column(Text, comment="维保信息")
    remarks = Column(Text, comment="备注")
    source = Column(String(64), default="manual", comment="来源: manual/excel/api_sync")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_asset_code", "asset_code"),
        Index("idx_asset_type", "asset_type"),
        Index("idx_status", "status"),
        Index("idx_ip", "ip_address"),
        Index("idx_owner", "owner"),
    )
