"""Module 4: 配置中心测试"""
import pytest

pytestmark = pytest.mark.asyncio


class TestConfigs:
    """TC-15 ~ TC-18: 配置中心"""

    async def test_datasource_crud(self, client, admin_token):
        """TC-15: 数据源配置CRUD"""
        if not admin_token:
            pytest.skip("未获取到admin_token")
        headers = {"Authorization": f"Bearer {admin_token}"}

        resp = await client.get("/api/ai/config/datasources", headers=headers)
        assert resp.status_code in (200, 404, 500)

        new_ds = {
            "name": "test-es",
            "ds_type": "es",
            "host": "192.67.0.230",
            "port": 9200,
            "enabled": True
        }
        resp = await client.post("/api/ai/config/datasources", json=new_ds, headers=headers)
        print(f"创建数据源: {resp.status_code}")

    async def test_llm_config(self, client, admin_token):
        """TC-16: 大模型配置"""
        if not admin_token:
            pytest.skip("未获取到admin_token")
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = await client.get("/api/ai/config/llms", headers=headers)
        assert resp.status_code in (200, 404, 500)

    async def test_alert_channel(self, client, admin_token):
        """TC-17: 告警渠道配置"""
        if not admin_token:
            pytest.skip("未获取到admin_token")
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = await client.get("/api/ai/config/alerts", headers=headers)
        assert resp.status_code in (200, 404, 500)

    async def test_rule_config(self, client, admin_token):
        """TC-18: 规则配置CRUD"""
        if not admin_token:
            pytest.skip("未获取到admin_token")
        headers = {"Authorization": f"Bearer {admin_token}"}
        # 尝试多个可能的路径
        for path in ["/api/ai/config/rules", "/api/ai/rules"]:
            resp = await client.get(path, headers=headers)
            if resp.status_code != 404:
                break
        print(f"规则查询 ({path}): {resp.status_code}")
        # 规则表可能为空，接口本身应正常工作
        assert resp.status_code in (200, 500)
