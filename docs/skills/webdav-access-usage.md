# WebDAV文件共享技能 - 快速使用指南

## 概述

WebDAV文件共享技能已成功创建并集成到AI-miniSOC项目中。该技能允许你通过NAS WebDAV服务器进行文件共享，适用于安全报告共享、日志归档、威胁样本共享等场景。

## 立即开始

### 1. 配置WebDAV服务器

编辑配置文件（请替换为你的实际NAS信息）：

```bash
vi skills/webdav-access/config.json
```

配置示例：
```json
{
  "config": {
    "server": "https://fnos.ishareread.com:5006/aisoc_sharedoc",
    "username": "xiejava",
    "password": "your_actual_password"
  }
}
```

### 2. 测试连接

```bash
# 方法1：运行测试脚本
python skills/webdav-access/test.py

# 方法2：运行快速开始示例
python skills/webdav-access/quickstart.py
```

### 3. 开始使用

#### Python API方式

```python
# 导入技能
from skills.webdav_access.main import WebDAVClient

# 创建客户端
client = WebDAVClient()

# 列出目录
contents = client.list_contents()
print(contents)

# 上传文件
success, message = client.upload_file(
    "/tmp/security_report.pdf",
    "reports/2026/security_report.pdf"
)

# 下载文件
success, message = client.download_file(
    "reports/2026/security_report.pdf",
    "/tmp/downloaded_report.pdf"
)
```

#### 自然语言命令方式

```python
from skills.webdav_access.main import handle_webdav_command

# 列出目录
result = handle_webdav_command("列出NAS共享目录内容")
print(result)

# 上传文件
result = handle_webdav_command("上传 /tmp/report.pdf 到NAS reports/")
print(result)

# 下载文件
result = handle_webdav_command("下载NAS文件 reports/report.pdf 到 /tmp/")
print(result)
```

## 在AI-miniSOC中的应用

### 1. 安全报告共享

上传每日安全报告到NAS共享目录。

```python
from skills.webdav_access.main import WebDAVClient
from datetime import datetime

client = WebDAVClient()

# 生成带日期的文件名
date_str = datetime.now().strftime("%Y%m%d")
filename = f"daily_security_report_{date_str}.pdf"

# 上传报告
success, message = client.upload_file(
    "/tmp/security_report.pdf",
    f"reports/daily/{filename}"
)

if success:
    print(f"✅ 报告已上传: reports/daily/{filename}")
```

### 2. 日志归档

导出Wazuh告警并上传到NAS。

```bash
#!/bin/bash
# scripts/archive-wazuh-alerts.sh

# 导出Wazuh告警
ALERT_FILE="/tmp/wazuh_alerts_$(date +%Y%m%d).json"
curl -s -X GET \
  "https://192.168.0.30:55000/api/alerts?offset=0&limit=1000" \
  -H "Authorization: Bearer $WAZUH_TOKEN" \
  > "$ALERT_FILE"

# 上传到NAS
python3 -c "
from skills.webdav_access.main import handle_webdav_command
handle_webdav_command('上传 $ALERT_FILE 到NAS logs/wazuh/')
"

# 清理临时文件
rm -f "$ALERT_FILE"
echo "✅ Wazuh告警已归档"
```

### 3. 威胁样本共享

上传可疑文件样本到NAS进行共享分析。

```python
from skills.webdav_access.uploader import WebDAVUploader

uploader = WebDAVUploader()

# 准备文件列表
files = [
    ("/tmp/suspicious1.exe", "threat-analysis/suspicious1.exe"),
    ("/tmp/suspicious2.dll", "threat-analysis/suspicious2.dll"),
    ("/tmp/suspicious3.pdf", "threat-analysis/suspicious3.pdf"),
]

# 批量上传
results = uploader.batch_upload(files)

# 显示结果
for remote_path, success, message in results:
    status = "✅" if success else "❌"
    print(f"{status} {remote_path}: {message}")
```

### 4. 配置备份

备份Wazuh和Grafana配置到NAS。

```bash
#!/bin/bash
# scripts/backup-configs.sh

BACKUP_DIR="/tmp/aisoc-config-backup-$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# 备份Wazuh配置
tar czf "$BACKUP_DIR/wazuh-config.tar.gz" /var/ossec/etc/ 2>/dev/null

# 备份Grafana仪表板
cp /var/lib/grafana/dashboards/*.json "$BACKUP_DIR/" 2>/dev/null

# 上传到NAS
python3 << EOF
from skills.webdav_access.main import WebDAVClient
client = WebDAVClient()
client.upload_file('$BACKUP_DIR/wazuh-config.tar.gz', 'backups/wazuh/config_$(date +%Y%m%d).tar.gz')
EOF

echo "✅ 配置备份完成"
```

### 5. Loki查询结果保存

保存Loki日志查询结果到NAS。

```python
# scripts/save-loki-query.py
import requests
import json
from skills.webdav_access.main import WebDAVClient
from datetime import datetime

def save_loki_query(query, start_time, end_time):
    """执行Loki查询并保存结果到NAS"""

    # 执行查询
    url = "http://192.168.0.30:3100/loki/api/v1/query_range"
    params = {
        "query": query,
        "start": start_time,
        "end": end_time,
        "limit": 1000
    }

    response = requests.get(url, params=params)
    results = response.json()

    # 保存到临时文件
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(results, f, indent=2)
        temp_file = f.name

    # 上传到NAS
    client = WebDAVClient()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    remote_path = f"loki-queries/query_{timestamp}.json"

    success, message = client.upload_file(temp_file, remote_path)

    # 清理临时文件
    import os
    os.unlink(temp_file)

    return success

# 使用示例
save_loki_query(
    '{job="wazuh-alerts"}',
    "1772932355000000000",
    "1773018755000000000"
)
```

## 高级用法

### 批量上传整个目录

```python
from skills.webdav_access.uploader import WebDAVUploader

uploader = WebDAVUploader()

# 上传整个报告目录
success_count, fail_count, errors = uploader.upload_directory(
    "/tmp/reports/",
    "reports/2026/"
)

print(f"成功: {success_count}, 失败: {fail_count}")
for error in errors:
    print(f"错误: {error}")
```

### 使用curl上传大文件（推荐）

```python
from skills.webdav_access.uploader import WebDAVUploader

uploader = WebDAVUploader()

# 使用curl上传，更快更稳定
success, message = uploader.upload_with_curl(
    "/tmp/large_backup.zip",
    "backup/large_backup.zip",
    timeout=600  # 10分钟超时
)

if success:
    print(f"✅ {message}")
else:
    print(f"❌ {message}")
```

### 检查文件是否存在

```python
from skills.webdav_access.main import WebDAVClient

client = WebDAVClient()

if client.file_exists("reports/2026/report.pdf"):
    print("文件存在")
else:
    print("文件不存在")
```

## 常见问题

### Q1: 连接失败怎么办？

检查以下几点：
1. 确认服务器地址正确
2. 确认用户名和密码正确
3. 确认网络连接正常
4. 确认NAS的WebDAV服务已启动
5. 检查防火墙设置

### Q2: 如何批量上传文件？

使用 `WebDAVUploader` 类的 `batch_upload()` 或 `upload_directory()` 方法。参见上文示例。

### Q3: 如何处理大文件？

对于大文件，建议使用 `upload_with_curl()` 方法，它更快且支持断点续传。

### Q4: 上传速度慢怎么办？

1. 使用 `upload_with_curl()` 代替 `upload_with_requests()`
2. 增加超时时间
3. 检查网络带宽
4. 考虑压缩文件后再上传

## 安全建议

1. **凭证管理**
   - 不要在代码中硬编码密码
   - 使用环境变量或加密配置文件
   - 定期更换WebDAV密码
   - 限制config.json文件权限（chmod 600）

2. **网络安全**
   - 确保使用HTTPS协议
   - 验证服务器SSL证书
   - 限制访问IP地址
   - 使用VPN或专用网络

3. **文件安全**
   - 敏感文件加密存储
   - 设置合理的文件权限
   - 定期审计访问日志
   - 及时清理过期文件

## 相关文档

- [技能说明文档](../skills/webdav-access/SKILL.md)
- [详细使用文档](../skills/webdav-access/README.md)
- [安装说明](../skills/webdav-access/INSTALLATION.md)
- [项目架构](architecture.md)

## 获取帮助

如果遇到问题：
1. 查看上述文档
2. 运行测试脚本诊断：`python skills/webdav-access/test.py`
3. 检查配置文件是否正确
4. 查看NAS WebDAV服务器日志
5. 联系系统管理员

---

**技能版本**: v1.0.0
**最后更新**: 2026-03-09
**作者**: xiejava
