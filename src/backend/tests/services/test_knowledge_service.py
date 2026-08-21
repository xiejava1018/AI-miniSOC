"""
F2.3 运维知识库服务测试

覆盖（PRD F2.3 / v1.2 修订）：
- 自动提取：已解决事件 → 三元组落库；GLM 降级模板；source_id 幂等去重；force 重提取；未解决事件不提取
- 检索：召回打分（title 加权）；待复审降权；空结果诚实返回；GLM 降级 recall 顺序
- 老化：COALESCE 基准（新提取不误入）；超 12 个月入 pending_review；validate 回 active+90
- CRUD：创建（manual 置信 90+已验证）；编辑；删除
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Incident
from app.models.knowledge import Knowledge
from app.services.knowledge_service import KnowledgeService


def _now():
    return datetime.now(timezone.utc)


def _make_incident(db, status="resolved", title="SSH 暴力破解告警堆积", notes=None):
    inc = Incident(
        title=title,
        description="多台主机出现大量 SSH 认证失败告警",
        status=status, severity="high", created_by="test",
        resolution_notes=notes or "确认为扫描器误报，已加白名单并封禁来源 IP",
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)
    return inc


class TestAutoExtract:
    def test_extract_fallback_and_dedup(self, db_session, monkeypatch):
        """GLM 预算拒绝 → 模板降级；同事件二次提取去重"""
        inc = _make_incident(db_session)
        monkeypatch.setattr("app.services.knowledge_service.ai_budget.allow", lambda: False)
        svc = KnowledgeService(db_session)
        s1 = svc.auto_extract()
        assert s1["extracted"] == 1 and s1["source"]["rule"] == 1
        k = db_session.query(Knowledge).filter_by(source_id=str(inc.id)).one()
        assert "扫描器误报" in k.content
        assert k.confidence_score == 70
        assert k.review_status == "active"

        s2 = svc.auto_extract()  # 幂等去重
        assert s2["extracted"] == 0
        assert db_session.query(Knowledge).filter_by(source_id=str(inc.id)).count() == 1

    def test_force_reextract(self, db_session, monkeypatch):
        inc = _make_incident(db_session)
        monkeypatch.setattr("app.services.knowledge_service.ai_budget.allow", lambda: False)
        svc = KnowledgeService(db_session)
        svc.auto_extract()
        s = svc.auto_extract(force=True)
        assert s["extracted"] == 1
        assert db_session.query(Knowledge).filter_by(source_id=str(inc.id)).count() == 2

    def test_open_incident_not_extracted(self, db_session, monkeypatch):
        _make_incident(db_session, status="in_progress")
        monkeypatch.setattr("app.services.knowledge_service.ai_budget.allow", lambda: False)
        s = KnowledgeService(db_session).auto_extract()
        assert s["candidates"] == 0 and s["extracted"] == 0


class TestSearch:
    def test_recall_and_fallback_rerank(self, db_session, monkeypatch):
        db_session.add(Knowledge(
            title="SSH 暴力破解处置手册", content="【故障】SSH 爆破\n【解决方案】启用 fail2ban",
            category="troubleshooting", source_type="manual", tags="ssh,暴力破解",
            confidence_score=90, last_validated_at=_now(),
        ))
        db_session.add(Knowledge(
            title="磁盘扩容操作", content="LVM 扩容步骤", source_type="manual",
            confidence_score=90, last_validated_at=_now(),
        ))
        db_session.commit()
        monkeypatch.setattr("app.services.knowledge_service.ai_budget.allow", lambda: False)
        out = KnowledgeService(db_session).search("SSH 爆破怎么处理")
        assert out["rerank_source"] == "recall"
        assert out["results"]
        assert "SSH" in out["results"][0]["title"]  # 相关性最高的排前

    def test_empty_result_honest(self, db_session, monkeypatch):
        monkeypatch.setattr("app.services.knowledge_service.ai_budget.allow", lambda: False)
        out = KnowledgeService(db_session).search("完全不相关的问题xyzzy")
        assert out["results"] == []
        assert "未找到" in out["message"]  # 诚实返回 + 引导

    def test_stale_deprioritized(self, db_session, monkeypatch):
        """待复审知识在召回中降权（排后）"""
        db_session.add(Knowledge(
            title="SSH 处置旧文档", content="ssh 旧方案", source_type="manual",
            review_status="pending_review", confidence_score=70,
        ))
        db_session.add(Knowledge(
            title="SSH 处置新文档", content="ssh 新方案", source_type="manual",
            review_status="active", confidence_score=70,
        ))
        db_session.commit()
        monkeypatch.setattr("app.services.knowledge_service.ai_budget.allow", lambda: False)
        out = KnowledgeService(db_session).search("ssh 处置")
        titles = [r["title"] for r in out["results"]]
        assert titles.index("SSH 处置新文档") < titles.index("SSH 处置旧文档")


class TestAging:
    def test_new_extraction_not_stale(self, db_session):
        """新提取（无验证时间）不误入待复审——COALESCE(created_at) 基准"""
        db_session.add(Knowledge(
            title="新知识", content="x", source_type="incident_summary",
            source_id="inc-1", confidence_score=70,  # last_validated_at=None
        ))
        db_session.commit()
        svc = KnowledgeService(db_session)
        assert svc.mark_stale() == 0
        assert db_session.query(Knowledge).filter_by(review_status="pending_review").count() == 0

    def test_old_knowledge_goes_stale(self, db_session):
        old = Knowledge(title="旧知识", content="x", source_type="manual", confidence_score=90)
        db_session.add(old)
        db_session.commit()
        # 手动把 created_at 拨回 13 个月前
        db_session.query(Knowledge).filter_by(id=old.id).update(
            {"created_at": _now() - timedelta(days=400), "last_validated_at": _now() - timedelta(days=400)})
        db_session.commit()
        svc = KnowledgeService(db_session)
        assert svc.mark_stale() == 1
        db_session.refresh(old)
        assert old.review_status == "pending_review"

    def test_validate_recovers(self, db_session):
        k = Knowledge(title="待验证", content="x", review_status="pending_review", confidence_score=70)
        db_session.add(k)
        db_session.commit()
        out = KnowledgeService(db_session).validate(k.id)
        assert out.confidence_score == 90
        assert out.review_status == "active"
        assert out.last_validated_at is not None


class TestCrud:
    def test_create_manual_defaults(self, db_session):
        k = KnowledgeService(db_session).create(
            {"title": "手动知识", "content": "内容", "tags": ["a", "b"]}, created_by="alice")
        assert k.source_type == "manual"
        assert k.confidence_score == 90       # 手动录入默认高置信 + 已验证
        assert k.last_validated_at is not None
        assert k.tag_list == ["a", "b"]

    def test_update_and_delete(self, db_session):
        k = KnowledgeService(db_session).create({"title": "t", "content": "c"})
        svc = KnowledgeService(db_session)
        updated = svc.update(k.id, {"title": "t2", "tags": ["x"]})
        assert updated.title == "t2" and updated.tag_list == ["x"]
        assert svc.delete(k.id) is True
        assert svc.delete(k.id) is False

    def test_list_filters(self, db_session):
        db_session.add(Knowledge(title="a", content="x", category="policy",
                                 review_status="pending_review", source_type="manual"))
        db_session.add(Knowledge(title="b", content="y", category="troubleshooting",
                                 source_type="manual"))
        db_session.commit()
        svc = KnowledgeService(db_session)
        assert svc.list_items(category="policy")["total"] == 1
        assert svc.list_items(review_status="pending_review")["total"] == 1
        assert svc.list_items(q="y")["total"] == 1
