<template>
  <div class="asset-detail-page art-full-height">
    <!-- 顶部返回栏 -->
    <div class="detail-header">
      <ElButton @click="goBack" :icon="ArrowLeft" text>返回列表</ElButton>
    </div>

    <!-- 资产基本信息卡片 -->
    <ElCard shadow="never" class="info-card" v-loading="detailLoading">
      <template #header>
        <div class="card-header">
          <span class="title">{{ assetDetail.name || assetDetail.asset_ip || '资产详情' }}</span>
          <div class="header-tags">
            <ElTag v-if="assetDetail.asset_status" :type="statusTagType" effect="dark" size="small">
              {{ statusLabelMap[assetDetail.asset_status] || assetDetail.asset_status || '--' }}
            </ElTag>
            <ElTag v-if="assetDetail.criticality" :type="criticalityTagType" effect="plain" size="small">
              {{ criticalityLabelMap[assetDetail.criticality] || assetDetail.criticality || '--' }}
            </ElTag>
            <ElTag v-if="assetDetail.data_source" type="info" effect="plain" size="small">
              {{ dataSourceLabelMap[assetDetail.data_source] || assetDetail.data_source || '--' }}
            </ElTag>
          </div>
        </div>
      </template>

      <ElDescriptions :column="3" border>
        <ElDescriptionsItem label="IP地址">{{ assetDetail.asset_ip || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="资产名称">{{ assetDetail.name || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="资产类型">{{ assetTypeLabelMap[assetDetail.asset_type] || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="网络段">{{ assetDetail.network_segment || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="网络区域">{{ networkZoneLabelMap[assetDetail.network_zone] || assetDetail.network_zone || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="MAC地址">{{ assetDetail.mac_address || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="负责人">{{ assetDetail.owner || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="负责人电话">{{ assetDetail.owner_contact || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="数据分类">
          <ElTag v-if="assetDetail.data_classification" type="warning" effect="plain" size="small">
            {{ dataClassLabelMap[assetDetail.data_classification] || assetDetail.data_classification }}
          </ElTag>
          <span v-else>--</span>
        </ElDescriptionsItem>
        <ElDescriptionsItem label="业务单元">{{ assetDetail.business_unit || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="操作系统">
          {{ assetDetail.os_name ? `${assetDetail.os_name} ${assetDetail.os_version || ''}`.trim() : '--' }}
        </ElDescriptionsItem>
        <ElDescriptionsItem label="Wazuh Agent">{{ assetDetail.wazuh_agent_id || '--' }}</ElDescriptionsItem>
        <!-- P3/F3.2：生命周期 -->
        <ElDescriptionsItem label="采购日期">{{ assetDetail.purchase_date || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="保修到期">
          <span v-if="assetDetail.warranty_end" :class="{ 'text-danger': warrantyDays !== null && warrantyDays < 0 }">
            {{ assetDetail.warranty_end }}
            <span class="lc-days">({{ warrantyDaysText }})</span>
          </span>
          <span v-else>--</span>
        </ElDescriptionsItem>
        <ElDescriptionsItem label="预期 EOL">
          <template v-if="assetDetail.expected_eol">
            <ElTag :type="eolTagType" size="small" effect="light">{{ assetDetail.expected_eol }}</ElTag>
            <span class="lc-days">{{ eolDaysText }}</span>
            <ElTag
              size="small"
              effect="plain"
              :type="assetDetail.expected_eol_source === 'manual' ? 'info' : ''"
              class="lc-source-tag"
            >
              {{ assetDetail.expected_eol_source === 'manual' ? '人工指定' : '参考表匹配' }}
            </ElTag>
          </template>
          <span v-else class="lc-none">未匹配（无对应预置条目）</span>
          <ElButton size="small" text type="primary" class="lc-edit-btn" @click="openEolDialog">设置</ElButton>
        </ElDescriptionsItem>
        <ElDescriptionsItem label="创建时间">{{ formatTime(assetDetail.created_at) }}</ElDescriptionsItem>
        <ElDescriptionsItem label="更新时间">{{ formatTime(assetDetail.updated_at) }}</ElDescriptionsItem>
        <ElDescriptionsItem label="状态更新">{{ formatTime(assetDetail.status_updated_at) }}</ElDescriptionsItem>
        <ElDescriptionsItem label="描述" :span="3">{{ assetDetail.asset_description || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="标签" :span="3">
          <ElTag
            v-for="tag in tagsData"
            :key="tag.id"
            type="info"
            effect="light"
            class="mr-1 mb-1"
            closable
            @close="handleDeleteTag(tag)"
          >
            {{ tag.tag_key }}: {{ tag.tag_value }}
          </ElTag>
          <ElButton size="small" type="primary" plain @click="showTagDialog('add')">
            <ElIcon><Plus /></ElIcon>添加标签
          </ElButton>
        </ElDescriptionsItem>
      </ElDescriptions>
    </ElCard>

    <!-- 安全摘要卡(详情页 v2 新增) -->
    <ElCard shadow="never" class="summary-card" v-loading="summaryLoading">
      <template #header>
        <div class="card-header">
          <span class="title">安全摘要</span>
          <ElButton size="small" text :icon="Refresh" @click="loadSummary" :loading="summaryLoading">刷新</ElButton>
        </div>
      </template>

      <div class="summary-grid">
        <MetricCard
          label="24h 告警"
          :value="summary.alert_24h"
          type="danger"
          :clickable="summary.alert_24h > 0"
          @click="activeTab = 'alerts'"
          :sub-label="summary.alert_critical_24h > 0 ? `高危 ${summary.alert_critical_24h}` : '无高危'"
        />
        <MetricCard
          label="高危 CVE"
          :value="summary.vuln_critical"
          type="danger"
          :clickable="summary.vuln_critical > 0"
          @click="activeTab = 'vulnerabilities'"
          :sub-label="`未修复 ${summary.vuln_total} 个`"
        />
        <MetricCard
          label="开放端口"
          :value="summary.open_ports"
          :type="summary.high_risk_ports > 0 ? 'warning' : 'info'"
          :clickable="true"
          @click="activeTab = 'ports'"
          :sub-label="summary.high_risk_ports > 0 ? `高危 ${summary.high_risk_ports}` : '无高危'"
        />
        <MetricCard
          label="应用数"
          :value="summary.applications"
          type="info"
          :clickable="false"
          sub-label="Wazuh packages"
        />
        <MetricCard
          :label="summary.sca_pass_rate !== null ? 'SCA 合规率' : 'SCA 不合规'"
          :value="summary.sca_pass_rate !== null ? Math.round(summary.sca_pass_rate * 100) : (summary.sca_failed ?? 0)"
          :type="summary.sca_pass_rate !== null ? scaPassRateType : (summary.sca_failed > 0 ? 'warning' : 'info')"
          :clickable="summary.sca_pass_rate === null && summary.sca_failed > 0"
          @click="activeTab = 'baseline'"
          :suffix="summary.sca_pass_rate !== null ? '%' : ' 项'"
          :sub-label="summary.sca_pass_rate !== null ? '' : '合规率待接入(P5)'"
        />
        <MetricCard
          label="在线状态"
          :value="onlineStatusLabel"
          :type="onlineStatusType"
          :clickable="false"
          :sub-label="summary.last_port_scan ? `端口扫描 ${relativeTime.format(summary.last_port_scan)}` : '尚无扫描'"
        />
      </div>
    </ElCard>

    <!-- P3/F1.1：资产风险卡（评分 + AI 摘要 + 维度明细 + 趋势，PRD §八-C 可解释性） -->
    <ElCard shadow="never" class="risk-card" v-loading="riskLoading">
      <template #header>
        <div class="card-header">
          <span class="title">资产风险</span>
          <div class="card-header-right">
            <span v-if="riskData?.risk_scored_at" class="risk-scored-at">评分于 {{ formatTime(riskData.risk_scored_at) }}</span>
            <ElButton size="small" text :icon="Refresh" @click="handleRefreshRisk" :loading="riskLoading">刷新</ElButton>
          </div>
        </div>
      </template>

      <template v-if="riskData">
        <div v-if="riskData.risk_score === null || riskData.risk_score === undefined" class="risk-na">
          <ElTag type="info" effect="plain">N/A</ElTag>
          <span class="risk-na-text">数据不足（无端口/漏洞/告警证据），暂不评分——避免误导</span>
        </div>
        <template v-else>
          <div class="risk-main">
            <div class="risk-score" :class="riskScoreClass">
              <div class="risk-score-number">{{ riskData.risk_score }}</div>
              <div class="risk-score-label">/ 100</div>
            </div>
            <div class="risk-summary-area">
              <div class="risk-summary-text">{{ riskData.risk_summary || '（暂无 AI 摘要，点击右上「刷新」生成）' }}</div>
              <div class="risk-summary-meta">
                <span v-if="riskData.risk_summary" class="risk-summary-src">{{ riskData.summary_source === 'glm' ? 'GLM 生成' : '规则生成' }}</span>
                <AiFeedback target-type="risk_summary" :target-id="assetId" :visible="!!riskData.risk_summary" />
              </div>
            </div>
          </div>

          <!-- 维度明细（可解释性：为什么是这个分） -->
          <div v-if="riskDimensions.length" class="risk-dimensions">
            <div v-for="d in riskDimensions" :key="d.key" class="risk-dim">
              <div class="risk-dim-head">
                <span class="risk-dim-name">{{ d.label }}</span>
                <span class="risk-dim-score" :class="`is-${d.level}`">{{ d.score }}</span>
                <ElTag v-if="d.dataGap" size="small" type="warning" effect="plain">数据缺失·半权</ElTag>
              </div>
              <ElProgress :percentage="d.score" :stroke-width="8" :color="d.color" :show-text="false" />
              <div class="risk-dim-reasons">{{ d.reasons }}</div>
            </div>
          </div>

          <!-- 趋势 sparkline（90 天） -->
          <div v-if="riskTrendPoints.length >= 2" class="risk-trend">
            <span class="risk-trend-label">近 90 天评分趋势</span>
            <svg class="risk-trend-svg" :viewBox="`0 0 ${trendW} ${trendH}`" preserveAspectRatio="none">
              <polyline :points="trendPolyline" fill="none" stroke="currentColor" stroke-width="2" />
            </svg>
            <span v-if="riskDelta7d !== null" class="risk-trend-delta" :class="riskDelta7d >= 0 ? 'is-up' : 'is-down'">
              7天 {{ riskDelta7d >= 0 ? '+' : '' }}{{ riskDelta7d }}
            </span>
          </div>
        </template>
      </template>
      <ElEmpty v-else-if="!riskLoading" description="尚未评分，可到资产列表页点击“风险评分”" :image-size="60" />
    </ElCard>

    <!-- Tab 区域 -->
    <ElCard shadow="never" class="tab-card">
      <ElTabs v-model="activeTab">
        <!-- 1. 应用清单(M3: OpenSearch states-inventory-packages 直查) -->
        <ElTabPane label="应用清单" name="applications">
          <template v-if="!hasWazuhAgent">
            <ElEmpty description="该资产无 Wazuh Agent，应用清单数据不适用">
              <template #image>
                <ElIcon :size="48" color="#909399"><Box /></ElIcon>
              </template>
            </ElEmpty>
          </template>
          <template v-else>
            <div class="tab-header">
              <span class="tab-header-title">已安装软件包
                <ElTag v-if="appsTotal" size="small" effect="plain" class="ml-2">{{ appsTotal }} 个</ElTag>
              </span>
              <div class="tab-header-actions">
                <ElInput
                  v-model="appsSearch"
                  placeholder="搜索包名"
                  clearable
                  style="width: 200px"
                  @keyup.enter="handleAppsSearch"
                  @clear="handleAppsSearch"
                />
                <ElButton type="primary" size="small" :icon="Refresh" @click="loadApplications" :loading="appsLoading">刷新</ElButton>
              </div>
            </div>
            <ElTable :data="appsData" v-loading="appsLoading" border stripe style="width: 100%">
              <ElTableColumn prop="name" label="软件名" min-width="180" fixed show-overflow-tooltip>
                <template #default="{ row }">
                  <span class="cve-id-text">{{ row.name }}</span>
                </template>
              </ElTableColumn>
              <ElTableColumn prop="version" label="版本" min-width="180" show-overflow-tooltip />
              <ElTableColumn prop="type" label="类型" width="80" align="center">
                <template #default="{ row }">
                  <ElTag size="small" effect="plain" :type="row.type === 'deb' ? 'primary' : 'success'">{{ row.type || '-' }}</ElTag>
                </template>
              </ElTableColumn>
              <ElTableColumn label="大小" width="90" align="center">
                <template #default="{ row }">{{ formatSize(row.size) }}</template>
              </ElTableColumn>
              <ElTableColumn prop="path" label="安装路径" min-width="220" show-overflow-tooltip>
                <template #default="{ row }">{{ row.path || '—' }}</template>
              </ElTableColumn>
            </ElTable>
            <div v-if="appsTotal > appsPageSize" class="apps-pagination">
              <ElPagination
                v-model:current-page="appsPage"
                :page-size="appsPageSize"
                :total="appsTotal"
                layout="total, prev, pager, next"
                @current-change="loadApplications"
              />
            </div>
            <ElEmpty v-if="!appsLoading && appsData.length === 0" :description="appsSearch ? '未找到匹配的软件包' : 'Agent 未开启软件包清点或暂无数据'" />
          </template>
        </ElTabPane>

        <!-- 2. 漏洞(M1/T3: 接通 soc_asset_vulnerabilities 真实数据) -->
        <ElTabPane label="漏洞" name="vulnerabilities">
          <template v-if="!hasWazuhAgent">
            <ElEmpty description="该资产无 Wazuh Agent，漏洞数据不适用">
              <template #image>
                <ElIcon :size="48" color="#909399"><Warning /></ElIcon>
              </template>
            </ElEmpty>
          </template>
          <template v-else>
            <div class="tab-header">
              <span class="tab-header-title">未修复漏洞（SCAP）
                <ElTag v-if="vulnsTotal" size="small" type="danger" effect="plain" class="ml-2">{{ vulnsTotal }} 项</ElTag>
              </span>
              <ElButton type="primary" size="small" :icon="Refresh" @click="loadVulns" :loading="vulnsLoading">刷新</ElButton>
            </div>
            <ElTable :data="vulnsData" v-loading="vulnsLoading" border stripe style="width: 100%">
              <ElTableColumn prop="cve_id" label="CVE 编号" width="160" fixed>
                <template #default="{ row }">
                  <span class="cve-id-text">{{ row.cve_id }}</span>
                </template>
              </ElTableColumn>
              <ElTableColumn prop="title" label="漏洞标题" min-width="220" show-overflow-tooltip />
              <ElTableColumn label="严重程度" width="90" align="center">
                <template #default="{ row }">
                  <ElTag :type="vulnSeverityType(row.severity)" size="small" effect="dark">{{ vulnSeverityLabel(row.severity) }}</ElTag>
                </template>
              </ElTableColumn>
              <ElTableColumn prop="cvss_score" label="CVSS" width="75" align="center">
                <template #default="{ row }">{{ row.cvss_score ?? '-' }}</template>
              </ElTableColumn>
              <ElTableColumn label="AI 风险" width="95" align="center">
                <template #default="{ row }">
                  <span v-if="row.risk_score != null" :class="['risk-score', riskLevelClass(row.risk_score)]">
                    {{ row.risk_score.toFixed(1) }}
                  </span>
                  <span v-else>-</span>
                </template>
              </ElTableColumn>
              <ElTableColumn label="状态" width="85" align="center">
                <template #default="{ row }">
                  <ElTag :type="row.status === 'open' ? 'danger' : row.status === 'in_progress' ? 'warning' : 'success'" size="small" effect="light">
                    {{ avStatusLabel(row.status) }}
                  </ElTag>
                </template>
              </ElTableColumn>
              <ElTableColumn label="SLA" width="90" align="center">
                <template #default="{ row }">
                  <ElTag v-if="row.sla_status === 'overdue'" type="danger" size="small" effect="plain">已逾期</ElTag>
                  <ElTag v-else-if="row.sla_status === 'warning'" type="warning" size="small" effect="plain">临期</ElTag>
                  <ElTag v-else-if="row.sla_status" type="info" size="small" effect="plain">正常</ElTag>
                  <span v-else>-</span>
                </template>
              </ElTableColumn>
              <ElTableColumn label="检测时间" width="150" align="center">
                <template #default="{ row }">
                  <span :title="formatTime(row.detected_at)">{{ formatTime(row.detected_at) }}</span>
                </template>
              </ElTableColumn>
              <ElTableColumn label="操作" width="100" align="center" fixed="right">
                <template #default="{ row }">
                  <ElButton type="warning" link size="small" :loading="incidentCreatingId === row.id" @click="handleCreateIncident(row)">生成事件</ElButton>
                </template>
              </ElTableColumn>
            </ElTable>
            <ElEmpty v-if="!vulnsLoading && vulnsData.length === 0" description="该资产暂无未修复漏洞" />
            <div v-if="vulnsTotal > vulnsPageSize" class="apps-pagination">
              <ElPagination
                v-model:current-page="vulnsPage"
                :page-size="vulnsPageSize"
                :total="vulnsTotal"
                layout="total, prev, pager, next"
                @current-change="loadVulns"
              />
            </div>
          </template>
        </ElTabPane>

        <!-- 3. 端口管理(M4: 本地 CRUD + Wazuh 实时端口双源合并, 漏洞列接真实数据) -->
        <ElTabPane label="端口" name="ports">
          <div class="tab-header">
            <span class="tab-header-title">端口信息
              <ElTag v-if="wazuhPortsData.length" size="small" type="success" effect="plain" class="ml-2">Wazuh 实时 {{ wazuhPortsData.length }} 条</ElTag>
            </span>
            <ElButton type="primary" size="small" @click="showPortDialog">添加端口</ElButton>
          </div>
          <ElTable :data="pagedPortsData" v-loading="portsLoading" border stripe style="width: 100%">
            <ElTableColumn prop="port" label="端口" width="70" align="center">
              <template #default="{ row }">
                <span :class="{ 'high-risk-port': isHighRisk(row.port) }">{{ row.port }}</span>
              </template>
            </ElTableColumn>
            <ElTableColumn prop="protocol" label="协议" width="75" align="center" />
            <ElTableColumn label="来源" width="85" align="center">
              <template #default="{ row }">
                <ElTag :type="row.source === 'wazuh' ? 'success' : 'info'" size="small" effect="plain">
                  {{ row.source === 'wazuh' ? 'Wazuh' : '本地' }}
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn prop="state" label="状态" width="85" align="center">
              <template #default="{ row }">
                <ElTag :type="row.state === 'open' || row.state === 'listening' ? 'success' : row.state === 'closed' ? 'danger' : 'warning'" size="small" effect="light">
                  {{ row.state || '--' }}
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn label="服务/进程" min-width="140" align="left" show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row.process">{{ row.process }}<span v-if="row.pid" class="pid-text"> ({{ row.pid }})</span></span>
                <span v-else>{{ row.service || '--' }}</span>
              </template>
            </ElTableColumn>
            <ElTableColumn prop="version" label="版本" min-width="130" align="center" show-overflow-tooltip />
            <ElTableColumn label="风险等级" width="170" align="center">
              <template #default="{ row }">
                <ElTag v-if="isHighRisk(row.port)" :type="riskTagType(row.port)" size="small" effect="dark">
                  {{ riskLabel(row.port) }}
                </ElTag>
                <span v-else class="text-placeholder">--</span>
              </template>
            </ElTableColumn>
            <ElTableColumn label="关联漏洞" min-width="180" align="left">
              <template #default="{ row }">
                <template v-if="matchedVulns(row).length">
                  <ElTag
                    v-for="v in matchedVulns(row)"
                    :key="v.cve_id"
                    type="danger"
                    size="small"
                    effect="plain"
                    class="mr-1 mb-1 cursor-pointer"
                    @click="activeTab = 'vulnerabilities'"
                  >
                    {{ v.cve_id }}
                  </ElTag>
                </template>
                <span v-else class="text-placeholder">--</span>
              </template>
            </ElTableColumn>
            <ElTableColumn label="扫描时间" width="160" align="center">
              <template #default="{ row }">
                <span v-if="row.scan_time" :title="formatTime(row.scan_time)">{{ relativeTime.format(row.scan_time) }}</span>
                <span v-else class="text-placeholder">实时</span>
              </template>
            </ElTableColumn>
            <ElTableColumn label="操作" width="80" align="center" fixed="right">
              <template #default="{ row }">
                <ElButton v-if="row.source === 'local'" type="danger" link size="small" @click="handleDeletePort(row)">删除</ElButton>
                <span v-else class="text-placeholder">—</span>
              </template>
            </ElTableColumn>
          </ElTable>
          <ElEmpty v-if="!portsLoading && mergedPortsData.length === 0" description="暂无端口数据" />
          <div v-if="mergedPortsData.length > portsPageSize" class="apps-pagination">
            <ElPagination
              v-model:current-page="portsPage"
              :page-size="portsPageSize"
              :total="mergedPortsData.length"
              layout="total, prev, pager, next"
            />
          </div>
        </ElTabPane>

        <!-- 4. 基线(M2/T5: SCA 不合规配置项, vuln_type=sca) -->
        <ElTabPane label="基线" name="baseline">
          <template v-if="!hasWazuhAgent">
            <ElEmpty description="该资产无 Wazuh Agent，基线数据不适用">
              <template #image>
                <ElIcon :size="48" color="#909399"><Document /></ElIcon>
              </template>
            </ElEmpty>
          </template>
          <template v-else>
            <div class="tab-header">
              <span class="tab-header-title">不合规安全配置项（SCA 基线核查）
                <ElTag v-if="baselineTotal" size="small" type="warning" effect="plain" class="ml-2">{{ baselineTotal }} 项</ElTag>
              </span>
              <ElButton type="primary" size="small" :icon="Refresh" @click="loadBaseline" :loading="baselineLoading">刷新</ElButton>
            </div>
            <ElTable :data="baselineData" v-loading="baselineLoading" border stripe style="width: 100%">
              <ElTableColumn prop="cve_id" label="检查项 ID" width="220" fixed show-overflow-tooltip>
                <template #default="{ row }">
                  <span class="cve-id-text">{{ row.cve_id }}</span>
                </template>
              </ElTableColumn>
              <ElTableColumn prop="title" label="基线要求" min-width="220" show-overflow-tooltip />
              <ElTableColumn label="严重程度" width="90" align="center">
                <template #default="{ row }">
                  <ElTag :type="vulnSeverityType(row.severity)" size="small" effect="dark">{{ vulnSeverityLabel(row.severity) }}</ElTag>
                </template>
              </ElTableColumn>
              <ElTableColumn prop="fix_suggestion" label="修复建议 / Remediation" min-width="260" show-overflow-tooltip>
                <template #default="{ row }">{{ row.fix_suggestion || '—' }}</template>
              </ElTableColumn>
              <ElTableColumn label="检测时间" width="150" align="center">
                <template #default="{ row }">{{ formatTime(row.detected_at) }}</template>
              </ElTableColumn>
            </ElTable>
            <ElEmpty v-if="!baselineLoading && baselineData.length === 0" description="该资产基线检查全部合规" />
            <div v-if="baselineTotal > baselinePageSize" class="apps-pagination">
              <ElPagination
                v-model:current-page="baselinePage"
                :page-size="baselinePageSize"
                :total="baselineTotal"
                layout="total, prev, pager, next"
                @current-change="loadBaseline"
              />
            </div>
          </template>
        </ElTabPane>

        <!-- 5. 告警(M5: 时间范围/等级筛选/分页增强) -->
        <ElTabPane label="告警" name="alerts">
          <!-- F1.2：AI 安全态势摘要横幅（告警簇+事件+风险聚合；带溯源与反馈） -->
          <div v-if="secSummary" class="sec-summary" v-loading="secSummaryLoading">
            <div class="sec-summary-head">
              <span class="sec-summary-title">
                AI 态势摘要
                <ElTag size="small" :type="secSummary.summary_source === 'glm' ? 'primary' : 'info'" effect="plain">
                  {{ secSummary.summary_source === 'glm' ? 'GLM' : '统计' }}
                </ElTag>
              </span>
              <span class="sec-summary-actions">
                <ElTooltip :content="secSummaryWindowLabel" placement="top">
                  <ElIcon class="sec-summary-meta-icon"><InfoFilled /></ElIcon>
                </ElTooltip>
                <ElIcon class="sec-summary-refresh" @click="loadSecSummary(true)"><Refresh /></ElIcon>
                <AiFeedback target-type="security_summary" :target-id="assetId" />
              </span>
            </div>
            <div class="sec-summary-text">{{ secSummary.summary }}</div>
            <div v-if="secSummaryTopRules.length" class="sec-summary-rules">
              <ElTag v-for="r in secSummaryTopRules" :key="r.description" size="small" effect="light" type="info">
                {{ r.description }} ×{{ r.count }}
              </ElTag>
            </div>
          </div>
          <div class="tab-header">
            <div class="tab-header-actions">
              <ElSelect v-model="alertsHours" style="width: 110px" @change="handleAlertsQuery">
                <ElOption label="最近 24h" :value="24" />
                <ElOption label="最近 7d" :value="168" />
                <ElOption label="最近 30d" :value="720" />
              </ElSelect>
              <ElSelect v-model="alertsMinLevel" placeholder="全部等级" clearable style="width: 120px" @change="handleAlertsQuery">
                <ElOption label="L12+ 严重" :value="12" />
                <ElOption label="L8+ 高危" :value="8" />
                <ElOption label="L4+ 中危" :value="4" />
              </ElSelect>
            </div>
            <ElButton type="primary" size="small" :icon="Refresh" @click="loadAlerts" :loading="alertsLoading">刷新</ElButton>
          </div>
          <ElTable :data="alertsData" v-loading="alertsLoading" border stripe style="width: 100%">
            <ElTableColumn label="时间" width="165" align="center">
              <template #default="{ row }">{{ formatTime(row.timestamp) }}</template>
            </ElTableColumn>
            <ElTableColumn label="等级" width="85" align="center">
              <template #default="{ row }">
                <ElTag :type="getAlertLevelType(row.rule?.level)" size="small" effect="dark">
                  L{{ row.rule?.level ?? '-' }}
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn prop="rule.description" label="规则描述" min-width="280" align="left" show-overflow-tooltip />
            <ElTableColumn prop="agent.id" label="Agent" width="85" align="center" />
            <ElTableColumn prop="location" label="位置" width="120" align="center" show-overflow-tooltip />
            <ElTableColumn prop="rule.id" label="规则ID" width="95" align="center" />
          </ElTable>
          <div v-if="alertsTotal > alertsPageSize" class="apps-pagination">
            <ElPagination
              v-model:current-page="alertsPage"
              :page-size="alertsPageSize"
              :total="alertsTotal"
              layout="total, prev, pager, next"
              @current-change="loadAlerts"
            />
          </div>
          <ElEmpty v-if="!alertsLoading && alertsData.length === 0" :description="`暂无告警（默认查询最近 ${alertsHours}h）`" />
        </ElTabPane>

        <!-- 6. 数据来源 -->
        <ElTabPane label="数据来源" name="datasources">
          <ElTable :data="datasourcesData" v-loading="datasourcesLoading" border stripe style="width: 100%">
            <ElTableColumn prop="source" label="来源" width="160" align="center">
              <template #default="{ row }">
                <ElTag type="primary" effect="plain" size="small">
                  {{ sourceLabelMap[row.source] || row.source }}
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn prop="source_id" label="来源ID" width="140" align="center" />
            <ElTableColumn prop="source_status" label="来源状态" width="120" align="center">
              <template #default="{ row }">
                <ElTag v-if="row.source_status" :type="getSourceStatusTagType(row.source_status)" size="small" effect="dark">
                  {{ statusLabelMap[row.source_status] || row.source_status }}
                </ElTag>
                <span v-else class="text-placeholder">--</span>
              </template>
            </ElTableColumn>
            <ElTableColumn prop="last_seen_at" label="最后发现" width="170" align="center">
              <template #default="{ row }">
                <span :title="formatTime(row.last_seen_at)">{{ relativeTime.format(row.last_seen_at) }}</span>
              </template>
            </ElTableColumn>
            <ElTableColumn label="来源详情" min-width="280" align="left">
              <template #default="{ row }">
                <ElPopover v-if="row.source_metadata && Object.keys(row.source_metadata).length > 0" placement="left" :width="320" trigger="click">
                  <template #reference>
                    <ElButton size="small" type="info" link>查看详情 ({{ Object.keys(row.source_metadata).length }} 项)</ElButton>
                  </template>
                  <div class="source-meta-popover">
                    <div v-for="(val, key) in row.source_metadata" :key="key" class="source-meta-row">
                      <span class="source-meta-key">{{ key }}:</span>
                      <span class="source-meta-value">{{ val ?? '--' }}</span>
                    </div>
                  </div>
                </ElPopover>
                <span v-else class="text-placeholder">--</span>
              </template>
            </ElTableColumn>
          </ElTable>
          <ElEmpty v-if="!datasourcesLoading && datasourcesData.length === 0" description="暂无数据来源记录" />
        </ElTabPane>
      </ElTabs>
    </ElCard>

    <!-- 端口弹窗 -->
    <ElDialog v-model="portDialogVisible" title="添加端口" width="450px" align-center :close-on-click-modal="false">
      <ElForm ref="portFormRef" :model="portFormData" :rules="portRules" label-width="80px">
        <ElFormItem label="端口" prop="port">
          <ElInputNumber v-model="portFormData.port" :min="1" :max="65535" style="width: 100%" />
        </ElFormItem>
        <ElFormItem label="协议" prop="protocol">
          <ElSelect v-model="portFormData.protocol" style="width: 100%">
            <ElOption label="TCP" value="tcp" />
            <ElOption label="UDP" value="udp" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="状态" prop="state">
          <ElSelect v-model="portFormData.state" style="width: 100%">
            <ElOption label="开放" value="open" />
            <ElOption label="关闭" value="closed" />
            <ElOption label="过滤" value="filtered" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="服务" prop="service">
          <ElInput v-model="portFormData.service" placeholder="如: ssh, http, mysql" />
        </ElFormItem>
        <ElFormItem label="版本" prop="version">
          <ElInput v-model="portFormData.version" placeholder="服务版本信息" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="portDialogVisible = false">取消</ElButton>
        <ElButton type="primary" @click="handlePortSubmit">确定</ElButton>
      </template>
    </ElDialog>

    <!-- 标签弹窗(从基本信息卡触发) -->
    <ElDialog
      v-model="tagDialogVisible"
      :title="tagDialogType === 'add' ? '添加标签' : '编辑标签'"
      width="450px"
      align-center
      :close-on-click-modal="false"
    >
      <ElForm ref="tagFormRef" :model="tagFormData" :rules="tagRules" label-width="80px">
        <ElFormItem label="标签键" prop="tag_key">
          <ElSelect
            v-model="tagFormData.tag_key"
            filterable
            allow-create
            placeholder="选择或输入标签键"
            style="width: 100%"
          >
            <ElOption
              v-for="item in commonTagKeys"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="标签值" prop="tag_value">
          <ElSelect
            v-if="tagKeyOptions.length > 0"
            v-model="tagFormData.tag_value"
            filterable
            allow-create
            placeholder="选择或输入标签值"
            style="width: 100%"
          >
            <ElOption
              v-for="opt in tagKeyOptions"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </ElSelect>
          <ElInput v-else v-model="tagFormData.tag_value" placeholder="请输入标签值" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="tagDialogVisible = false">取消</ElButton>
        <ElButton type="primary" @click="handleTagSubmit">确定</ElButton>
      </template>
    </ElDialog>

    <!-- P3/F3.2：EOL 设置（人工指定优先于参考表，操作落审计） -->
    <ElDialog v-model="eolDialogVisible" title="设置预期 EOL" width="460px" align-center>
      <p class="eol-hint">
        系统默认根据预置生命周期参考表自动匹配 EOL。手动指定后将<strong>优先于参考表</strong>，
        批量刷新不再覆盖；操作会记入审计日志。
      </p>
      <ElForm label-width="90px">
        <ElFormItem label="EOL 日期">
          <ElDatePicker
            v-model="eolFormDate"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            style="width: 100%"
          />
        </ElFormItem>
        <ElFormItem label="当前口径">
          <span class="eol-current">
            {{ assetDetail.expected_eol || '未设置' }}
            <ElTag size="small" effect="plain">
              {{ assetDetail.expected_eol_source === 'manual' ? '人工指定' : '参考表匹配' }}
            </ElTag>
          </span>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton
          v-if="assetDetail.expected_eol_source === 'manual'"
          @click="handleClearEol"
          :loading="eolSubmitting"
        >
          恢复自动匹配
        </ElButton>
        <ElButton @click="eolDialogVisible = false">取消</ElButton>
        <ElButton type="primary" @click="handleSaveEol" :loading="eolSubmitting">确定</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ref, reactive, computed, onMounted, nextTick, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { ArrowLeft, Refresh, Plus, Box, Warning, Document, InfoFilled } from '@element-plus/icons-vue'
  import { FormInstance, ElMessageBox, ElMessage } from 'element-plus'
  import { getAssetVulnerabilities, createIncidentFromVulnerability } from '@/api/vulnerabilities'
  import {
    getAssetDetail,
    getAssetPorts,
    addAssetPort,
    deleteAssetPort,
    getAssetTags,
    addAssetTag,
    deleteAssetTag,
    getCommonTagKeys,
    getAssetSummary,
    getAssetSources
  } from '@/api/asset'
  import { getAlertsByIp, getAlertsByAgentId } from '@/api/alert'
  import { getAssetApplications, getAssetWazuhPorts } from '@/api/asset'
  import { useDictStore } from '@/store/modules/dict'
  import { useRelativeTime } from '@/composables/useRelativeTime'
  import { getHighRiskPort, type PortRisk } from '@/constants/highRiskPorts'
  import MetricCard from './components/MetricCard.vue'
  import AiFeedback from '@/components/business/ai-feedback/index.vue'
  import { getAssetRisk, getAssetRiskHistory, refreshAssetRiskSummary, getAssetSecuritySummary, type AssetRiskDetail, type SecuritySummaryResult } from '@/api/asset'
  import { overrideAssetEol, clearAssetEol } from '@/api/asset'

  const route = useRoute()
  const router = useRouter()
  const assetId = computed(() => route.params.id as string)
  const dictStore = useDictStore()
  const relativeTime = useRelativeTime()

  // 字典映射
  const assetTypeLabelMap = computed(() => dictStore.getLabelMap('asset_type'))
  const criticalityLabelMap = computed(() => dictStore.getLabelMap('asset_criticality'))
  const criticalityColorMap = computed(() => dictStore.getColorMap('asset_criticality'))
  const statusLabelMap = computed(() => dictStore.getLabelMap('asset_status'))
  const statusColorMap = computed(() => dictStore.getColorMap('asset_status'))
  const networkZoneLabelMap = computed(() => dictStore.getLabelMap('network_zone'))
  const dataSourceLabelMap = computed(() => dictStore.getLabelMap('data_source'))
  const dataClassLabelMap = computed(() => dictStore.getLabelMap('data_classification'))

  // 资产详情
  const detailLoading = ref(false)
  const assetDetail = ref<any>({})
  const statusTagType = computed(() => statusColorMap.value[assetDetail.value.asset_status] as any || 'info')
  const criticalityTagType = computed(() => criticalityColorMap.value[assetDetail.value.criticality] as any || 'info')

  const loadDetail = async () => {
    if (!assetId.value) return
    detailLoading.value = true
    try {
      const res = await getAssetDetail(assetId.value)
      const r: any = res
      assetDetail.value = r?.data || r || {}
    } catch (err) {
      console.error('获取资产详情出错:', err)
      ElMessage.error('获取资产详情失败')
    } finally {
      detailLoading.value = false
    }
  }

  // ---------- P3/F3.2：生命周期（EOL / 保修） ----------

  const daysUntil = (d?: string): number | null => {
    if (!d) return null
    const target = new Date(`${d}T00:00:00Z`).getTime()
    const today = new Date()
    const todayUtc = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate())
    return Math.round((target - todayUtc) / 86400000)
  }

  const eolDays = computed(() => daysUntil(assetDetail.value.expected_eol))
  const warrantyDays = computed(() => daysUntil(assetDetail.value.warranty_end))

  const daysText = (n: number | null) => {
    if (n === null) return ''
    if (n < 0) return `已过期 ${Math.abs(n)} 天`
    if (n === 0) return '今日到期'
    return `剩 ${n} 天`
  }

  const eolDaysText = computed(() => daysText(eolDays.value))
  const warrantyDaysText = computed(() => daysText(warrantyDays.value))

  const eolTagType = computed(() => {
    const n = eolDays.value
    if (n === null) return 'info'
    if (n < 0) return 'danger'
    if (n <= 30) return 'danger'
    if (n <= 90) return 'warning'
    return 'success'
  })

  const eolDialogVisible = ref(false)
  const eolFormDate = ref<string>('')
  const eolSubmitting = ref(false)

  const openEolDialog = () => {
    eolFormDate.value = assetDetail.value.expected_eol || ''
    eolDialogVisible.value = true
  }

  const handleSaveEol = async () => {
    if (!eolFormDate.value) {
      ElMessage.warning('请选择 EOL 日期')
      return
    }
    eolSubmitting.value = true
    try {
      const res: any = await overrideAssetEol(assetId.value, eolFormDate.value)
      if (res.code === 200) {
        ElMessage.success('已设为人工指定 EOL')
        eolDialogVisible.value = false
        await loadDetail()
      } else {
        ElMessage.warning(res.msg || '设置失败')
      }
    } catch {
      ElMessage.error('设置 EOL 失败')
    } finally {
      eolSubmitting.value = false
    }
  }

  const handleClearEol = async () => {
    eolSubmitting.value = true
    try {
      const res: any = await clearAssetEol(assetId.value)
      if (res.code === 200) {
        ElMessage.success(
          res.data?.expected_eol
            ? `已恢复自动匹配：${res.data.expected_eol}`
            : '已恢复自动匹配（当前无对应预置条目）'
        )
        eolDialogVisible.value = false
        await loadDetail()
      } else {
        ElMessage.warning(res.msg || '恢复失败')
      }
    } catch {
      ElMessage.error('恢复自动匹配失败')
    } finally {
      eolSubmitting.value = false
    }
  }

  // Tab - 默认进 ports(Phase 1 唯一有数据的 Tab)
  // Phase 3 接入应用数据后,改回默认 applications(设计文档 §4.2)
  const activeTab = ref('ports')

  // ========== 安全摘要 ==========
  const summaryLoading = ref(false)
  const summary = ref<Api.Asset.AssetSummary>({
    asset_id: '',
    online_status: 'unknown',
    alert_24h: 0,
    alert_critical_24h: 0,
    open_incidents: 0,
    vuln_critical: 0,
    vuln_high: 0,
    vuln_total: 0,
    open_ports: 0,
    high_risk_ports: 0,
    applications: 0,
    sca_pass_rate: null,
    sca_total: 0,
    sca_failed: 0,
    last_port_scan: null,
    last_vuln_scan: null,
    last_sca_scan: null,
    data_classification: 'internal',
    owner: null,
    owner_contact: null,
    tags: []
  })

  const loadSummary = async () => {
    if (!assetId.value) return
    summaryLoading.value = true
    try {
      const res = await getAssetSummary(assetId.value)
      const r: any = res
      const d = r?.data
      if (d) {
        summary.value = { ...summary.value, ...d }
      }
    } catch (err) {
      console.error('获取安全摘要失败:', err)
    } finally {
      summaryLoading.value = false
    }
  }

  // 摘要派生
  const onlineStatusLabel = computed(() => {
    const map: Record<string, string> = {
      online: '在线',
      offline: '离线',
      unknown: '未知'
    }
    return map[summary.value.online_status] || '未知'
  })

  const onlineStatusType = computed<'success' | 'danger' | 'info'>(() => {
    if (summary.value.online_status === 'online') return 'success'
    if (summary.value.online_status === 'offline') return 'danger'
    return 'info'
  })

  const scaPassRateType = computed<'success' | 'warning' | 'danger' | 'neutral'>(() => {
    if (summary.value.sca_pass_rate === null) return 'neutral'
    if (summary.value.sca_pass_rate >= 0.9) return 'success'
    if (summary.value.sca_pass_rate >= 0.7) return 'warning'
    return 'danger'
  })

  // ========== 端口管理 ==========
  const portsLoading = ref(false)
  const portsData = ref<any[]>([])
  const portDialogVisible = ref(false)
  const portFormRef = ref<FormInstance>()
  const portFormData = reactive({
    port: 80,
    protocol: 'tcp',
    state: 'open',
    service: '',
    version: ''
  })
  const portRules = {
    port: [{ required: true, message: '请输入端口号', trigger: 'blur' }],
    protocol: [{ required: true, message: '请选择协议', trigger: 'change' }],
    state: [{ required: true, message: '请选择状态', trigger: 'change' }]
  }

  const isHighRisk = (port: number) => getHighRiskPort(port) !== null
  const riskLabel = (port: number) => getHighRiskPort(port)?.reason ?? ''
  const riskTagType = (port: number): 'danger' | 'warning' | 'info' => {
    const info = getHighRiskPort(port)
    if (!info) return 'info'
    if (info.risk === 'critical' || info.risk === 'high') return 'danger'
    return 'warning'
  }

  // （旧 parseVulns 自由文本解析已由 M4 matchedVulns 真实数据匹配替代）

  const loadPorts = async () => {
    if (!assetId.value) return
    portsLoading.value = true
    try {
      const res = await getAssetPorts(assetId.value, { page: 1, pageSize: 100 })
      const r: any = res
      const d = r?.data
      portsData.value = Array.isArray(d?.items) ? d.items : Array.isArray(d) ? d : []
    } catch {
      portsData.value = []
    } finally {
      portsLoading.value = false
    }
  }

  const showPortDialog = () => {
    portDialogVisible.value = true
    portFormData.port = 80
    portFormData.protocol = 'tcp'
    portFormData.state = 'open'
    portFormData.service = ''
    portFormData.version = ''
    nextTick(() => portFormRef.value?.clearValidate())
  }

  const handlePortSubmit = async () => {
    if (!portFormRef.value) return
    await portFormRef.value.validate(async (valid) => {
      if (valid) {
        try {
          const res = await addAssetPort(assetId.value, {
            ...portFormData,
            asset_ip: assetDetail.value.asset_ip
          })
          if ((res as any)?.code === 200 || res) {
            ElMessage.success('端口添加成功')
            portDialogVisible.value = false
            portsPage.value = 1
            loadPorts()
          } else {
            ElMessage.error((res as any)?.msg || '添加失败')
          }
        } catch (err) {
          ElMessage.error('添加端口失败')
        }
      }
    })
  }

  const handleDeletePort = (row: any) => {
    ElMessageBox.confirm(`确定删除端口 ${row.port}/${row.protocol}？`, '删除端口', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
      .then(async () => {
        try {
          await deleteAssetPort(row.id)
          ElMessage.success('删除成功')
          loadPorts()
        } catch {
          ElMessage.error('删除失败')
        }
      })
      .catch(() => {})
  }

  // ========== 标签管理(从基本信息卡触发) ==========
  const tagsLoading = ref(false)
  const tagsData = ref<any[]>([])
  const tagDialogVisible = ref(false)
  const tagDialogType = ref('add')
  const tagFormRef = ref<FormInstance>()
  const tagFormData = reactive({
    id: '',
    tag_key: '',
    tag_value: ''
  })
  const tagRules = {
    tag_key: [{ required: true, message: '请输入或选择标签键', trigger: 'change' }],
    tag_value: [{ required: true, message: '请输入标签值', trigger: 'change' }]
  }

  // 常用标签键(Phase 4 改字典驱动)
  const commonTagKeys = [
    { label: '环境 (environment)', value: 'environment' },
    { label: '业务系统 (business_system)', value: 'business_system' },
    { label: '位置 (location)', value: 'location' },
    { label: '团队 (team)', value: 'team' },
    { label: '数据分类 (data_classification)', value: 'data_classification' }
  ]

  const tagKeyOptionsMap: Record<string, string[]> = {
    environment: ['production', 'staging', 'development', 'testing'],
    business_system: ['hr-system', 'finance-system', 'crm', 'erp', 'oa-system'],
    location: ['beijing', 'shanghai', 'guangzhou', 'shenzhen'],
    team: ['backend', 'frontend', 'devops', 'security'],
    data_classification: ['public', 'internal', 'confidential', 'secret']
  }

  const tagKeyOptions = computed(() => tagKeyOptionsMap[tagFormData.tag_key] || [])

  const loadTags = async () => {
    if (!assetId.value) return
    tagsLoading.value = true
    try {
      const res = await getAssetTags(assetId.value, { page: 1, pageSize: 100 })
      const r: any = res
      const d = r?.data
      tagsData.value = Array.isArray(d?.items) ? d.items : Array.isArray(d) ? d : []
    } catch {
      tagsData.value = []
    } finally {
      tagsLoading.value = false
    }
  }

  const showTagDialog = (type: string, row?: any) => {
    tagDialogVisible.value = true
    tagDialogType.value = type
    if (type === 'edit' && row) {
      tagFormData.id = row.id
      tagFormData.tag_key = row.tag_key
      tagFormData.tag_value = row.tag_value
    } else {
      tagFormData.id = ''
      tagFormData.tag_key = ''
      tagFormData.tag_value = ''
    }
    nextTick(() => tagFormRef.value?.clearValidate())
  }

  const handleTagSubmit = async () => {
    if (!tagFormRef.value) return
    await tagFormRef.value.validate(async (valid) => {
      if (valid) {
        try {
          const res = await addAssetTag(assetId.value, {
            tag_key: tagFormData.tag_key,
            tag_value: tagFormData.tag_value
          })
          if ((res as any)?.code === 200 || res) {
            ElMessage.success('添加成功')
            tagDialogVisible.value = false
            loadTags()
          } else {
            ElMessage.error((res as any)?.msg || '操作失败')
          }
        } catch (err) {
          ElMessage.error('操作失败')
        }
      }
    })
  }

  const handleDeleteTag = (row: any) => {
    ElMessageBox.confirm(`确定删除标签 ${row.tag_key}?`, '删除标签', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
      .then(async () => {
        try {
          await deleteAssetTag(row.id)
          ElMessage.success('删除成功')
          loadTags()
        } catch {
          ElMessage.error('删除失败')
        }
      })
      .catch(() => {})
  }

  // ========== 漏洞/基线 Tab（M1/M2：接 soc_asset_vulnerabilities） ==========
  const hasWazuhAgent = computed(() => !!assetDetail.value.wazuh_agent_id)

  const vulnsLoading = ref(false)
  const vulnsData = ref<any[]>([])
  const vulnsTotal = ref(0)
  const vulnsPage = ref(1)
  const vulnsPageSize = 10
  const baselineLoading = ref(false)
  const baselineData = ref<any[]>([])
  const baselineTotal = ref(0)
  const baselinePage = ref(1)
  const baselinePageSize = 10
  const incidentCreatingId = ref('')

  const loadVulns = async () => {
    if (!assetId.value || !hasWazuhAgent.value) return
    vulnsLoading.value = true
    try {
      // 注意：request.get 无 keepFullResponse → 返回已解包的业务本体 {items,total}
      const d: any = await getAssetVulnerabilities({
        asset_id: assetId.value,
        vuln_type: 'scap',
        status: 'open',
        skip: (vulnsPage.value - 1) * vulnsPageSize,
        limit: vulnsPageSize
      })
      vulnsData.value = Array.isArray(d?.items) ? d.items : []
      vulnsTotal.value = d?.total || 0
    } catch {
      vulnsData.value = []
      vulnsTotal.value = 0
    } finally {
      vulnsLoading.value = false
    }
  }

  const loadBaseline = async () => {
    if (!assetId.value || !hasWazuhAgent.value) return
    baselineLoading.value = true
    try {
      const d: any = await getAssetVulnerabilities({
        asset_id: assetId.value,
        vuln_type: 'sca',
        status: 'open',
        skip: (baselinePage.value - 1) * baselinePageSize,
        limit: baselinePageSize
      })
      baselineData.value = Array.isArray(d?.items) ? d.items : []
      baselineTotal.value = d?.total || 0
    } catch {
      baselineData.value = []
      baselineTotal.value = 0
    } finally {
      baselineLoading.value = false
    }
  }

  // severity 中文化（与漏洞列表页同语义）
  const vulnSeverityLabel = (s: string) =>
    ({ critical: '严重', high: '高危', medium: '中危', low: '低危' } as Record<string, string>)[s] || s || '-'
  const vulnSeverityType = (s: string): 'danger' | 'warning' | 'info' | 'success' =>
    ({ critical: 'danger', high: 'danger', medium: 'warning', low: 'info' } as Record<string, any>)[s] || 'info'
  const avStatusLabel = (s: string) =>
    ({ open: '未修复', in_progress: '修复中', fixed: '已修复' } as Record<string, string>)[s] || s

  // AI 风险分级配色（与漏洞列表页同口径 0-100 四档）
  const riskLevelClass = (score: number) =>
    score >= 80 ? 'risk-critical' : score >= 60 ? 'risk-high' : score >= 40 ? 'risk-medium' : 'risk-low'

  // 生成事件（漏洞→事件闭环，复用 vulnerabilities API）
  const handleCreateIncident = async (row: any) => {
    try {
      await ElMessageBox.confirm(
        `确认为漏洞 ${row.cve_id} 生成安全事件？`,
        '生成事件',
        { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
      )
    } catch {
      return
    }
    incidentCreatingId.value = row.id
    try {
      // request.post 无 keepFullResponse → 返回业务本体 {message, incident}
      const d: any = await createIncidentFromVulnerability(row.id)
      ElMessage.success(`事件已创建：${d?.incident?.title || row.cve_id}（可在事件管理页处理）`)
    } catch (err) {
      ElMessage.error('生成事件失败')
    } finally {
      incidentCreatingId.value = ''
    }
  }

  // ========== 应用清单 Tab（M3：OpenSearch 直查） ==========
  const appsLoading = ref(false)
  const appsData = ref<any[]>([])
  const appsTotal = ref(0)
  const appsPage = ref(1)
  const appsPageSize = 10
  const appsSearch = ref('')

  const formatSize = (bytes: number) => {
    if (!bytes || bytes <= 0) return '—'
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
    return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
  }

  const handleAppsSearch = () => {
    appsPage.value = 1
    loadApplications()
  }

  const loadApplications = async () => {
    if (!assetId.value || !hasWazuhAgent.value) return
    appsLoading.value = true
    try {
      const r: any = await getAssetApplications(assetId.value, {
        search: appsSearch.value || undefined,
        skip: (appsPage.value - 1) * appsPageSize,
        limit: appsPageSize
      })
      const d = r?.data
      appsData.value = d?.items || []
      appsTotal.value = d?.total || 0
    } catch {
      appsData.value = []
      appsTotal.value = 0
      ElMessage.error('应用清单数据源暂不可用')
    } finally {
      appsLoading.value = false
    }
  }

  // ========== Wazuh 实时端口（M4：双源合并） ==========
  const wazuhPortsData = ref<any[]>([])
  const wazuhPortsLoading = ref(false)
  const portsPage = ref(1)
  const portsPageSize = 10

  const loadWazuhPorts = async () => {
    if (!assetId.value || !hasWazuhAgent.value) return
    wazuhPortsLoading.value = true
    try {
      const r: any = await getAssetWazuhPorts(assetId.value)
      const d = r?.data
      wazuhPortsData.value = d?.items || []
    } catch {
      wazuhPortsData.value = []
    } finally {
      wazuhPortsLoading.value = false
    }
  }

  // 双源合并：本地(手动/nmap, 可删) + Wazuh(实时, 带进程)。同 port+protocol 去重
  // （本地优先；Wazuh 内部同键也去重——如 53/tcp IPv4/IPv6 双监听只计一次，与摘要统计口径一致）
  const mergedPortsData = computed(() => {
    const local = portsData.value.map((p: any) => ({ ...p, source: 'local' }))
    const localKeys = new Set(local.map((p: any) => `${p.port}/${p.protocol}`))
    const wazuhSeen = new Set<string>()
    const wazuh = wazuhPortsData.value
      .filter((p: any) => {
        const key = `${p.port}/${p.protocol}`
        if (localKeys.has(key) || wazuhSeen.has(key)) return false
        wazuhSeen.add(key)
        return true
      })
      .map((p: any) => ({
        id: `wazuh-${p.port}-${p.protocol}`,
        port: p.port,
        protocol: p.protocol,
        state: p.state,
        process: p.process,
        pid: p.pid,
        service: p.process,
        version: '',
        scan_time: null,
        source: 'wazuh'
      }))
    return [...local, ...wazuh]
  })

  // 端口内存分页（双源合并后前端切片）
  const pagedPortsData = computed(() => {
    const start = (portsPage.value - 1) * portsPageSize
    return mergedPortsData.value.slice(start, start + portsPageSize)
  })

  // 端口↔漏洞 best-effort 匹配（M4：service/process 与漏洞标题/包名匹配，点击跳漏洞 Tab）
  const matchedVulns = (portRow: any) => {
    const svc = (portRow.process || portRow.service || '').toLowerCase().replace(/\d+$/, '')
    if (!svc || svc.length < 3) return []
    return vulnsData.value.filter((v: any) => {
      const t = `${v.title || ''} ${v.cve_id || ''}`.toLowerCase()
      return t.includes(svc)
    }).slice(0, 3)
  }

  // ========== 告警 Tab（M5：时间范围/等级筛选/分页增强） ==========
  const alertsLoading = ref(false)
  const alertsData = ref<any[]>([])
  const alertsHours = ref(24)
  const alertsMinLevel = ref<number | undefined>(undefined)
  const alertsPage = ref(1)
  const alertsPageSize = 10
  const alertsTotal = ref(0)

  const handleAlertsQuery = () => {
    alertsPage.value = 1
    loadAlerts()
  }

  const loadAlerts = async () => {
    if (!assetId.value || !assetDetail.value.asset_ip) return
    alertsLoading.value = true
    try {
      // 优先使用 wazuh_agent_id 查询，更准确
      const agentId = assetDetail.value.wazuh_agent_id
      const params = {
        hours: alertsHours.value,
        level: alertsMinLevel.value || undefined,
        skip: (alertsPage.value - 1) * alertsPageSize,
        limit: alertsPageSize
      }

      let res
      if (agentId) {
        // 通过 agent_id 查询
        res = await getAlertsByAgentId(agentId, params)
      } else {
        // 没有 agent_id 时使用 IP 查询（降级方案）
        res = await getAlertsByIp(assetDetail.value.asset_ip, params)
      }

      const r: any = res
      const d = r?.data
      alertsData.value = Array.isArray(d?.items) ? d.items : Array.isArray(d) ? d : []
      alertsTotal.value = d?.total ?? alertsData.value.length
    } catch {
      alertsData.value = []
      alertsTotal.value = 0
    } finally {
      alertsLoading.value = false
    }
  }

  const getAlertLevelType = (level?: number): 'danger' | 'warning' | 'info' | 'success' => {
    if (!level) return 'info'
    if (level >= 12) return 'danger'
    if (level >= 8) return 'warning'
    if (level >= 4) return 'info'
    return 'success'
  }

  // ========== 数据来源 Tab ==========
  const datasourcesLoading = ref(false)
  const datasourcesData = ref<any[]>([])

  // 来源标签映射
  const sourceLabelMap: Record<string, string> = {
    'wazuh': 'Wazuh',
    'tplink-router': 'TP-Link 路由器',
    'nmap': 'Nmap',
    'manual': '手动录入'
  }

  const getSourceStatusTagType = (status: string): 'success' | 'danger' | 'warning' | 'info' => {
    if (status === 'online' || status === 'active') return 'success'
    if (status === 'offline' || status === 'disconnected') return 'danger'
    if (status === 'never_connected' || status === 'pending') return 'warning'
    return 'info'
  }

  const loadDataSources = async () => {
    if (!assetId.value) return
    datasourcesLoading.value = true
    try {
      const res = await getAssetSources(assetId.value)
      const r: any = res
      const d = r?.data
      datasourcesData.value = Array.isArray(d) ? d : []
    } catch (err) {
      console.error('获取数据来源失败:', err)
      datasourcesData.value = []
    } finally {
      datasourcesLoading.value = false
    }
  }

  // ========== 工具函数 ==========
  const formatTime = (time?: string) => {
    if (!time) return '--'
    return new Date(time).toLocaleString('zh-CN')
  }

  const goBack = () => {
    router.push('/assets/list')
  }

  // 详情返回后触发依赖 assetDetail 的懒加载（修复既有问题：onMounted 时 assetDetail 为空，
  // loadAlerts/loadVulns/loadBaseline 的 hasAgent/IP 判断会直接 return）
  watch(
    () => assetDetail.value,
    (nv) => {
      if (nv && nv.id) {
        loadAlerts()
        loadVulns()
        loadBaseline()
        loadApplications()
        loadWazuhPorts()
      }
    }
  )

  // 加载数据
  // ============ P3/F1.1：资产风险卡 ============

  const riskLoading = ref(false)
  const riskData = ref<AssetRiskDetail | null>(null)
  const riskHistory = ref<Array<{ risk_score: number; scored_at: string }>>([])

  const DIM_LABELS: Record<string, string> = {
    exposure: '暴露面',
    health: '系统健康度',
    alerts: '告警密度',
    importance: '资产重要性'
  }

  const loadRisk = async () => {
    if (!assetId.value) return
    riskLoading.value = true
    try {
      const [riskRes, histRes] = await Promise.all([
        getAssetRisk(assetId.value),
        getAssetRiskHistory(assetId.value, 90)
      ])
      if (riskRes.code === 200) riskData.value = riskRes.data
      if (histRes.code === 200) riskHistory.value = histRes.data?.history || []
    } catch {
      /* 静默，卡片显示空态 */
    } finally {
      riskLoading.value = false
    }
  }

  /** 刷新 = 按需生成摘要（POST refresh-summary），而非重新 GET 已存数据 */
  const handleRefreshRisk = async () => {
    if (!assetId.value) return
    riskLoading.value = true
    try {
      const res = await refreshAssetRiskSummary(assetId.value)
      if (res.code === 200 && res.data) {
        riskData.value = res.data
        if (res.data.message) {
          ElMessage.info(res.data.message)
        } else if (res.data.risk_summary) {
          ElMessage.success('风险摘要已更新')
        }
      } else {
        ElMessage.warning(res.msg || '摘要生成失败')
      }
    } catch {
      ElMessage.error('刷新请求失败，请稍后重试')
    } finally {
      riskLoading.value = false
    }
  }

  // ============ P3/F1.2：AI 安全态势摘要（告警 Tab 顶部横幅） ============

  const secSummary = ref<SecuritySummaryResult | null>(null)
  const secSummaryLoading = ref(false)

  const loadSecSummary = async (force = false) => {
    if (!assetId.value) return
    secSummaryLoading.value = true
    try {
      const res = await getAssetSecuritySummary(assetId.value, 30, force)
      if (res.code === 200 && res.data) {
        secSummary.value = res.data
      }
    } catch {
      /* 静默：横幅不显示即可，不影响告警列表 */
    } finally {
      secSummaryLoading.value = false
    }
  }

  const secSummaryWindowLabel = computed(() => {
    const s = secSummary.value?.stats
    if (!s) return ''
    const g = s.alert_groups
    return `数据窗口：近 ${s.window.days} 天｜告警簇 ${g.total}（降噪后）｜事件 ${s.incidents.total}（未关闭 ${s.incidents.open}）`
  })

  const secSummaryTopRules = computed(() => secSummary.value?.stats?.alert_groups?.top_rules?.slice(0, 3) || [])

  const riskScoreClass = computed(() => {
    const s = riskData.value?.risk_score ?? 0
    if (s >= 80) return 'is-critical'
    if (s >= 60) return 'is-high'
    if (s >= 40) return 'is-medium'
    return 'is-low'
  })

  const riskDimensions = computed(() => {
    const dims = riskData.value?.score_breakdown?.dimensions || {}
    return Object.entries(dims).map(([key, d]) => {
      const level = d.score >= 80 ? 'critical' : d.score >= 60 ? 'high' : d.score >= 40 ? 'medium' : 'low'
      const color =
        d.score >= 80 ? '#f56c6c' : d.score >= 60 ? '#e6a23c' : d.score >= 40 ? '#f7ba2a' : '#67c23a'
      return {
        key,
        label: DIM_LABELS[key] || key,
        score: d.score,
        dataGap: d.data_gap,
        reasons: (d.reasons || []).join('；'),
        level,
        color
      }
    })
  })

  // 趋势 sparkline
  const trendW = 320
  const trendH = 48
  const riskTrendPoints = computed(() => riskHistory.value.map((h) => h.risk_score))
  const trendPolyline = computed(() => {
    const pts = riskTrendPoints.value
    if (pts.length < 2) return ''
    const min = Math.min(...pts)
    const max = Math.max(...pts)
    const range = max - min || 1
    const step = trendW / (pts.length - 1)
    return pts
      .map((v, i) => `${(i * step).toFixed(1)},${(trendH - 4 - ((v - min) / range) * (trendH - 8)).toFixed(1)}`)
      .join(' ')
  })

  const riskDelta7d = computed(() => {
    const d = (riskData.value?.score_breakdown as any)?.delta_7d
    return typeof d === 'number' ? d : null
  })

  onMounted(() => {
    loadDetail()
    loadSummary()
    loadRisk()
    loadSecSummary()
    loadPorts()
    loadTags()
    loadDataSources()
  })
</script>

<style lang="scss" scoped>
  /* P3/F3.2 生命周期 */
  .text-danger {
    color: var(--el-color-danger, #f56c6c);
  }

  .lc-days {
    margin-left: 6px;
    font-size: 12px;
    color: var(--el-text-color-secondary, #909399);
  }

  .lc-source-tag {
    margin-left: 6px;
  }

  .lc-none {
    font-size: 13px;
    color: var(--el-text-color-secondary, #909399);
  }

  .lc-edit-btn {
    margin-left: 8px;
  }

  .eol-hint {
    margin: 0 0 14px;
    font-size: 12px;
    line-height: 1.7;
    color: var(--el-text-color-secondary, #909399);
  }

  .eol-current {
    font-size: 13px;
  }

  .asset-detail-page {
    // ============ P3/F1.1 资产风险卡 ============
    .risk-card {
      .card-header-right {
        display: flex;
        align-items: center;
        gap: 8px;

        .risk-scored-at {
          font-size: 12px;
          color: var(--el-text-color-secondary);
        }
      }

      .risk-na {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 12px 0;

        .risk-na-text {
          font-size: 13px;
          color: var(--el-text-color-secondary);
        }
      }

      .risk-main {
        display: flex;
        align-items: center;
        gap: 24px;

        .risk-score {
          display: flex;
          align-items: baseline;
          gap: 4px;
          flex-shrink: 0;

          .risk-score-number {
            font-size: 44px;
            font-weight: 700;
            line-height: 1;
          }

          .risk-score-label {
            font-size: 13px;
            color: var(--el-text-color-secondary);
          }

          &.is-critical .risk-score-number { color: #f56c6c; }
          &.is-high .risk-score-number { color: #e6a23c; }
          &.is-medium .risk-score-number { color: #f7ba2a; }
          &.is-low .risk-score-number { color: #67c23a; }
        }

        .risk-summary-area {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 6px;

          .risk-summary-text {
            font-size: 13px;
            line-height: 1.7;
            color: var(--el-text-color-primary);
          }

          .risk-summary-meta {
            display: flex;
            align-items: center;
            gap: 10px;

            .risk-summary-src {
              font-size: 12px;
              color: var(--el-text-color-secondary);
            }
          }
        }
      }

      .risk-dimensions {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 14px 24px;
        margin-top: 16px;

        .risk-dim {
          .risk-dim-head {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 4px;

            .risk-dim-name { font-size: 13px; }
            .risk-dim-score {
              font-weight: 700;
              font-size: 13px;

              &.is-critical { color: #f56c6c; }
              &.is-high { color: #e6a23c; }
              &.is-medium { color: #f7ba2a; }
              &.is-low { color: #67c23a; }
            }
          }

          .risk-dim-reasons {
            font-size: 12px;
            color: var(--el-text-color-secondary);
            margin-top: 4px;
            line-height: 1.5;
          }
        }
      }

      .risk-trend {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-top: 16px;
        color: var(--el-color-primary);

        .risk-trend-label {
          font-size: 12px;
          color: var(--el-text-color-secondary);
          flex-shrink: 0;
        }

        .risk-trend-svg {
          flex: 1;
          height: 48px;
        }

        .risk-trend-delta {
          font-size: 13px;
          font-weight: 600;
          flex-shrink: 0;

          &.is-up { color: #f56c6c; }
          &.is-down { color: #67c23a; }
        }
      }
    }

    padding: 0;
    // 兜底滚动: 在小屏/小笔记本上 (顶部信息卡+摘要卡+Tab 累加高度 > 视口高度)
    // .art-full-height 的 height: var(--art-full-height) 会让内容溢出但不可滚。
    // 这里强制允许页面级滚动, 避免下半截被截断。
    // 大屏 (信息卡+摘要卡 < 视口的 ~70%) 时 Tab 内部 overflow-y 仍生效, 互不冲突。
    overflow: auto;
    // 自适应内容高度 —— 内容超出视口时让父容器随内容伸展
    height: auto;
    min-height: var(--art-full-height);

    .detail-header {
      flex-shrink: 0;
      margin-bottom: 12px;
    }

    .info-card,
    .summary-card {
      flex-shrink: 0;
      margin-bottom: 16px;
    }

    // 取消 tab-card 的 flex:1 + overflow:hidden,
    // 让卡片高度随内容伸展, 避免被父级 scroll 夹住压成 0 高度
    .tab-card {
      // F1.2：安全态势摘要横幅
      .sec-summary {
        margin-bottom: 12px;
        padding: 12px 14px;
        border: 1px solid var(--el-color-primary-light-8);
        border-radius: 6px;
        background: var(--el-color-primary-light-9, #f0f7ff);

        .sec-summary-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 8px;

          .sec-summary-title {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 13px;
            font-weight: 600;
            color: var(--el-text-color-primary);
          }

          .sec-summary-actions {
            display: inline-flex;
            align-items: center;
            gap: 8px;

            .sec-summary-meta-icon {
              color: var(--el-text-color-secondary);
              cursor: help;
            }

            .sec-summary-refresh {
              color: var(--el-text-color-secondary);
              cursor: pointer;

              &:hover {
                color: var(--el-color-primary);
              }
            }
          }
        }

        .sec-summary-text {
          font-size: 13px;
          line-height: 1.7;
          color: var(--el-text-color-primary);
        }

        .sec-summary-rules {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-top: 8px;
        }
      }
      flex-shrink: 0;
      margin-bottom: 16px;

      // Tab 内部滚动限制改轻 —— 表格自身有滚动条
      :deep(.el-tabs__content) {
        overflow: visible;
      }

      :deep(.el-tab-pane) {
        height: auto;
        overflow: visible;
      }
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;

      .title {
        font-size: 16px;
        font-weight: 600;
      }

      .header-tags {
        display: flex;
        gap: 8px;
      }
    }

    .summary-grid {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
    }

    .tab-header {
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .tab-header-title {
      font-size: 13px;
      font-weight: 500;
      color: var(--el-text-color-regular, #606266);
    }

    .ml-2 {
      margin-left: 8px;
    }

    /* 漏洞/基线 Tab（M1/M2）：CVE 编号 + AI 风险分级配色（与漏洞列表页同口径） */
    .cve-id-text {
      font-family: 'JetBrains Mono', monospace;
      font-weight: 600;
      font-size: 12px;
    }

    .risk-score {
      font-family: 'JetBrains Mono', monospace;
      font-weight: 600;

      &.risk-critical { color: var(--el-color-danger, #f56c6c); }
      &.risk-high { color: var(--el-color-warning, #e6a23c); }
      &.risk-medium { color: var(--el-color-primary, #409eff); }
      &.risk-low { color: var(--el-color-success, #67c23a); }
    }

    .tab-header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .apps-pagination {
      margin-top: 12px;
      display: flex;
      justify-content: center;
    }

    .pid-text {
      color: var(--el-text-color-secondary, #909399);
      font-size: 12px;
    }

    .cursor-pointer {
      cursor: pointer;
    }

    .text-placeholder {
      color: var(--el-text-color-placeholder, #c0c4cc);
    }

    .high-risk-port {
      color: var(--el-color-danger, #f56c6c);
      font-weight: 600;
    }

    .mr-1 {
      margin-right: 4px;
    }

    .mb-1 {
      margin-bottom: 4px;
    }

    // 数据来源 popover 样式
    .source-meta-popover {
      max-height: 300px;
      overflow-y: auto;

      .source-meta-row {
        display: flex;
        gap: 8px;
        padding: 2px 0;
        font-size: 13px;
        line-height: 1.6;
      }

      .source-meta-key {
        flex-shrink: 0;
        color: var(--el-text-color-secondary, #909399);
        font-weight: 500;
        min-width: 100px;
      }

      .source-meta-value {
        color: var(--el-text-color-primary, #303133);
        word-break: break-all;
      }
    }
  }

  @media (max-width: 1400px) {
    .summary-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
    }
  }

  @media (max-width: 900px) {
    .summary-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    }
  }
</style>
