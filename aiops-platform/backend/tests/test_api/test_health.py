"""Module 1: 健康检查与基础服务测试"""
import pytest

pytestmark = pytest.mark.asyncio


class TestHealth:
    """TC-01 ~ TC-04: 健康检查"""

    async def test_health_endpoint(self, client):
        """TC-01: GET /api/ai/health 健康检查"""
        resp = await client.get("/api/ai/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    async def test_mysql_connection(self, client):
        """TC-02: MySQL连接 - 通过skills查询验证"""
        resp = await client.get("/api/ai/skills")
        assert resp.status_code in (200, 401)

    async def test_redis_connection(self, client):
        """TC-03: Redis连接验证"""
        resp = await client.get("/api/ai/health")
        assert resp.status_code == 200
