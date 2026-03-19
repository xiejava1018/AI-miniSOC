<template>
  <div class="dashboard">
    <!-- Stats Grid -->
    <div class="stats-grid">
      <div
        v-for="(stat, index) in stats"
        :key="stat.label"
        class="stat-card"
        :class="`stat-${stat.variant}`"
        :style="{ animationDelay: `${index * 100}ms` }"
      >
        <div class="stat-background">
          <div class="stat-glow"></div>
          <div class="stat-grid"></div>
        </div>

        <div class="stat-header">
          <div class="stat-icon">
            <component :is="stat.icon" />
          </div>
          <span class="stat-label">{{ stat.label }}</span>
        </div>

        <div class="stat-value-container">
          <div class="stat-value">{{ stat.value }}</div>
          <div v-if="stat.change" class="stat-change" :class="stat.changeClass">
            <svg viewBox="0 0 24 24" fill="none">
              <path
                d="M18 15L12 9L6 15"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            <span>{{ stat.change }}</span>
          </div>
        </div>

        <div class="stat-footer">
          <div class="stat-progress">
            <div class="stat-progress-bar" :style="{ width: stat.progress + '%' }"></div>
          </div>
          <span class="stat-meta">{{ stat.meta }}</span>
        </div>
      </div>
    </div>

    <!-- Content Grid -->
    <div class="content-grid">
      <!-- Recent Incidents -->
      <div class="panel panel-incidents">
        <div class="panel-header">
          <div class="panel-title">
            <svg viewBox="0 0 24 24" fill="none">
              <path
                d="M12 8V12L15 15"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2"/>
            </svg>
            <span>最近事件</span>
          </div>
          <router-link to="/incidents" class="panel-action">查看全部</router-link>
        </div>

        <div class="panel-content">
          <div v-if="recentIncidents.length === 0" class="empty-state">
            <svg viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
              <path d="M12 8V12L16 14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
            <p>暂无事件</p>
          </div>

          <div v-else class="incident-list">
            <div
              v-for="incident in recentIncidents"
              :key="incident.id"
              class="incident-item"
            >
              <div class="incident-icon" :class="`severity-${incident.severity}`">
                <svg viewBox="0 0 24 24" fill="none">
                  <path
                    d="M12 9V11M12 15H12.01M5 19C5 15.134 8.13401 12 12 12C15.866 12 19 15.134 19 19M19 19C19 19 19 19 19 19C19 19 19 19 19 19H5C5 19 5 19 5 19C5 19 5 19 5 19ZM12 3C8.68629 3 6 5.68629 6 9C6 12.3137 8.68629 15 12 15C15.3137 15 18 12.3137 18 9C18 5.68629 15.3137 3 12 3Z"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </div>
              <div class="incident-info">
                <div class="incident-title">{{ incident.title }}</div>
                <div class="incident-meta">
                  <span class="incident-time">{{ incident.created_at }}</span>
                  <span class="incident-status">{{ incident.status }}</span>
                </div>
              </div>
              <div class="incident-arrow">
                <svg viewBox="0 0 24 24" fill="none">
                  <path d="M9 18L15 12L9 6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- High Priority Alerts -->
      <div class="panel panel-alerts">
        <div class="panel-header">
          <div class="panel-title">
            <svg viewBox="0 0 24 24" fill="none">
              <path
                d="M12 9V11M12 15H12.01M5.63605 5.63604C2.12132 9.15076 2.12132 14.8492 5.63605 18.3639C9.15076 21.8787 14.8492 21.8787 18.3639 18.3639C21.8787 14.8492 21.8787 9.15076 18.3639 5.63604C14.8492 2.12132 9.15076 2.12132 5.63605 5.63604Z"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            <span>高危告警</span>
          </div>
          <router-link to="/alerts" class="panel-action">查看全部</router-link>
        </div>

        <div class="panel-content">
          <div v-if="highAlerts.length === 0" class="empty-state">
            <svg viewBox="0 0 24 24" fill="none">
              <path
                d="M9 12L11 14L15 10M21 12C21 16.9706 16.9706 21 12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3C16.9706 3 21 7.02944 21 12Z"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            <p>暂无告警</p>
          </div>

          <div v-else class="alert-list">
            <div
              v-for="alert in highAlerts"
              :key="alert.id"
              class="alert-item"
              :class="`alert-${alert.level}`"
            >
              <div class="alert-indicator"></div>
              <div class="alert-content">
                <div class="alert-title">{{ alert.title }}</div>
                <div class="alert-source">{{ alert.source }}</div>
              </div>
              <div class="alert-time">{{ alert.time }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- AI Analysis Summary -->
      <div class="panel panel-ai">
        <div class="panel-header">
          <div class="panel-title">
            <svg viewBox="0 0 24 24" fill="none">
              <path
                d="M9.87868 3.51472C11.0503 2.34315 12.9497 2.34315 14.1213 3.51472L20.4853 9.87868C21.6569 11.0503 21.6569 12.9497 20.4853 14.1213L14.1213 20.4853C12.9497 21.6569 11.0503 21.6569 9.87868 20.4853L3.51472 14.1213C2.34315 12.9497 2.34315 11.0503 3.51472 9.87868L9.87868 3.51472Z"
                stroke="currentColor"
                stroke-width="2"
              />
              <path d="M12 8V12L14 14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
            <span>AI分析摘要</span>
          </div>
          <span class="ai-badge">AI Powered</span>
        </div>

        <div class="panel-content">
          <div class="ai-summary">
            <div class="ai-metric">
              <div class="ai-metric-label">今日分析</div>
              <div class="ai-metric-value">127</div>
              <div class="ai-metric-unit">条告警</div>
            </div>
            <div class="ai-metric">
              <div class="ai-metric-label">威胁识别</div>
              <div class="ai-metric-value critical">23</div>
              <div class="ai-metric-unit">个</div>
            </div>
            <div class="ai-metric">
              <div class="ai-metric-label">准确率</div>
              <div class="ai-metric-value success">94.2%</div>
              <div class="ai-metric-unit"></div>
            </div>
          </div>

          <div class="ai-insight">
            <div class="ai-insight-header">
              <svg viewBox="0 0 24 24" fill="none">
                <path
                  d="M13 16H12V12H11M12 8H12.01M21 12C21 16.9706 16.9706 21 12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3C16.9706 3 21 7.02944 21 12Z"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
              <span>AI 洞察</span>
            </div>
            <p class="ai-insight-text">
              检测到3个IP地址存在异常登录行为，建议立即检查192.168.0.100和192.168.0.105的访问日志。
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Monitor, Warning, Bell, DataAnalysis } from '@element-plus/icons-vue'

interface Stat {
  label: string
  value: string | number
  variant: string
  icon: any
  change?: string
  changeClass?: string
  progress: number
  meta: string
}

const stats = ref<Stat[]>([
  {
    label: '总资产',
    value: 37,
    variant: 'cyan',
    icon: Monitor,
    change: '+2',
    changeClass: 'positive',
    progress: 85,
    meta: '较昨日'
  },
  {
    label: '待处理事件',
    value: 3,
    variant: 'critical',
    icon: Warning,
    change: '-1',
    changeClass: 'positive',
    progress: 60,
    meta: '较昨日'
  },
  {
    label: '高危告警',
    value: 5,
    variant: 'warning',
    icon: Bell,
    change: '+3',
    changeClass: 'negative',
    progress: 75,
    meta: '过去24小时'
  },
  {
    label: '在线资产',
    value: 32,
    variant: 'success',
    icon: DataAnalysis,
    progress: 86,
    meta: '86% 在线率'
  },
])

const recentIncidents = ref<any[]>([])
const highAlerts = ref<any[]>([
  {
    id: 1,
    title: 'SSH暴力破解攻击',
    source: '192.168.0.100',
    level: 'critical',
    time: '2分钟前'
  },
  {
    id: 2,
    title: '异常端口扫描',
    source: '192.168.0.105',
    level: 'high',
    time: '15分钟前'
  },
  {
    id: 3,
    title: '多次登录失败',
    source: '192.168.0.42',
    level: 'warning',
    time: '1小时前'
  },
])

onMounted(async () => {
  // TODO: 从 API 获取真实数据
  recentIncidents.value = [
    {
      id: 1,
      title: 'SSH暴力破解攻击',
      severity: 'critical',
      status: '处理中',
      created_at: '2小时前'
    },
    {
      id: 2,
      title: '异常文件修改',
      severity: 'high',
      status: '待处理',
      created_at: '5小时前'
    },
    {
      id: 3,
      title: '可疑网络连接',
      severity: 'medium',
      status: '已解决',
      created_at: '1天前'
    },
  ]
})
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
  max-width: 100%;
}

/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 20px;
}

.stat-card {
  position: relative;
  padding: 24px;
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--glass-border);
  border-radius: 16px;
  overflow: hidden;
  animation: slideIn 0.5s ease forwards;
  opacity: 0;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.stat-background {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}

.stat-glow {
  position: absolute;
  top: -50%;
  right: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(circle, var(--accent-cyan-dim) 0%, transparent 70%);
  opacity: 0.5;
}

.stat-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
  background-size: 20px 20px;
}

.stat-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  position: relative;
}

.stat-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

.stat-card.stat-cyan .stat-icon {
  background: linear-gradient(135deg, rgba(0, 212, 255, 0.2), rgba(0, 212, 255, 0.05));
  color: var(--accent-cyan);
}

.stat-card.stat-critical .stat-icon {
  background: linear-gradient(135deg, rgba(255, 42, 109, 0.2), rgba(255, 42, 109, 0.05));
  color: var(--status-critical);
}

.stat-card.stat-warning .stat-icon {
  background: linear-gradient(135deg, rgba(255, 193, 7, 0.2), rgba(255, 193, 7, 0.05));
  color: var(--status-warning);
}

.stat-card.stat-success .stat-icon {
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(16, 185, 129, 0.05));
  color: var(--status-success);
}

.stat-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stat-value-container {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 16px;
  position: relative;
}

.stat-value {
  font-size: 42px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1;
  font-family: 'JetBrains Mono', monospace;
}

.stat-change {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 6px;
}

.stat-change.positive {
  color: var(--status-success);
  background: rgba(16, 185, 129, 0.1);
}

.stat-change.negative {
  color: var(--status-critical);
  background: rgba(255, 42, 109, 0.1);
}

.stat-change svg {
  width: 14px;
  height: 14px;
}

.stat-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: relative;
}

.stat-progress {
  flex: 1;
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: 2px;
  overflow: hidden;
  margin-right: 12px;
}

.stat-progress-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--accent-cyan), var(--accent-blue));
  border-radius: 2px;
  transition: width 1s ease;
}

.stat-card.stat-critical .stat-progress-bar {
  background: linear-gradient(90deg, var(--status-critical), var(--status-high));
}

.stat-card.stat-warning .stat-progress-bar {
  background: linear-gradient(90deg, var(--status-warning), var(--status-high));
}

.stat-card.stat-success .stat-progress-bar {
  background: linear-gradient(90deg, var(--status-success), var(--status-info));
}

.stat-meta {
  font-size: 12px;
  color: var(--text-muted);
}

/* Content Grid */
.content-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 20px;
}

.panel {
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--glass-border);
  border-radius: 16px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.panel-incidents,
.panel-alerts {
  grid-column: span 1;
}

.panel-ai {
  grid-column: span 2;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-color);
  background: rgba(0, 212, 255, 0.03);
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--accent-cyan);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.panel-title svg {
  width: 18px;
  height: 18px;
}

.panel-action {
  font-size: 13px;
  color: var(--text-secondary);
  text-decoration: none;
  transition: color var(--transition-fast);
}

.panel-action:hover {
  color: var(--accent-cyan);
}

.ai-badge {
  padding: 4px 12px;
  background: linear-gradient(135deg, var(--accent-purple), var(--accent-blue));
  color: white;
  font-size: 11px;
  font-weight: 600;
  border-radius: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.panel-content {
  padding: 20px 24px;
  flex: 1;
}

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: var(--text-muted);
}

.empty-state svg {
  width: 48px;
  height: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-state p {
  font-size: 14px;
}

/* Incident List */
.incident-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.incident-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: var(--bg-tertiary);
  border-radius: 10px;
  border: 1px solid var(--border-color);
  cursor: pointer;
  transition: all var(--transition-base);
}

.incident-item:hover {
  border-color: var(--accent-cyan);
  background: rgba(0, 212, 255, 0.05);
  transform: translateX(4px);
}

.incident-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.incident-icon.severity-critical {
  background: rgba(255, 42, 109, 0.2);
  color: var(--status-critical);
}

.incident-icon.severity-high {
  background: rgba(255, 107, 53, 0.2);
  color: var(--status-high);
}

.incident-icon.severity-medium {
  background: rgba(255, 193, 7, 0.2);
  color: var(--status-warning);
}

.incident-icon svg {
  width: 18px;
  height: 18px;
}

.incident-info {
  flex: 1;
}

.incident-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.incident-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
}

.incident-time {
  color: var(--text-muted);
}

.incident-status {
  padding: 2px 8px;
  background: var(--bg-secondary);
  border-radius: 4px;
  color: var(--text-secondary);
}

.incident-arrow {
  color: var(--text-muted);
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.incident-item:hover .incident-arrow {
  opacity: 1;
}

.incident-arrow svg {
  width: 18px;
  height: 18px;
}

/* Alert List */
.alert-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.alert-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: var(--bg-tertiary);
  border-radius: 10px;
  border-left: 3px solid;
  position: relative;
  overflow: hidden;
}

.alert-item::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at top right, rgba(255, 255, 255, 0.05), transparent 60%);
  opacity: 0;
  transition: opacity var(--transition-base);
}

.alert-item:hover::before {
  opacity: 1;
}

.alert-item.alert-critical {
  border-left-color: var(--status-critical);
}

.alert-item.alert-high {
  border-left-color: var(--status-high);
}

.alert-item.alert-warning {
  border-left-color: var(--status-warning);
}

.alert-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.alert-item.alert-critical .alert-indicator {
  background: var(--status-critical);
  box-shadow: 0 0 8px var(--status-critical);
  animation: pulse 2s ease-in-out infinite;
}

.alert-item.alert-high .alert-indicator {
  background: var(--status-high);
  box-shadow: 0 0 6px var(--status-high);
}

.alert-item.alert-warning .alert-indicator {
  background: var(--status-warning);
}

.alert-content {
  flex: 1;
}

.alert-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.alert-source {
  font-size: 12px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
}

.alert-time {
  font-size: 12px;
  color: var(--text-muted);
  flex-shrink: 0;
}

/* AI Summary */
.ai-summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  margin-bottom: 20px;
}

.ai-metric {
  text-align: center;
  padding: 20px;
  background: var(--bg-tertiary);
  border-radius: 12px;
  border: 1px solid var(--border-color);
}

.ai-metric-label {
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.ai-metric-value {
  font-size: 32px;
  font-weight: 700;
  color: var(--text-primary);
  font-family: 'JetBrains Mono', monospace;
  margin-bottom: 4px;
}

.ai-metric-value.critical {
  color: var(--status-critical);
}

.ai-metric-value.success {
  color: var(--status-success);
}

.ai-metric-unit {
  font-size: 12px;
  color: var(--text-muted);
}

.ai-insight {
  padding: 20px;
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.1), rgba(59, 130, 246, 0.1));
  border-radius: 12px;
  border: 1px solid rgba(139, 92, 246, 0.2);
}

.ai-insight-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--accent-purple);
}

.ai-insight-header svg {
  width: 16px;
  height: 16px;
}

.ai-insight-text {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
}
</style>
