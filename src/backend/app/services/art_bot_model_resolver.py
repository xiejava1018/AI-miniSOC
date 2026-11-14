"""Art Bot 模型解析：统一走「配置中心 → AI 模型管理」（soc_ai_providers）

背景（2026-11-10 生产事故）
------------------------
Art Bot（pi_agent 后端）此前把模型硬编码成 ``agnes/agnes-2.0-flash``：

    # pi_agent_chat_service.py
    DEFAULT_MODEL = "agnes/agnes-2.0-flash"

后果：
  1. 「配置中心 → AI 模型管理」里配置的模型实例对 Art Bot **完全无效**
     —— 改配置没反应（用户以为没生效，其实是另一条链路）。
  2. Agnes AI 免费额度打满时（HTTP 429 rate limit），Art Bot 静默无响应：
     runner 的 error 事件被丢弃，Python 侧也没有 error 分支，
     SSE 只吐 ``data: [DONE]``，前端表现为「聊天没反应」。

现在改为：**Art Bot 使用配置中心「AI 模型管理」里启用的模型实例**，
通过已有的 ``data_source_resolver.resolve_ai(scene="chat")`` 解析：

  1. scenes 含 "chat" 的启用实例（精确路由）→ 优先
  2. is_default=true 的启用实例
  3. 任一启用实例（WARN）
  4. 表里一个实例都没有 → 回落 env GLM_*（迁移期零中断）
  5. 有实例但全部停用 → 不回落，AI 不可用（尊重用户明确意图）

解析结果转成 Node runner 能懂的环境变量（见 agent_process_manager._spawn）：
  PI_MODEL           = "<provider_code>/<model_name>"
  PI_PROVIDER_CODE   = "<provider_code>"
  PI_BASE_URL        = "<base_url>"
  PI_PROTOCOL        = "<protocol>"（openai / openai-responses）
  PI_MAX_TOKENS      = "<max_tokens>"
  PI_TIMEOUT_SECONDS = "<timeout_seconds>"
  PI_API_KEY         = "<解密后的 key>"

设计要点
--------
- **不硬编码任何模型名**：DEFAULT_MODEL 保留为兼容旧会话的兜底，
  新会话走 resolve_ai 的结果。
- **api_key 只在内存里传给子进程 env**，不落库、不进日志。
- **env 回落仍支持**：老部署没有配置 AI 实例时用 GLM_*，
  与其他 AI 功能保持一致的行为。
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# 兼容旧会话 / 配置缺失时的兜底模型标识。
# 注意：这是「最后兜底」，正常路径由 resolve_ai 从配置中心解析。
DEFAULT_MODEL = "openai/glm-4-flash"

# Art Bot 使用的场景标签 → 匹配 soc_ai_providers.scenes 里的 "chat"
ART_BOT_SCENE = "chat"

# provider_code → Node 侧 pi-ai 的 api 类型。
#   openai-responses → POST {base}/responses（Agnes AI 用）
#   openai-completions → POST {base}/chat/completions（GLM / DeepSeek 等用）
_PROTOCOL_TO_API = {
    "openai": "openai-completions",
    "openai-completions": "openai-completions",
    "openai-responses": "openai-responses",
}


class ArtBotModelConfig:
    """Art Bot 使用的模型配置（已解密，可直接传给子进程）。"""

    def __init__(
        self,
        model: str,
        provider_code: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api: str = "openai-completions",
        max_tokens: Optional[int] = None,
        timeout_seconds: Optional[int] = None,
        origin: str = "unknown",
    ) -> None:
        self.model = model
        self.provider_code = provider_code
        self.base_url = base_url
        self.api_key = api_key
        self.api = api
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.origin = origin

    def to_env(self) -> Dict[str, str]:
        """转成 Node 子进程的环境变量（api_key 只在这里出现，不落日志）。"""
        env: Dict[str, str] = {
            "PI_MODEL": self.model,
            "PI_PROVIDER_CODE": self.provider_code,
            "PI_API": self.api,
        }
        if self.base_url:
            env["PI_BASE_URL"] = self.base_url
        if self.api_key:
            env["PI_API_KEY"] = self.api_key
        if self.max_tokens:
            env["PI_MAX_TOKENS"] = str(self.max_tokens)
        if self.timeout_seconds:
            env["PI_TIMEOUT_SECONDS"] = str(self.timeout_seconds)
        return env

    def __repr__(self) -> str:  # pragma: no cover - 仅调试
        return (
            f"ArtBotModelConfig(model={self.model!r}, provider_code={self.provider_code!r}, "
            f"api={self.api!r}, origin={self.origin!r}, has_key={bool(self.api_key)})"
        )


def resolve_art_bot_model(db=None) -> ArtBotModelConfig:
    """解析 Art Bot 应使用的模型配置。

    优先「配置中心 → AI 模型管理」；表里没有实例时回落 env GLM_*。
    """
    # ---- 1) 配置中心（soc_ai_providers）----
    try:
        from app.services.data_source_resolver import data_source_resolver

        resolved = data_source_resolver.resolve_ai(scene=ART_BOT_SCENE, db=db)
        cfg = resolved.config or {}
        cjson = cfg.get("config_json") or {}

        provider_code = resolved.source_code or "db"
        model_name = cjson.get("model")
        base_url = cfg.get("endpoint")
        api_key = cfg.get("password")  # 已由 resolver 解密

        if model_name and api_key:
            protocol = (cjson.get("protocol") or "openai").lower()
            api = _PROTOCOL_TO_API.get(protocol, "openai-completions")
            # 传给 runner 的模型标识：provider_code/model_name
            full_model = f"{provider_code}/{model_name}"
            # timeout_seconds 是「连通性测试」用的超时（配置中心默认 5s），
            # 拿来做推理会必然超时 → 用 ART_BOT_TIMEOUT_SECONDS 兜底为 120s。
            # 显式设置 PI_TIMEOUT_SECONDS 时才覆盖。
            raw_timeout = cfg.get("timeout_seconds")
            timeout = None
            env_timeout = os.getenv("ART_BOT_TIMEOUT_SECONDS")
            if env_timeout:
                timeout = int(env_timeout)
            elif raw_timeout and int(raw_timeout) >= 30:
                # 配置值足够大才采纳（区分「测试超时」与「推理超时」）
                timeout = int(raw_timeout)
            else:
                timeout = 120
            logger.info(
                "Art Bot 使用配置中心 AI 模型: provider=%s model=%s api=%s timeout=%ss origin=%s",
                provider_code,
                model_name,
                api,
                timeout,
                resolved.origin,
            )
            return ArtBotModelConfig(
                model=full_model,
                provider_code=provider_code,
                base_url=base_url,
                api_key=api_key,
                api=api,
                max_tokens=cjson.get("max_tokens"),
                timeout_seconds=timeout,
                origin=resolved.origin,
            )

        if resolved.origin == "none":
            # 有实例但全部停用 → 用户明确关闭，不回落 env
            logger.warning(
                "Art Bot：全部 AI Provider 均已停用，聊天不可用（不回落 env）"
            )
            raise RuntimeError(
                "AI 模型不可用：配置中心「AI 模型管理」中的模型实例均已停用"
            )
    except RuntimeError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning("Art Bot 解析配置中心 AI 模型失败（回落 env）：err=%s", e)

    # ---- 2) env 回落（GLM_*）----
    glm_key = os.getenv("GLM_API_KEY")
    glm_model = os.getenv("GLM_MODEL")
    glm_base = os.getenv("GLM_API_BASE")
    if glm_key and glm_model:
        logger.warning(
            "Art Bot 回落 env GLM 模型: model=%s（配置中心无启用实例）", glm_model
        )
        return ArtBotModelConfig(
            model=f"env/{glm_model}",
            provider_code="env",
            base_url=glm_base,
            api_key=glm_key,
            api="openai-completions",
            origin="env",
        )

    raise RuntimeError(
        "AI 模型不可用：配置中心「AI 模型管理」无启用实例，且 env GLM_API_KEY/GLM_MODEL 未配置"
    )


def build_agent_config(
    db=None,
    model_override: Optional[str] = None,
    trace_id: Optional[str] = None,
    system_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """构造 AgentProcessManager 的 config。

    优先用 model_override（旧会话里存的 model_name）；否则用配置中心解析结果。
    """
    model_cfg = resolve_art_bot_model(db=db)

    config: Dict[str, Any] = {
        "model": model_override or model_cfg.model,
        "env": model_cfg.to_env(),
        "trace_id": trace_id,
    }
    if system_prompt:
        config["system_prompt"] = system_prompt
    # 兼容旧字段：runner 仍读 AGNES_API_KEY（Agnes 场景）
    if model_cfg.api == "openai-responses" and model_cfg.api_key:
        config["api_key"] = model_cfg.api_key
    return config
