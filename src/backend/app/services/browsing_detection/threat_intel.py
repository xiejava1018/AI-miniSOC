"""
威胁情报同步

从公开威胁情报源（abuse.ch URLhaus）拉取恶意域名，写入 soc_browsing_blacklist。

数据源：
  - URLhaus csv_recent: https://urlhaus.abuse.ch/downloads/csv_recent/
    （最近30天恶意URL，CSV格式，url 在第3列）

后续可扩展 PhishTank 等源。
"""

import csv
import io
import logging
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.models.browsing_blacklist import BrowsingBlacklist

logger = logging.getLogger(__name__)

URLHAUS_CSV_URL = "https://urlhaus.abuse.ch/downloads/csv_recent/"


class ThreatIntelSync:
    """威胁情报同步服务"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def sync_urlhaus(self, limit: int = 5000) -> dict:
        """同步 URLhaus 恶意域名到黑名单

        Args:
            limit: 最多拉取的域名数（避免过多）
        Returns:
            {"source": "urlhaus", "fetched": N, "new": M, "error": None}
        """
        result = {"source": "urlhaus", "fetched": 0, "new": 0, "error": None}
        try:
            resp = httpx.get(URLHAUS_CSV_URL, timeout=60, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("拉取 URLhaus 失败: %s", e)
            result["error"] = f"拉取失败: {e}"
            return result

        # 解析 CSV，提取域名
        domains: set[str] = set()
        reader = csv.reader(io.StringIO(resp.text))
        for row in reader:
            if not row or row[0].startswith("#"):
                continue
            # CSV 列: id, dateadded, url, url_status, last_online, threat, tags, urlhaus_link, reporter
            if len(row) < 3:
                continue
            url = row[2].strip()
            if not url:
                continue
            try:
                host = urlparse(url).hostname
                if host:
                    domains.add(host.lower())
            except (ValueError, TypeError):
                continue
            if len(domains) >= limit:
                break

        result["fetched"] = len(domains)
        if not domains:
            result["error"] = "未解析到任何域名"
            return result

        # 写入黑名单（去重）
        existing = {
            r[0]
            for r in self.db.query(BrowsingBlacklist.domain)
            .filter(BrowsingBlacklist.domain.in_(domains))
            .all()
        }
        new_domains = domains - existing
        for d in new_domains:
            self.db.add(
                BrowsingBlacklist(domain=d, source="threat_intel", reason="URLhaus")
            )
        self.db.commit()
        result["new"] = len(new_domains)
        logger.info("URLhaus 同步: 拉取 %d 个域名，新增 %d", len(domains), len(new_domains))
        return result
