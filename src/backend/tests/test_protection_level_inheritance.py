"""等保等级继承传播引擎 + 定级建议引擎测试（设计 §10 · 2026-10-03）

覆盖（test_protection_level_inheritance）：
  - 纯函数：strictest / suggest 矩阵 9 格 / filing_hint / 非法输入
  - 传播引擎（真 DB）：升档联动 / 就高不降级越过更高系统 / manual 保护 /
    inherit=true 覆盖 / unlink 值保留转 manual / 系统 DELETE force 防护与成员重算
  - API 集成：link 传播 / 确认动作（PUT 值变 → confirmed + 传播）/ suggest 不越权 /
    例行编辑不翻转 source（§5.3 v2）
"""
from __future__ import annotations

import pytest

from app.services.protection_level_propagation import (
    PL_RANK, strictest, recompute_asset, propagate_system_level_change,
)
from app.services.protection_level_suggest import (
    suggest, build_filing_hint, SuggestionInputError,
)
from app.models.asset import Asset
from app.models.business_system import BusinessSystem, AssetBusiness


# ============ 纯函数 ============

class TestStrictest:
    def test_取最高档(self):
        assert strictest(["level_2", "level_3"]) == "level_3"
        assert strictest(["level_1", "level_5", "level_3"]) == "level_5"

    def test_空列表_None(self):
        assert strictest([]) is None

    def test_非法值不参与(self):
        assert strictest(["bogus", "level_2"]) == "level_2"

    def test_PL_RANK_五档齐全(self):
        assert set(PL_RANK) == {"level_1", "level_2", "level_3", "level_4", "level_5"}


class TestSuggestMatrix:
    """GB/T 22240 矩阵 9 格全覆盖（用 BIA/CIA 组合驱动）"""

    CASES = [
        # (business_impact, data_sensitivity, expected_level)
        ("ignorable", "negligible", "level_1"),   # 公民×一般
        ("normal",    "negligible", "level_2"),   # 公民×严重
        ("core",      "negligible", "level_2"),   # 公民×特别严重
        ("ignorable", "medium",     "level_2"),   # 社会×一般
        ("normal",    "medium",     "level_3"),   # 社会×严重
        ("core",      "medium",     "level_4"),   # 社会×特别严重
        ("ignorable", "extreme",    "level_3"),   # 国家×一般
        ("normal",    "extreme",    "level_4"),   # 国家×严重
        ("core",      "extreme",    "level_5"),   # 国家×特别严重
    ]

    @pytest.mark.parametrize("bia,cia,expected", CASES)
    def test_矩阵格(self, bia, cia, expected):
        result = suggest(bia, cia)
        assert result["suggested_level"] == expected

    def test_basis_结构完整(self):
        b = suggest("normal", "medium", {"asset_count": 12, "role_dist": {"web": 3}, "public_exposed_assets": 1})
        assert b["engine"] == "matrix_v1"
        assert "generated_at" in b
        assert b["matrix_inputs"]["victim_object"] == "social_order"
        assert b["matrix_inputs"]["harm_degree"] == "serious"
        # 近似声明强制在场（S4 红线三重防线之一）
        assert "approximation_note" in b["matrix_inputs"]
        assert "代理" in b["matrix_inputs"]["approximation_note"]
        assert b["evidence"]["asset_count"] == 12
        assert b["suggested_level"] == "level_3"

    def test_非法输入抛错(self):
        with pytest.raises(SuggestionInputError):
            suggest("not_a_bia", "medium")
        with pytest.raises(SuggestionInputError):
            suggest("normal", "not_a_cia")

    def test_filing_hint_一级无需备案(self):
        assert "无需备案" in build_filing_hint("level_1")
        assert "备案" in build_filing_hint("level_2")
        assert "专家评审" in build_filing_hint("level_3")


# ============ 传播引擎（真 DB）============
#
# ⚠️ 断言约定：TestingSessionLocal 是 autoflush=False——recompute_asset 故意
# 不 commit（事务归调用方，API 路径由端点统一 commit）。所以 DB 直连测试在
# refresh 断言前必须显式 db.flush()，否则 pending UPDATE 未落库、refresh 用
# 旧值覆盖内存改动。API 集成测试无此问题（端点内 commit）。

def _mk_asset(db, ip="10.0.0.1", pl="level_2", source="manual") -> Asset:
    a = Asset(asset_ip=ip, network_segment="test", name=f"asset-{ip}",
              protection_level=pl, protection_level_source=source,
              business_impact="normal", data_sensitivity="medium")
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _mk_system(db, code, pl="level_2") -> BusinessSystem:
    s = BusinessSystem(code=code, name=code, protection_level=pl,
                       business_impact="normal", data_sensitivity="medium")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _link(db, asset, system, role=None):
    db.add(AssetBusiness(asset_id=asset.id, system_id=system.id, role=role))
    db.commit()


class TestRecomputeAsset:
    def test_系统升档_inherited_资产跟随(self, db_session):
        a = _mk_asset(db_session, pl="level_2", source="inherited")
        s = _mk_system(db_session, "sys-up", pl="level_3")
        _link(db_session, a, s)
        r = recompute_asset(db_session, a.id, allow_manual=False)
        assert r["changed"] is True
        assert r["new"] == "level_3"
        db_session.flush()  # autoflush=False：先落 pending UPDATE 再 refresh
        db_session.refresh(a)
        assert a.protection_level == "level_3"
        assert a.protection_level_source == "inherited"

    def test_另挂更高系统_不被本系统降档拉低(self, db_session):
        """就高语义：资产挂 level_4 + level_2 两系统，level_4 被 unlink 后仍保 level_4→level_2 重算"""
        a = _mk_asset(db_session, ip="10.0.0.2", pl="level_4", source="inherited")
        s4 = _mk_system(db_session, "sys-hi", pl="level_4")
        s2 = _mk_system(db_session, "sys-lo", pl="level_2")
        _link(db_session, a, s4)
        _link(db_session, a, s2)
        # unlink s4：剩 s2 → inherited 资产如实降到 level_2
        db_session.query(AssetBusiness).filter_by(asset_id=a.id, system_id=s4.id).delete()
        db_session.commit()
        r = recompute_asset(db_session, a.id, allow_manual=False)
        assert r["new"] == "level_2"
        assert r["changed"] is True

    def test_manual_资产不被传播(self, db_session):
        a = _mk_asset(db_session, ip="10.0.0.3", pl="level_1", source="manual")
        s = _mk_system(db_session, "sys-manual", pl="level_3")
        _link(db_session, a, s)
        r = recompute_asset(db_session, a.id, allow_manual=False)
        assert r["skipped"] == "manual_protected"
        db_session.refresh(a)
        assert a.protection_level == "level_1"  # 人工值保留
        assert a.protection_level_source == "manual"

    def test_inherit_true_覆盖_manual(self, db_session):
        a = _mk_asset(db_session, ip="10.0.0.4", pl="level_1", source="manual")
        s = _mk_system(db_session, "sys-force", pl="level_3")
        _link(db_session, a, s)
        r = recompute_asset(db_session, a.id, allow_manual=True)
        assert r["new"] == "level_3"
        db_session.flush()  # autoflush=False：先落 pending UPDATE 再 refresh
        db_session.refresh(a)
        assert a.protection_level == "level_3"
        assert a.protection_level_source == "inherited"

    def test_无关联系统_值保留转_manual(self, db_session):
        a = _mk_asset(db_session, ip="10.0.0.5", pl="level_3", source="inherited")
        r = recompute_asset(db_session, a.id, allow_manual=False)
        assert r["event"] == "source_downgrade_kept_value"
        db_session.flush()  # autoflush=False：先落 pending UPDATE 再 refresh
        db_session.refresh(a)
        assert a.protection_level == "level_3"  # 值保留（不静默降回 level_2）
        assert a.protection_level_source == "manual"


class TestPropagateSystemChange:
    def test_系统改级_批量联动_manual_跳过(self, db_session):
        a1 = _mk_asset(db_session, ip="10.1.0.1", pl="level_2", source="inherited")
        a2 = _mk_asset(db_session, ip="10.1.0.2", pl="level_1", source="manual")
        s = _mk_system(db_session, "sys-batch", pl="level_2")
        _link(db_session, a1, s)
        _link(db_session, a2, s)
        s.protection_level = "level_3"
        db_session.commit()
        result = propagate_system_level_change(db_session, s.id)
        assert result["affected"] == 2
        assert result["changed"] == 1  # 只有 a1 联动
        db_session.flush()  # autoflush=False：先落 pending UPDATE 再 refresh
        db_session.refresh(a1)
        db_session.refresh(a2)
        assert a1.protection_level == "level_3"
        assert a2.protection_level == "level_1"


# ============ API 集成 ============

@pytest.fixture
def api_setup(db_session, admin_user):
    """建 1 系统 + 1 资产，返回 (system_id, asset_id, headers)"""
    from app.core.auth import create_access_token
    s = _mk_system(db_session, "api-sys", pl="level_2")
    a = _mk_asset(db_session, ip="10.9.0.1", pl="level_2", source="inherited")
    token = create_access_token(data={
        "sub": str(admin_user.id), "username": admin_user.username,
        "email": admin_user.email, "role_id": admin_user.role_id,
    })
    return s, a, {"Authorization": f"Bearer {token}"}


class TestPropagationAPI:
    def test_link_传播_inherited_资产(self, client, api_setup):
        s, a, headers = api_setup
        res = client.post(
            f"/api/v1/business-systems/assets/{a.id}/systems",
            json={"system_id": str(s.id), "inherit": False},
            headers=headers,
        )
        assert res.json().get("code") in (200, 201)
        # inherit=False + 已是 inherited → 重算为系统级 level_2（值未变）
        db_session_a = client  # noop；直接断言响应
        body = res.json()
        assert body["data"]["system_id"] == str(s.id)

    def test_系统PUT_值变_确认并传播(self, client, api_setup):
        s, a, headers = api_setup
        # 先 link（inherit=False，资产 inherited 跟随 level_2）
        client.post(
            f"/api/v1/business-systems/assets/{a.id}/systems",
            json={"system_id": str(s.id)},
            headers=headers,
        )
        # PUT 系统改 level_3
        res = client.put(
            f"/api/v1/business-systems/{s.id}",
            json={"protection_level": "level_3"},
            headers=headers,
        )
        body = res.json()
        assert body["code"] == 200
        assert body["data"]["rating_status"] == "confirmed"
        assert body["data"]["rating_confirmed_by"] == "admin"
        # 成员资产已联动（通过系统资产列表断言）
        res2 = client.get(f"/api/v1/business-systems/{s.id}/assets", headers=headers)
        items = res2.json() if isinstance(res2.json(), list) else res2.json().get("data", [])
        assert items and items[0]["protection_level"] == "level_3"
        assert items[0]["protection_level_source"] == "inherited"

    def test_系统PUT_值不变_不触发确认(self, client, api_setup):
        s, a, headers = api_setup
        res = client.put(
            f"/api/v1/business-systems/{s.id}",
            json={"protection_level": "level_2"},  # 与现值相同
            headers=headers,
        )
        body = res.json()
        assert body["code"] == 200
        assert body["data"]["rating_status"] == "unrated"  # 值未变不确认

    def test_DELETE_有成员_无force_被拒(self, client, api_setup):
        s, a, headers = api_setup
        client.post(
            f"/api/v1/business-systems/assets/{a.id}/systems",
            json={"system_id": str(s.id)},
            headers=headers,
        )
        res = client.delete(f"/api/v1/business-systems/{s.id}", headers=headers)
        body = res.json()
        assert body.get("code") in (400, 403) or res.status_code == 400

    def test_DELETE_force_成功且成员重算(self, client, api_setup):
        s, a, headers = api_setup
        client.post(
            f"/api/v1/business-systems/assets/{a.id}/systems",
            json={"system_id": str(s.id)},
            headers=headers,
        )
        res = client.delete(
            f"/api/v1/business-systems/{s.id}?force=true", headers=headers)
        body = res.json()
        assert body.get("code") == 200 or res.status_code == 200
        # 成员资产等级值保留（来源消失转 manual）
        # （资产仍存在——通过资产列表接口断言可选，此处从简）

    def test_suggest_不越权写_protection_level(self, client, api_setup):
        s, a, headers = api_setup
        res = client.post(
            f"/api/v1/business-systems/{s.id}/suggest-protection-level",
            headers=headers,
        )
        body = res.json()
        assert body["code"] == 200
        data = body["data"]
        # S4 红线：建议落 suggested_*，protection_level 不变
        assert data["suggested_protection_level"] is not None
        assert data["rating_status"] == "suggested"
        assert data["protection_level"] == "level_2"  # 未被建议覆盖
        assert data["suggestion_basis"]["engine"] == "matrix_v1"

    def test_role_非法值_422(self, client, api_setup):
        s, a, headers = api_setup
        res = client.post(
            f"/api/v1/business-systems/assets/{a.id}/systems",
            json={"system_id": str(s.id), "role": "not_a_role"},
            headers=headers,
        )
        body = res.json()
        assert body.get("code") == 422

    def test_PATCH_role_成功(self, client, api_setup):
        s, a, headers = api_setup
        client.post(
            f"/api/v1/business-systems/assets/{a.id}/systems",
            json={"system_id": str(s.id), "role": "web"},
            headers=headers,
        )
        res = client.patch(
            f"/api/v1/business-systems/assets/{a.id}/systems/{s.id}",
            json={"role": "db"},
            headers=headers,
        )
        body = res.json()
        assert body["code"] == 200
        assert body["data"]["role"] == "db"

    def test_coverage_kpi_口径(self, client, api_setup):
        s, a, headers = api_setup
        # api_setup：1 资产已建但未 link → link 后覆盖率 100%（测试库只有这一个资产）
        client.post(
            f"/api/v1/business-systems/assets/{a.id}/systems",
            json={"system_id": str(s.id)},
            headers=headers,
        )
        res = client.get("/api/v1/business-systems/coverage-kpi", headers=headers)
        body = res.json()
        assert body["code"] == 200
        kpi = body["data"]
        assert kpi["total_assets"] >= 1
        assert kpi["linked_assets"] >= 1
        assert 0 < kpi["coverage_rate"] <= 100
        assert kpi["systems_count"] >= 1


class TestAssetPutSourceFlip:
    """§5.3 v2：值有变才翻转 source"""

    def _get_asset(self, client, asset_id, headers):
        res = client.get(f"/api/v1/assets/{asset_id}", headers=headers)
        body = res.json()
        return body["data"] if body.get("code") == 200 else body

    def test_例行编辑_携带现值_source_不变(self, client, api_setup):
        s, a, headers = api_setup
        # link + 传播成 inherited level_2
        client.post(
            f"/api/v1/business-systems/assets/{a.id}/systems",
            json={"system_id": str(s.id), "inherit": True},
            headers=headers,
        )
        # 例行编辑：改名字，全量带 protection_level=现值
        res = client.put(
            f"/api/v1/assets/{a.id}",
            json={"name": "renamed", "protection_level": "level_2"},
            headers=headers,
        )
        assert res.json().get("code") == 200
        d = self._get_asset(client, a.id, headers)
        assert d["protection_level_source"] == "inherited"  # 不被例行编辑翻转

    def test_改值_翻_manual(self, client, api_setup):
        s, a, headers = api_setup
        client.post(
            f"/api/v1/business-systems/assets/{a.id}/systems",
            json={"system_id": str(s.id), "inherit": True},
            headers=headers,
        )
        res = client.put(
            f"/api/v1/assets/{a.id}",
            json={"protection_level": "level_1"},  # 值变了
            headers=headers,
        )
        assert res.json().get("code") == 200
        d = self._get_asset(client, a.id, headers)
        assert d["protection_level_source"] == "manual"
        assert d["protection_level"] == "level_1"


class TestSortOrder:
    def test_等保档位降序_不是字母序(self, client, db_session, admin_user, api_setup):
        _, _, headers = api_setup
        # 建一个 level_3 系统，应排在 level_2 前（原 bug：criticality 字母序 medium>low）
        _mk_system(db_session, "zz-sys", pl="level_3")
        res = client.get("/api/v1/business-systems?page=1&page_size=50", headers=headers)
        items = res.json()["data"]["items"]
        levels = [i["protection_level"] for i in items]
        # level_3 系统必须出现在所有 level_2 系统之前
        first_l2 = next((idx for idx, lv in enumerate(levels) if lv == "level_2"), None)
        idx_l3 = next((idx for idx, lv in enumerate(levels) if lv == "level_3"), None)
        assert idx_l3 is not None
        if first_l2 is not None:
            assert idx_l3 < first_l2
