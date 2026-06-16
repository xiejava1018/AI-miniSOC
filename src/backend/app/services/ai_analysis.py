"""
智谱 AI 分析服务 (支持 Pi Agent 集成)
"""

from zhipuai import ZhipuAI
from app.core.config import settings
from app.models import AIAnalysis
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
        self.client = ZhipuAI(api_key=settings.GLM_API_KEY)
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
        """根据规则级别返回风险描述"""
        if rule_level is None:
            return "未知风险"
        if rule_level >= 12:
            return "高风险 (严重)"
        elif rule_level >= 7:
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
            level = int(match.group(1))
            if level >= 12:
                return "高风险 (严重)"
            elif level >= 7:
                return "中风险"
            else:
                return "低风险"
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
