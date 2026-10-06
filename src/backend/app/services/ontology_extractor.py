"""本体驱动 LLM 抽取（OH-1.7）

输入非结构化文本（工单 / 渗透测试报告 / 告警描述），由**本体类定义驱动**
LLM 抽取实体，输出 STIX 2.1 兼容的结构化 JSON。

流程：
  text → build_extraction_prompt（本体目标类型清单）→ ai_chat(json_mode)
       → parse_extraction（容错解析 + 归一）→ ExtractionResult

复用而非重写：
  - LLM 调用走 ``ai_client.ai_chat``（含限流/熔断/场景路由）。
  - 目标类型清单来自本体（asset_ontology 的 STIX 标准层），不手抄。
  - 输出 STIX 兼容结构，与 OH-1.6 的导出语义一致。

诚实红线：
  - LLM 抽取**只做提取与呈现，不自动入库 / 不自动建资产**（抽取结果
    可能幻觉，需人工确认后落库——防止脏数据直接进 CMDB）。
  - 解析失败 / LLM 不可用 → 返回 extracted=False + 原始片段，不伪造实体。
  - 置信度是启发式（实体类型合法 + 数量），不是经过标注语料校准的概率。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core import asset_ontology

logger = logging.getLogger(__name__)

# 抽取目标 STIX 类型（从本体 standard_layer 读取；这里是默认/兜底清单）
_DEFAULT_SCO_TYPES = [
    "ipv4-addr", "ipv6-addr", "domain-name", "mac-addr", "url",
    "user-account",
]
_DEFAULT_SDO_TYPES = ["identity", "vulnerability", "location"]

SYSTEM_PROMPT = (
    "你是安全情报实体抽取器。只从给定文本中抽取明确出现的实体，"
    "不得推测或补全文本中没有的信息。输出严格遵循指定 JSON 结构。"
)


def _target_types() -> Tuple[List[str], List[str]]:
    """从本体读取 STIX SCO/SDO 类型清单（读不到用默认）。"""
    try:
        layer = asset_ontology.load().standard_layer
        stix = layer.get("stix_2_1", {})
        return (
            stix.get("sco", _DEFAULT_SCO_TYPES),
            stix.get("sdo", _DEFAULT_SDO_TYPES),
        )
    except Exception:
        return _DEFAULT_SCO_TYPES, _DEFAULT_SDO_TYPES


def build_extraction_prompt(text: str) -> str:
    sco, sdo = _target_types()
    return (
        "从下面文本抽取安全实体，输出 JSON：\n"
        '{"entities": [{"type": <STIX类型>, "name"/"value": ..., "raw": <原文片段>}]}\n\n'
        f"允许的 SCO 类型：{', '.join(sco)}\n"
        f"允许的 SDO 类型：{', '.join(sdo)}\n"
        "要求：\n"
        "1) 只抽文本中明确出现的（IP/域名/漏洞/账号/组织等）；\n"
        "2) IP/域名/MAC/URL 用 value 键，其他用 name 键；\n"
        "3) 每个实体附 raw 原文片段；没有实体就输出 {\"entities\": []}；\n"
        "4) 只输出 JSON，不要解释。\n\n"
        f"文本：\n{text[:6000]}"
    )


def parse_extraction(raw: str, allowed: set[str]) -> Dict[str, Any]:
    """容错解析 LLM 输出；类型不在白名单 / 结构坏 → 诚实标注。

    纯函数（便于单测，不调 LLM）。
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # 尝试截取首个 {...} 片段
        extracted = _loose_json(raw)
        if extracted is None:
            return {
                "extracted": False,
                "entities": [],
                "error": "LLM 输出不是合法 JSON",
                "raw_preview": (raw or "")[:200],
            }
        data = extracted

    entities = data.get("entities", []) if isinstance(data, dict) else []
    valid: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    for e in entities:
        if not isinstance(e, dict):
            continue
        etype = e.get("type")
        if etype not in allowed:
            dropped.append({"entity": e, "reason": "type_not_allowed"})
            continue
        # 归一：必须有 name 或 value
        if not (e.get("name") or e.get("value")):
            dropped.append({"entity": e, "reason": "missing_name_or_value"})
            continue
        valid.append(e)

    return {
        "extracted": True,
        "entities": valid,
        "dropped": dropped,
        "entity_count": len(valid),
    }


def _loose_json(raw: str) -> Optional[dict]:
    if not raw:
        return None
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


class OntologyExtractor:
    """本体驱动的非结构化文本抽取器。"""

    def __init__(self, db: Session):
        self.db = db

    def extract(self, text: str) -> Dict[str, Any]:
        text = (text or "").strip()
        if len(text) < 3:
            raise ValueError("待抽取文本不能为空")

        sco, sdo = _target_types()
        allowed = set(sco) | set(sdo)

        from app.services.ai_client import ai_chat
        try:
            raw = ai_chat(
                build_extraction_prompt(text),
                system=SYSTEM_PROMPT,
                scene="ontology_extraction",
                temperature=0.0,
                json_mode=True,
                db=self.db,
            )
        except Exception as e:
            logger.warning("抽取 LLM 调用失败: %s", e)
            return {
                "extracted": False,
                "entities": [],
                "error": f"LLM 不可用：{e}",
                "red_line": "抽取结果需人工确认，不自动入库",
            }

        result = parse_extraction(raw, allowed)
        result["confidence"] = self._confidence(result)
        result["red_line"] = "抽取结果需人工确认，不自动入库；置信度为启发式"
        return result

    @staticmethod
    def _confidence(result: Dict[str, Any]) -> Optional[float]:
        if not result.get("extracted"):
            return None
        n = result["entity_count"]
        dropped = len(result.get("dropped", []))
        # 实体越多 + 丢弃越少 → 启发式置信度
        base = min(0.9, 0.6 + 0.05 * n)
        if dropped:
            base -= 0.1 * dropped
        return round(max(0.3, base), 2)
