"""ARL-Next 集成采集器（OH-ARL.1，docs/design/2026-11-14-ARL-Next集成设计方案.md §6.1）

拉模型只读：从 ARL-Next 归档态端点（/api/asset_*，按 scope_id 白名单）
定时拉取资产/站点/漏洞测绘数据，规范化后推送 AI-miniSOC：

    data_type = arl_site  → ArlSiteSyncHandler（来源溯源 + 端口融合 + 影子发现）
    data_type = arl_vuln  → ArlVulnSyncHandler（CVE 分流入漏洞模型，无 CVE 旁路发现）

SOC 后端对 ARL 零直接依赖（C7 诚实降级）：ARL 停机仅影响本轮增量，
主数据与告警链路不受影响。采集器不触发任何 ARL 扫描（只读，C3）。
"""

__version__ = "0.1.0"
