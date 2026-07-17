"""一次性迁移脚本：为网络洞察模块添加结构化配置知识库表。

用法：
    cd backend
    python migrate_net_config_structured.py

该脚本是幂等的：已存在的列/表会跳过。
"""

import asyncio
from sqlalchemy import text
from core.db import engine


async def column_exists(conn, table: str, column: str) -> bool:
    result = await conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = :table "
        "AND COLUMN_NAME = :column"
    ), {"table": table, "column": column})
    return result.scalar() > 0


async def table_exists(conn, table: str) -> bool:
    result = await conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table"
    ), {"table": table})
    return result.scalar() > 0


async def main():
    async with engine.begin() as conn:
        # 1. 扩展 net_configs 表
        print("[migration] 检查 net_configs 表扩展字段 ...")
        new_columns = [
            ("content_hash", "VARCHAR(64)", "文件内容SHA256"),
            ("parsed_at", "DATETIME", "最近一次解析完成时间"),
            ("parse_status", "INT DEFAULT 0", "0未解析 1成功 2失败"),
            ("parse_error", "TEXT", "解析错误信息"),
        ]
        for col_name, col_type, comment in new_columns:
            if await column_exists(conn, "net_configs", col_name):
                print(f"[migration]  net_configs.{col_name} 已存在，跳过")
                continue
            print(f"[migration]  添加 net_configs.{col_name} ...")
            await conn.execute(text(
                f"ALTER TABLE net_configs ADD COLUMN {col_name} {col_type} "
                f"COMMENT '{comment}'"
            ))

        # 2. 创建 net_config_sync_state 表
        if await table_exists(conn, "net_config_sync_state"):
            print("[migration] net_config_sync_state 表已存在，跳过")
        else:
            print("[migration] 创建 net_config_sync_state 表 ...")
            await conn.execute(text("""
                CREATE TABLE net_config_sync_state (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    last_processed_commit VARCHAR(64) COMMENT '上次处理完的 Git commit hash',
                    last_processed_at DATETIME COMMENT '上次处理时间',
                    total_commits_processed INT DEFAULT 0 COMMENT '累计处理提交数',
                    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW()
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='网络洞察配置同步状态'
            """))

    print("[migration] 完成。其余结构化知识表将在应用启动时由 SQLAlchemy create_all 自动创建。")


if __name__ == "__main__":
    asyncio.run(main())
