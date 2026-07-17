"""一次性迁移脚本：为 skills 表添加 query_filter 列。

用法：
    cd backend
    python migrate_query_filter.py

该脚本是幂等的：如果列已存在则跳过。
"""

import asyncio
from sqlalchemy import text
from core.db import engine


async def main():
    async with engine.begin() as conn:
        # 检查列是否已存在（MySQL 8.0+ 不支持 IF NOT EXISTS for ADD COLUMN）
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'skills' "
            "AND COLUMN_NAME = 'query_filter'"
        ))
        exists = result.scalar()

        if exists:
            print("[migration] 列 query_filter 已存在，跳过")
            return

        print("[migration] 添加 query_filter 列到 skills 表 ...")
        await conn.execute(text(
            "ALTER TABLE skills "
            "ADD COLUMN query_filter TEXT "
            "COMMENT 'ES查询过滤条件JSON：{logic:AND/OR,conditions:[{field,operator,value}]}' "
            "AFTER field_schema"
        ))
        print("[migration] 完成！")


if __name__ == "__main__":
    asyncio.run(main())
