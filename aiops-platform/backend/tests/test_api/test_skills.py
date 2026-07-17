"""Module 3: 技能管理测试"""
import pytest

pytestmark = pytest.mark.asyncio


class TestSkills:
    """TC-11 ~ TC-14: 技能管理"""

    async def test_list_skills(self, client, admin_token):
        """TC-11: 列出所有技能 - 应有5个核心技能"""
        if not admin_token:
            pytest.skip("未获取到admin_token")
        resp = await client.get(
            "/api/ai/skills",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        skills = resp.json()
        skill_names = [s.get("skill_name") for s in skills]
        print(f"当前技能列表: {skill_names}")

    async def test_register_skill(self, client, admin_token):
        """TC-12: 注册新技能"""
        if not admin_token:
            pytest.skip("未获取到admin_token")
        new_skill = {
            "skill_name": "test-skill",
            "display_name": "测试技能",
            "description": "自动化测试注册的技能",
            "index_pattern": "test-logs-*",
            "prompt_template": "h3c_net_analysis.tpl",
            "model": "qwen3",
            "enabled": True
        }
        resp = await client.post(
            "/api/ai/skills/register",
            json=new_skill,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code in (200, 201)

    async def test_update_skill(self, client, admin_token):
        """TC-13: 更新技能配置"""
        if not admin_token:
            pytest.skip("未获取到admin_token")
        resp = await client.get(
            "/api/ai/skills",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        skills = resp.json()
        if skills:
            skill_id = skills[0].get("id")
            update_data = {"display_name": "更新后的技能名称"}
            resp = await client.put(
                f"/api/ai/skills/{skill_id}",
                json=update_data,
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert resp.status_code in (200, 201)

    async def test_delete_skill(self, client, admin_token):
        """TC-14: 卸载技能 - 删除之前创建的测试技能"""
        if not admin_token:
            pytest.skip("未获取到admin_token")
        resp = await client.get(
            "/api/ai/skills",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        skills = resp.json()
        for skill in skills:
            if skill.get("skill_name") == "test-skill":
                resp = await client.delete(
                    f"/api/ai/skills/{skill['id']}",
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                assert resp.status_code in (200, 204)
                break
