# WebDAV文件共享访问技能

AI-miniSOC的WebDAV文件共享访问技能，用于与NAS WebDAV服务器进行文件交互。

## 功能特性

- ✅ 文件上传/下载
- ✅ 目录列表
- ✅ 文件删除
- ✅ 目录创建
- ✅ 批量操作
- ✅ 自然语言命令接口

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置

编辑 `config.json` 文件，设置你的WebDAV服务器信息：

```json
{
  "server": "https://your-nas-server:5006/aisoc_sharedoc",
  "username": "your_username",
  "password": "your_password"
}
```

## 使用方法

### Python API

```python
from skills.webdav_access.main import WebDAVClient

# 创建客户端
client = WebDAVClient()

# 列出目录
contents = client.list_contents("reports/")
print(contents)

# 上传文件
success, message = client.upload_file(
    "/tmp/report.pdf",
    "reports/2026/report.pdf"
)

# 下载文件
success, message = client.download_file(
    "reports/2026/report.pdf",
    "/tmp/downloaded_report.pdf"
)

# 删除文件
success, message = client.delete_file("reports/old_report.pdf")

# 创建目录
success, message = client.create_directory("reports/2026/")
```

### 自然语言接口

```python
from skills.webdav_access.main import handle_webdav_command

# 列出目录
result = handle_webdav_command("列出NAS共享目录内容")
print(result)

# 上传文件
result = handle_webdav_command("上传 /tmp/file.pdf 到NAS reports/")
print(result)

# 下载文件
result = handle_webdav_command("下载NAS文件 reports/file.pdf 到 /tmp/")
print(result)
```

### 命令行

```bash
# 列出目录
python -m skills.webdav_access.main "列出NAS共享目录内容"

# 上传文件
python -m skills.webdav_access.main "上传 /tmp/file.pdf 到NAS reports/"

# 测试技能
python skills/webdav-access/test.py

# 完整测试
python skills/webdav-access/test.py --full
```

### 高级上传器

```python
from skills.webdav_access.uploader import WebDAVUploader

uploader = WebDAVUploader()

# 使用curl上传（更快）
success, message = uploader.upload_with_curl(
    "/tmp/large_file.zip",
    "backup/large_file.zip"
)

# 批量上传
files = [
    ("/tmp/file1.pdf", "reports/file1.pdf"),
    ("/tmp/file2.pdf", "reports/file2.pdf"),
]
results = uploader.batch_upload(files)

# 上传整个目录
success_count, fail_count, errors = uploader.upload_directory(
    "/tmp/reports/",
    "reports/2026/"
)
```

## 安全运营应用场景

### 1. 报告共享

```python
# 上传每日安全报告
handle_webdav_command("上传 /tmp/daily_report.pdf 到NAS reports/daily/")
```

### 2. 日志归档

```bash
# 导出Wazuh告警并上传到NAS
curl -s "https://192.168.0.30:55000/api/alerts?limit=1000" \
  -H "Authorization: Bearer $TOKEN" \
  > /tmp/alerts.json

python -c "
from skills.webdav_access.main import handle_webdav_command
handle_webdav_command('上传 /tmp/alerts.json 到NAS logs/wazuh/')
"
```

### 3. 威胁样本共享

```python
# 上传可疑文件样本
client = WebDAVClient()
client.upload_file(
    "/tmp/suspicious.exe",
    "threat-analysis/suspicious.exe"
)
```

### 4. 配置备份

```bash
# 备份Wazuh配置
tar czf /tmp/wazuh-config-backup.tar.gz /var/ossec/etc/rules/

python -c "
from skills.webdav_access.main import handle_webdav_command
handle_webdav_command('上传 /tmp/wazuh-config-backup.tar.gz 到NAS backups/wazuh/')
"
```

## 在AI-miniSOC中的应用

### 与报告生成集成

```python
# scripts/generate-report.py
from skills.webdav_access.main import WebDAVClient

def upload_report(report_path: str, category: str):
    """生成报告后自动上传到NAS"""
    client = WebDAVClient()

    from datetime import datetime
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"security_report_{date_str}.pdf"
    remote_path = f"{category}/{filename}"

    success, message = client.upload_file(report_path, remote_path)

    if success:
        print(f"✅ 报告已上传到NAS: {remote_path}")
    else:
        print(f"❌ 上传失败: {message}")

    return success
```

### 与日志查询集成

```python
# scripts/loki-query.py
from skills.webdav_access.main import WebDAVClient

def save_query_results(query: str, results: dict):
    """保存Loki查询结果到NAS"""
    import json
    import tempfile

    # 保存到临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(results, f, indent=2)
        temp_file = f.name

    # 上传到NAS
    client = WebDAVClient()
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    remote_path = f"loki-queries/query_{timestamp}.json"

    success, message = client.upload_file(temp_file, remote_path)

    # 清理临时文件
    os.unlink(temp_file)

    return success
```

### 与告警系统集成

```python
# services/alert-engine/notifier.py
from skills.webdav_access.main import WebDAVClient

def archive_alert(alert: dict):
    """归档告警到NAS"""
    import json
    import tempfile
    from datetime import datetime

    # 创建告警JSON
    alert_data = {
        "alert": alert,
        "archived_at": datetime.now().isoformat(),
        "archived_by": "AI-miniSOC"
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(alert_data, f, indent=2)
        temp_file = f.name

    # 上传到归档目录
    client = WebDAVClient()
    date_str = datetime.now().strftime("%Y/%m/%d")
    alert_id = alert.get("id", "unknown")
    remote_path = f"alerts-archive/{date_str}/{alert_id}.json"

    success, message = client.upload_file(temp_file, remote_path)
    os.unlink(temp_file)

    return success
```

## 测试

运行测试脚本验证技能功能：

```bash
# 基础测试
python skills/webdav-access/test.py

# 完整测试（包括文件操作）
python skills/webdav-access/test.py --full
```

## 安全建议

1. **凭证管理**
   - 不要在代码中硬编码密码
   - 使用环境变量存储敏感信息
   - 定期更换WebDAV密码

2. **网络安全**
   - 确保使用HTTPS协议
   - 验证服务器SSL证书
   - 限制访问IP地址

3. **文件安全**
   - 敏感文件加密存储
   - 设置合理的文件权限
   - 定期审计访问日志

## 故障排查

### 连接失败
```
❌ 无法连接到WebDAV服务器
```
解决：检查服务器地址、网络连接、防火墙设置

### 认证失败
```
❌ 认证失败，请检查用户名和密码
```
解决：验证config.json中的凭证是否正确

### 权限不足
```
❌ 权限不足
```
解决：检查WebDAV用户是否有足够的权限

## 相关文档

- [技能说明文档](SKILL.md)
- [项目架构](../../docs/design/architecture.md)
- [API文档](../../docs/api/)

## 许可证

MIT License

## 作者

xiejava

## 版本

v1.0.0 - 2026-03-09
