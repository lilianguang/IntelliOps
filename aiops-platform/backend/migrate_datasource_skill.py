"""数据迁移脚本: 技能表关联数据源

功能:
1. ALTER TABLE skills 添加 datasource_id, ds_type, query_config 字段
2. ALTER TABLE rules 扩展 rule_type 枚举（新增 metric_threshold）
3. 自动填充现有技能的 ds_type = 'es'
4. 查找已有 ES 数据源，为现有技能自动关联 datasource_id
5. 将现有 index_pattern + query_filter 写入 query_config

用法: python migrate_datasource_skill.py
"""

import asyncio
import json
from sqlalchemy import text
from core.db import engine, async_session_factory


async def migrate():
    """执行迁移"""
    async with engine.begin() as conn:
        print("[迁移] 开始执行数据源-技能关联迁移...")

        # ============================================================
        # Step 1: skills 表添加新字段（幂等，先检查列是否存在）
        # ============================================================
        print("[迁移] Step 1: 检查并添加 skills 表新字段...")

        # 检查 datasource_id 列
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = 'skills' AND column_name = 'datasource_id'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "ALTER TABLE skills ADD COLUMN datasource_id INT COMMENT '关联数据源ID' AFTER id"
            ))
            print("  - 添加列: datasource_id")
        else:
            print("  - 列 datasource_id 已存在，跳过")

        # 检查 ds_type 列
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = 'skills' AND column_name = 'ds_type'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "ALTER TABLE skills ADD COLUMN ds_type VARCHAR(32) DEFAULT 'es' COMMENT '数据源类型' AFTER datasource_id"
            ))
            print("  - 添加列: ds_type")
        else:
            print("  - 列 ds_type 已存在，跳过")

        # 检查 query_config 列
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = 'skills' AND column_name = 'query_config'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "ALTER TABLE skills ADD COLUMN query_config JSON COMMENT '查询配置JSON' AFTER query_filter"
            ))
            print("  - 添加列: query_config")
        else:
            print("  - 列 query_config 已存在，跳过")

        # 添加索引（幂等）
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND table_name = 'skills' AND index_name = 'idx_datasource'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "ALTER TABLE skills ADD INDEX idx_datasource (datasource_id)"
            ))
            print("  - 添加索引: idx_datasource")

        # 将 index_pattern 改为可空（兼容 Prometheus 技能无索引的情况）
        await conn.execute(text(
            "ALTER TABLE skills MODIFY COLUMN index_pattern VARCHAR(128) COMMENT 'ES索引模式(兼容旧版)'"
        ))
        print("  - 修改 index_pattern 为可空")

        # ============================================================
        # Step 2: rules 表扩展 rule_type 枚举
        # ============================================================
        print("[迁移] Step 2: 扩展 rules.rule_type 枚举...")
        try:
            await conn.execute(text(
                "ALTER TABLE rules MODIFY COLUMN rule_type ENUM("
                "'severity_filter','command_monitor','dangerous_command',"
                "'http_status_alert','response_time_alert','keyword_match',"
                "'ai_analysis_trigger','ignore_rule','metric_threshold'"
                ") NOT NULL COMMENT '规则类型'"
            ))
            print("  - rule_type 枚举已扩展(新增 metric_threshold)")
        except Exception as e:
            print(f"  - rule_type 扩展跳过: {e}")

    # ============================================================
    # Step 3: 为现有技能填充 ds_type 和 query_config
    # ============================================================
    print("[迁移] Step 3: 为现有技能填充数据...")

    async with async_session_factory() as session:
        # 查找所有未设置 ds_type 或 ds_type='' 的技能
        result = await session.execute(text(
            "SELECT id, index_pattern, query_filter, ds_type, datasource_id FROM skills"
        ))
        skills = result.fetchall()

        # 查找已有的 ES 数据源（取第一个启用的）
        ds_result = await session.execute(text(
            "SELECT id FROM datasources WHERE ds_type = 'es' AND enabled = 1 LIMIT 1"
        ))
        es_ds = ds_result.fetchone()
        es_datasource_id = es_ds[0] if es_ds else None

        updated = 0
        for skill in skills:
            skill_id, index_pattern, query_filter, ds_type, datasource_id = skill

            updates = {}

            # 填充 ds_type（如果为空则默认 es）
            if not ds_type:
                updates["ds_type"] = "es"

            # 填充 datasource_id（如果为空且有 ES 数据源）
            if not datasource_id and es_datasource_id:
                updates["datasource_id"] = es_datasource_id

            # 构建 query_config（如果尚未设置）
            if index_pattern:
                query_config = {"index_pattern": index_pattern}
                if query_filter:
                    try:
                        query_config["query_filter"] = json.loads(query_filter)
                    except json.JSONDecodeError:
                        pass
                updates["query_config"] = json.dumps(query_config, ensure_ascii=False)

            if updates:
                set_parts = []
                for k, v in updates.items():
                    if v is None:
                        set_parts.append(f"{k} = NULL")
                    elif isinstance(v, int):
                        set_parts.append(f"{k} = {v}")
                    else:
                        set_parts.append(f"{k} = :val_{k}")
                set_clause = ", ".join(set_parts)
                params = {f"val_{k}": v for k, v in updates.items() if v is not None and not isinstance(v, int)}
                params["skill_id"] = skill_id

                # 动态构建 UPDATE 语句
                update_sql = f"UPDATE skills SET {set_clause} WHERE id = :skill_id"
                await session.execute(text(update_sql), params)
                updated += 1

        await session.commit()
        print(f"  - 已更新 {updated}/{len(skills)} 个技能记录")

    print("[迁移] 完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
