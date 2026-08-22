"""
智谱 AI 分析服务 (支持 Pi Agent 集成)
"""

from zhipuai import ZhipuAI
from app.core.config import settings
from app.core.alert_levels import LEVEL_CRITICAL, LEVEL_HIGH, LEVEL_MEDIUM
from app.models import AIAnalysis, AlertGroupAnalysis
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
import logging
from datetime import datetime, timedelta
import asyncio
import json
import uuid

logger = logging.getLogger(__name__)


class AIAnalysisService:
    """AI 分析服务 (支持 Agent 降级)"""

    def __init__(self, db: Session):
        self.db = db
        # 容错：智谱客户端初始化失败（如未配密钥）不应阻断整个服务，
        # 后续簇研判会自动降级到启发式兜底。
        try:
            self.client = ZhipuAI(api_key=settings.GLM_API_KEY)
        except Exception as e:
            logger.warning("ZhipuAI 初始化失败，将仅走启发式兜底: %s", e)
            self.client = None
        # POC: 懒加载 AgentProcessManager
        self._agent_manager = None

    def _get_agent_manager(self):
        """获取全局 AgentProcessManager 单例"""
        if self._agent_manager is None:
            from app.api.ai_agent import get_agent_manager
            self._agent_manager = get_agent_manager()
        return self._agent_manager

    async def analyze_alert(
        self,
        alert_id: str,
        rule_id: Optional[int] = None,
        rule_level: Optional[int] = None,
        rule_description: Optional[str] = None,
        full_log: Optional[str] = None,
        agent_name: Optional[str] = None,
        agent_ip: Optional[str] = None,
        force_refresh: bool = False,
        trace_id: Optional[str] = None
    ) -> AIAnalysis:
        """分析告警: 先查缓存 -> 尝试 Agent -> 降级 ZhipuAI"""

        # 生成 trace_id
        if not trace_id:
            trace_id = str(uuid.uuid4())

        # 生成告警指纹用于缓存
        alert_fingerprint = self._generate_fingerprint(
            rule_id, rule_level, rule_description
        )

        # 检查缓存（除非强制刷新）
        if not force_refresh:
            cached = self._get_cached_analysis(alert_id, alert_fingerprint)
            if cached:
                logger.info(f"使用缓存的AI分析: {alert_id}")
                return cached

        # 构建分析提示词
        prompt = self._build_analysis_prompt(
            rule_id, rule_level, rule_description,
            full_log, agent_name, agent_ip
        )

        # 优先尝试 Agent 分析
        try:
            result = await self._analyze_with_agent(
                alert_id=alert_id,
                rule_id=rule_id,
                rule_level=rule_level,
                rule_description=rule_description,
                full_log=full_log,
                agent_name=agent_name,
                agent_ip=agent_ip,
                trace_id=trace_id
            )
        except Exception as e:
            logger.warning(f"Agent 分析失败，降级到 ZhipuAI: {e}")
            # 降级到原始 ZhipuAI
            result = await self._analyze_with_zhipuai(prompt)

        # 保存到数据库
        analysis = self._save_analysis(
            alert_id=alert_id,
            alert_fingerprint=alert_fingerprint,
            explanation=result.get("explanation"),
            risk_assessment=result.get("risk_assessment"),
            recommendations=result.get("recommendations")
        )

        return analysis

    async def _analyze_with_agent(
        self,
        alert_id: str,
        rule_id: Optional[int],
        rule_level: Optional[int],
        rule_description: Optional[str],
        full_log: Optional[str],
        agent_name: Optional[str],
        agent_ip: Optional[str],
        trace_id: str,
    ) -> dict:
        """用 Pi Agent 分析告警"""
        import time
        start_time = time.time()

        manager = self._get_agent_manager()
        session_id = f"alert-analysis-{alert_id}"

        # 构建 prompt
        prompt = self._build_analysis_prompt(
            rule_id, rule_level, rule_description,
            full_log, agent_name, agent_ip
        )

        # 调用 Agent
        try:
            result = await manager.call(session_id, "agent.prompt", {
                "sessionId": session_id,
                "userMessage": prompt,
                "model": settings.GLM_MODEL or "glm-4-flash",
                "trace_id": trace_id,
            })

            # 记录 Prometheus 埋点
            duration = time.time() - start_time
            logger.info(f"Agent 分析完成: alert_id={alert_id}, duration={duration:.2f}s")

            # 解析 Agent 返回
            # POC 阶段: 从 result 中提取文本再解析
            text = result.get("text", "") if isinstance(result, dict) else str(result)

            return self._parse_agent_response(text, alert_id)

        except asyncio.TimeoutError:
            logger.warning(f"Agent 调用超时: alert_id={alert_id}")
            raise
        except Exception as e:
            logger.error(f"Agent 调用异常: alert_id={alert_id}, error={e}")
            raise

    def _parse_agent_response(self, text: str, alert_id: str) -> dict:
        """从 Agent 响应中解析分析结果"""
        # POC: 尝试从文本中提取 JSON
        try:
            # 尝试提取 JSON 部分
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            data = json.loads(text)
            return {
                "explanation": data.get("explanation", ""),
                "risk_assessment": data.get("risk_assessment", ""),
                "recommendations": data.get("recommendations", "")
            }
        except json.JSONDecodeError:
            # JSON 解析失败，尝试从文本中提取关键信息
            logger.warning(f"Agent 响应 JSON 解析失败，使用备用解析: alert_id={alert_id}")
            return {
                "explanation": text[:500] if text else "Agent 分析结果解析失败",
                "risk_assessment": f"规则级别 {self._get_rule_level(rule_id)}",
                "recommendations": "请查看完整日志进行详细分析"
            }

    def _get_rule_level(self, rule_level: Optional[int]) -> str:
        """根据规则级别返回风险描述。

        阈值用全项目权威定义（app/core/alert_levels.py，13/10/7/4）——
        此前这里是 12/7，导致 level 10-11 的告警在「AI 分析」页显示
        "中风险"而在「安全报告」里计为 high（生产 7 天实测 4,921 条受影响）。
        """
        if rule_level is None:
            return "未知风险"
        if rule_level >= LEVEL_CRITICAL:
            return "高风险 (严重)"
        elif rule_level >= LEVEL_HIGH:
            return "高风险"
        elif rule_level >= LEVEL_MEDIUM:
            return "中风险"
        else:
            return "低风险"

    async def _analyze_with_zhipuai(self, prompt: str) -> dict:
        """降级: 直接调 ZhipuAI SDK"""
        return self._call_ai_analysis(prompt)

    def _generate_fingerprint(
        self,
        rule_id: Optional[int],
        rule_level: Optional[int],
        rule_description: Optional[str]
    ) -> str:
        """生成告警指纹用于缓存"""
        import hashlib
        content = f"{rule_id}-{rule_level}-{rule_description}"
        return hashlib.md5(content.encode()).hexdigest()

    def _get_cached_analysis(
        self,
        alert_id: str,
        alert_fingerprint: str
    ) -> Optional[AIAnalysis]:
        """获取缓存的AI分析"""
        from datetime import timezone

        # 首先查找完全匹配的 alert_id
        analysis = self.db.query(AIAnalysis).filter(
            AIAnalysis.alert_id == alert_id
        ).first()

        if analysis:
            # 检查是否过期
            if analysis.expires_at:
                # 如果expires_at是naive，添加时区
                if analysis.expires_at.tzinfo is None:
                    expires_at = analysis.expires_at.replace(tzinfo=timezone.utc)
                else:
                    expires_at = analysis.expires_at

                now = datetime.now(timezone.utc)
                if expires_at > now:
                    return analysis

        # 如果没有完全匹配，查找指纹匹配且未过期的
        if not analysis and alert_fingerprint:
            analysis = self.db.query(AIAnalysis).filter(
                AIAnalysis.alert_fingerprint == alert_fingerprint
            ).first()

            if analysis and analysis.expires_at:
                if analysis.expires_at.tzinfo is None:
                    expires_at = analysis.expires_at.replace(tzinfo=timezone.utc)
                else:
                    expires_at = analysis.expires_at

                now = datetime.now(timezone.utc)
                if expires_at > now:
                    return analysis

        return analysis

    def _build_analysis_prompt(
        self,
        rule_id: Optional[int],
        rule_level: Optional[int],
        rule_description: Optional[str],
        full_log: Optional[str],
        agent_name: Optional[str],
        agent_ip: Optional[str]
    ) -> str:
        """构建AI分析提示词"""

        prompt = f"""你是一个网络安全专家，请分析以下安全告警。

## 告警信息
- 规则ID: {rule_id or '未知'}
- 规则级别: {rule_level or '未知'} (0-20级别，数字越大越严重)
- 规则描述: {rule_description or '未知'}
- 影响主机: {agent_name or '未知'} ({agent_ip or '未知'})
- 完整日志: {full_log or '无'}

请提供以下分析（请用中文回复）：

1. **发生了什么**：用简洁易懂的语言解释这个告警的含义
2. **风险等级**：评估风险等级（低/中/高/严重）并说明理由
3. **影响评估**：可能的影响和后果
4. **处置建议**：给出具体的处置步骤（3-5条）

请以JSON格式返回：
{{
  "explanation": "发生了什么的详细说明",
  "risk_assessment": "风险评估（等级+理由）",
  "recommendations": "处置建议1\\n处置建议2\\n处置建议3"
}}
"""

        return prompt

    def _call_ai_analysis(self, prompt: str) -> Dict[str, str]:
        """调用智谱AI进行分析"""

        response = self.client.chat.completions.create(
            model=settings.GLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的网络安全分析师，擅长分析安全告警和日志。"
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # 降低随机性，提高一致性
        )

        content = response.choices[0].message.content.strip()

        # 尝试解析JSON响应
        try:
            # 提取JSON部分（如果响应包含其他文本）
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)
            return result

        except json.JSONDecodeError:
            # 如果JSON解析失败，尝试从文本中提取信息
            return {
                "explanation": content[:500],
                "risk_assessment": f"规则级别 {self._get_rule_level_from_prompt(prompt)}",
                "recommendations": "请查看完整日志进行详细分析"
            }

    def _get_rule_level_from_prompt(self, prompt: str) -> str:
        """从提示词中提取规则级别"""
        import re
        match = re.search(r"规则级别[:\s]*(\d+)", prompt)
        if match:
            # 与 _get_rule_level 同一权威阈值（13/10/7/4）
            return self._get_rule_level(int(match.group(1)))
        return "未知风险"

    def _save_analysis(
        self,
        alert_id: str,
        alert_fingerprint: str,
        explanation: str,
        risk_assessment: str,
        recommendations: str
    ) -> AIAnalysis:
        """保存AI分析结果到数据库"""

        # 设置缓存过期时间（7天）
        expires_at = datetime.utcnow() + timedelta(days=7)

        analysis = AIAnalysis(
            alert_id=alert_id,
            alert_fingerprint=alert_fingerprint,
            explanation=explanation,
            risk_assessment=risk_assessment,
            recommendations=recommendations,
            model_name=settings.GLM_MODEL,
            model_version="latest",
            created_at=datetime.utcnow(),
            expires_at=expires_at
        )

        self.db.add(analysis)
        self.db.commit()
        self.db.refresh(analysis)

        return analysis

    # ── 告警簇级研判（Phase 1）──────────────────────────
    #
    # 与单条告警 analyze_alert 不同，这里把"一簇 N 条同类告警"当作整体，
    # 输出结构化 verdict：{priority, is_noise, confidence, rationale,
    # recommended_action, suggest_incident, source, model_name, ...}
    # 落库到独立的 soc_alert_group_analyses（按 fingerprint 唯一缓存 + 7 天 TTL）。
    # 降级链：缓存 -> Pi Agent -> 智谱 -> 启发式兜底（source='heuristic'）。

    async def triage_alert_group(
        self, signature: dict, force_refresh: bool = False
    ) -> dict:
        """对一个告警簇做结构化 AI 研判。

        signature 需含：fingerprint, rule_id, agent_id, rule_description,
        rule_id/agent_id/level_min/level_max/count/first_seen/last_seen/
        distinct_srcips/top_srcips/agent_name/agent_ip/linked_asset/
        sample_full_log/window_hours/linked_asset_id。
        """
        fp = signature.get("fingerprint")
        if not force_refresh:
            cached = self._get_cached_group_analysis(fp)
            if cached:
                logger.info("使用缓存的告警簇研判: %s", fp)
                return cached.to_dict()

        prompt = self._build_group_triage_prompt(signature)
        trace_id = str(uuid.uuid4())
        source = "heuristic"
        try:
            text, source = await self._llm_text_for_group(prompt, trace_id)
            verdict = self._parse_verdict_json(text)
            verdict["source"] = source
        except Exception as e:
            logger.warning("告警簇研判 AI 失败，启发式兜底: %s", e)
            verdict = self._heuristic_verdict(signature)

        # 关联元数据
        verdict["fingerprint"] = fp
        verdict["rule_id"] = signature.get("rule_id")
        verdict["agent_id"] = signature.get("agent_id")
        verdict["rule_description"] = signature.get("rule_description")
        verdict["window_hours"] = signature.get("window_hours")
        verdict["linked_asset_id"] = signature.get("linked_asset_id")
        if not verdict.get("model_name"):
            verdict["model_name"] = (
                settings.GLM_MODEL if verdict["source"] != "heuristic" else "heuristic"
            )

        self._save_group_analysis(verdict)
        return verdict

    async def _llm_text_for_group(self, prompt: str, trace_id: str):
        """优先 Pi Agent，失败降级智谱，返回 (text, source)。"""
        # 1. Pi Agent
        try:
            manager = self._get_agent_manager()
            session_id = f"group-triage-{trace_id}"
            result = await manager.call(
                session_id,
                "agent.prompt",
                {
                    "sessionId": session_id,
                    "userMessage": prompt,
                    "model": settings.GLM_MODEL or "glm-4-flash",
                    "trace_id": trace_id,
                },
            )
            text = result.get("text", "") if isinstance(result, dict) else str(result)
            if text and text.strip():
                return text, "agent"
        except Exception as e:
            logger.warning("Agent 簇研判失败，降级智谱: %s", e)

        # 2. 智谱
        if self.client is None:
            raise RuntimeError("智谱客户端未初始化")
        resp = self.client.chat.completions.create(
            model=settings.GLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个资深网络安全分析师，擅长对一批同类安全告警做整体研判与优先级排序。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        text = resp.choices[0].message.content.strip()
        return text, "zhipu"

    def _build_group_triage_prompt(self, signature: dict) -> str:
        """构建告警簇研判提示词（强调"这是 N 条同类告警的聚合"）。"""
        linked = signature.get("linked_asset") or {}
        criticality = linked.get("criticality") or "未知"
        top_srcips = signature.get("top_srcips") or []
        srcip_hint = ", ".join(str(ip) for ip in top_srcips[:5]) or "无"

        return f"""你是一个网络安全专家。下面是一批**同类安全告警聚合而成的告警簇**（不是单条告警），请综合研判并给出处置优先级。

## 告警簇信息
- 指纹: {signature.get('fingerprint')}
- 规则: {signature.get('rule_id')} {signature.get('rule_description') or ''}
- 受影响资产: {signature.get('agent_name') or signature.get('agent_id')} (IP: {signature.get('agent_ip') or '未知'})
- 告警总量: {signature.get('count')} 条
- 等级跨度: L{signature.get('level_min')} ~ L{signature.get('level_max')}
- 首次/最近出现: {signature.get('first_seen')} ~ {signature.get('last_seen')}
- 不同攻击源 IP 数: {signature.get('distinct_srcips')}（Top: {srcip_hint}）
- 关联资产重要度: {criticality}
- 样本日志: {(signature.get('sample_full_log') or '无')[:800]}

## 研判要求
请综合 **量级、等级跨度、受影响资产重要度、攻击源多样性、时间持续性** 给出结论，并以**严格 JSON** 返回（不要任何多余文本/解释）：
{{
  "priority": "P0|P1|P2|P3",
  "is_noise": true|false,
  "confidence": 0.0~1.0,
  "rationale": "为什么是这个优先级（2-3 句）",
  "recommended_action": "处置步骤1\\n处置步骤2\\n处置步骤3",
  "suggest_incident": true|false
}}
注：P0=需立即处置的重大事件；P1=高优先级需尽快处理；P2=中优先级可排期；P3=低优先级/观察。is_noise=true 表示可判定为良性噪声，可移出必处理清单。
"""

    def _parse_verdict_json(self, text: str) -> dict:
        """从 LLM 返回中解析 verdict JSON；失败抛异常交由调用方启发式兜底。"""
        raw = text or ""
        try:
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            data = json.loads(raw)
        except Exception:
            logger.warning("告警簇研判 JSON 解析失败，启发式兜底")
            raise ValueError("无法解析为 JSON")

        priority = str(data.get("priority", "P3")).upper()
        if priority not in ("P0", "P1", "P2", "P3"):
            priority = "P3"
        try:
            confidence = float(data.get("confidence", 0.6) or 0.6)
        except (TypeError, ValueError):
            confidence = 0.6
        return {
            "priority": priority,
            "is_noise": bool(data.get("is_noise", False)),
            "confidence": confidence,
            "rationale": data.get("rationale", ""),
            "recommended_action": data.get("recommended_action", ""),
            "suggest_incident": bool(data.get("suggest_incident", False)),
            "source": "unknown",  # 由调用方覆盖
            "model_name": None,
        }

    def _heuristic_verdict(self, signature: dict, reason: str = "模型不可用（启发式兜底）") -> dict:
        """无 AI 时的启发式 verdict：按最高等级 + 量级给 P 级，source='heuristic'。"""
        level_max = signature.get("level_max") or 0
        count = signature.get("count") or 0
        # 阈值同权威定义（13/10/7/4）。此前 12/8：level 10-11 的告警簇在降级
        # 路径下被判 P2 而非 P1，进而拉低 F1.1 风险分。P 级会持久化到
        # soc_alert_group_analyses.priority 并喂给 _score_alerts。
        if level_max >= LEVEL_CRITICAL:
            priority = "P1"
        elif level_max >= LEVEL_HIGH:
            priority = "P2"
        else:
            priority = "P3"
        return {
            "priority": priority,
            "is_noise": False,
            "confidence": 0.4,
            "rationale": f"{reason}：按最高等级 L{level_max}、告警量 {count} 给 {priority}。",
            "recommended_action": "建议人工复核该簇日志，确认是否需要处置或加白。",
            "suggest_incident": priority == "P1",
            "source": "heuristic",
            "model_name": "heuristic",
        }

    def _get_cached_group_analysis(self, fingerprint: str) -> Optional[AlertGroupAnalysis]:
        """按 fingerprint 取未过期的簇研判缓存。"""
        from datetime import timezone

        obj = (
            self.db.query(AlertGroupAnalysis)
            .filter(AlertGroupAnalysis.fingerprint == fingerprint)
            .first()
        )
        if not obj:
            return None
        if obj.expires_at:
            exp = (
                obj.expires_at.replace(tzinfo=timezone.utc)
                if obj.expires_at.tzinfo is None
                else obj.expires_at
            )
            if exp <= datetime.now(timezone.utc):
                return None
        return obj

    def _save_group_analysis(self, verdict: dict) -> AlertGroupAnalysis:
        """upsert 一条告警簇研判（按 fingerprint 唯一）。"""
        from uuid import UUID as _UUID

        linked = verdict.get("linked_asset_id")
        if linked and not isinstance(linked, _UUID):
            try:
                linked = _UUID(str(linked))
            except Exception:
                linked = None

        obj = AlertGroupAnalysis(
            fingerprint=verdict.get("fingerprint"),
            rule_id=str(verdict.get("rule_id")) if verdict.get("rule_id") is not None else None,
            agent_id=verdict.get("agent_id"),
            rule_description=verdict.get("rule_description"),
            priority=verdict.get("priority", "P3"),
            is_noise=bool(verdict.get("is_noise", False)),
            confidence=float(verdict.get("confidence", 0.0) or 0.0),
            rationale=verdict.get("rationale"),
            recommended_action=verdict.get("recommended_action"),
            suggest_incident=bool(verdict.get("suggest_incident", False)),
            source=verdict.get("source", "heuristic"),
            model_name=verdict.get("model_name"),
            window_hours=verdict.get("window_hours"),
            linked_asset_id=linked,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=7),
        )

        existing = (
            self.db.query(AlertGroupAnalysis)
            .filter(AlertGroupAnalysis.fingerprint == obj.fingerprint)
            .first()
        )
        if existing:
            for attr in (
                "rule_id", "agent_id", "rule_description", "priority", "is_noise",
                "confidence", "rationale", "recommended_action", "suggest_incident",
                "source", "model_name", "window_hours", "linked_asset_id",
                "created_at", "expires_at",
            ):
                setattr(existing, attr, getattr(obj, attr))
            self.db.commit()
            self.db.refresh(existing)
            return existing

        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    async def analyze_log(self, log_content: str) -> Dict[str, str]:
        """自然语言解释日志内容"""

        prompt = f"""请用简洁易懂的中文解释以下日志内容：

{log_content}

请说明：
1. 这条日志记录了什么事件
2. 关键信息是什么
3. 是否需要关注

请用2-3句话概括。"""

        try:
            response = self.client.chat.completions.create(
                model=settings.GLM_MODEL,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            content = response.choices[0].message.content.strip()
            return {"explanation": content}

        except Exception as e:
            logger.error(f"日志解释失败: {e}")
            return {"explanation": "无法解释该日志内容"}
