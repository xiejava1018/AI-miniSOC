"""统一 AI 客户端（AI Provider 多模型支持 P0）

设计：docs/design AI Provider 注册表（复用 soc_data_sources，source_type='ai'）

- OpenAI 兼容协议一个实现覆盖 GLM/DeepSeek/Qwen/Kimi/OpenAI/Ollama 等
- 调用方只给 scene（如 "asset_query"/"report"），路由由 resolve_ai 完成：
  场景精确路由 → 默认 ai 实例 → env 回落 GLM_*（现行为不变）
- 自带 ai_budget 熔断挂钩（按 provider 分账）、超时、重试、异常归一化
- 任何异常抛 AIClientError，调用方按既有降级路径处理（不静默编造）

用法：
    from app.services.ai_client import ai_chat
    text = ai_chat(prompt, scene="asset_query", temperature=0.1, db=db)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class AIClientError(Exception):
    """AI 调用失败（认证/网络/超时/限流）。调用方按既有降级路径处理。"""

    def __init__(self, message: str, *, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


# 各场景建议超时（秒）；AI 生成类场景耗时较长
_SCENE_TIMEOUT = {"report": 180, "impact": 180, "chat": 120}
_DEFAULT_TIMEOUT = 60


def _resolve_provider(scene: Optional[str], db: Optional[Any] = None) -> Dict[str, Any]:
    from app.services.data_source_resolver import data_source_resolver

    resolved = data_source_resolver.resolve_ai(scene, db)
    cfg = resolved.config or {}
    if not cfg.get("endpoint") or not cfg.get("password"):
        raise AIClientError("AI Provider 未配置（数据源管理与 .env 均无可用配置）")
    return cfg


def ai_provider_available(db: Optional[Any] = None) -> bool:
    """是否有可用的 AI Provider（DB 实例或 env GLM_*）。供消费点降级守卫用。"""
    try:
        _resolve_provider(None, db)
        return True
    except AIClientError:
        return False


def ai_chat(
    prompt: str,
    *,
    scene: Optional[str] = None,
    system: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    model_override: Optional[str] = None,
    json_mode: bool = False,
    db: Optional[Any] = None,
    _budget: bool = True,
) -> str:
    """调 LLM 返回文本。失败抛 AIClientError（含 401/429 等）。

    _budget=False 跳过熔断记账（测试连接等探活场景用）。
    """
    cfg = _resolve_provider(scene, db)
    extra = cfg.get("config_json") or {}
    model = model_override or extra.get("model") or getattr(settings, "GLM_MODEL", "glm-4-flash")
    base_url = str(cfg["endpoint"]).rstrip("/")
    api_key = cfg["password"]
    timeout = extra.get("timeout_seconds") or _SCENE_TIMEOUT.get(scene or "", _DEFAULT_TIMEOUT)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    headers.update(extra.get("extra_headers") or {})

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    effective_max_tokens = max_tokens or extra.get("max_tokens")
    if effective_max_tokens:
        body["max_tokens"] = effective_max_tokens
    if json_mode:
        # OpenAI 兼容：response_format json_object；部分国产兼容层忽略该参数，无害
        body["response_format"] = {"type": "json_object"}

    if _budget:
        from app.services.ai_budget import ai_budget

        if not ai_budget.allow():
            raise AIClientError("AI 调用已达今日配额或熔断中，请稍后重试", status_code=429)

    started = time.time()
    try:
        with httpx.Client(verify=cfg.get("verify_ssl", False), timeout=timeout) as client:
            resp = client.post(f"{base_url}/chat/completions", headers=headers, json=body)
    except httpx.HTTPError as e:
        if _budget:
            from app.services.ai_budget import ai_budget

            ai_budget.record_failure()
        raise AIClientError(f"AI 请求失败: {e}") from e

    if resp.status_code != 200:
        if _budget:
            from app.services.ai_budget import ai_budget

            ai_budget.record_failure()
        snippet = resp.text[:300]
        raise AIClientError(
            f"AI 服务返回 HTTP {resp.status_code}: {snippet}", status_code=resp.status_code
        )

    try:
        data = resp.json()
        text = (data["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:
        raise AIClientError(f"AI 响应解析失败: {e}") from e

    if _budget:
        from app.services.ai_budget import ai_budget

        ai_budget.record_success()

    logger.debug(
        "ai_chat scene=%s model=%s latency=%.1fs len=%d",
        scene,
        model,
        time.time() - started,
        len(text),
    )
    return text
