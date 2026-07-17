"""一次性迁移脚本：将 system_settings.setting_value 从 TEXT 升级为 LONGTEXT。

背景：站点 Logo/图标改为本地上传后以 base64 data URL 形式存入 site 配置，
TEXT（约 64KB）无法容纳，需升级为 LONGTEXT（最大 4GB）。

用法：
    cd backend
    python migrate_site_setting_longtext.py

该脚本是幂等的：如果列已是 longtext 则跳过。
"""

import asyncio
from sqlalchemy import text
from core.db import engine


async def main():
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT DATA_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'system_settings' "
            "AND COLUMN_NAME = 'setting_value'"
        ))
        data_type = result.scalar()

        if data_type is None:
            print("[migration] 未找到 system_settings.setting_value 列，跳过")
            return

        if str(data_type).lower() == "longtext":
            print("[migration] setting_value 已是 LONGTEXT，跳过")
            return

        print(f"[migration] 当前类型 {data_type}，升级 setting_value 为 LONGTEXT ...")
        await conn.execute(text(
            "ALTER TABLE system_settings "
            "MODIFY COLUMN setting_value LONGTEXT "
            "COMMENT '设置值（支持 base64 图片等大文本）'"
        ))
        print("[migration] 完成！")


if __name__ == "__main__":
    asyncio.run(main())
