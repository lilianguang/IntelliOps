"""Elasticsearch 异步客户端

从配置中心动态读取ES连接信息，支持运行时切换数据源。
"""

from typing import Optional
from elasticsearch import AsyncElasticsearch
from config.settings import settings


class ESClient:
    """ES客户端封装，支持动态配置"""

    def __init__(self):
        self._client: Optional[AsyncElasticsearch] = None
        self._hosts: str = settings.ES_HOSTS
        self._username: Optional[str] = settings.ES_USERNAME
        self._password: Optional[str] = settings.ES_PASSWORD

    async def get_client(self) -> AsyncElasticsearch:
        """获取或创建ES客户端"""
        if self._client is None:
            await self._create_client()
        return self._client

    async def _create_client(self):
        """创建ES连接"""
        hosts = self._hosts.split(",") if "," in self._hosts else [self._hosts]
        # 自动添加 scheme（如果未指定）
        hosts = [
            f"http://{h}" if not h.startswith(("http://", "https://")) else h
            for h in hosts
        ]
        kwargs = {
            "hosts": hosts,
            "verify_certs": settings.ES_VERIFY_CERTS,
        }
        if self._username and self._password:
            kwargs["basic_auth"] = (self._username, self._password)
        self._client = AsyncElasticsearch(**kwargs)

    async def reconfigure(self, hosts: str, username: Optional[str] = None, password: Optional[str] = None):
        """运行时重新配置ES连接（从配置中心调用）"""
        await self.close()
        self._hosts = hosts
        self._username = username
        self._password = password
        await self._create_client()

    async def get_field_types(self, index: str) -> dict:
        """获取索引的字段类型映射，合并多索引结果。

        Returns:
            {"types": {field_name: es_type}, "has_keyword": set(field_names_with_.keyword)}
        """
        client = await self.get_client()
        try:
            result = await client.indices.get_mapping(index=index)
            field_types: dict = {}
            has_keyword: set = set()
            for idx_data in result.values():
                props = idx_data.get("mappings", {}).get("properties", {})
                for fname, finfo in props.items():
                    ftype = finfo.get("type", "")
                    if ftype:
                        field_types[fname] = ftype
                    sub_fields = finfo.get("fields", {})
                    if isinstance(sub_fields, dict) and "keyword" in sub_fields:
                        has_keyword.add(fname)
            return {"types": field_types, "has_keyword": has_keyword}
        except Exception:
            return {"types": {}, "has_keyword": set()}

    async def search(self, index: str, query: dict, size: int = 100, **kwargs) -> dict:
        """执行ES检索"""
        client = await self.get_client()
        # ES 9.x 不允许 size 同时出现在 URL 参数和 body 中
        # 统一将 size 放入 body，避免冲突
        body = dict(query)
        if "size" not in body:
            body["size"] = size
        return await client.search(index=index, body=body, **kwargs)

    async def count(self, index: str, query: dict = None) -> int:
        """统计文档数"""
        client = await self.get_client()
        result = await client.count(index=index, body=query)
        return result["count"]

    async def close(self):
        """关闭连接"""
        if self._client:
            await self._client.close()
            self._client = None


# 全局单例
es_client = ESClient()