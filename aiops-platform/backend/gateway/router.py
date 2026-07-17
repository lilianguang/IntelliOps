"""技能路由引擎 - 根据请求路由到对应技能"""

from typing import Optional
from models.skill import Skill


class SkillRouter:
    """技能路由引擎"""

    async def route(self, skill_name: Optional[str] = None, query: str = "") -> Optional[Skill]:
        """
        路由到目标技能

        Args:
            skill_name: 指定的技能名称
            query: 用户查询文本（用于语义匹配）
        Returns:
            Skill 对象或 None
        """
        if skill_name:
            return await self._route_by_name(skill_name)
        if query:
            return await self._route_by_semantic(query)
        return None

    async def _route_by_name(self, skill_name: str) -> Optional[Skill]:
        """按技能名称路由"""
        # TODO: 从数据库查询技能
        # session = get_session()
        # skill = await session.get(Skill, ...)
        from core.db import async_session_factory
        from sqlalchemy import select
        async with async_session_factory() as session:
            result = await session.execute(
                select(Skill).where(
                    Skill.skill_name == skill_name,
                    Skill.enabled == 1
                )
            )
            return result.scalar_one_or_none()

    @staticmethod
    def _tokenize_query(query: str) -> list:
        """将查询文本切分为可匹配的 token 列表（支持中英文混合）

        中文没有空格分词，直接 query.split() 只会得到整句，无法与技能关键词命中。
        这里采用混合策略：
        - 英文/数字：按空格 & 标点切分为单词
        - 中文：提取连续汉字，并生成字符级 2-gram / 3-gram 子串
        例如 "分析最近异常" → ["分析", "析最", "最近", "近异", "异常", "分析最近", "最近异常"]
        """
        import re
        tokens: list = []

        # 英文/数字单词
        for word in re.findall(r"[A-Za-z0-9_]+", query):
            w = word.lower()
            if len(w) >= 2:
                tokens.append(w)

        # 中文字符级 n-gram（2-gram + 3-gram）
        for seg in re.findall(r"[\u4e00-\u9fff]+", query):
            for n in (2, 3):
                for i in range(len(seg) - n + 1):
                    tokens.append(seg[i:i + n])
        return tokens

    async def _route_by_semantic(self, query: str) -> Optional[Skill]:
        """按语义匹配路由"""
        from core.db import async_session_factory
        from sqlalchemy import select
        async with async_session_factory() as session:
            result = await session.execute(
                select(Skill).where(Skill.enabled == 1)
            )
            skills = result.scalars().all()

        # 混合关键词匹配：中文 n-gram + 英文单词（后续可升级为向量匹配）
        query_tokens = self._tokenize_query(query)
        best_skill = None
        best_score = 0

        for skill in skills:
            score = 0
            # 匹配技能名称和描述
            keywords = (skill.skill_name or "").lower() + " " + (skill.description or "").lower()
            for token in query_tokens:
                if token in keywords:
                    score += 10
            if score > best_score:
                best_score = score
                best_skill = skill

        # 最佳匹配
        if best_skill and best_score > 0:
            return best_skill

        # 降级到 incident-analysis 综合技能
        async with async_session_factory() as session:
            result = await session.execute(
                select(Skill).where(
                    Skill.skill_name == "incident-analysis",
                    Skill.enabled == 1
                )
            )
            return result.scalar_one_or_none()


# 全局单例
skill_router = SkillRouter()