---
name: webdav
description: This skill should be used when the user asks to "upload to NAS", "download from NAS", "list NAS files", "WebDAV operations", "access NAS shared folder", or mentions "webdav", "NAS file sharing". Provides WebDAV file operations for AI-miniSOC project including upload, download, list, and delete operations on the NAS server.
version: 1.0.0
---

# WebDAV NAS Access Skill

AI-miniSOC的WebDAV文件访问技能，用于与NAS服务器进行文件共享操作。

## 技能位置

实现代码位于：`skills/webdav-access/`

## 配置

**配置文件**：`skills/webdav-access/config.json`

当前配置：
- **服务器**：`https://fnos.ishareread.com:5006/aisoc_sharedoc`
- **用户名**：`xiejava`
- **密码**：已配置

## 可用操作

### 1. 列出目录内容
```bash
# 列出根目录
python3 skills/webdav-access/main.py "列出NAS共享目录内容"

# 列出特定目录
python3 skills/webdav-access/main.py "列出NAS目录 reports/"
```

### 2. 上传文件
```bash
# 基本上传
python3 skills/webdav-access/main.py "上传 /tmp/file.txt 到NAS test/file.txt"

# 使用curl直接上传（推荐）
curl -T /tmp/file.txt -u 'xiejava:PASSWORD' --insecure \
  https://fnos.ishareread.com:5006/aisoc_sharedoc/test/file.txt
```

### 3. 下载文件
```bash
python3 skills/webdav-access/main.py "下载NAS文件 test/file.txt 到 /tmp/"
```

### 4. 删除文件
```bash
python3 skills/webdav-access/main.py "删除NAS文件 test/file.txt"
```

### 5. 创建目录
```bash
python3 skills/webdav-access/main.py "在NAS上创建目录 reports/2026/"
```

## Python API使用

```python
from skills.webdav_access.main import WebDAVClient

# 创建客户端
client = WebDAVClient()

# 上传文件
success, message = client.upload_file(
    "/tmp/report.pdf",
    "reports/report.pdf"
)

# 下载文件
success, message = client.download_file(
    "reports/report.pdf",
    "/tmp/downloaded.pdf"
)

# 列出目录
contents = client.list_contents("reports/")

# 删除文件
success, message = client.delete_file("reports/old.pdf")
```

## 使用场景

### 安全报告上传
```bash
# 生成报告后上传到NAS
python3 scripts/generate-report.py
python3 skills/webdav-access/main.py "上传 /tmp/security_report.pdf 到NAS reports/"
```

### 日志归档
```bash
# 归档Wazuh日志到NAS
python3 skills/webdav-access/main.py "上传 /var/log/wazuh/alerts.json 到NAS logs/$(date +%Y%m%d)/"
```

### 配置备份
```bash
# 备份配置到NAS
python3 skills/webdav-access/main.py "上传 /tmp/config-backup.tar.gz 到NAS backups/"
```

## 常用curl命令

```bash
# 上传文件
curl -T <本地文件> -u 'xiejava:PASSWORD' --insecure \
  <WebDAV_URL>/<远程路径>

# 下载文件
curl -u 'xiejava:PASSWORD' --insecure -o <本地文件> \
  <WebDAV_URL>/<远程路径>

# 删除文件
curl -X DELETE -u 'xiejava:PASSWORD' --insecure \
  <WebDAV_URL>/<远程路径>

# 创建目录
curl -X MKCOL -u 'xiejava:PASSWORD' --insecure \
  <WebDAV_URL>/<目录路径>

# 列出目录
curl -X PROPFIND -u 'xiejava:PASSWORD' --insecure \
  <WebDAV_URL>/<目录路径>
```

## 注意事项

- 所有密码都存储在 `config.json` 中，请勿泄露
- 建议使用HTTPS确保传输安全
- 文件大小限制由NAS服务器配置决定
- 上传大文件时建议使用curl命令（支持断点续传）

## 相关文件

- **主程序**：`skills/webdav-access/main.py`
- **上传器**：`skills/webdav-access/uploader.py`
- **快速开始**：`skills/webdav-access/quickstart.py`
- **测试程序**：`skills/webdav-access/test.py`
- **完整文档**：`skills/webdav-access/README.md`
