# Wazuh 配置信息文档

**主机**: pve-ubuntu01 (192.168.0.40)
**文档生成时间**: 2026-03-09
**Wazuh版本**: 4.13.0-1

---

## 目录

- [主机信息](#主机信息)
- [Wazuh组件版本](#wazuh组件版本)
- [已注册的Agent列表](#已注册的agent列表)
- [Wazuh服务状态](#wazuh服务状态)
- [网络配置](#网络配置)
- [Dashboard用户](#dashboard用户)
- [配置文件位置](#配置文件位置)
- [OpenSearch配置](#opensearch配置)
- [访问凭证](#访问凭证)
- [SSH访问](#ssh访问)

---

## 主机信息

| 项目 | 详情 |
|------|------|
| 主机名 | pve-ubuntu01 |
| IP地址 | 192.168.0.40 |
| 操作系统 | Ubuntu 24.04.2 LTS |
| 内核版本 | 6.8.0-87-generic |
| 运行时间 | 105 天 |
| 磁盘使用 | 53% (24G/48G) |

---

## Wazuh组件版本

| 组件 | 版本 | 状态 |
|------|------|------|
| Wazuh Manager | 4.13.0-1 | ✅ 运行中 |
| Wazuh Dashboard | 4.13.0-1 | ✅ 运行中 |
| Wazuh Indexer | 4.13.0-1 | ✅ 运行中 |

### 进程统计

| 组件 | 进程数 | 说明 |
|------|--------|------|
| Wazuh Dashboard | 3 | Node.js进程 |
| Wazuh API | 5 | Python worker进程 |
| Wazuh Manager | 9 | 核心守护进程 |
| Wazuh Indexer | 3 | Java/OpenSearch进程 |

### 运行的核心进程

- `wazuh-dashboard` - Web可视化界面
- `wazuh-api` - REST API服务
- `wazuh-authd` - Agent认证服务
- `wazuh-db` - 数据库服务
- `wazuh-analysisd` - 日志分析引擎
- `wazuh-remoted` - 远程Agent通信
- `wazuh-syscheckd` - 文件完整性监控
- `wazuh-logcollector` - 日志收集器
- `wazuh-monitord` - 监控服务
- `wazuh-modulesd` - 模块管理器
- `wazuh-indexer` - OpenSearch搜索引擎

---

## 已注册的Agent列表

**总计**: 14个Agent
**活跃**: 8个
**断开**: 6个

### ✅ 活跃Agent（8个）

| ID | 名称 | IP地址 | 状态 | 操作系统 |
|----|------|--------|------|----------|
| 000 | pve-ubuntu01 (server) | 127.0.0.1 | Active/Local | Ubuntu 24.04 |
| 002 | fnos-vm-ubuntu01 | any | Active | Ubuntu |
| 003 | pve-kail-linux | any | Active | Kali Linux |
| 010 | xiejava-fnNAS | any | Active | NAS系统 |
| 008 | aliCloudECS-120.25.191.240-agent | any | Active | 阿里云ECS |
| 016 | pve-host1-28 | any | Active | PVE虚拟机 |
| 019 | pve-ubuntu-harbor | any | Active | Ubuntu Harbor |
| 020 | pve-ubuntu-defence | any | Active | Ubuntu Defence |

### ❌ 断开Agent（6个）

| ID | 名称 | IP地址 | 状态 | 备注 |
|----|------|--------|------|------|
| 013 | x230i-kali-agent | any | Disconnected | 需要检查 |
| 009 | aliCloudECS-120.25.217.112-agent | any | Disconnected | 阿里云ECS |
| 011 | starvm-103.40.14.59-agent | any | Disconnected | 星云主机 |
| 007 | Lenovo-L13-agent | any | Disconnected | 笔记本电脑 |
| 015 | pve-host2-35 | any | Disconnected | PVE虚拟机 |
| 018 | pve-LXC-harbor | any | Disconnected | LXC容器 |

---

## Wazuh服务状态

| 服务 | 状态 | 说明 |
|------|------|------|
| wazuh-manager | ✅ 运行中 | Wazuh管理器 |
| wazuh-api | ✅ 运行中 | API服务 |
| wazuh-dashboard | ✅ 运行中 | Web界面 |
| wazuh-indexer | ✅ 运行中 | OpenSearch搜索引擎 |
| wazuh-authd | ✅ 运行中 | Agent认证守护进程 |
| wazuh-db | ✅ 运行中 | 数据库服务 |
| wazuh-analysisd | ✅ 运行中 | 日志分析守护进程 |
| wazuh-remoted | ✅ 运行中 | 远程通信守护进程 |
| wazuh-syscheckd | ✅ 运行中 | 文件完整性监控 |
| wazuh-logcollector | ✅ 运行中 | 日志收集守护进程 |
| wazuh-monitord | ✅ 运行中 | 监控守护进程 |
| wazuh-execd | ✅ 运行中 | 主动响应执行器 |
| wazuh-modulesd | ✅ 运行中 | 模块守护进程 |
| wazuh-clusterd | ❌ 未运行 | 集群守护进程 |
| wazuh-maild | ❌ 未运行 | 邮件通知守护进程 |

---

## 网络配置

### 端口监听状态

| 端口 | 服务 | 协议 | 监听地址 | 状态 |
|------|------|------|----------|------|
| 55000 | Wazuh Dashboard/API | HTTPS | 0.0.0.0 | ✅ 监听 |
| 55000 | Wazuh Dashboard/API | HTTPS | ::: | ✅ 监听 |
| 1514 | Agent通信 | TCP | 0.0.0.0 | ✅ 监听 |
| 1515 | Agent通信 | UDP | 0.0.0.0 | ✅ 监听 |
| 9200 | OpenSearch | HTTP | ::: | ✅ 监听 |

### 访问地址

| 服务 | URL | 说明 |
|------|-----|------|
| Wazuh Dashboard | https://192.168.0.40:55000 | Web管理界面 |
| Wazuh API | https://192.168.0.40:55000/api | REST API端点 |
| OpenSearch | http://192.168.0.40:9200 | 搜索引擎API |

---

## Dashboard用户

### 内置用户账户

| 用户名 | 类型 | 说明 |
|--------|------|------|
| wazuh-wui | Web界面用户 | Dashboard登录用户 |
| wazuh | API用户 | API认证用户 |
| admin | OpenSearch管理员 | OpenSearch管理员 |
| administrator | Wazuh管理员角色 | 完整权限 |

### 用户角色

| 角色 | 权限 |
|------|------|
| administrator | 完整系统管理权限 |
| cluster_admin | 集群管理权限 |
| agents_admin | Agent管理权限 |
| users_admin | 用户管理权限 |

---

## 配置文件位置

### 主配置文件

| 文件 | 路径 | 说明 |
|------|------|------|
| Manager配置 | `/var/ossec/etc/ossec.conf` | Wazuh主配置文件 |
| Agent密钥 | `/var/ossec/etc/client.keys` | 已注册Agent密钥 |
| 内部选项 | `/var/ossec/etc/internal_options.conf` | 内部配置选项 |
| 本地选项 | `/var/ossec/etc/local_internal_options.conf` | 本地配置选项 |

### API配置

| 文件 | 路径 | 说明 |
|------|------|------|
| API配置 | `/var/ossec/api/configuration/api.yaml` | API主配置文件 |
| RBAC数据库 | `/var/ossec/api/configuration/security/rbac.db` | 用户权限数据库 |
| SSL证书 | `/var/ossec/api/configuration/ssl/` | SSL证书目录 |
| 私钥 | `/var/ossec/api/configuration/security/private_key.pem` | API私钥 |
| 公钥 | `/var/ossec/api/configuration/security/public_key.pem` | API公钥 |

### 规则和解码器

| 目录 | 路径 | 说明 |
|------|------|------|
| 规则 | `/var/ossec/etc/rules/` | 告警规则定义 |
| 解码器 | `/var/ossec/etc/decoders/` | 日志解码器 |
| Rootkit数据库 | `/var/ossec/etc/rootcheck/` | Rootkit检测规则 |
| 列表 | `/var/ossec/etc/lists/` | 各种列表文件 |

### 日志文件

| 目录 | 路径 | 说明 |
|------|------|------|
| 主日志目录 | `/var/ossec/logs/` | 所有日志文件 |
| 告警日志 | `/var/ossec/logs/alerts/alerts.log` | 安全告警 |
| 归档日志 | `/var/ossec/logs/archives/` | 历史告警归档 |
| API日志 | `/var/ossec/logs/api.log` | API访问日志 |
| 防火墙日志 | `/var/ossec/logs/firewall/` | 防火墙相关日志 |

---

## OpenSearch配置

### 集群配置

```yaml
cluster.name: wazuh-cluster
node.name: node-1
network.host: 0.0.0.0

cluster.initial_master_nodes:
  - node-1

node.max_local_storage_nodes: "3"

path.data: /var/lib/wazuh-indexer
path.logs: /var/log/wazuh-indexer
```

### SSL/TLS配置

```yaml
plugins.security.ssl.http.enabled: true
plugins.security.ssl.http.pemcert_filepath: /etc/wazuh-indexer/certs/wazuh-indexer.pem
plugins.security.ssl.http.pemkey_filepath: /etc/wazuh-indexer/certs/wazuh-indexer-key.pem
plugins.security.ssl.http.pemtrustedcas_filepath: /etc/wazuh-indexer/certs/root-ca.pem

plugins.security.ssl.transport.pemcert_filepath: /etc/wazuh-indexer/certs/wazuh-indexer.pem
plugins.security.ssl.transport.pemkey_filepath: /etc/wazuh-indexer/certs/wazuh-indexer-key.pem
plugins.security.ssl.transport.pemtrustedcas_filepath: /etc/wazuh-indexer/certs/root-ca.pem

plugins.security.ssl.transport.enforce_hostname_verification: false
plugins.security.ssl.transport.resolve_hostname: false
```

### Java配置

```bash
Xms: 1024m (初始堆内存)
Xmx: 1024m (最大堆内存)
MaxDirectMemorySize: 1073741824 (1GB)
```

---

## 访问凭证

### SSH访问

```
主机: 192.168.0.40
用户: xiejava
密码: <见环境变量配置>
```

### Wazuh Dashboard

```
URL: https://192.168.0.40:55000
默认用户: wazuh-wui
密码: (需要从rbac.db获取或重置)
```

### Wazuh API

```
URL: https://192.168.0.40:55000/api
认证方式: JWT Token
```

### OpenSearch

```
URL: http://192.168.0.40:9200
管理员: admin
```

---

## SSH访问

### 快速连接命令

```bash
# SSH连接到Wazuh服务器
ssh xiejava@192.168.0.40

# 查看Wazuh服务状态
ssh xiejava@192.168.0.40 "sudo /var/ossec/bin/wazuh-control status"

# 查看已注册的Agent列表
ssh xiejava@192.168.0.40 "sudo /var/ossec/bin/agent_control -l"

# 查看特定Agent信息
ssh xiejava@192.168.0.40 "sudo /var/ossec/bin/agent_control -i <agent_id>"
```

### Sudo密码

```
<见环境变量配置或本地密码管理器>
```

---

## 常用命令

### Wazuh控制命令

```bash
# 查看所有服务状态
sudo /var/ossec/bin/wazuh-control status

# 启动Wazuh服务
sudo /var/ossec/bin/wazuh-control start

# 停止Wazuh服务
sudo /var/ossec/bin/wazuh-control stop

# 重启Wazuh服务
sudo /var/ossec/bin/wazuh-control restart
```

### Agent管理命令

```bash
# 列出所有Agent
sudo /var/ossec/bin/agent_control -l

# 查看Agent详细信息
sudo /var/ossec/bin/agent_control -i <agent_id>

# 重启Agent
sudo /var/ossec/bin/agent_control -R <agent_id>

# 删除Agent
sudo /var/ossec/bin/manage_agents -r <agent_name>
```

### 日志查看命令

```bash
# 查看实时告警
sudo tail -f /var/ossec/logs/alerts/alerts.log

# 查看API日志
sudo tail -f /var/ossec/logs/api.log

# 搜索特定规则的告警
sudo grep "Rule: 5502" /var/ossec/logs/alerts/alerts.log
```

---

## 告警示例

### 最近告警（2026-03-09）

**规则 5502 (Level 3)**: PAM: Login session closed
```
2026 Mar 09 04:56:05 pve-ubuntu01->journald
User: root, xiejava
```

**规则 5402 (Level 3)**: Successful sudo to ROOT executed
```
2026 Mar 09 04:56:04 pve-ubuntu01->journald
User: xiejava
Command: /usr/bin/bash -c ...
```

---

## 维护建议

### 定期维护任务

1. **检查断开的Agent**
   ```bash
   sudo /var/ossec/bin/agent_control -l | grep Disconnected
   ```

2. **备份配置文件**
   ```bash
   sudo tar -czf wazuh-config-backup-$(date +%Y%m%d).tar.gz /var/ossec/etc/
   ```

3. **检查磁盘空间**
   ```bash
   df -h | grep -E '(/$|/var)'
   ```

4. **查看日志大小**
   ```bash
   du -sh /var/ossec/logs/*
   ```

5. **测试API连接**
   ```bash
   curl -k https://192.168.0.40:55000/api/
   ```

### 性能优化

- 定期清理旧日志归档
- 监控OpenSearch内存使用
- 调整日志保留策略
- 优化告警规则以减少误报

---

## 故障排查

### Agent连接问题

如果Agent显示Disconnected：
1. 检查Agent主机网络连接
2. 验证防火墙规则（端口1514/1515）
3. 查看Agent日志：`/var/ossec/logs/ossec.log`
4. 重新注册Agent（如需要）

### Dashboard访问问题

如果无法访问Dashboard：
1. 检查服务状态：`sudo /var/ossec/bin/wazuh-control status`
2. 验证端口监听：`sudo netstat -tlnp | grep 55000`
3. 查看API日志：`sudo tail -f /var/ossec/logs/api.log`
4. 检查SSL证书有效期

### 性能问题

如果系统响应缓慢：
1. 检查系统负载：`uptime`
2. 查看内存使用：`free -h`
3. 检查OpenSearch状态：`curl http://127.0.0.1:9200/_cluster/health`
4. 分析慢查询日志

---

## 参考链接

- Wazuh官方文档: https://documentation.wazuh.com/
- Wazuh API文档: https://documentation.wazuh.com/current/api/api.html
- OpenSearch文档: https://opensearch.org/docs/

---

**文档版本**: v1.0
**最后更新**: 2026-03-09
**维护者**: xiejava
