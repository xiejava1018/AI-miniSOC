"""
邮件模板注册表（OH-NOT-F2 · Phase 2）

CLAUDE.md §0 模板维护约定 + §1.2 数据来源单一。

Phase 2 策略：内置 Python str.format 模板（CLAUDE.md §0 「简单可读优先于花哨模板」），
HTML 用 escape 自动防 XSS（CLAUDE.md §0 「邮件可读性 + 安全」）。

Phase 3 才支持用户自定义模板（届时改用 Jinja2 沙箱 — Jinja2 已加进 requirements.txt 备用）。
"""

from __future__ import annotations

import html
import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailTemplate:
    """邮件模板（三件套：subject + text + html）

    text/plain 给不支持 HTML 的邮件客户端；
    text/html 给支持 HTML 的（带 HTML escape 防 XSS）。
    """

    type: str
    subject_tmpl: str
    text_tmpl: str
    html_tmpl: str

    def render_subject(self, ctx: Dict[str, Any]) -> str:
        return self.subject_tmpl.format(**ctx)

    def render_text(self, ctx: Dict[str, Any]) -> str:
        return self.text_tmpl.format(**ctx)

    def render_html(self, ctx: Dict[str, Any]) -> str:
        # 自动 escape 防 XSS（CLAUDE.md §0）
        safe_ctx: Dict[str, Any] = {}
        for k, v in ctx.items():
            if isinstance(v, str):
                safe_ctx[k] = html.escape(v)
            elif isinstance(v, dict):
                safe_ctx[k] = {kk: html.escape(vv) if isinstance(vv, str) else vv for kk, vv in v.items()}
            else:
                safe_ctx[k] = v
        return self.html_tmpl.format(**safe_ctx)


# ============================================================
# 内置模板
# ============================================================

# 通用 fallback 模板
DEFAULT_TEMPLATE = EmailTemplate(
    type="_default",
    subject_tmpl="[AI-miniSOC] {notification[title]}",
    text_tmpl=(
        "你好 {user[username]},\n\n"
        "{notification[title]}\n"
        "--------------------\n"
        "{notification[content]}\n\n"
        "查看详情：{notification[link]}\n"
        "--\n"
        "AI-miniSOC 通知中心\n"
        "如不再需要此类邮件，可直接退订：{unsubscribe_url}"
    ),
    html_tmpl=(
        "<!DOCTYPE html><html><body style=\"font-family:Arial,sans-serif\">"
        "<p>你好 {user[username]},</p>"
        "<h2 style=\"color:#3a86ff\">{notification[title]}</h2>"
        "<div style=\"padding:16px;border-left:4px solid #3a86ff;background:#f8f9fa\">"
        "<p>{notification[content]}</p>"
        "</div>"
        "<p><a href=\"{notification[link]}\" style=\"background:#3a86ff;color:#fff;padding:8px 16px;border-radius:4px;text-decoration:none\">查看详情</a></p>"
        "<hr><small style=\"color:#999\">AI-miniSOC 通知中心 · "
        "<a href=\"{unsubscribe_url}\" style=\"color:#999\">退订此类邮件</a></small>"
        "</body></html>"
    ),
)

# EOL 临近
TEMPLATE_EOL_WARNING = EmailTemplate(
    type="push:eol_warning",
    subject_tmpl="[资产 EOL 临近] {eol_count} 台资产将在 {days_until_eol} 天内到期",
    text_tmpl=(
        "你好 {user[username]},\n\n"
        "系统检测到 {eol_count} 台资产即将到达 EOL (End of Life) 时间：\n"
        "  - 最临近：{days_until_eol} 天后\n"
        "  - 总数：{eol_count} 台\n"
        "  - 列表预览（top {sample_count}）：\n{eol_list}\n\n"
        "请尽快评估升级或替换计划。\n"
        "查看详情：{notification[link]}\n"
    ),
    html_tmpl=(
        "<!DOCTYPE html><html><body style=\"font-family:Arial,sans-serif\">"
        "<p>你好 {user[username]},</p>"
        "<h2 style=\"color:#d97706\">⚠️ {eol_count} 台资产 EOL 临近</h2>"
        "<p>最临近：<strong>{days_until_eol} 天后</strong></p>"
        "<pre style=\"background:#fff7ed;padding:12px;border-left:4px solid #d97706\">{eol_list}</pre>"
        "<p><a href=\"{notification[link]}\">查看详情</a></p>"
        "</body></html>"
    ),
)

# 数据源中断
TEMPLATE_SOURCE_DOWN = EmailTemplate(
    type="push:source_down",
    subject_tmpl="[数据源中断] {source_code} 已中断 {down_hours} 小时",
    text_tmpl=(
        "你好 {user[username]},\n\n"
        "数据源 {source_code} 已中断 {down_hours} 小时 (超过阈值 {down_threshold} 小时)。\n"
        "影响：{impact}\n\n"
        "建议排查：\n  1. 检查数据源配置\n  2. 检查网络/防火墙\n"
        "  3. 查看 [source_health] 页面\n\n"
        "查看详情：{notification[link]}"
    ),
    html_tmpl=(
        "<!DOCTYPE html><html><body style=\"font-family:Arial,sans-serif\">"
        "<h2 style=\"color:#dc2626\">🔴 数据源中断</h2>"
        "<p>{source_code} 已中断 <strong>{down_hours} 小时</strong> (阈值 {down_threshold} 小时)</p>"
        "<p>影响：{impact}</p>"
        "<p><a href=\"{notification[link]}\">查看详情</a></p>"
        "</body></html>"
    ),
)

# 风险评分突变
TEMPLATE_RISK_SPIKE = EmailTemplate(
    type="push:risk_spike",
    subject_tmpl="[风险评分突变] {asset_count} 台资产评分上升",
    text_tmpl=(
        "你好 {user[username]},\n\n"
        "近 7 天检测到 {asset_count} 台资产评分显著上升：\n"
        "{asset_list}\n\n"
        "查看详情：{notification[link]}"
    ),
    html_tmpl=(
        "<!DOCTYPE html><html><body style=\"font-family:Arial,sans-serif\">"
        "<h2 style=\"color:#dc2626\">📈 风险评分突变</h2>"
        "<pre style=\"background:#fee2e2;padding:12px;border-left:4px solid #dc2626\">{asset_list}</pre>"
        "<p><a href=\"{notification[link]}\">查看详情</a></p>"
        "</body></html>"
    ),
)

# 影子资产发现
TEMPLATE_SHADOW_ASSET = EmailTemplate(
    type="push:shadow_asset",
    subject_tmpl="[影子资产] {count} 台新影子资产待确认",
    text_tmpl=(
        "你好 {user[username]},\n\n"
        "系统检测到 {count} 台新影子资产待确认。\n"
        "{shadow_list}\n\n"
        "请到「资产 → 影子资产」页面确认。\n"
        "查看详情：{notification[link]}"
    ),
    html_tmpl=(
        "<!DOCTYPE html><html><body style=\"font-family:Arial,sans-serif\">"
        "<h2 style=\"color:#7c3aed\">👥 新影子资产待确认</h2>"
        "<pre>{shadow_list}</pre>"
        "<p><a href=\"{notification[link]}\">查看详情</a></p>"
        "</body></html>"
    ),
)

# 系统/任务告警
TEMPLATE_TASK_ALERT = EmailTemplate(
    type="task_zombie",
    subject_tmpl="[任务异常] {task_key} zombie (失败 {retry_count} 次)",
    text_tmpl=(
        "你好 {user[username]},\n\n"
        "任务 {task_key} 状态异常：zombie (运行超过 2x timeout 且无进度)。\n"
        "已自动转 failed 状态 (retry_count={retry_count})。\n\n"
        "查看详情：{notification[link]}"
    ),
    html_tmpl=(
        "<!DOCTYPE html><html><body style=\"font-family:Arial,sans-serif\">"
        "<h2 style=\"color:#dc2626\">⚠️ 任务异常: {task_key}</h2>"
        "<p>状态: <strong>zombie</strong> · 自动转 failed · retry_count={retry_count}</p>"
        "<p><a href=\"{notification[link]}\">查看详情</a></p>"
        "</body></html>"
    ),
)

# 测试模板（admin /test 端点用）
TEMPLATE_TEST = EmailTemplate(
    type="test",
    subject_tmpl="[AI-miniSOC 邮件测试] 来自通知中心",
    text_tmpl=(
        "你好 {user[username]},\n\n"
        "这是一封来自 AI-miniSOC 通知中心 SMTP 配置测试邮件。\n"
        "如果你收到这封邮件说明 SMTP 配置正确。\n"
        "测试时间：{test_time}\n"
        "退订：{unsubscribe_url}"
    ),
    html_tmpl=(
        "<!DOCTYPE html><html><body style=\"font-family:Arial,sans-serif\">"
        "<h2 style=\"color:#10b981\">SMTP 配置测试</h2>"
        "<p>你好 {user[username]},</p>"
        "<p>这是一封来自 AI-miniSOC 通知中心的 SMTP 测试邮件。</p>"
        "<p>测试时间：<strong>{test_time}</strong></p>"
        "<hr><small><a href=\"{unsubscribe_url}\" style=\"color:#999\">退订此类邮件</a></small>"
        "</body></html>"
    ),
)


# ============================================================
# Registry (单例 + 线程安全)
# ============================================================

class EmailTemplateRegistry:
    """线程安全的模板注册表（CLAUDE.md §0 + §3.2 模块化）

    Phase 3：优先级 = DB 覆盖（soc_email_templates.enabled=true）> 内置。
    """

    _DB_OVERRIDE_TTL = 60  # 秒

    def __init__(self) -> None:
        self._templates: Dict[str, EmailTemplate] = {}
        self._db_overrides: Dict[str, EmailTemplate] = {}
        self._db_loaded_at: float = 0.0
        self._lock = threading.Lock()
        self._register_defaults()

    def _register_defaults(self) -> None:
        """注册 Phase 2 内置模板（CLAUDE.md §0 模板来源单一）。"""
        for tpl in (
            DEFAULT_TEMPLATE,
            TEMPLATE_EOL_WARNING,
            TEMPLATE_SOURCE_DOWN,
            TEMPLATE_RISK_SPIKE,
            TEMPLATE_SHADOW_ASSET,
            TEMPLATE_TASK_ALERT,
            TEMPLATE_TEST,
        ):
            self._templates[tpl.type] = tpl

    # ---------------- Phase 3: DB 覆盖 ----------------

    def ensure_db_overrides(self, db) -> None:
        """从 soc_email_templates 加载 enabled 覆盖（60s 缓存）。

        调用方传 db session（worker / API 均有）；失败静默回退内置
        （CLAUDE.md §4.13：模板库故障不应阻断邮件投递）。
        """
        import time as _time
        with self._lock:
            if _time.time() - self._db_loaded_at < self._DB_OVERRIDE_TTL:
                return
        try:
            from app.models.notification_channel import EmailTemplateOverride
            rows = (
                db.query(EmailTemplateOverride)
                .filter(EmailTemplateOverride.enabled.is_(True))
                .all()
            )
            overrides = {
                r.type: EmailTemplate(
                    type=r.type,
                    subject_tmpl=r.subject_tmpl,
                    text_tmpl=r.text_tmpl,
                    html_tmpl=r.html_tmpl,
                )
                for r in rows
            }
            with self._lock:
                self._db_overrides = overrides
                self._db_loaded_at = _time.time()
        except Exception:  # noqa: BLE001
            logger.warning("email template db override load failed; fallback builtin",
                           exc_info=True)
            with self._lock:
                self._db_loaded_at = _time.time()  # 失败也记账，避免每封邮件都撞库

    def invalidate_db_overrides(self) -> None:
        """admin 改完模板后立即清缓存。"""
        with self._lock:
            self._db_loaded_at = 0.0
            self._db_overrides = {}

    def get(self, type: str) -> Optional[EmailTemplate]:
        return self._db_overrides.get(type) or self._templates.get(type)

    def get_builtin(self, type: str) -> Optional[EmailTemplate]:
        """仅查内置（API 展示「重置到默认」用）。"""
        return self._templates.get(type)

    def list_builtin_types(self) -> list[str]:
        return list(self._templates.keys())

    def get_default(self) -> EmailTemplate:
        return self._db_overrides.get("_default") or self._templates["_default"]

    def register(self, template: EmailTemplate) -> None:
        """进程内注册（测试用；生产覆盖走 DB）"""
        with self._lock:
            self._templates[template.type] = template
        logger.info("email template registered: %s", template.type)


_REGISTRY: Optional[EmailTemplateRegistry] = None


def get_template_registry() -> EmailTemplateRegistry:
    """进程级单例"""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = EmailTemplateRegistry()
    return _REGISTRY


__all__ = [
    "EmailTemplate",
    "EmailTemplateRegistry",
    "get_template_registry",
    "DEFAULT_TEMPLATE",
]