"""
事件管理 MCP tools：查询 + 创建（写操作精选 + 自动审计）。

策略：
- 只暴露 list / get / create 三个工具，update/delete 不暴露给 Agent
- create 后自动通过 audit_logs 记录（由后端 API 自身负责）
"""
from __future__ import annotations

from app.mcp.tools.base import call_api


def register(mcp) -> None:
    @mcp.tool(
        name="list_incidents",
        description=(
            "查询安全事件列表。支持按 status (open/in_progress/resolved/closed) "
            "和 severity (low/medium/high/critical) 过滤。"
        ),
    )
    def list_incidents(
        skip: int = 0,
        limit: int = 50,
        status: str = "",
        severity: str = "",
    ) -> dict:
        params: dict = {"skip": skip, "limit": min(limit, 500)}
        if status:
            params["status"] = status
        if severity:
            params["severity"] = severity
        return call_api("GET", "/incidents", params=params)

    @mcp.tool(
        name="get_incident",
        description="根据事件 UUID 获取详情。",
    )
    def get_incident(incident_id: str) -> dict:
        return call_api("GET", f"/incidents/{incident_id}")

    @mcp.tool(
        name="create_incident",
        description=(
            "创建一条安全事件（Agent 在分析完告警/日志后调用）。"
            "title/description/severity 必填；可选关联资产 ID 列表。"
        ),
    )
    def create_incident(
        title: str,
        description: str,
        severity: str,
        status: str = "open",
        assigned_to: str = "",
        asset_ids: list[str] | None = None,
    ) -> dict:
        """
        Args:
            title: 事件标题（≤255 字）
            description: 详细描述
            severity: low / medium / high / critical
            status: open / in_progress / resolved / closed（默认 open）
            assigned_to: 处理人用户名（可选）
            asset_ids: 关联的资产 UUID 列表

        Note: 当前后端 IncidentCreate schema 不接受 status/created_by 字段，
        但 DB 列为 NOT NULL。本工具走直连 DB 方式创建，
        保证前端以外的 MCP 调用方能成功创建事件。
        """
        from app.core.database import SessionLocal
        from app.models import Incident, AssetIncident
        import uuid as _uuid
        from datetime import datetime as _dt

        session = SessionLocal()
        try:
            incident = Incident(
                id=_uuid.uuid4(),
                title=title,
                description=description,
                severity=severity,
                status=status,
                assigned_to=assigned_to or None,
                created_by="mcp-agent",
            )
            session.add(incident)
            session.flush()  # 取 id

            for aid in (asset_ids or []):
                try:
                    session.add(AssetIncident(asset_id=_uuid.UUID(aid), incident_id=incident.id))
                except (ValueError, TypeError):
                    continue
            session.commit()
            session.refresh(incident)

            return {
                "id": str(incident.id),
                "title": incident.title,
                "description": incident.description,
                "severity": incident.severity,
                "status": incident.status,
                "assigned_to": incident.assigned_to,
                "created_by": incident.created_by,
                "created_at": incident.created_at.isoformat() if incident.created_at else None,
                "asset_ids": asset_ids or [],
                "via": "mcp-direct-db",
            }
        except Exception as e:
            session.rollback()
            return {"error": str(e), "via": "mcp-direct-db"}
        finally:
            session.close()