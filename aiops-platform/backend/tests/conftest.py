"""pytest 公共配置和 Fixtures"""

import pytest
import httpx
import asyncio

BASE_URL = "http://aiops-backend:8000"
TEST_USER = {"username": "admin", "password": "admin123"}


@pytest.fixture(scope="function")
def event_loop():
    """每个测试函数独立的事件循环"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def client():
    """每个测试函数独立创建HTTP客户端"""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        yield c


@pytest.fixture(scope="function")
async def admin_token(client):
    """获取管理员token"""
    resp = await client.post("/api/auth/login", json=TEST_USER)
    if resp.status_code == 200:
        return resp.json().get("access_token", "")
    return ""
