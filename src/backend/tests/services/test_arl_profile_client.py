"""OH-ARL.5 · ARL 外部画像客户端 + 研判 prompt 集成测试。

验证（design §6.2）：
  - 未配置 ARL_PROFILE_BASE_URL → available=False（unconfigured），功能关闭
  - 缓存：同 target TTL 内二次调用不发 HTTP
  - 熔断：连续失败 ≥3 → open，冷却期内直接 short-circuit
  - 摘要裁剪：ports ≤10 / vulns ≤5（控 token，C6）
  - prompt 渲染：available=True 注入画像段 + P1 起评规则；
    available=False 显式「不可用」段（C7 诚实降级，不静默当无风险）
"""
from __future__ import annotations

import asyncio

import pytest

from app.services.ai_analysis import AIAnalysisService
from app.services.arl_profile_client import ARLProfileClient


@pytest.fixture
def unconfigured(monkeypatch):
    monkeypatch.setattr(
        "app.services.arl_profile_client.settings.ARL_PROFILE_BASE_URL", None
    )
    return ARLProfileClient()


def test_unconfigured_returns_unavailable(unconfigured):
    out = asyncio.run(unconfigured.get_external_profile("192.168.0.60"))
    assert out == {"available": False, "reason": "unconfigured"}


def test_no_target_short_circuits(unconfigured):
    out = asyncio.run(unconfigured.get_external_profile(None))
    assert out["available"] is False


def test_cache_hit_no_second_fetch(monkeypatch):
    monkeypatch.setattr(
        "app.services.arl_profile_client.settings.ARL_PROFILE_BASE_URL",
        "https://192.168.0.42:5173",
    )
    c = ARLProfileClient()
    calls = []

    async def fake_fetch(base, target):
        calls.append(target)
        return {"target": target,
                "ports": [{"port": 9000, "service": "http",
                           "product": "Portainer"}],
                "vulns": [], "os": "Linux", "resolved_ips": [target]}

    c._fetch = fake_fetch
    first = asyncio.run(c.get_external_profile("192.168.0.60"))
    second = asyncio.run(c.get_external_profile("192.168.0.60"))
    assert first["available"] is True
    assert second["available"] is True
    assert calls == ["192.168.0.60"]  # 第二次走缓存
    assert second["ports"][0]["product"] == "Portainer"


def test_circuit_opens_after_consecutive_failures(monkeypatch):
    monkeypatch.setattr(
        "app.services.arl_profile_client.settings.ARL_PROFILE_BASE_URL",
        "https://192.168.0.42:5173",
    )
    c = ARLProfileClient()
    calls = []

    async def fake_fail(base, target):
        calls.append(target)

    c._fetch = fake_fail
    for _ in range(3):
        out = asyncio.run(c.get_external_profile("10.0.0.1"))
        assert out["available"] is False
    assert len(calls) == 3
    # 熔断 open：第 4 次 short-circuit，不再调 _fetch
    out = asyncio.run(c.get_external_profile("10.0.0.1"))
    assert out["reason"] == "circuit_open"
    assert len(calls) == 3


def test_summarize_truncates():
    profile = {
        "target": "192.168.0.60",
        "resolved_ips": ["192.168.0.60"],
        "os": "Linux",
        "ports": [{"port": i, "service": "http"} for i in range(1, 21)],
        "vulns": [{"plugin_name": f"P{i}", "vuln_url": f"http://x/{i}"}
                  for i in range(1, 9)],
        "cert": {"subject": "test"},
    }
    out = ARLProfileClient._summarize(profile)
    assert len(out["ports"]) == 10 and out["ports_total"] == 20
    assert len(out["vulns"]) == 5 and out["vulns_total"] == 8
    assert out["available"] is True


class TestPromptRender:
    def _sig(self, ext):
        return {
            "fingerprint": "fp-1", "rule_id": "504",
            "rule_description": "暴力破解", "agent_name": "host-a",
            "agent_ip": "192.168.0.60", "count": 10,
            "level_min": 5, "level_max": 10, "sample_full_log": "log",
            "external_profile": ext,
        }

    def test_available_profile_rendered(self):
        sig = self._sig({
            "available": True, "source": "arl-next", "target": "192.168.0.60",
            "resolved_ips": ["192.168.0.60"], "os": "Linux",
            "ports": [{"port": 9000, "service": "http", "product": "Portainer"}],
            "ports_total": 1,
            "vulns": [{"plugin_name": "Swagger_Json_Identify",
                       "url": "https://192.168.0.42:5173"}],
            "vulns_total": 1,
        })
        prompt = AIAnalysisService.__new__(
            AIAnalysisService
        )._build_group_triage_prompt(sig)
        assert "外部攻击面画像（ARL-Next 主动测绘实测" in prompt
        assert "9000/http(Portainer)" in prompt
        assert "Swagger_Json_Identify" in prompt
        assert "至少 P1 起评" in prompt

    def test_unavailable_profile_honest_degradation(self):
        sig = self._sig({"available": False, "reason": "circuit_open"})
        prompt = AIAnalysisService.__new__(
            AIAnalysisService
        )._build_group_triage_prompt(sig)
        assert "不可用（原因: circuit_open）" in prompt
        assert "不代表资产无暴露风险" in prompt
        assert "至少 P1 起评" not in prompt
